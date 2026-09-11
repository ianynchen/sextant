"""fluent engine for endpoint derivation (D02 §2's `fluent` style).

No single call carries the declaration here — the request is assembled
across several calls on a builder, so the derivation is a walk over one
caller's own `call_sites`, following each `result → receiver` link (D00 §5).
`matches` names `roots` (an owner+method pair that starts a chain, seeding
literal captures such as the verb), `steps` (a method name, owner-free by
default, whose captures fold into the running chain wherever it is reached,
last wins — an optional `owner` narrows a step to one type, needed only
where a library reuses a method name for two different roles on two
different types), and `terminal` (the method names — or, for the OkHttp
join, a `{method, terminal_via_argument}` entry, `true` or an `{owner,
method}` mapping that narrows the join — that make a chain executable).

`terminal` marks *executability*, not the walk's end: captures keep folding
past it, exactly as a real WebClient chain's `bodyToMono` follows `retrieve`.
The walk only stops, and derives one endpoint per path that ever reached a
terminal, once no further row's `receiver` matches the current row's own
chain key — a constructor row's key is its `receiver` (its `result` is void,
checkpoint ruling CP-3), every other row's key is its own `result`. A chain
that never reaches a terminal derives nothing (D02 §4's "the true answer").

The same link is followed BACKWARD once, from each root, to fold whatever
the chain already captured before it (2F design §4): a builder states its
base address before the call that carries the verb, so a forward-only walk
could never see it.

Shares `argument_descriptor`, `url_of` and `supertypes_of` verbatim with
`single_call` (`shapes.arguments`) — the same D00 §5 argument grammar,
resolved here off a captured step argument rather than a `methods` row's
positional slot.
"""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.shapes.arguments import (
    CallFacts,
    CarrierRules,
    FieldFacts,
    _arg_at,
    _capture_resolved,
    address_argument,
    argument_descriptor,
    carries_expression,
    channel_of,
    declared_parameters_of,
    field_facts,
    linked_channels,
    split_url,
    supertypes_of,
    url_of,
)
from sextant.application.resolve.shapes.expansion import _enum_symbols, _rules_of
from sextant.application.resolve.shapes.rooting import _catalog_symbol, catalog_symbols
from sextant.domain.paths import canonical_http_path, serves_urls
from sextant.domain.redaction import REDACTED, Redactor
from sextant.domain.symbols import bare_descriptor

# The capture fields whose declared value is an `argN` reference into
# the matched call site's own arguments, rather than a literal already known
# from the catalog (`http_method`, `response_is`). `channel` (Task 12,
# 2E-prep) is `url`'s destination-shaped counterpart, exactly as
# `single_call`'s own `channel_arg` is `url_arg`'s — never split into a peer
# (D02 §2's `fluent` style), and resolved through the SAME literal-first,
# `channel_via`-fallback ladder `single_call`/`interface_implementation`
# already use, rather than `url_of`'s CP-2 split. `base` (2F design §4) is
# the other half of ONE address: a builder's own base address, composed with
# the `url` capture at derive time rather than read as an address of its own.
_ARGUMENT_FIELDS = ("url", "base", "body", "response", "channel")

# The capture fields a catalog may spell EITHER as its own literal or as an
# `argN` reference (`A-C2`, principles sweep §3.2). Only `http_method`, and
# only because the framework itself offers both spellings: OkHttp names the
# verb in the method (`.post(body)`) AND takes it as an argument
# (`.method(verb, body)`), so a grammar that could read only the first left
# the second as an unmatched step, passing through uncaptured while the root's
# own `http_method: GET` default stood at `resolved`/`compiler` — a verb no
# evidence supports. Kept apart from `_ARGUMENT_FIELDS` rather than folded
# into it because those five are argument positions ALWAYS, which is what
# `_validate_captures` refuses a non-`argN` value for; a verb literal is the
# ordinary case here and must keep loading.
_LITERAL_OR_ARGUMENT_FIELDS = ("http_method",)

# F5 §6.2 (W29). Where a chain's collected metadata entries ride while it is walked.
# A reserved key inside `captures` rather than a second parameter threaded through
# `_walk`: the walk already copies `captures` per branch, which is exactly the per-branch
# independence these need, and a parallel structure would have to reimplement it.
_COLLECTED = "\x00collected"

# F5 §6.2 (W29): the BUILT-IN rule set, used where a metadata value is read.
#
# The built-ins are the credential names — `authorization`, `token`, `secret`, `apikey`,
# `credential`, `password`, `passphrase`, `privatekey` — and the design's own position is
# that they are "exactly this table's shape", so nothing needed adding.
#
# **A module's own `.sextant.yml` `redact:` additions do NOT widen this** (`OI-71`), and
# that is a real limit rather than a decision: those additions reach the export's redactor
# through the composition root, and no redactor reaches a resolve engine. Threading one
# would widen all thirteen engines' signature for one engine's need. The direction of the
# gap is the safe one only because the built-ins already cover credential-named headers;
# a repository adding a pattern for a header name of its own gets no masking from it.
_REDACTOR = Redactor.from_rules()

# The two captures that are halves of one address (2F design §4's base
# composition) — `channel`'s alternative, and what
# `_validate_url_channel_exclusivity` weighs against it as a group.
_ADDRESS_FIELDS = ("base", "url")

_ARG_REFERENCE = re.compile(r"^arg(\d+)$")

# A `when` guard's own two keys (D02 §2's `fluent` style): `{arg: int,
# equals: str}` exactly.
_WHEN_KEYS = {"arg", "equals"}

# The D00 §5 compiler's own "unresolved" argument kind — what a `when` guard
# poisons a step's declared captures to when the guard's own argument cannot
# be read as a string literal. Every downstream reader already treats this
# kind as an honest read failure, never an omission: `url_of` falls through
# to its own unresolved answer, and `_capture_resolved` (Task 4's unified
# helper) reads a `kind != "unresolved"` argument as failed to resolve.
# Immutable (GUIDELINES §8): every downstream reader only ever reads it —
# never a template a caller mutates in place — so a plain `dict` invites a
# shared-mutable-state bug this constant should not have to defend against.
_UNRESOLVED_ARGUMENT = MappingProxyType({"kind": "unresolved"})


def run(workspace: Workspace, catalog: Catalog) -> None:
    """Derives one endpoint row per chain reaching a terminal, via the same
    `call_endpoints` insert-if-absent every style uses (D02 §5). `caller` is
    the calling method symbol; `handler` and `peer` follow the same rule
    `single_call` does — NULL unless the captured url is itself absolute
    (CP-2) — and `direction`/`protocol` are the catalog's own declared
    fields."""
    matches = catalog.matches
    # Validated on the RAW (pre-`_catalog_symbol`) entries, before
    # `_channel_via_forms` ever dereferences an `owner` — the same two-phase
    # discipline `single_call._validate_methods` keeps for its own
    # `channel_via` (shape first, symbol conversion only once shape is
    # known-good).
    _validate_channel_via_entries(matches.get("roots", []), catalog)
    _validate_channel_via_entries(matches.get("steps", []), catalog)
    roots = [
        {
            # A LIST or a scalar (§3.1): one library reachable under its class name
            # and under the interface a codebase more often declares its field as.
            # `owners`, not `owner` — the plural name is what makes every consumer
            # of the old singular key fail loudly rather than compare a call site's
            # owner against a tuple and silently match nothing.
            "owners": catalog_symbols(root["owner"], f"{catalog.source}: roots[].owner"),
            "method": root["method"],
            "captures": _merged_captures(root),
            # Carried forward (never a root's own field, D02 §2's `fluent`
            # style) purely so `_validate_captures` can see and refuse it,
            # exactly as an unchecked value must not silently survive the file.
            "when": root.get("when"),
        }
        for root in matches.get("roots", [])
    ]
    steps = [
        {
            "method": step["method"],
            # Steps stay owner-free by default (D02 §4) — `owner` is an
            # optional filter, needed only where a library reuses one method
            # name for two different roles on two different types (a
            # RestClient's `body(Object)` request-setter and its
            # `body(Class)` response-extractor).
            "owners": (
                catalog_symbols(step["owner"], f"{catalog.source}: steps[].owner")
                if "owner" in step
                else None
            ),
            "captures": _merged_captures(step),
            # F5 §6.2 (W29): the repeatable half. A step declaring `collects` accumulates
            # an entry per visit instead of overwriting, because a request may carry any
            # number of headers and last-wins would keep the final one and claim it was
            # the only one. Carried through explicitly — this dict is REBUILT from named
            # keys, so a key not listed here is silently dropped at load, which is exactly
            # what happened to `collects` the first time and produced a catalog
            # declaration that read as valid and derived nothing.
            "collects": step.get("collects"),
            # D02 §2's `fluent` style: a step may declare a value guard on
            # another argument — None for the (default) unguarded step, read
            # by `_walk` (`_step_captures`) where `_matching_step` finds this
            # row.
            "when": step.get("when"),
        }
        for step in matches.get("steps", [])
    ]
    _validate_steps(steps, catalog)
    _validate_captures(roots, catalog, allow_when=False)
    _validate_captures(steps, catalog, allow_when=True)
    _validate_url_channel_exclusivity(roots, steps, catalog)
    terminal_names, via_argument_names = _terminal_index(matches.get("terminal", []))
    carrier_rules = CarrierRules(
        rules=_rules_of(catalog),
        enums=_enum_symbols(workspace),
        type_carriers=tuple(_catalog_symbol(t) for t in matches.get("type_carriers", [])),
        call_wrappers={
            _catalog_symbol(wrapper["type"]): wrapper["payload_ctor_arg"]
            for wrapper in matches.get("call_wrappers", [])
        },
    )
    supertypes = supertypes_of(workspace)
    # Read once per run, the same `_rules_of`/`_enum_symbols` precedent —
    # None for a catalog declaring no `field_sources` block, which is exactly
    # what keeps such a catalog's rows what they were before 2F.
    field_sources = field_facts(workspace, catalog)
    # Parsed once, as single_call does, for the same reason: both the root
    # scan below and the shared `argument_descriptor`'s `call_wrappers`
    # one-hop need the parsed list, never the raw JSON text.
    call_sites = [
        {**site, "arguments": json.loads(str(site["arguments"]))}
        for site in workspace.query("call_sites")
    ]
    by_caller: dict[str, list[dict[str, Any]]] = {}
    for site in call_sites:
        by_caller.setdefault(str(site["caller"]), []).append(site)
    # The same index keyed by BARE descriptor, for following a `lambda` argument into its
    # own body (`OI-73`): a call argument names the synthetic method without the module
    # coordinates the `caller` column carries, so the two spellings never match directly.
    by_bare_caller: dict[str, list[dict[str, Any]]] = {}
    for caller_symbol, caller_sites in by_caller.items():
        by_bare_caller[bare_descriptor(caller_symbol)] = caller_sites

    # A list, not a set — NFR-1, the same reason single_call's own
    # `referenced` accumulator is one.
    referenced: list[str] = []
    rows: list[dict[str, Any]] = []
    # Only a row whose identity is known dedups here, exactly as
    # single_call: two chains whose paths nobody could read carry nothing to
    # compare, so each stays its own row — the key is the identity columns,
    # never the `resolution` column. Required by
    # derive_call_endpoints.sql's own contract — it only guards against what
    # is already in the table, not against duplicates arriving in the same
    # `$rows` batch.
    seen: set[tuple[str, str, str, str, str | None, str | None]] = set()
    # F5 §6.2 (W29). Accumulated across every caller and inserted once, the `rows`
    # discipline: a per-caller insert would be one statement per method in the module.
    caller_parameters = declared_parameters_of(workspace)
    metadata: list[dict[str, Any]] = []
    for caller, sites in by_caller.items():
        # Chain reconstruction is within-method only (D00 §5): `by_receiver`
        # is built fresh per caller, over that caller's own sites alone, so a
        # value id from one method can never be mistaken for a link in
        # another.
        by_receiver: dict[Any, list[dict[str, Any]]] = {}
        for site in sites:
            by_receiver.setdefault(site["receiver"], []).append(site)
        facts = CallFacts(
            supertypes=supertypes,
            caller_call_sites=sites,
            referenced=referenced,
            # `OI-77`, the same fix `single_call` takes: a body handed straight through
            # from the caller's own signature names its type there and nowhere else.
            caller_parameters=caller_parameters.get(caller, ()),
        )
        context = _ChainContext(
            caller=caller,
            sites=sites,
            by_receiver=by_receiver,
            steps=steps,
            terminal_names=terminal_names,
            via_argument_names=via_argument_names,
            catalog=catalog,
            facts=facts,
            carrier_rules=carrier_rules,
            field_sources=field_sources,
            rows=rows,
            seen=seen,
            metadata=metadata,
            by_caller=by_bare_caller,
        )
        # Sites are already ordinal-ordered (the `call_sites` query), so a
        # fork — several rows sharing one receiver — is walked in ordinal
        # order too (NFR-1), via `by_receiver`'s own insertion order below.
        for site in sites:
            root = _matching_root(site, roots)
            if root is None:
                continue
            # A root's own captures fold ON TOP of whatever the chain already
            # carried before reaching it — the root is later in the chain, so
            # last-wins holds exactly as it does forward of here.
            captures = {
                **_prefix_captures(site, context),
                **_resolve_captures(root["captures"], site),
            }
            _walk(site, captures, reached_terminal=False, context=context)

    workspace.derive("call_endpoints", rows=rows)
    # After the endpoints, never before: an entry names the endpoint it belongs to by that
    # row's own columns, so the row has to exist for the pair to mean anything to a reader
    # joining them. The RESET is the pipeline's, once per resolve, for the
    # `open_questions` reason — several catalogs write this table and a reset owned by any
    # one of them would erase whichever ran first.
    if metadata:
        workspace.derive("endpoint_metadata_insert", rows=metadata)


@dataclass(frozen=True)
class _ChainContext:
    """Everything one caller's walk shares across every root and every step
    reached from it — grouped so the recursive walker's own signature stays
    just the two things that change per row: the row itself and the captures
    folded so far."""

    caller: str
    sites: list[dict[str, Any]]
    by_receiver: dict[Any, list[dict[str, Any]]]
    steps: list[dict[str, Any]]
    terminal_names: set[str]
    via_argument_names: dict[str, dict[str, str] | None]
    catalog: Catalog
    facts: CallFacts
    carrier_rules: CarrierRules
    field_sources: FieldFacts | None
    rows: list[dict[str, Any]]
    seen: set[tuple[str, str, str, str, str | None, str | None]]
    # F5 §6.2 (W29). One entry per metadata item the chains carried — a header, a query
    # parameter — already redacted. Separate from `rows` because it is per ENTRY and a
    # chain may carry any number, which is why D01 gives it a side table rather than
    # columns.
    metadata: list[dict[str, Any]]
    # Every caller's own call sites, so a chain can follow a `lambda`-kind argument into
    # the synthetic method that IS that lambda (`OI-73`). Chain reconstruction stays
    # within-method — the lambda body is walked as its own chain, not spliced into this
    # one — and only its captures come back.
    by_caller: dict[str, list[dict[str, Any]]]


def _prefix_captures(root_site: dict[str, Any], context: _ChainContext) -> dict[str, Any]:
    """The captures the chain already carried BEFORE its root — the same
    `result → receiver` link `_walk` follows forward, followed backward from
    the root instead (Task 6 checkpoint: "a pre-root backward walk is
    well-defined", and 2F design §4's `base` capture is why one is needed at
    all: `WebClient.builder().baseUrl(…).build().get()` puts the base address
    two calls BEFORE the row that roots the chain, where a forward-only walk
    can never see it).

    Unambiguous by construction: a row's `receiver` is one value id, and the
    row that produced it is the one whose own chain key (CP-3) IS that id —
    never a search by proximity. Ties are broken by the caller's own ordinal
    order (the `call_sites` query, NFR-1), and a value id already visited ends
    the walk rather than looping. Captures fold in real chain order —
    outermost producer first — so last-wins reads the same backward as
    forward.

    **Only steps that declare an `owner` fold backward** (fix round 1, two
    fabrications proven by probe: an unrelated registry's own
    `uri("registry-key")` reached backward from a WebClient root became that
    row's address, and one chain's `uri` leaked into a DIFFERENT chain's root
    through a shared prefix). This is `combinator`'s own owner-gated rooting
    rule reapplied: an owner-free entry "matches any owner, which is useful
    for reaching a step and reckless for deciding a chain belongs to this
    catalog at all". Forward of a root the walk is already chain-rooted, so an
    owner-free step there can only fold within a chain this catalog matched;
    BACKWARD, the prefix is exactly the part of the chain no root has vouched
    for yet, so the owner is what vouches for it instead."""
    producers: list[dict[str, Any]] = []
    visited: set[Any] = set()
    current = root_site
    while True:
        receiver = current.get("receiver")
        if receiver is None or receiver in visited:
            break
        visited.add(receiver)
        producer = next(
            (
                site
                for site in context.sites
                if site is not current and _chain_key(site) == receiver
            ),
            None,
        )
        if producer is None:
            break
        producers.append(producer)
        current = producer
    owned = [step for step in context.steps if step["owners"] is not None]
    captures: dict[str, Any] = {}
    # `reversed`: `producers` was collected from the root outward, so this
    # folds the outermost producer first — real chain order, which is what
    # makes last-wins mean the same thing on both sides of the root.
    for producer in reversed(producers):
        step = _matching_step(producer, owned)
        if step is not None:
            captures.update(_step_captures(step, producer))
    return captures


def _walk(
    site: dict[str, Any],
    captures: dict[str, Any],
    reached_terminal: bool,
    context: _ChainContext,
) -> None:
    """Follows one row forward through its own chain key (CP-3), folding
    every branch's captures independently — "two rows may share a receiver"
    is exactly a fork, and each continuation derives on its own. Derivation
    happens only at a walk's true end (no row's `receiver` matches this row's
    own chain key), never merely on reaching a terminal, because captures
    still fold past it."""
    name = str(site["name"])
    if name in context.terminal_names or (
        name in context.via_argument_names
        and _has_execute_join(site, context.sites, context.via_argument_names[name])
    ):
        reached_terminal = True
    chain_key = _chain_key(site)
    # A void ordinary call (`result` null, D00 §5) has nothing a following
    # row's `receiver` could ever really match — `None` is not a value id,
    # and treating it as one would pull in every static call in this caller
    # (their own `receiver` is `None` too) as spurious continuations. The
    # chain honestly ends here instead, exactly as it does when nothing
    # matches a real id.
    if chain_key is None:
        nexts: list[dict[str, Any]] = []
    else:
        # A constructor's own chain key IS its own `receiver` (CP-3), so
        # `by_receiver` — grouped by that same field — trivially contains the
        # constructor row itself wherever its key is looked up; excluded
        # here so a `<init>` root never chains into itself.
        nexts = [s for s in context.by_receiver.get(chain_key, []) if s is not site]
    if not nexts:
        if reached_terminal:
            _derive(captures, context)
        return
    for next_site in nexts:
        next_captures = dict(captures)
        step = _matching_step(next_site, context.steps)
        if step is not None:
            # Last wins (D02 §4): a repeated step overwrites its own earlier
            # capture here, in visitation order, with no extra bookkeeping.
            # `next_site`'s own arguments are what a `when` guard (D02 §2's
            # `fluent` style) reads, so the guard is evaluated here, in
            # `_resolve_captures`'s caller, rather than inside it.
            next_captures.update(_step_captures(step, next_site))
            # F5 §6.2 (W29): a `collects` step ACCUMULATES instead, because the thing it
            # reads is repeatable — a request may carry any number of headers, and
            # last-wins would keep only the final one and silently claim it was the only
            # one. Appended to a tuple rather than a list so each branch of a fork gets
            # its own value by copy, exactly as `dict(captures)` above gives each branch
            # its own captures.
            collected = _step_collects(step, next_site)
            if collected:
                previous = next_captures.get(_COLLECTED) or ()
                next_captures[_COLLECTED] = (*previous, *collected)
            # `OI-73`: a step whose captured argument IS a lambda takes its captures from
            # the lambda's own body. `uri(b -> b.path("/x").queryParam("q", term).build())`
            # is the idiomatic way to build a URL with query parameters, and the address
            # is the row's identity — without this the row derives with `path` NULL and a
            # real outbound call has no address at all.
            _fold_lambda_captures(next_captures, context)
        _walk(next_site, next_captures, reached_terminal, context)


def _derive(captures: dict[str, Any], context: _ChainContext) -> None:
    # A verb the catalog spelled as a literal is that literal; one it spelled
    # as `argN` (`A-C2`) is whatever the matched call's own argument reads as a
    # string, and None where nothing could read it — the honest gap, not the
    # root's default.
    declared_verb = captures.get("http_method")
    verb = declared_verb if isinstance(declared_verb, str) else _string_value(declared_verb)
    # A chain whose root (and every step it folded through) never captured
    # `http_method` is verbless by declaration — mirroring single_call's D02
    # §2 `verbless` row (a topic has no verb, precondition commit, 2E-prep
    # Task 11): SQS's `SendMessageRequest.builder()` chain never seeds one.
    # `"http_method" not in captures` is what tells "no root ever declared
    # one" apart from a read failure, and since `A-C2` the two are genuinely
    # different answers: a verb read off an argument CAN fail to resolve, and
    # the row below is then `unresolved` with `method` NULL rather than
    # carrying whichever literal an earlier step happened to seed.
    verbless = "http_method" not in captures
    body_argument = captures.get("body")
    response_argument = captures.get("response")
    # A chain's own identity comes from EITHER an address capture — `url`
    # (CP-2's peer/path split, `aws-sqs-sdk.yml`'s absolute queue URL) and
    # 2F's `base`, composed into one address by `_composed_address` — OR a
    # `channel` capture (Task 12: an opaque destination, never split into a
    # peer — D02 §2's `fluent` style, the same rule `single_call`'s own
    # `channel_arg` keeps) — `_validate_url_channel_exclusivity` refuses a catalog whose
    # roots/steps declare both ANYWHERE (checked over their union, not per
    # entry — fix round 1), so at most one is ever folded in here.
    # `channel`'s own ladder mirrors
    # `single_call`/`interface_implementation`'s: try the literal argument
    # first (`channel_of`), and only fall back to the declared
    # `channel_via` linked call when the literal itself did not resolve —
    # `Publisher.newBuilder(String, ...)` genuinely has a same-arity
    # `TopicName` overload, so the literal read is tried even where
    # `channel_via` is declared. `linked_channels` may answer several
    # destinations (`all_strings`); a bare `url`/no-`channel` chain always
    # collapses to the same one-tuple list `single_call`'s own non-ladder
    # case builds by hand.
    destinations: Sequence[tuple[str | None, str | None, str]]
    if "channel" in captures:
        channel_argument = _address_read(captures.get("channel"), context)
        literal = channel_of(channel_argument)
        channel_via_forms = captures.get("channel_via") or []
        if literal[2] != "resolved" and channel_via_forms:
            destinations = linked_channels(channel_argument, context.facts, channel_via_forms)
        else:
            destinations = [literal]
    else:
        destinations = [_composed_address(captures, context)]
    # Computed once, outside the destinations loop — the same
    # `single_call` reasoning: neither depends on peer/path/resolution, and
    # `argument_descriptor` appends to the shared `referenced` accumulator,
    # so calling it once per row rather than once per destination keeps
    # that list from carrying the same shape root once per channel.
    request_shape = argument_descriptor(body_argument, context.facts, context.carrier_rules)
    response_shape = _response_descriptor(
        response_argument, captures.get("response_is"), context.facts, context.carrier_rules
    )
    for peer, path, url_resolution in destinations:
        # 2O design §8, folded in from single_call: identity is the URL the
        # framework serves, canonicalized before the dedup key below is built
        # from it (`domain/paths.py`). Inert for every fluent catalog shipped
        # today, all of which are outbound — R8's exclusion, stated here
        # rather than left implicit, because a future inbound fluent catalog
        # would need it and would otherwise have to rediscover it.
        if path is not None and serves_urls(context.catalog.protocol, context.catalog.direction):
            path = canonical_http_path(path)
        # Checkpoint ruling I1, folded in from single_call: a capture that
        # WAS reached but which the scanner could not read drops the row's
        # resolution; a capture never reached at all is simply not part of
        # this chain's declaration and cannot fail it. Presence of the key
        # is what separates the two — a reached step always writes its
        # declared field, even when the slot it addresses is empty (I4), so
        # `None` under a key that exists is a read failure while an absent
        # key is no claim at all. `verb is not None or verbless` is
        # single_call's own rule (`_verb_of` callers): the missing verb
        # narrows a verbless row's resolution only when a verb was declared
        # but unreadable, never when none was ever declared at all — "this
        # method calls something over a channel" stays true and useful on
        # its own.
        resolution = (
            "resolved"
            if (verb is not None or verbless)
            and url_resolution == "resolved"
            # What the captures PRODUCED, the `single_call` change one engine along
            # (`OI-77`, W43's review): a body capture that filled its column did not fail.
            and _capture_resolved("body" in captures, body_argument, request_shape)
            and _capture_resolved("response" in captures, response_argument, response_shape)
            else "unresolved"
        )
        if path is not None and (verb is not None or verbless):
            # `verb or ""` — single_call's own dedup key (`_matching_method`'s
            # caller): a verbless row has no method to distinguish it by, so
            # every verbless resolved identity collapses to `(protocol,
            # direction, "", path)`, deduping on `(protocol, direction, path)`
            # alone exactly as the brief requires; a verbed row's own `verb` is
            # always a non-empty string, so this is unchanged for every shipped
            # fluent catalog (okhttp/webclient/restclient), none of which is
            # verbless.
            #
            # **`caller` and `peer` ARE in the key** (F5 §6.1 rule 1, W27 fix), and this
            # comment used to say the opposite — "outbound producer rows collapse across
            # callers on wire identity alone". They should not. Measured on a two-caller
            # probe: two hosts and one path derived ONE row with the second caller gone —
            # no row, no peer, no gap, no question. That is RC-5, comparing identity
            # without `peer`, which W27 removed from the inbound/outbound merge and left
            # standing here.
            #
            # "Collapse only within one caller, where both sides are observable" (§6.1):
            # one method calling one target twice is still one row, because caller and
            # peer are equal there.
            key = (
                context.catalog.protocol,
                context.catalog.direction,
                verb or "",
                path,
                context.caller,
                peer,
            )
            if key in context.seen:
                continue
            context.seen.add(key)
        for entry in captures.get(_COLLECTED) or ():
            context.metadata.append(_metadata_row(entry, context, verb, path))
        context.rows.append(
            {
                "protocol": context.catalog.protocol,
                "direction": context.catalog.direction,
                # Not `str(verb)`: a verbless chain's `verb` is genuinely None
                # (no root ever declared `http_method`), and `str(None)` would
                # write the literal text "None" into a column NULL is supposed
                # to mean "no verb" — single_call's own `method: verb` (never
                # stringified) is the same answer for the same reason.
                "method": verb,
                "path": path,
                "handler": None,
                "caller": context.caller,
                "peer": peer,
                "handler_signature": None,
                "resolution": resolution,
                "evidence": "compiler",
                "catalog_id": context.catalog.id,
                "request_shape": request_shape,
                "response_shape": response_shape,
                "consumes": None,
                "produces": None,
            }
        )


def _metadata_row(
    entry: dict[str, Any], context: "_ChainContext", verb: str | None, path: str | None
) -> dict[str, Any]:
    """One `endpoint_metadata` row, keyed to the endpoint this chain just derived and
    **redacted here, where the value is read** (F5 §6.2, W29).

    Nothing in this system reads a metadata value — no pass substitutes one into an
    address the way `resolved_config.value` is substituted into a peer — so masking at the
    origin costs no analysis and there is no export query to add for THIS column. A
    compiled-in `Authorization: Bearer …` is realistic and the bundle is the trust
    boundary.

    **It is not the only place the value is written down**, and saying so here was wrong
    until `redact_json` gained its paired rule. The same literal is a `call_site` fact,
    and therefore also `call_sites.arguments` and `raw_facts.payload`; measured on this
    repo's own fixture, `Bearer sk-live-fixture-secret` shipped verbatim in two
    `graph/*.parquet` files of a bundle whose `endpoint_metadata` said `«redacted»`. The
    mask that closes it is the export exit's, keyed on the same name by the same rule —
    so the two agree because they ask the same redactor the same question, not because
    this row is the only copy.

    The redactor keys on the entry's own NAME, which is exactly the shape it was built for
    (`redact_value(key, value)`): `BUILTIN_KEY_PATTERNS` already holds `authorization`,
    `token`, `secret`, `apikey`, `credential`, `password`, `passphrase` and `privatekey`.

    A value that is not a literal — a variable, a field, a method result — resolves to
    None and the row is `unresolved`. That is the distinction the trust columns exist for:
    *this call sends an `Authorization` header whose value we could not read* is a
    materially different statement from *this call sends no such header*, and a table
    that recorded only readable values could not tell them apart.
    """
    name = _string_value(entry["name"]) if entry["name"] is not None else None
    literal = _string_value(entry["value"])
    return {
        "protocol": context.catalog.protocol,
        "direction": context.catalog.direction,
        "method": verb,
        "path": path,
        "caller": context.caller,
        "kind": entry["kind"],
        "name": name,
        # A value whose NAME could not be read is masked WHOLE. The rule keys on the
        # name, so an unread name is an unanswerable question — and `redact_value("")`
        # answers it "not a secret", which is the one direction this module refuses to
        # guess in: a header assembled from a constant field is exactly where a
        # compiled-in credential hides. No live instance on the fixture or the corpora
        # (zero rows carry a value with no name), so this closes a hole rather than
        # changing an answer.
        "value": None
        if literal is None
        else (REDACTED if name is None else _REDACTOR.redact_value(name, literal)),
        "resolution": "resolved" if literal is not None else "unresolved",
        "evidence": "compiler",
    }


def _address_read(argument: dict[str, Any] | None, context: _ChainContext) -> dict[str, Any] | None:
    """One address-position argument as it should be READ (2F design §4): a
    `field`-kind argument — or a getter's own result — that the field ladder
    can name a configuration expression for is replaced by that expression as
    a string literal BEFORE any existing resolution path sees it, so an
    imperatively-fed address behaves downstream exactly as a written one."""
    return address_argument(argument, context.field_sources, context.facts)


def _composed_address(
    captures: dict[str, Any], context: _ChainContext
) -> tuple[str | None, str | None, str]:
    """One chain's peer/path/resolution from its `base` and `url` captures
    together (2F design §4's base composition).

    A chain declaring no `base` at all is exactly what it was before 2F: the
    `url` capture alone, through `url_of` (which answers `unresolved` for a
    chain that never reached a url step either). A `base` that WAS captured
    and could not be read poisons the whole address — path NULL, `unresolved`
    — rather than reporting the path alone as if it were the address: a
    relative path presented as the row's whole identity would misstate the URL
    the module actually calls, which is the one thing an address column must
    never do. A url capture that was REACHED and could not be read is the same
    answer for the same reason — half an address is not an address — while a
    url capture never reached at all is no claim, and the base then stands
    alone as the whole address (spec §4's "a base with no url stands alone").

    The composed string is then read by `_address_of`, so a composed absolute
    literal splits by CP-2 exactly as a written one does and a composition
    carrying an expression stays whole."""
    url_argument = _address_read(captures.get("url"), context) if "url" in captures else None
    if "base" not in captures:
        return url_of(url_argument)
    base = _string_value(_address_read(captures.get("base"), context))
    if base is None:
        return None, None, "unresolved"
    if "url" not in captures:
        return _address_of(base)
    path = _string_value(url_argument)
    if path is None:
        return None, None, "unresolved"
    return _address_of(base + path)


def _address_of(composed: str) -> tuple[str | None, str | None, str]:
    """One composed address as peer/path/resolution. CP-2's split applies to
    the composed string exactly as it would to a literal at a url position —
    but only where the composition is splittable at all: an address carrying a
    placeholder anywhere keeps the WHOLE expression as `path` with `peer` NULL
    (2F design §4), checked BEFORE the split rather than after.

    Fix round 1: `url_of` alone got this wrong for a base that is an absolute
    literal with an expression INSIDE it (`https://${billing.host}` + `/x`).
    That matches CP-2's absolute-URL shape, so the split fired and wrote
    `${billing.host}` into `peer` — a fabricated authority, and one the
    per-environment join could then only resolve as a peer rather than as the
    address it is half of."""
    if carries_expression(composed):
        return None, composed, "resolved"
    peer, path = split_url(composed)
    return peer, path, "resolved"


def _string_value(argument: dict[str, Any] | None) -> str | None:
    """A captured argument's own string literal, or None for anything else —
    `url_of`'s own test, needed on its own here because composition works on
    the two halves' TEXT before either is read as an address."""
    if (
        argument is not None
        and argument.get("kind") == "string"
        and isinstance(argument.get("value"), str)
    ):
        return str(argument["value"])
    return None


def _response_descriptor(
    argument: dict[str, Any] | None,
    response_is: str | None,
    facts: CallFacts,
    carrier_rules: CarrierRules,
) -> str | None:
    """`response_is: array` (a `bodyToFlux`-shaped step) wraps the argument's
    own descriptor in a collection envelope — the same `{wire_type: array,
    item: …}` grammar `_described` builds for a declared `List<T>` field —
    rather than describing `argument_descriptor`'s own (scalar) answer for
    the element type alone."""
    descriptor_json = argument_descriptor(argument, facts, carrier_rules)
    if descriptor_json is None or response_is != "array":
        return descriptor_json
    wrapped = {
        "wire_type": "array",
        "wire_format": "",
        "nullable": True,
        "item": json.loads(descriptor_json),
    }
    return json.dumps(wrapped, sort_keys=True, separators=(",", ":"))


def _matching_root(site: dict[str, Any], roots: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next(
        (
            root
            for root in roots
            if site["owner"] in root["owners"] and site["name"] == root["method"]
        ),
        None,
    )


def _matching_step(site: dict[str, Any], steps: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The one declared step matching `site` — the whole entry, `captures`
    and its optional `when` guard together, since evaluating the guard
    (D02 §2's `fluent` style) needs `site`'s own arguments, read by
    `_step_captures` in `_walk` where they are at hand — or None where
    nothing does:
    "unmatched steps pass through uncaptured" (D02 §4). An owner-less step
    matches any owner; `_validate_steps` already refused any catalog where
    more than one entry could match the same row, so at most one candidate
    here ever applies."""
    name = str(site["name"])
    return next(
        (
            step
            for step in steps
            if step["method"] == name
            and (step["owners"] is None or site["owner"] in step["owners"])
        ),
        None,
    )


def _validate_steps(steps: list[dict[str, Any]], catalog: Catalog) -> None:
    """Refuses a catalog where two step entries share a method name with no
    `owner` telling them apart — silent last-wins would hide exactly the bug
    it is meant to catch (`ports/catalogs.py`'s own discipline: an unchecked
    value does not stay in the file). Two entries are distinguishable only
    when BOTH declare an `owner` and the owners differ; an owner-less entry
    matches every owner, so it collides with any sibling regardless of what
    that sibling declares."""
    by_method: dict[str, list[dict[str, Any]]] = {}
    for step in steps:
        by_method.setdefault(step["method"], []).append(step)
    for method, group in by_method.items():
        if len(group) < 2:
            continue
        # Two entries are distinguishable only when both declare owners and no
        # owner is shared. Sets rather than values, because a list may now name
        # several (§3.1): `[JmsTemplate, JmsOperations]` beside `[JmsOperations]`
        # is two entries that both match a `JmsOperations` receiver, which is the
        # same silent last-wins this refusal exists to prevent — a scalar pair
        # could only collide by being equal.
        owner_sets = [step["owners"] for step in group]
        overlapping = any(
            first is None or second is None or set(first) & set(second)
            for index, first in enumerate(owner_sets)
            for second in owner_sets[index + 1 :]
        )
        if overlapping:
            raise CatalogError(
                f"loading catalog {catalog.source}: steps named `{method}` need distinct "
                f"`owner`s to tell them apart (D02 §4's fluent style)"
            )


def _validate_captures(
    entries: list[dict[str, Any]], catalog: Catalog, *, allow_when: bool
) -> None:
    """Refuses a catalog whose `url`/`body`/`response`/`channel` capture does
    not name a call-site position (`ports/catalogs.py`'s own discipline
    again: an unchecked value does not stay in the file).

    These four fields address an argument by position, and anything that is
    not `argN` — a typo, a bare number, a field name — silently captures
    nothing: the row still derives, with the payload column NULL and the url
    unresolved, which is indistinguishable from a call site that genuinely
    carries neither. A capture out of *range* is a different answer and
    cannot be checked here, because the range belongs to each matched call
    site rather than to the catalog; ruling I1 already covers it at derive
    time, where the site is known.

    `url`/`channel` exclusivity is NOT checked here, per entry — that is
    `_validate_url_channel_exclusivity`'s own job, over the UNION of every
    root's and every step's own captures (fix round 1: a per-entry-only
    check let `channel` on one step and `url` on a DIFFERENT step load with
    no error at all, silently discarding the url capture at derive time —
    mutation-proven against a real okhttp-shaped probe).

    `when` (D02 §2's `fluent` style) is a STEP's own guard — a root starts
    the chain, with no prior capture a guard could ever condition, so
    `allow_when=False`
    (roots) refuses ANY declared `when` outright, well-formed or not;
    `allow_when=True` (steps) instead checks the guard is exactly `{arg:
    int, equals: str}`. Both checked here, at the same load-time pass,
    rather than only discovered the first time a call site reaches a
    misplaced or malformed guard."""
    for entry in entries:
        for field, value in entry["captures"].items():
            if field in _ARGUMENT_FIELDS and not _ARG_REFERENCE.match(str(value)):
                raise CatalogError(
                    f"loading catalog {catalog.source}: `{entry['method']}` captures "
                    f"`{field}: {value}`, which is not a call-site position — an argument "
                    f"capture reads `argN` (D02 §4's fluent style)"
                )
        when = entry.get("when")
        if when is None:
            continue
        if not allow_when:
            raise CatalogError(
                f"loading catalog {catalog.source}: root `{entry['method']}` declares "
                f"`when` — `when` guards steps only; a root has no prior chain to guard "
                f"(D02 §2's `fluent` style)"
            )
        if not _valid_when(when):
            raise CatalogError(
                f"loading catalog {catalog.source}: `{entry['method']}` declares "
                f"`when: {when!r}`, which must be `{{arg: int, equals: str}}` exactly "
                f"(D02 §2's `fluent` style, the value-guarded step)"
            )


def _validate_url_channel_exclusivity(
    roots: list[dict[str, Any]], steps: list[dict[str, Any]], catalog: Catalog
) -> None:
    """Refuses a catalog whose `roots`/`steps`, TAKEN TOGETHER, declare both
    an address capture (`url`, or 2F's `base` half of one) and a `channel`
    capture anywhere — the two are
    different readings of the same identity position (D02 §2's `fluent` style, mirroring
    `single_call`'s own `url_arg`/`channel_arg` exclusivity), and `_derive`
    only ever reads one of the two (`"channel" in captures` wins outright,
    `url_of(captures.get("url"))` otherwise).

    Checked over the UNION of every entry's own captures, never per entry
    (fix round 1, mutation-proven): a chain's own `captures` dict is folded
    step by step as the walk proceeds (`_walk`'s own last-wins fold), so
    `channel` declared on one step and `url` declared on a DIFFERENT step
    in the SAME catalog still collide in that one running dict by the time
    `_derive` reads it — a per-entry-only check let exactly this load with
    no error at all, silently discarding whichever capture folded in
    first."""
    fields: set[str] = set()
    for entry in (*roots, *steps):
        fields.update(entry["captures"])
    address = sorted(field for field in _ADDRESS_FIELDS if field in fields)
    if address and "channel" in fields:
        raise CatalogError(
            f"loading catalog {catalog.source}: this catalog's roots/steps declare both "
            f"`{'`/`'.join(address)}` and `channel` captures — they are two different "
            f"readings of the same identity position (D02 §2's `fluent` style, mirroring "
            f"single_call's own `url_arg`/`channel_arg` exclusivity)"
        )


def _valid_when(when: Any) -> bool:
    """Whether a declared `when` guard is exactly `{arg: int, equals:
    str}` — no missing key, no extra key, no wrong-typed value."""
    return (
        isinstance(when, dict)
        and set(when) == _WHEN_KEYS
        and isinstance(when.get("arg"), int)
        and isinstance(when.get("equals"), str)
    )


def _merged_captures(entry: dict[str, Any]) -> dict[str, Any]:
    """An entry's own `captures` plus its `channel_via` ladder (Task 12),
    when declared — folded into the SAME dict `_resolve_captures`/
    `_step_captures` already fold forward chain-wide, so a root's own
    `channel_via` forms travel alongside its `channel` capture through
    every later step exactly like `http_method`/`response_is` already do
    (neither is an `argN` position, so both take the same literal
    pass-through branch in `_resolve_captures`). Only ever called on an
    entry `_validate_channel_via_entries` already checked, at `run` start —
    `_channel_via_forms`'s own `_catalog_symbol` conversion is safe here."""
    captures = dict(entry.get("captures", {}))
    if "channel_via" in entry:
        captures["channel_via"] = _channel_via_forms(entry)
    return captures


def _validate_channel_via_entries(entries: list[dict[str, Any]], catalog: Catalog) -> None:
    """Refuses a broken `channel_via` ladder before any call site is
    matched, on the RAW (pre-`_catalog_symbol`) `roots`/`steps` entries —
    the same two-phase discipline `single_call._validate_methods` keeps for
    its own `channel_via` (shape checked here; `_channel_via_forms`'s
    symbol conversion only ever runs on an entry this already passed).
    `channel_via` without a `channel` capture is missing the position it
    describes — the same `single_call` rule, `_merged_captures` never
    reaches it because this raises first."""
    for entry in entries:
        for form in _channel_via_entries(entry):
            valid = (
                isinstance(form, dict)
                and isinstance(form.get("owner"), str)
                and isinstance(form.get("method"), str)
                and (form.get("arg") == "all_strings" or isinstance(form.get("arg"), int))
            )
            if not valid:
                raise CatalogError(
                    f"loading catalog {catalog.source}: `{entry.get('method')}` declares a "
                    f"`channel_via` entry that must be `{{owner, method, "
                    f'arg: int|"all_strings"}}`, got {form!r}'
                )
        if "channel_via" in entry and "channel" not in entry.get("captures", {}):
            raise CatalogError(
                f"loading catalog {catalog.source}: `{entry.get('method')}` declares "
                f"`channel_via` without a `channel` capture — `channel_via` says how to "
                f"read an instance already named by `channel`, never a destination on its "
                f"own (D02 §2's `fluent` style, mirroring single_call's own rule)"
            )


def _channel_via_entries(entry: dict[str, Any]) -> list[Any]:
    """`channel_via`'s `{owner, method, arg}` | `[{...}, ...]` grammar,
    normalized to a list without touching the entries themselves — the
    `single_call`/`interface_implementation` precedent, shared in spirit
    rather than in code (this module owns its own root/step shape, never a
    `methods`/`registration` row)."""
    via = entry.get("channel_via")
    if via is None:
        return []
    return via if isinstance(via, list) else [via]


def _channel_via_forms(entry: dict[str, Any]) -> list[dict[str, Any]]:
    """`channel_via` entries, each declared `owner` converted to the SCIP
    symbol form once — only ever called on an entry
    `_validate_channel_via_entries` already passed, at `run` start."""
    return [
        {"owner": _catalog_symbol(form["owner"]), "method": form["method"], "arg": form["arg"]}
        for form in _channel_via_entries(entry)
    ]


def _terminal_index(
    entries: list[Any],
) -> tuple[set[str], dict[str, dict[str, str] | None]]:
    """Splits `matches.terminal` into method names that end a chain on their
    own, and ones that only do so through the execute-join (checkpoint
    ruling: the catalog marks it `terminal_via_argument: true` on the
    terminal entry) — the OkHttp shape, where `build`'s own row carries no
    link to `newCall` except through a *different* row's argument `source`.
    A bare `true` joins to any row carrying the argument link; an
    `{owner, method}` mapping instead narrows the join to that one declared
    call, closing the fabrication a bare join leaves open — `Request r =
    builder.build(); log.debug("…", r)` consumes `build`'s own result too,
    and without a filter that non-executing use would complete the chain."""
    plain: set[str] = set()
    via_argument: dict[str, dict[str, str] | None] = {}
    for entry in entries:
        if isinstance(entry, str):
            plain.add(entry)
            continue
        marker = entry.get("terminal_via_argument")
        if not marker:
            plain.add(entry["method"])
            continue
        via_argument[entry["method"]] = (
            {"owner": _catalog_symbol(marker["owner"]), "method": marker["method"]}
            if isinstance(marker, dict)
            else None
        )
    return plain, via_argument


def _has_execute_join(
    site: dict[str, Any], sites: list[dict[str, Any]], join_filter: dict[str, str] | None
) -> bool:
    """Whether some row in this same caller carries an argument whose
    `source` names `site`'s own `result` — the OkHttp `build()` → `newCall()`
    split, joined through D00 §5's `arguments[].source` rather than through
    `receiver`/`result` chaining, because `newCall`'s own receiver is the
    client, not the request builder. `join_filter`, when the catalog
    declared one, additionally requires the joining row itself to be that
    exact owner+method — otherwise any consumer of the built value (a log
    statement, an equality check) would count as executing it."""
    result = site["result"]
    if result is None:
        return False
    for candidate in sites:
        if join_filter is not None and (
            candidate["owner"] != join_filter["owner"] or candidate["name"] != join_filter["method"]
        ):
            continue
        if any(argument.get("source") == result for argument in candidate["arguments"]):
            return True
    return False


def _chain_key(site: dict[str, Any]) -> Any:
    """The value id a following row's `receiver` must match to extend this
    row's own chain (checkpoint ruling CP-3): a constructor's `result` is
    void by construction, so its own `receiver` — the constructed value's id
    — is what the next call in the chain actually holds; every other call's
    own `result` is its answer, exactly as it is fed forward in real
    bytecode."""
    return site["receiver"] if site["name"] == "<init>" else site["result"]


def _step_captures(step: dict[str, Any], site: dict[str, Any]) -> dict[str, Any]:
    """The captures one matched step contributes for `site` — plain
    `_resolve_captures` where the step declares no `when`, and D02 §2's
    `fluent` style's three-way guard answer otherwise, read off `site`'s own
    arguments:

    - the guard argument is a string literal equal to `when["equals"]` —
      the step's own captures apply, exactly as an unguarded step's would;
    - the guard argument is a string literal, but a DIFFERENT one — the
      step still matched the chain (D02 §2's `fluent` style: "the step
      matches the chain either way"), only its captures do not apply, so nothing here
      overwrites whatever an earlier step already folded in;
    - anything else (no argument at that position, the wrong kind, or the
      compiler's own `unresolved`) poisons every ARGUMENT capture this step
      declares to `_UNRESOLVED_ARGUMENT` — it might have been the guarded
      key, and an unreadable key must never let a chain preserve an
      earlier confident answer.

    Only the `_ARGUMENT_FIELDS` are poisoned (final review, minor): every
    other declared field is a literal the catalog already knows, not a
    position read off the call site, and none of their readers has an
    `unresolved` form to fall through to. `channel_via` is the case that
    proved it — `_merged_captures` folds a step's own ladder in under that
    same key, so poisoning it replaced a list of `{owner, method, arg}`
    forms with a one-key mapping, and `linked_channels` iterating that
    mapping raised `TypeError: string indices must be integers` the moment
    a later step rewrote `channel` with a readable argument. The same
    poisoning wrote the mapping itself into `http_method`, which reaches
    the `method` column unstringified. So a literal a guarded step declares
    is simply not folded in when the guard could not be read — the step
    contributed no readable evidence, and an earlier step's own literal is
    left standing rather than replaced by a value nothing can interpret."""
    when = step.get("when")
    if when is None:
        return _resolve_captures(step["captures"], site)
    guard = _arg_at(site["arguments"], when["arg"])
    if guard is not None and guard.get("kind") == "string" and isinstance(guard.get("value"), str):
        if guard["value"] == when["equals"]:
            return _resolve_captures(step["captures"], site)
        return {}
    return {
        field: _UNRESOLVED_ARGUMENT
        for field, value in step["captures"].items()
        if _reads_an_argument(field, value)
    }


def _fold_lambda_captures(captures: dict[str, Any], context: "_ChainContext") -> None:
    """Replaces any captured value that is a LAMBDA with what that lambda's own body
    captured, in place (`OI-73`).

    `webClient.get().uri(b -> b.path("/v2/inventory/search").queryParam("q", term).build())`
    is the idiomatic way to build a URL with query parameters, and before this the row
    derived with `path` NULL and `resolution: unresolved` — the call recorded and its whole
    address unread. The address IS the row's identity: DR-5 matches on the wire contract,
    so a pathless outbound row links to nothing and tells a reader only that this method
    calls out over HTTP.

    **This is reading, not guessing**, which is the objection the earlier behaviour was
    written against. The lambda is one argument of one call, the fact stream names the
    synthetic method it compiled to, and that method's own call sites are a chain of their
    own. There is no ambiguity about which builder belongs to this call — the argument says
    so — and nothing here reaches for a literal it cannot attribute.

    **Chain reconstruction stays within-method** (D00 §5). The lambda body is walked as its
    OWN chain over its OWN sites; only the captures come back, and the two chains are never
    spliced. One hop only: a lambda reached from inside a lambda is not followed, because
    each hop is a place the argument could belong to something else and the discipline that
    bounds `_prefix_captures` bounds this too.
    """
    for field, value in list(captures.items()):
        if not isinstance(value, dict) or value.get("kind") != "lambda":
            continue
        symbol = value.get("symbol")
        if symbol is None:
            continue
        folded, collected = _captures_of_body(str(symbol), context)
        if field in folded:
            captures[field] = folded[field]
        if collected:
            captures[_COLLECTED] = (*(captures.get(_COLLECTED) or ()), *collected)


def _captures_of_body(
    symbol: str, context: "_ChainContext"
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    """Everything the chain inside one lambda body captured and collected.

    Its sites are found by the lambda's own symbol — the fact stream records them under it
    as `caller`, exactly as it records any other method's — and linked by the same
    `result → receiver` key `_walk` follows. The head is the site no other site in the body
    feeds, so a body holding two independent chains folds both rather than guessing which
    one the caller meant; where they disagree on one field, last-wins holds as it does
    everywhere else.
    """
    # By BARE descriptor on both sides. `call_sites.caller` carries the module
    # coordinates a fact writes (D00 §5a) and a `lambda` argument's `symbol` does not —
    # a call argument never repeats them — so a lookup on the raw strings misses every
    # time, silently, which is exactly what the first version of this did.
    sites = context.by_caller.get(bare_descriptor(symbol), [])
    if not sites:
        return {}, ()
    produced = {_chain_key(site) for site in sites}
    folded: dict[str, Any] = {}
    collected: tuple[dict[str, Any], ...] = ()
    for site in sites:
        # Every site in the body, in ordinal order (the `call_sites` query, NFR-1). A
        # head-first walk would be the same order for the linear chain a builder produces,
        # and this needs no linkage to be correct: a step matches on its own method name,
        # and a site whose receiver came from outside the body is as much part of what the
        # lambda did as one whose receiver came from inside it.
        if site["receiver"] is not None and site["receiver"] not in produced:
            # ...except a site operating on something the body did not make and the
            # caller did not hand it, which belongs to no chain this argument names.
            continue
        step = _matching_step(site, context.steps)
        if step is None:
            continue
        folded.update(_step_captures(step, site))
        collected = (*collected, *_step_collects(step, site))
    return folded, collected


def _step_collects(step: dict[str, Any], site: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """The metadata entries one matched step contributes (F5 §6.2, W29).

    A `collects` block names a KIND — the catalog's own word for what this is, `header` or
    `query` — and the argument positions its name and value sit at:

        - { method: header, collects: { kind: header, name: arg0, value: arg1 } }

    `name` is optional: a Kafka partition key and an AMQP routing key have a value and no
    name at all, and writing one in would invent a label the wire does not carry.

    **The value is the RAW argument here, not a string.** Resolving it is the caller's
    job, because whether it resolved is what the entry's own `resolution` records — an
    entry read off a variable is present-and-unresolved, which is a different and more
    useful answer than absent. That distinction is the whole reason D01 gives every entry
    its own trust columns.
    """
    collects = step.get("collects")
    if not collects:
        return ()
    arguments = site["arguments"]
    name = _arg_at(arguments, _arg_index(collects["name"])) if "name" in collects else None
    value = _arg_at(arguments, _arg_index(collects["value"]))
    return tuple(
        {"kind": str(collects["kind"]), "name": name, "value": held} for held in _held_values(value)
    )


def _held_values(argument: dict[str, Any] | None) -> tuple[dict[str, Any] | None, ...]:
    """One entry's value, or each of them where the position holds several.

    **A VARARGS position arrives as an array, and the elements are the answer.** Every
    header-setting API in the measured set is varargs — spring-webflux 6.1.6 declares
    `header(String name, String... values)`, and `header("X-Tenant", "acme")` compiles to
    an array construction, which the scanner models as
    `{"kind": "array", "elements": [...]}`. Reading the array itself resolves to no
    literal, so the first version of this recorded every header as `unresolved` including
    the ones written as literals — a table full of "present, value unreadable" for values
    written in plain sight.

    One entry per element rather than one joined entry, because that is the wire:
    `header("Accept", "a", "b")` sends two values under one name, and the table's own
    ordering already contemplates a repeated name as legal HTTP.

    An empty array is a call that sets nothing and contributes no entry — `uri`'s own
    trailing `Object...` arrives empty on every call that passes no template variable, so
    this is the ordinary case rather than an edge.
    """
    if argument is not None and argument.get("kind") == "array":
        elements = argument.get("elements") or []
        return tuple(element for element in elements)
    return (argument,)


def _resolve_captures(declared: dict[str, Any], site: dict[str, Any]) -> dict[str, Any]:
    """One matched row's own captured values: `url`/`body`/`response` read
    the `argN`-addressed argument off `site` itself (the raw D00 §5 argument,
    resolved later exactly as `single_call` resolves a positional one);
    `http_method` reads one too where the catalog spelled `argN`, and is the
    catalog's own literal otherwise; every other field (`response_is`) is
    always the literal, unchanged.

    The two-spelling field is decided HERE rather than at load, because
    `argN` is a positional read and a verb literal is not: the same key means
    "read argument 0" in one row and "the verb is DELETE" in the next, and
    only the value itself says which."""
    resolved: dict[str, Any] = {}
    for field, value in declared.items():
        if _reads_an_argument(field, value):
            resolved[field] = _arg_at(site["arguments"], _arg_index(value))
        else:
            resolved[field] = value
    return resolved


def _reads_an_argument(field: str, value: Any) -> bool:
    """Whether one declared capture addresses a call-site position rather than
    stating a value. Spelled once because `_resolve_captures` and
    `_step_captures`'s guard-poisoning must agree exactly: a field poisoned in
    one and read as a literal in the other would write the poison mapping
    itself into the `method` column."""
    return field in _ARGUMENT_FIELDS or (
        field in _LITERAL_OR_ARGUMENT_FIELDS and _ARG_REFERENCE.match(str(value)) is not None
    )


def _arg_index(value: Any) -> int | None:
    match = _ARG_REFERENCE.match(str(value))
    return int(match.group(1)) if match else None
