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
method}` mapping that narrows the join, each half one name or a list —
that make a chain executable). A root or step capturing `url` may also
declare `url_via`, `channel_via`'s linked-call ladder applied to the
address (`_url_argument`): the JDK client's `uri(URI.create("…"))` hands
the step no string, and the address lives on `URI.create`'s own argument.

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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.beans import (
    BeanRef,
    BeanTable,
    Parameter,
    Unresolved,
    bean_table,
    qualifier_of,
)
from sextant.application.resolve.conditions import annotation_index
from sextant.application.resolve.shapes.arguments import (
    QUERY_KIND,
    CallFacts,
    CarrierRules,
    FieldFacts,
    _arg_at,
    _capture_resolved,
    address_argument,
    argument_descriptor,
    call_site_index,
    carries_expression,
    channel_of_answer,
    channels_of,
    declared_parameters_of,
    field_facts,
    query_entries,
    split_url,
    supertypes_of,
    url_of,
    valid_via_arity,
    with_authority,
)
from sextant.application.resolve.shapes.client_base import client_base, client_base_of, join_url
from sextant.application.resolve.shapes.expansion import _enum_symbols, _rules_of
from sextant.application.resolve.shapes.member_values import (
    member_table,
    names_members,
    static_field_value,
)
from sextant.application.resolve.shapes.rooting import _catalog_symbol, catalog_symbols
from sextant.application.resolve.values import (
    EXPRESSION,
    LITERAL,
    STRING,
    Answer,
    ValueIndex,
    cached_value_index,
    resolve_site,
)
from sextant.domain.closed_sets import Direction, Resolution
from sextant.domain.paths import canonical_http_path, serves_urls
from sextant.domain.redaction import REDACTED, Redactor
from sextant.domain.symbols import bare_descriptor, method_descriptor, parameter_types

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

# Every other capture field a catalog may spell EITHER as its own literal or
# as an `argN` reference, and the value itself says which (`_reads_an_argument`).
# `http_method` was the first (`A-C2`, principles sweep §3.2), because the
# framework itself offers both spellings: OkHttp names the verb in the method
# (`.post(body)`) AND takes it as an argument (`.method(verb, body)`), so a
# grammar that could read only the first left the second as an unmatched step,
# passing through uncaptured while the root's own `http_method: GET` default
# stood at `resolved`/`compiler` — a verb no evidence supports. The
# registration words (spec 2026-09-21 §4) made it the rule rather than the
# exception: `handler` is `argN` or the literal `none`, and the halves a
# `compose:` joins are fields the catalog itself names (`exchange: arg0`), so
# no fixed list could hold them. Kept apart from `_ARGUMENT_FIELDS` rather than
# folded into it because those five are argument positions ALWAYS, which is
# what `_validate_captures` refuses a non-`argN` value for; a verb literal is
# the ordinary case elsewhere and must keep loading.
#
# The two consumer-side captures of a registration chain (spec 2026-09-21 §2,
# §4), each with the one literal spelling it admits beside `argN`: `handler`
# takes `none` — a `discard` step's TRUE answer, a registration that hands its
# messages to nobody (§5) — and `channel_link` takes `{bean_via: argN}`, the
# channel named through a bean reference rather than a string, which the bean
# fold (§3a) reads. Neither is an address field: `_validate_captures` checks
# each against exactly these two shapes.
_HANDLER_NONE = "none"
_BEAN_VIA = "bean_via"
# Where a capture was read — `(caller, ordinal, slot)`, stamped by `_captured_at`, which
# says why the walk needs all three. Spelled with no `\x00` prefix because unlike
# `_CONTINUE` below it is not a pseudo-field of `captures`: it rides on one ARGUMENT, in
# the same namespace as the scanner's own keys, which is why the name is unmistakable.
_CAPTURED_AT = "captured_at"
# D00 §5's kind for an address the code ASSEMBLES. Spelled here because `_url_argument`
# treats it as the catalog's own declared position rather than as a hop - see there.
_CONCAT = "concat"

# The `read_by` end of the channel edge (spec 2026-09-21 §3b), read here for the
# names the channel index knows — the bean fold's name rung for a channel
# reference (§3a): the container auto-creates a channel under any referenced
# name, so a name a handler's annotation carries is a channel whether or not a
# factory method declares it. Only a RESOLVED reader's name counts: one still
# spelled as a placeholder configuration never answered names nothing. The
# rows are there when this engine runs because `resolve/endpoints.py` runs the
# index's catalog first (`_writes_only_the_channel_edge`).
_READ_BY = "read_by"
# The edge's third role (§3b's reserved slot), and its first writer (fix round
# 1, finding 3): a `channel_link` captured AFTER a handler is that handler's
# OUTPUT channel, not the wire's feed.
_SENDS_TO = "sends_to"

# The two consumer-side channel captures that name a channel rather than an
# address: `channel_link` — the channel this registration FEEDS (§3b) — and
# `channel_source` — the channel a flow CONSUMES (`from("ch")`, §5; fix round
# 1, finding 4). Each reads `argN` or `{bean_via: argN}` (the bean's name).
_CHANNEL_NAME_FIELDS = ("channel_link", "channel_source")

_DIRECTIONS = sorted(member.value for member in Direction)

# Spec 2026-09-21 §4's `poisons:` — the value a poisoned capture holds from
# the poisoning step to the chain's end. The SAME shape as `_UNRESOLVED_ARGUMENT`
# below, so every reader answers it the same way (path NULL, `unresolved`,
# no handler), but a DISTINCT object, because the two are overwritten
# differently: a guard's poison is a step's own read failure, and a later
# step that reads the field lifts it (`_step_captures`' own docstring walks
# that case); a catalog poison is a statement about the CHAIN — a `divert`
# step means the message may leave the linear flow, so a `handle` after it is
# not certainly what receives it (§5, §0b A5) — and stays for the rest of the
# walk, which `_fold` enforces by identity.
_POISONED = MappingProxyType({"kind": "unresolved", "reason": "poisoned"})

# Two more reserved keys inside `captures`, the `_COLLECTED` precedent: a root's
# own `direction:` override and its `compose:` declaration ride with the chain
# they start, because `_derive` reads them where it reads the captures and the
# walk already copies `captures` per branch.
_DIRECTION = "\x00direction"
_COMPOSE = "\x00compose"
# Two more (spec 2026-09-21 §5): the consumer a root's `via_argument_of …
# continue: true` names, riding with the chain so its end — wherever the
# value is handed on — can find that consumer (`_continuations`); and the
# `channel_link` value the chain's `handler` was captured AFTER — present
# exactly when a link step of ANY readability preceded the handler, holding
# that link's value as it stood then — which is what makes that handler a
# READER of the linked channel rather than the wire's (or the source's) own
# consumer (`_derive`'s `read_by` edge). The VALUE, not a flag, and never
# reset by a later link (residual fix, 2026-09-21): a link after the handler
# overwrites `channel_link` but not what the handler read, so
# `.channel("b").handle(h).channel("c")` keeps `b` here while `channel_link`
# holds `c`. An unreadable value here (a poisoned spec form, a read failure)
# says the handler reads a channel nobody can name — no edge, and never the
# source or the wire in its place.
_CONTINUE = "\x00continue"
_READS_LINK = "\x00reads_link"
# The handler a `channel_link` was captured AFTER (fix round 1, finding 3) —
# present exactly when the link sits after a handler step, holding that
# handler's argument: the link is then that handler's output channel
# (`sends_to`), and the row's handler is that handler, whatever a later
# `handle` after the link captured (a reader of the channel, `_READS_LINK`).
_LINK_SENDER = "\x00link_sender"
# The client the chain's request is issued on (spec 2026-10-26 §3c): the executing call's
# `client_base.client_arg` argument, stamped with where it was read. Present only for a
# catalog declaring `client_base`, on a chain that reached its terminal through an
# argument join with exactly one executing call.
_CLIENT = "\x00client"

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
    fields.

    A registration chain (spec 2026-09-21 §4) differs in three ways, each an
    optional word no request catalog spells: a root may carry its own
    `direction:`, an INBOUND chain's row carries the `handler` it captured,
    and a chain that captured a `channel_link` writes a `channel_bindings`
    `fed_by` edge — INSTEAD of a row when inbound (the join pass mints the
    row from the edge, so a linked adapter is never counted twice), beside
    its row when outbound (§3b: so the question is not asked).

    Since 2026-09-21 (Task 6) the field ladder's parameter rung answers in this
    engine as it does in `single_call`: an address handed in as the calling
    method's own `@Value` parameter — `uri(url)`, `new Adapter(ops, subscription)`
    — derives its `${…}` expression where it derived `unresolved`, and so does
    each element of a varargs slot. Every shipped fluent catalog sees it; it is
    more resolution in the direction the ladder already took, never a new claim
    (`_own_parameter`, `_address_read`)."""
    matches = catalog.matches
    # Validated on the RAW (pre-`_catalog_symbol`) entries, before
    # `_channel_via_forms` ever dereferences an `owner` — the same two-phase
    # discipline `single_call._validate_methods` keeps for its own
    # `channel_via` (shape first, symbol conversion only once shape is
    # known-good).
    _validate_channel_via_entries(matches.get("roots", []), catalog)
    _validate_channel_via_entries(matches.get("steps", []), catalog)
    _validate_channel_via_entries(matches.get("beans", []), catalog)
    roots = [_root_entry(root, catalog, "roots") for root in matches.get("roots", [])]
    # Spec 2026-09-21 §4's `beans:` — root-shaped entries reachable only through a
    # `bean_via` capture: the chain a referenced bean's own factory method
    # builds, walked for its captures and never for a row of its own
    # (`_bean_chain_capture`). The same shape as `roots`, validated the same
    # way, kept apart so a container's constructor never starts a chain of
    # this catalog's on its own.
    bean_roots = [_root_entry(root, catalog, "beans") for root in matches.get("beans", [])]
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
            # Spec 2026-09-21 §5 (Task 6): an optional `descriptor` narrows a step
            # to ONE overload of its name — `handle(Class, GenericHandler)` carries
            # the handler at slot 1, `handle(GenericHandler)` at slot 0, and a name
            # alone would read one slot for both. None for the ordinary step.
            "descriptor": _validated_descriptor(step, catalog, "steps"),
            # Spec 2026-10-26 §3c: the argument a step's receiver arrives as, for an
            # extension function compiled to a static method (its argument 0 is the
            # receiver, its own `receiver` null). None for the ordinary step, which joins
            # the chain through its own `receiver`.
            "receiver_arg": _validated_receiver_arg(step, catalog),
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
            # Spec 2026-09-21 §4: the fields this step makes unreadable from
            # here to the chain's end (`_step_captures`) — None for the
            # ordinary step, checked by `_validate_poisons`.
            "poisons": step.get("poisons"),
            # §5: a step whose result is handed to a consumer that continues
            # the walk — the same word a root may carry; None otherwise.
            "continue_via": _validated_continuation(step, catalog),
        }
        for step in matches.get("steps", [])
    ]
    _validate_steps(steps, catalog)
    _validate_captures(roots, catalog, allow_when=False)
    _validate_captures(bean_roots, catalog, allow_when=False)
    _validate_captures(steps, catalog, allow_when=True)
    _validate_url_channel_exclusivity([*roots, *bean_roots], steps, catalog)
    undeclared_owners, undeclared_poisons = _undeclared_steps(matches, catalog)
    _validate_poisons([*roots, *bean_roots], steps, undeclared_poisons, catalog)
    terminal_names, via_argument_names = _terminal_index(matches.get("terminal", []), catalog)
    verb_fields = _verb_fields(matches, catalog)
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
    # `arguments` arrives decoded from the workspace (`_DECODED_COLUMNS`), as
    # single_call reads it: both the root scan below and the shared
    # `argument_descriptor`'s `call_wrappers` one-hop read the list, never text.
    # Indexed once per load, not once per catalog (`Workspace.once`, `CallSiteIndex`);
    # the shared lists are read, never written into.
    by_caller = workspace.once(call_site_index).by_caller
    # The same index keyed by BARE descriptor, for following a `lambda` argument into its
    # own body (`OI-73`): a call argument names the synthetic method without the module
    # coordinates the `caller` column carries, so the two spellings never match directly.
    by_bare_caller: dict[str, list[dict[str, Any]]] = {}
    for caller_symbol, caller_sites in by_caller.items():
        by_bare_caller[bare_descriptor(caller_symbol)] = caller_sites
    # The method symbols a `handler` capture joins a lambda's bare body name to
    # (spec 2026-09-21 §3c) — `combinator`'s own `_handler_of` join, keyed the
    # same way for the same reason (a call argument never repeats the module
    # coordinates a symbol fact carries). Read only where a catalog declares
    # the capture: every shipped request catalog declares none, and a read
    # nothing consumes is a read per catalog for nothing (GUIDELINES §8.7).
    #
    # The bean fold's direct-call rung joins through the same map (spec §3a:
    # `setOutputChannel(ordersChannel())` names the declaring method by the
    # call's own owner+name+descriptor, which `method_descriptor` spells bare),
    # so a catalog spelling any `bean_via` reads it too.
    method_symbols: dict[str, str] = {}
    resolves_beans = any(
        _valid_bean_via(value)
        for entry in (*roots, *bean_roots, *steps)
        for value in entry["captures"].values()
    )
    if resolves_beans or any("handler" in entry["captures"] for entry in (*roots, *steps)):
        for row in workspace.query("method_symbols"):
            method_symbols.setdefault(bare_descriptor(str(row["symbol"])), str(row["symbol"]))
    # Spec 2026-09-21 §3a: the declared beans of the module, read only where a
    # catalog spells a `bean_via` — `bean_table` refuses a catalog naming no
    # model, by file, at load rather than at the first chain that reaches the
    # capture. `known_channels` is the channel index's `read_by` end (the
    # comment above `_READ_BY`).
    beans: BeanTable | None = None
    if resolves_beans:
        known_channels = frozenset(
            str(row["channel"])
            for row in workspace.query("channel_bindings")
            if row["role"] == _READ_BY and row["resolution"] == "resolved"
        )
        beans = bean_table(workspace, catalog, known_channels)
    # §4's `method_annotation`: the constructing method's own annotations, read
    # through the shared index only where a root declares the word.
    annotations = (
        annotation_index(workspace)
        if any(root["method_annotation"] is not None for root in roots)
        else {}
    )

    # A list, not a set — NFR-1, the same reason single_call's own
    # `referenced` accumulator is one.
    referenced: list[str] = []
    # The walk's index, SHARED across every catalog in this resolve
    # (`values.cached_value_index`). `_ChainContext` is frozen and rebuilt per caller, so
    # a lazily-built index would either mutate a frozen dataclass or pay the fold once per
    # METHOD rather than once per module — hence built here, once, at the top.
    #
    # **The `_declares_a_hop` gate is gone, and the measurement is why it could go.** It
    # existed because each catalog built its own index: removing it with that still true
    # cost +1.3s on `mall-admin` (6.22s -> 7.50s end to end). It also kept the walk away
    # from an ASSEMBLED address, which is not a hop and declares no key, so a catalog whose
    # url is `base + "/path"` could never reach it (`OI-138`, ruling 1). Sharing the index
    # makes the gate unnecessary instead of merely cheaper — `mall-admin` built the same
    # index five times before.
    walk_index = cached_value_index(workspace)
    # The steps that join through an argument (`receiver_arg`), by name — empty for every
    # catalog declaring none, which then indexes each site by its own `receiver` exactly as
    # before and pays nothing for the rule (GUIDELINES §8.7).
    extension_steps: dict[str, list[dict[str, Any]]] = {}
    for step in steps:
        if step["receiver_arg"] is not None:
            extension_steps.setdefault(step["method"], []).append(step)
    client_base = client_base_of(matches, catalog.source)
    rows: list[dict[str, Any]] = []
    # Spec 2026-09-21 §3b: the `fed_by` edges the chains wrote, one per chain
    # that captured a readable `channel_link` — accumulated across every
    # caller and inserted once, the `rows`/`metadata` discipline.
    bindings: list[dict[str, Any]] = []
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
    caller_parameters = workspace.once(declared_parameters_of)
    metadata: list[dict[str, Any]] = []
    for caller, sites in by_caller.items():
        # Chain reconstruction is within-method only (D00 §5): `by_receiver`
        # is built fresh per caller, over that caller's own sites alone, so a
        # value id from one method can never be mistaken for a link in
        # another.
        by_receiver: dict[Any, list[dict[str, Any]]] = {}
        for site in sites:
            by_receiver.setdefault(_receiver_of(site, extension_steps), []).append(site)
        facts = CallFacts(
            supertypes=supertypes,
            caller_call_sites=sites,
            referenced=referenced,
            # `OI-77`, the same fix `single_call` takes: a body handed straight through
            # from the caller's own signature names its type there and nowhere else.
            caller_parameters=caller_parameters.get(caller, ()),
        )
        context = _ChainContext(
            workspace=workspace,
            values=walk_index,
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
            method_symbols=method_symbols,
            bindings=bindings,
            undeclared_owners=undeclared_owners,
            undeclared_poisons=undeclared_poisons,
            beans=beans,
            bean_roots=bean_roots,
            roots=roots,
            all_parameters=caller_parameters,
            annotations=annotations,
            verb_fields=verb_fields,
            client_base=client_base,
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
            captures = {**_prefix_captures(site, context), **_root_captures(root, site, context)}
            if root["continue_via"] is not None:
                captures[_CONTINUE] = root["continue_via"]
            _fold_bean_captures(captures, context)
            _walk(site, captures, reached_terminal=False, context=context)

    workspace.derive("call_endpoints", rows=rows)
    if bindings:
        workspace.derive("channel_bindings_insert", rows=bindings)
    # After the endpoints, never before: an entry names the endpoint it belongs to by that
    # row's own columns, so the row has to exist for the pair to mean anything to a reader
    # joining them. The RESET is the pipeline's, once per resolve, for the
    # `open_questions` reason — several catalogs write this table and a reset owned by any
    # one of them would erase whichever ran first.
    if metadata:
        workspace.derive("endpoint_metadata_insert", rows=metadata)


# The root words a `beans:` entry may not carry (fix round 1, Minor 2): a bean's
# chain is walked for its captures alone (`_bean_chain_capture` takes one field
# and nothing else), so a direction, a composition, an annotation capture or a
# continuation on it would be read by nothing — silently, which is the one
# thing a catalog key must never be.
_ROOT_ONLY_WORDS = ("direction", "compose", "method_annotation", "via_argument_of", "continue")


def _root_entry(root: dict[str, Any], catalog: Catalog, where: str) -> dict[str, Any]:
    """One `roots` (or `beans` — `where`) entry as the walk reads it."""
    if where == "beans":
        carried = sorted(word for word in _ROOT_ONLY_WORDS if word in root)
        if carried:
            raise CatalogError(
                f"loading catalog {catalog.source}: a `beans` entry (`{root.get('method')}`) "
                f"declares `{'`, `'.join(carried)}` — a bean's chain is walked for its "
                f"captures alone, and nothing reads those there (spec 2026-09-21 §4)"
            )
    # `poisons:` is a step's word: a root starts the chain with nothing yet
    # captured to poison, and this dict is rebuilt from named keys, so the
    # word would load, read as valid, and do nothing (the `collects` lesson
    # one function over).
    if "poisons" in root:
        raise CatalogError(
            f"loading catalog {catalog.source}: a `{where}` entry (`{root.get('method')}`) "
            f"declares `poisons` — a poison is a step's own effect on the chain it sits "
            f"in, and a root has no chain before it (spec 2026-09-21 §4)"
        )
    # `receiver_arg` is how a step JOINS a chain, and a root starts one: the word would
    # load and do nothing, the `poisons` reason above.
    if "receiver_arg" in root:
        raise CatalogError(
            f"loading catalog {catalog.source}: a `{where}` entry (`{root.get('method')}`) "
            f"declares `receiver_arg` — it says which argument a STEP joins the chain "
            f"through, and a root starts the chain (spec 2026-10-26 §3c)"
        )
    return {
        # A LIST or a scalar (§3.1): one library reachable under its class name
        # and under the interface a codebase more often declares its field as.
        # `owners`, not `owner` — the plural name is what makes every consumer
        # of the old singular key fail loudly rather than compare a call site's
        # owner against a tuple and silently match nothing.
        "owners": catalog_symbols(root.get("owner"), f"{catalog.source}: {where}[].owner"),
        "method": _root_method(root, catalog, where),
        # §5: an optional `descriptor` narrows the root to one overload — the ten
        # `messageDrivenChannelAdapter` overloads carry their topics at different
        # slots (CP-27 row 6), and one name matching all ten would read one slot
        # for each; None for the root that matches by owner and name alone.
        "descriptor": _validated_descriptor(root, catalog, where),
        "captures": _merged_captures(root),
        # Carried forward (never a root's own field, D02 §2's `fluent`
        # style) purely so `_validate_captures` can see and refuse it,
        # exactly as an unchecked value must not silently survive the file.
        "when": root.get("when"),
        # Spec 2026-09-21 §4: a root's own direction, overriding the
        # catalog's for the chains it starts (the outbound handler bean
        # declared in an inbound catalog); None keeps the catalog's.
        "direction": _validated_direction(root, catalog),
        # §4's `compose:` — one field joined from two captured halves at
        # derive time; None for the root that declares none.
        "compose": _validated_compose(root, catalog),
        # §4's `method_annotation:` — a capture read off the constructing
        # method's own annotation; None for the root that declares none.
        "method_annotation": _validated_method_annotation(root, catalog),
        # §5's `via_argument_of: {owner, method}, continue: true` — the
        # consumer whose own chain continues this one; None for the root
        # that ends where its chain ends.
        "continue_via": _validated_continuation(root, catalog),
    }


def _root_method(root: dict[str, Any], catalog: Catalog, where: str) -> str:
    """The method a root entry names, refused when missing: an entry without
    one would match no site and derive nothing with nothing saying why — the
    `beans:` list is where that first mattered, being reachable through no
    chain a test could observe start."""
    method = root.get("method")
    if not isinstance(method, str) or not method:
        raise CatalogError(
            f"loading catalog {catalog.source}: a `{where}` entry names no `method` — "
            f"got {root!r} (D02 §2's `fluent` style)"
        )
    return method


@dataclass(frozen=True)
class _JoinFilter:
    """The execute-join a `terminal_via_argument` mapping narrows to: the built value must
    be consumed by a call to one of `methods` on one of `owners`. Several owners because one
    library routinely reaches a wire through more than one client — `SendMessageRequest`
    goes to `SqsClient` or `SqsAsyncClient` — and a scalar stays valid (§3.1). Several
    methods for the same reason one step over (A2 Task 8): the JDK client issues a built
    request through `send` OR `sendAsync`, one builder chain, one address, two executing
    calls — and two `build` entries in `terminal` would silently overwrite each other in
    `_terminal_index`'s dict, which is the defect the owners widening already closed."""

    owners: tuple[str, ...]
    methods: tuple[str, ...]
    # Spec 2026-09-21 §5's `continue: true`: the join does not END the chain, it
    # hands the built value to the consumer, whose own result chain the walk
    # then continues with the same captures (`_continue`). False is the
    # execute-join as it always was — the consumer executes, the chain derives.
    continues: bool = False


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
    via_argument_names: dict[str, _JoinFilter | None]
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
    # Spec 2026-09-21 §3c: the module's method symbols by bare descriptor, what a
    # captured `handler` lambda's body name is joined to — empty for a catalog declaring
    # no `handler` capture, which never reads it.
    method_symbols: dict[str, str]
    # §3b: the `fed_by` edges this run's chains wrote, one per chain that captured a
    # readable `channel_link`; inserted once by `run`, the `rows` discipline.
    bindings: list[dict[str, Any]]
    # §5's rule for an unknown member of a flow definition: the owners
    # `undeclared_steps` names (SCIP form), and the fields a call on one of them that
    # matches no declared step poisons. Both empty for a catalog declaring none.
    undeclared_owners: tuple[str, ...]
    undeclared_poisons: tuple[str, ...]
    # Spec 2026-09-21 §3a/§4: the module's declared beans under the catalog's
    # model — None for a catalog spelling no `bean_via`, and None again in the
    # collecting context that walks a referenced bean's own chain, which is
    # how a `bean_via` met there is not followed (one hop).
    beans: BeanTable | None
    # §4's `beans:` — the roots a referenced bean's chain may start from.
    bean_roots: list[dict[str, Any]]
    # The catalog's roots, for the continuation's prefix (`_prefix_captures`):
    # the flow's own source is a root the sink chain arrives at backward.
    roots: list[dict[str, Any]]
    # Every declared method's parameters (`declared_parameters_of`), so a
    # referenced bean's own method gets its `CallFacts` exactly as the caller
    # got its own; `facts.caller_parameters` is this caller's slice of it.
    all_parameters: dict[str, tuple[dict[str, Any], ...]]
    # §4's `method_annotation`: every annotation by target, or empty where no
    # root declares the word.
    annotations: dict[str, list[tuple[str, dict[str, Any]]]]
    # Spec 2026-10-26 §3a: the static fields that name a verb (`verb_values.fields`),
    # keyed on `(owner, field name)` — what an `http_method: argN` capture reads when
    # its argument is a static field (`enum`- or `field`-kind, D00 §5). Empty for a
    # catalog declaring none.
    verb_fields: dict[tuple[str, str], str]
    # Spec 2026-10-26 §3c: where the executing CLIENT's base address is set
    # (`matches.client_base`, read by `shapes.client_base.client_base_of`) — a relative address is
    # relative to it. None for every catalog not declaring it, whose relative address reads
    # as it always has.
    client_base: Mapping[str, Any] | None = None
    # Where a walk records each chain END's captures instead of deriving a row
    # — the collecting context `_bean_chain_capture` builds. None on the
    # deriving walk.
    collect: list[dict[str, Any]] | None = None
    # The workspace and the walk's index, for the hop ladders (Task 9). The index is built
    # ONCE PER RUN and only where this catalog declares a hop at all — not lazily per
    # caller, because this dataclass is frozen and a per-caller rebuild would pay
    # `value_index`'s fold for every method rather than for every module. A catalog
    # declaring no `channel_via`/`url_via` anywhere gets `None` and never builds it, which
    # is the same not-charging-the-innocent rule Task 7 measured at 0.16s on `mall-admin`.
    workspace: "Workspace | None" = None
    values: "ValueIndex | None" = None


def _prefix_captures(
    root_site: dict[str, Any], context: _ChainContext, roots: Sequence[dict[str, Any]] = ()
) -> dict[str, Any]:
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
    for yet, so the owner is what vouches for it instead.

    `roots` (spec 2026-09-21 §5, the continuation) lets a producer that IS one
    of the catalog's roots fold its own captures backward too — `from("ch")`
    before `handle(sinkSpec)`, where the flow's source is a root and the walk
    arrives at `handle` from the sink chain, never from that root. A root is
    owner-gated by construction, so the rule above holds for it. Empty on the
    root walk itself, whose prefix is what it always was."""
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
        root = _matching_root(producer, roots)
        if root is not None:
            captures.update(_root_captures(root, producer, context))
            continue
        step = _matching_step(producer, owned)
        if step is not None:
            captures.update(_step_captures(step, producer))
    return captures


def _root_captures(
    root: dict[str, Any], site: dict[str, Any], context: _ChainContext
) -> dict[str, Any]:
    """What one root contributes at its site: its captures (spec 2026-09-21
    §4's `method_annotation` among them) and its direction and composition
    under their reserved keys. Seeded by the root walk, and folded backward
    where the continuation's prefix reaches a root (`_prefix_captures`) —
    less `_CONTINUE`, which the root walk adds itself: it is the walk's own
    instruction, not a capture, and a root reached backward is not handing
    its value on."""
    captures = {
        **_resolve_captures(root["captures"], site),
        **_method_annotation_capture(root, context),
    }
    if root["direction"] is not None:
        captures[_DIRECTION] = root["direction"]
    if root["compose"] is not None:
        captures[_COMPOSE] = root["compose"]
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
    still fold past it.

    **A void call on the value is a configuration of it, not a fork** (spec
    2026-09-21 §4, the bean-wired registration). `new Adapter(ops, "q");
    adapter.setOutputChannelName("c"); adapter.setTopic("t")` is three rows
    sharing one receiver, and the two setters return nothing (D00 §5:
    `result` null) — there is no value for a chain of their own to continue
    from, and reading them as two forks derived two rows each seeing one
    setter, so no chain could ever hold both halves of an address (§4's
    `compose:`) or a link beside a destination. So a row whose own chain key
    is None folds its captures into THIS chain, in ordinal order, and the walk
    goes on to the next sibling; only a row whose result is a value forks. A
    void row that is itself a terminal marks the chain executable as it did
    when it was walked as a branch of its own, and a chain whose siblings
    were all void derives once, at the end, with everything they folded —
    which for a chain that had one void sibling is exactly the row it always
    derived. `captures` is this branch's own dict (copied per fork by the
    caller), so folding into it in place is folding into the branch."""
    if _reaches_terminal(site, context):
        reached_terminal = True
        _hold_client(site, captures, context)
    # Spec 2026-09-21 §5: a value this row produced that a declared consumer
    # takes as an argument hands the chain on — the walk continues from the
    # consumer with these captures, and derivation belongs to the continued
    # chain's end, never to this one's. Tested at every row the walk reaches,
    # because the value handed on is whichever the consumer's argument names:
    # the root's own (`from(Kafka.messageDrivenChannelAdapter(cf, "t"))`), a
    # configuring call's result on it, or a `build()`.
    consumers = _continuations(site, captures, context)
    for consumer in consumers:
        _continue(consumer, captures, context)
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
    forked = False
    for next_site in nexts:
        if _chain_key(next_site) is None:
            _fold_site(next_site, captures, context)
            if _reaches_terminal(next_site, context):
                reached_terminal = True
                _hold_client(next_site, captures, context)
            continue
        forked = True
        next_captures = dict(captures)
        _fold_site(next_site, next_captures, context)
        _walk(next_site, next_captures, reached_terminal, context)
    if forked or consumers:
        return
    # A collecting walk (spec 2026-09-21 §4's container hop) records every
    # chain end, terminal or not: a referenced bean's chain is that bean's
    # configuration, not a registration, and nothing marks it executable.
    if context.collect is not None:
        context.collect.append(captures)
    elif reached_terminal:
        _derive(captures, context)


def _hold_client(site: dict[str, Any], captures: dict[str, Any], context: _ChainContext) -> None:
    """Where the catalog declares `client_base`, the client the request at `site` is issued
    on, held in `captures` for the address join (`_against_client_base`): argument
    `client_arg` of the executing call that consumes `site`'s built value — Ktor's
    `HttpStatement(builder, client)`. Only where exactly one call executes the value: a
    request handed to two would have two clients, and which one a row means is not known."""
    name = str(site["name"])
    if context.client_base is None or name not in context.via_argument_names:
        return
    executing = _consumers(site, context.sites, context.via_argument_names[name])
    if len(executing) != 1:
        return
    slot = int(context.client_base["client_arg"])
    captures[_CLIENT] = _captured_at(_arg_at(executing[0]["arguments"], slot), executing[0], slot)


def _continuations(
    site: dict[str, Any], captures: dict[str, Any], context: _ChainContext
) -> list[dict[str, Any]]:
    """The consumers that continue the chain from `site` (spec 2026-09-21 §5):
    every row in this caller taking `site`'s own chain key as an argument
    that matches a continuing join — the one the chain's root or a step
    declared (`via_argument_of … continue: true`, riding in `captures`), or
    the one a `terminal` entry of `site`'s own name declared (`build`'s
    `terminal_via_argument … continue: true`). Empty for every chain of
    every catalog that spells neither."""
    filters: list[_JoinFilter] = []
    declared = captures.get(_CONTINUE)
    if isinstance(declared, _JoinFilter):
        filters.append(declared)
    terminal = context.via_argument_names.get(str(site["name"]))
    if terminal is not None and terminal.continues:
        filters.append(terminal)
    found: list[dict[str, Any]] = []
    for join_filter in filters:
        for consumer in _consumers(site, context.sites, join_filter):
            if all(consumer is not seen for seen in found):
                found.append(consumer)
    return found


def _continue(consumer: dict[str, Any], captures: dict[str, Any], context: _ChainContext) -> None:
    """Continues the walk from `consumer` (spec 2026-09-21 §5): its own
    receiver ancestry first — `from("ch")` before `handle(sinkSpec)`, roots
    included — then the handed-on chain's captures on top (a poison the
    prefix set stays, `_fold`'s rule), then the consumer's own step, and on
    along its result chain, executable from here: the consumer IS the
    terminal, so a flow needs no `get()` declared to derive. The handed-on
    chain's `_CONTINUE` does not travel — the continued chain ends where it
    ends, unless the consumer's own step hands it on again."""
    continued = _prefix_captures(consumer, context, context.roots)
    _fold(continued, {field: value for field, value in captures.items() if field != _CONTINUE})
    _fold_bean_captures(continued, context)
    _fold_site(consumer, continued, context)
    _walk(consumer, continued, reached_terminal=True, context=context)


def _reaches_terminal(site: dict[str, Any], context: _ChainContext) -> bool:
    """Whether `site` makes its chain executable: a plain terminal by name, or
    a `terminal_via_argument` one whose built value some executing call in
    this caller actually consumes."""
    name = str(site["name"])
    return name in context.terminal_names or (
        name in context.via_argument_names
        and _has_execute_join(site, context.sites, context.via_argument_names[name])
    )


def _fold_site(site: dict[str, Any], captures: dict[str, Any], context: _ChainContext) -> None:
    """Folds what one row the walk reached contributes into `captures`, in
    place: the captures and collected entries of the step it matches, or —
    where it matches none and its owner is one `undeclared_steps` names —
    the catalog's poisons for an unknown member (spec 2026-09-21 §5: an
    undeclared member of a flow definition is a `divert`). A terminal is a
    declared word too, so a terminal-named row on a listed owner poisons
    nothing. Every other unmatched row passes through uncaptured (D02
    §4)."""
    step = _matching_step(site, context.steps)
    if step is None:
        if site["owner"] in context.undeclared_owners and not _reaches_terminal(site, context):
            _fold(captures, dict.fromkeys(context.undeclared_poisons, _POISONED))
        return
    # Last wins (D02 §4): a repeated step overwrites its own earlier
    # capture here, in visitation order, with no extra bookkeeping.
    # `site`'s own arguments are what a `when` guard (D02 §2's
    # `fluent` style) reads, so the guard is evaluated here, in
    # `_resolve_captures`'s caller, rather than inside it.
    folded = _step_captures(step, site)
    # Spec 2026-09-21 §5 and fix round 1 (finding 3): a link's meaning depends
    # on where it sits. A handler captured AFTER a link the chain holds READS
    # the linked channel (the DSL subscribes the next endpoint to it —
    # `_READS_LINK` keeps the link's value, readable or not, because an
    # unreadable link before the handler still means the handler reads
    # SOMETHING other than the wire or the source); a link captured AFTER a
    # handler is that handler's OUTPUT channel (`_LINK_SENDER` holds it) and
    # leaves what the handler read untouched.
    if "channel_link" in folded:
        if "handler" in captures:
            captures[_LINK_SENDER] = captures["handler"]
        else:
            captures.pop(_LINK_SENDER, None)
    elif "handler" in folded and "channel_link" in captures:
        captures[_READS_LINK] = captures["channel_link"]
    _fold(captures, folded)
    if step["continue_via"] is not None:
        captures[_CONTINUE] = step["continue_via"]
    # F5 §6.2 (W29): a `collects` step ACCUMULATES instead, because the thing it
    # reads is repeatable — a request may carry any number of headers, and
    # last-wins would keep only the final one and silently claim it was the only
    # one. Appended to a tuple rather than a list so each branch of a fork gets
    # its own value by copy, exactly as `dict(captures)` in `_walk` gives each
    # branch its own captures.
    collected = _step_collects(step, site)
    if collected:
        previous = captures.get(_COLLECTED) or ()
        captures[_COLLECTED] = (*previous, *collected)
    # `OI-73`: a step whose captured argument IS a lambda takes its captures from
    # the lambda's own body. `uri(b -> b.path("/x").queryParam("q", term).build())`
    # is the idiomatic way to build a URL with query parameters, and the address
    # is the row's identity — without this the row derives with `path` NULL and a
    # real outbound call has no address at all.
    _fold_lambda_captures(captures, context)
    # Spec 2026-09-21 §4: a step whose captured argument is a BEAN reference
    # takes its value from the bean — its name, or the captures of its own
    # chain — resolved here, where the step folded, so a later setter's
    # literal overrides it exactly as it overrides any earlier capture.
    _fold_bean_captures(captures, context)


def _fold(captures: dict[str, Any], folded: dict[str, Any]) -> None:
    """Last wins (D02 §4), except for a field a catalog poison already holds:
    `_POISONED` stays to the chain's end, so the `handle` after a `divert`
    never becomes the row's handler (spec 2026-09-21 §5, §0b A5). A guard's
    own `_UNRESOLVED_ARGUMENT` is not a poison and is overwritten as it always
    was."""
    for field, value in folded.items():
        if captures.get(field) is not _POISONED:
            captures[field] = value


def _derive(captures: dict[str, Any], context: _ChainContext) -> None:
    """One chain's row (or, for an inbound chain that linked a channel, its
    `fed_by` edge instead — the join pass mints the row).

    A registration chain's `handler` (spec 2026-09-21 §3c) is the consumer it
    captured, written on an INBOUND row only: a `lambda` argument's body,
    joined to its full method symbol; NULL for the literal `none` (a
    `discard` step — the true answer), for a poisoned capture (a `divert`
    before it — §5), for an argument of any other kind (a bean handler, the
    bean fold's word), and for a chain that never reached a handler step.
    **The handler never moves the row's resolution**: the row's identity is
    the wire (`protocol`, `path`), which the chain read or did not, and a
    known wire whose consumer is unread is a resolved row with `handler`
    NULL — not an unresolved row, which would say the WIRE was unread.
    `evidence` is a closed set, so the reason stays in the walk, not the
    row."""
    # Spec 2026-09-21 §4: the root's own direction where it declared one,
    # the catalog's otherwise — read once, because every column and key
    # below that names a direction names this one.
    direction = captures.get(_DIRECTION, context.catalog.direction)
    if _COMPOSE in captures:
        composed_field, halves, join = captures[_COMPOSE]
        captures = {**captures, composed_field: _composed_field(halves, join, captures, context)}
    # The consumer the chain captured, whatever the direction (read on the row
    # for an inbound one alone, below); and — fix round 1, finding 4 — a
    # channel-sourced chain (`from("ch")…`, spec §5), whose row is decided by
    # what it captured: a WIRE (a sink's `topic`, a composed exchange/routing
    # key) makes it the OUTBOUND row, `caller` the flow method, with an
    # outbound `fed_by` for the source channel (§3b: the channel's wire end
    # is known, so the question is not asked); a handler and no wire makes it
    # the source channel's READER — `read_by`, no row (§5: "a channel-sourced
    # flow with an inline handler is a channel consumer, not a wire"); neither
    # says nothing about any wire (a bridge, `from("a").channel("b")` — the
    # stated boundary). A source whose name could not be read consumes an
    # unknown channel: its wire still derives (no edge to write), its handler
    # reads nothing nameable. A handler folded AFTER a link the chain holds
    # (`from("a").channel("b").handle(h)`, `_READS_LINK`) reads the LINKED
    # channel, M4's rule under `channel_source` too: the framework subscribes
    # `h` to `b`, and `a → b` is the bridge the boundary states — so the edge
    # is `read_by(b, h)` and nothing is written for the source. A link before
    # the handler that could not be read (`channel(<spec>)`, residual fix)
    # is the same bridge to a channel nobody can name: nothing is written,
    # and never `read_by(a, h)` in its place. A link AFTER the handler
    # (`_LINK_SENDER`) is that handler's output, `sends_to`, the wire
    # branch's own edge written here too.
    last_handler = _handler_symbol(captures.get("handler"), context.method_symbols)
    reads_link = _READS_LINK in captures
    read = _string_value(captures[_READS_LINK]) if reads_link else None
    sourced = "channel_source" in captures
    source = _string_value(captures.get("channel_source")) if sourced else None
    if sourced:
        if "channel" in captures:
            direction = "outbound"
        else:
            if not reads_link:
                read = source
            if read is not None and last_handler is not None:
                context.bindings.append(
                    _edge(_READ_BY, read, last_handler, context, "inbound", protocol=None)
                )
            sender = (
                _handler_symbol(captures[_LINK_SENDER], context.method_symbols)
                if _LINK_SENDER in captures
                else None
            )
            sent = _string_value(captures.get("channel_link"))
            if sent is not None and sender is not None:
                context.bindings.append(_edge(_SENDS_TO, sent, sender, context, "inbound"))
            return
    # A verb the catalog spelled as a literal is that literal; one it spelled
    # as `argN` (`A-C2`) is whatever the matched call's own argument reads as a
    # string, and None where nothing could read it — the honest gap, not the
    # root's default.
    declared_verb = captures.get("http_method")
    verb = (
        declared_verb
        if isinstance(declared_verb, str)
        else _string_value(declared_verb) or static_field_value(declared_verb, context.verb_fields)
    )
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
    # `channels_of`, not `channel_of` (spec 2026-09-21 §3c): a varargs
    # destination — the container's `setQueueNames("q1", "q2")`, one `array`
    # argument (9.15) — is one row per element; a slot that is not an array
    # reads exactly as it always did, one tuple, so the ladder below still
    # runs only where that one literal did not resolve.
    if "channel" in captures:
        channel_argument = _address_read(captures.get("channel"), context)
        literal = channels_of(channel_argument)
        channel_via_forms = captures.get("channel_via") or []
        if literal[0][2] != "resolved" and channel_via_forms:
            # **The backward walk, in place of this engine's own one-hop follow** (spec
            # §2b, Task 9). `linked_channels` followed ONE `source` to a call whose owner
            # and method a declared form named; `resolve_site` answers the same position
            # with no cap, and the hoisted identity table says which argument of the
            # producer IS the value. The ladder's order is untouched: the literal read runs
            # first and this answers only where it did not resolve, which is also what
            # keeps `_address_read`'s field rung above working — a field-fed address is
            # already a string by the time it gets here, so this never runs for one.
            #
            # **The position comes from `_captured_at`**, because a capture folds up out of
            # a chain and loses its site, and the walk names a position by
            # `(caller, ordinal, slot)` — the ordinal being what bounds the `escapes`
            # window (`values._used_at`). Resolving in the wrong method would read a
            # same-numbered value of another method and fabricate; `test_fluent_
            # registrations.py`'s negative half pins exactly that.
            destinations = _walked_channels(channel_argument, context, channel_via_forms) or literal
        else:
            destinations = literal
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
    # Spec 2026-09-21 §3c: the consumer, on an inbound row alone — an outbound
    # registration hands its messages to nobody in this module. Where the
    # chain's link sits AFTER a handler (finding 3), the row's handler is
    # THAT handler — the wire's consumer — not whatever a later `handle`
    # after the link captured, which reads the channel instead. A handler
    # that followed a link (`_READS_LINK`) is that channel's reader and not
    # the wire's consumer whether or not the link could be read (residual
    # fix): an unreadable link before it leaves the row's handler NULL rather
    # than crediting the wire with a consumer the framework subscribed
    # elsewhere.
    link_after_handler = _LINK_SENDER in captures
    handler = (
        (
            _handler_symbol(captures[_LINK_SENDER], context.method_symbols)
            if link_after_handler
            else None
            if reads_link
            else last_handler
        )
        if direction == "inbound"
        else None
    )
    # §3b: the channel this registration feeds, where the chain read its name.
    # Poisoned, unresolved or a bean the fold could not name all read None: a
    # channel we cannot name is not a channel we can bind, and the chain then
    # keeps its own row with `handler` NULL.
    link = _string_value(captures.get("channel_link"))
    for peer, path, url_resolution in destinations:
        # 2O design §8, folded in from single_call: identity is the URL the
        # framework serves, canonicalized before the dedup key below is built
        # from it (`domain/paths.py`). Inert for every fluent catalog shipped
        # today, all of which are outbound — R8's exclusion, stated here
        # rather than left implicit, because a future inbound fluent catalog
        # would need it and would otherwise have to rediscover it.
        if path is not None and serves_urls(context.catalog.protocol, direction):
            path = canonical_http_path(path)
        # **The query string is not part of the address** (`OI-151`), and it comes off HERE —
        # after the canonicaliser and before the dedup key below, which is built from the
        # path and must be built from the one the row publishes. `single_call` makes the same
        # call at the same point in its own loop; one function answers for both, which is
        # `OI-144`'s lesson about two engines and one piece of evidence.
        path, query = query_entries(path)
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
        # **THE ROW CARRIES THE ADDRESS'S OWN WORD**, which is `single_call`'s rule
        # verbatim (`engines/single_call.py`, spec 2026-10-18 §5) and the other half of
        # `OI-144`. Recomputing `resolved`/`unresolved` from it threw away the third word
        # the address reader can answer: `partial`, for an address the walk assembled and
        # read part of. Measured on `fixtures/orders-fluentaddress`: the path reached this
        # line as `<host>/owners` with `partial` beside it, and the row published the path
        # at `unresolved` — denying the half that WAS read, one engine disagreeing with the
        # other about one piece of evidence.
        #
        # I1's rule is untouched and is the other half of the condition: every declared
        # capture must still have read, so `partial` is a statement about the ADDRESS and
        # never a licence for an unread body.
        captures_read = (
            (verb is not None or verbless)
            # What the captures PRODUCED, the `single_call` change one engine along
            # (`OI-77`, W43's review): a body capture that filled its column did not fail.
            and _capture_resolved("body" in captures, body_argument, request_shape)
            and _capture_resolved("response" in captures, response_argument, response_shape)
        )
        resolution = (
            url_resolution
            if captures_read and url_resolution != str(Resolution.UNRESOLVED)
            else str(Resolution.UNRESOLVED)
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
                direction,
                verb or "",
                path,
                context.caller,
                peer,
            )
            if key in context.seen:
                continue
            context.seen.add(key)
        for entry in captures.get(_COLLECTED) or ():
            context.metadata.append(_metadata_row(entry, context, direction, verb, path))
        # Below the dedup `continue` on purpose: a row the key already saw writes no second
        # copy of its own query parameters either. Through `_metadata_row` like every other
        # entry this engine writes, so the value is masked by the same redactor on the same
        # rule — a query parameter named `access_token` is exactly the shape that matters.
        for name, value in query:
            context.metadata.append(
                _metadata_row(
                    {
                        "kind": QUERY_KIND,
                        "name": {"kind": "string", "value": name},
                        "value": None if value is None else {"kind": "string", "value": value},
                    },
                    context,
                    direction,
                    verb,
                    path,
                )
            )
        if source is not None:
            # Finding 4: the channel-sourced chain reached a wire — the source
            # channel's wire end is this row, an outbound `fed_by`.
            context.bindings.append(
                _edge("fed_by", source, context.caller, context, direction, path, resolution)
            )
        # Spec 2026-09-21 §5, §0b A4: a handler folded AFTER the link —
        # `.channel("x").handle(h)` — is a READER of the linked channel, the
        # same edge a handler's own annotation writes; the join pass then
        # mints the row naming the feeder and that reader, beside any other
        # reader of the channel. The channel is the one the handler FOLLOWED
        # (`_READS_LINK`), not the chain's last link, which a `.channel("y")`
        # after the handler overwrote (`OI-115`'s shape). Only a handler the
        # chain could name and a link it could read: an unread handler is no
        # reader, and an unreadable link is a channel nobody can name.
        if direction == "inbound" and read is not None and last_handler is not None:
            context.bindings.append(
                _edge(_READ_BY, read, last_handler, context, direction, protocol=None)
            )
        if link is not None and direction == "inbound" and link_after_handler:
            # Finding 3: a link AFTER the handler is the handler's OUTPUT channel
            # — `sends_to`, and the row derives with that handler: the wire's
            # consumer is known, and what it hands on is a separate edge.
            if handler is not None:
                context.bindings.append(_edge(_SENDS_TO, link, handler, context, direction))
        elif link is not None:
            # Spec 2026-09-21 §3b: the `fed_by` edge — the wire this chain read,
            # the constructing method, the registration's direction. An inbound
            # chain writes the edge INSTEAD of its row (the plan's ruling: the
            # join pass owns rows for linked registrations, so a linked adapter
            # is never counted twice — and `call_endpoints`' guard would refuse
            # the minted row, handler and all, behind a chain row with the same
            # identity); an outbound one writes both, its edge existing so that
            # `config_join.gaps` stops asking who feeds the channel. The row's
            # own `resolution` travels with it: the edge stands in for the row.
            context.bindings.append(
                _edge("fed_by", link, context.caller, context, direction, path, resolution)
            )
            if direction == "inbound":
                continue
        context.rows.append(
            {
                "protocol": context.catalog.protocol,
                "direction": direction,
                # Not `str(verb)`: a verbless chain's `verb` is genuinely None
                # (no root ever declared `http_method`), and `str(None)` would
                # write the literal text "None" into a column NULL is supposed
                # to mean "no verb" — single_call's own `method: verb` (never
                # stringified) is the same answer for the same reason.
                "method": verb,
                "path": path,
                "handler": handler,
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


def _edge(
    role: str,
    channel: str,
    symbol: str,
    context: _ChainContext,
    direction: str,
    destination: str | None = None,
    resolution: str = "resolved",
    *,
    protocol: str | None = "",
) -> dict[str, Any]:
    """One `channel_bindings` row (spec 2026-09-21 §3b): `fed_by` carries the
    wire (this catalog's protocol, the destination, the row's own resolution
    — the edge stands in for the row); `read_by` carries the reader and
    nothing about the wire (`protocol=None`, no destination — a reader knows
    only the channel's name); `sends_to` the sender under this catalog's
    protocol, the wire it hands on being the sender's own concern (no
    destination)."""
    return {
        "channel": channel,
        "role": role,
        "symbol": symbol,
        "protocol": context.catalog.protocol if protocol == "" else protocol,
        "direction": direction,
        "destination": destination,
        "catalog_id": context.catalog.id,
        "resolution": resolution,
    }


def _metadata_row(
    entry: dict[str, Any],
    context: "_ChainContext",
    direction: str,
    verb: str | None,
    path: str | None,
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
        "direction": direction,
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
        # An entry a call SENDS has no requirement (spec 2026-09-19 §5a) — stated on the
        # row, because a row missing a declared struct key takes the statement's
        # per-value retry route (`workspace.derive`), which the pipeline test forbids.
        "requirement": None,
    }


def _address_read(argument: dict[str, Any] | None, context: _ChainContext) -> dict[str, Any] | None:
    """One address-position argument as it should be READ (2F design §4): a
    `field`-kind argument — or a getter's own result — that the field ladder
    can name a configuration expression for is replaced by that expression as
    a string literal BEFORE any existing resolution path sees it, so an
    imperatively-fed address behaves downstream exactly as a written one. The
    caller handed to the ladder's parameter rung is the one the argument
    carries (`_own_parameter`) — the method whose signature the index is an
    index into — never the chain's, which a lambda body's capture is not."""
    if isinstance(argument, dict) and argument.get("kind") == "array":
        # A varargs slot is one `array` argument (9.15), one destination per
        # element (spec 2026-09-21 §3c) — and each element is an address in
        # its own right, so each takes the ladder: `inboundAdapter(cf,
        # this.valueQueue)` is a field-fed queue exactly as `uri(this.url)`
        # is a field-fed address. The array itself names no expression, so
        # before this every varargs registration fed from configuration read
        # `unresolved` element by element.
        return {
            **argument,
            "elements": [
                _address_read(element, context) for element in argument.get("elements") or []
            ],
        }
    caller = argument.get("caller") if isinstance(argument, dict) else None
    return address_argument(argument, context.field_sources, context.facts, caller)


def _declares_a_hop(matches: dict[str, Any]) -> bool:
    """Whether this catalog names a `channel_via` or `url_via` anywhere in `matches`.

    Anywhere, because the keys are not at one depth — `url_via` sits on a root, a step and
    a terminal, `channel_via` on those and on a bean entry — and this is a precondition on
    building an index rather than a reader of the entries themselves, so it must not learn
    any style's shape to answer it. The same walk `yaml_source._hoisted` makes, for the
    same reason.
    """

    def walk(node: Any) -> bool:
        if isinstance(node, dict):
            if "channel_via" in node or "url_via" in node:
                return True
            return any(walk(value) for value in node.values())
        if isinstance(node, list):
            return any(walk(entry) for entry in node)
        return False

    return walk(matches)


def _walked_channels(
    argument: dict[str, Any] | None,
    context: _ChainContext,
    forms: Sequence[dict[str, Any]] = (),
) -> Sequence[tuple[str | None, str | None, str]] | None:
    """One channel capture's destinations, resolved by the backward walk (Task 9).

    `None` where the walk cannot be asked rather than where it answers nothing, and the
    difference is the whole contract: a caller must be able to fall back to the literal
    read it already has. So `None` means this catalog declares no hop (no index was built),
    or the capture carries no `_captured_at` provenance, or the site it names is not one
    this workspace holds. An empty answer from the walk itself is NOT `None` — it is an
    answer, and `resolve_site` returning no binding means no path answered, which the
    caller publishes as one unresolved tuple exactly as the old ladder did.

    **One tuple per distinct destination, not one per path** (§1c), the same reasoning
    `single_call` and `interface_implementation` state: several paths routinely agree about
    this one slot, and keeping them apart would mint a second row for one registration.
    """
    # The provenance, the index and the site are all checked by `_walked_with`, which
    # does the walk; what is decided HERE is only which identities it may consult.
    if not isinstance(argument, dict):
        return None
    # **The identities are THIS ROW's declared producers, not the whole table**, and that
    # is load-bearing rather than cautious. `linked_channels` followed a `source` only to a
    # call whose owner AND method a declared form named; handed `catalog.value_model`
    # instead, the walk follows any producer ANY catalog declared, and a row then publishes
    # a destination its own form never reached. Two shipped guards say so —
    # `fluent.url-via-follows-only-a-declared-call` SURVIVED its mutation, and
    # `test_an_element_no_declared_form_reaches_is_unresolved_on_its_own` failed — so this
    # is measured rather than argued.
    #
    # `single_call` could take the shared table because Task 8 gave it a TYPE GATE: its
    # rows declare a descriptor, so a producer whose return type cannot be the declared
    # parameter type is refused. `fluent`'s rows here carry no descriptor (22 of its 29 hop
    # rows do not), so that gate cannot govern them and the row's own declaration is what
    # remains. §1e is the reading: the walk answers what a value is, the catalog says which
    # producer means the destination.
    # `descriptor` and `arity` travel too, and dropping them was a real regression caught
    # by `test_a_sibling_constructor_with_a_string_at_the_same_position_is_not_the_topic`:
    # a form's descriptor is what tells one overload from its siblings, so an entry without
    # it matches an overload whose argument 0 is something else entirely.
    identities = [
        {
            "owner": form["owner"],
            "method": form["method"],
            "arg": form["arg"],
            **({"descriptor": form["descriptor"]} if "descriptor" in form else {}),
            **({"arity": form["arity"]} if "arity" in form else {}),
        }
        for form in forms
        if isinstance(form, dict) and {"owner", "method", "arg"} <= set(form)
    ]
    if not identities:
        return None
    return _walked_with(argument, context, identities)


def _assembled_text(answer: "Answer | None") -> tuple[str | None, str | None, str]:
    """One walk answer for an assembled ADDRESS, as `(None, text, resolution)` where the text
    is the template VERBATIM.

    **Not `url_of_answer`, and the difference is one of layer rather than of rule.** That
    function answers a finished ROW — peer and path, split, with an unread host already
    written `<host>` — and this arm has to hand `url_of` an ARGUMENT, which it then splits
    once. Passing the finished row back in split it twice: `<host>/owners` carries no hole,
    so the second pass read it as not-an-address and published nothing. Measured, and the
    reason this reader exists rather than reusing that one.

    The classification is `url_of`'s own, with no address knowledge of its own: a whole
    string literal is `resolved`, a template is `partial`, everything else is `unresolved`.
    """
    if answer is None:
        return None, None, str(Resolution.UNRESOLVED)
    if answer.kind == LITERAL and answer.literal_kind == STRING:
        return None, str(answer.value), str(Resolution.RESOLVED)
    if answer.kind == EXPRESSION:
        return None, str(answer.value), str(Resolution.PARTIAL)
    return None, None, str(Resolution.UNRESOLVED)


def _walked_with(
    argument: dict[str, Any],
    context: _ChainContext,
    identities: Sequence[dict[str, Any]],
    reader: "Callable[[Answer | None], tuple[str | None, str | None, str]]" = channel_of_answer,
) -> Sequence[tuple[str | None, str | None, str]] | None:
    """`_walked_channels`' walk, with the identity list decided by the caller.

    `reader` turns one answer into `(peer, address, resolution)`. A CHANNEL is read with
    `channel_of_answer`, which refuses a template — a broker needs a whole destination — and
    an HTTP address with `url_of_answer`, which publishes the half it read (`OI-144`). The
    default keeps every existing caller reading channels, which is what they all are.

    Split out so that **an EMPTY list is reachable deliberately**, which is not the same
    thing as the refusal above it. That refusal exists because handing the walk
    `catalog.value_model` would let a row publish a destination its own form never
    reached, and two shipped guards measure it. An empty list has the OPPOSITE effect: no
    `identified_by` entry is consulted at all, so the walk can only answer values it
    reaches over plain value edges and can never conclude "this producer MEANS the
    destination". That is why the assembled-address caller may ask without declaring a
    hop.
    """
    if context.values is None or context.workspace is None:
        return None
    captured = argument.get(_CAPTURED_AT)
    if captured is None:
        return None
    caller, ordinal, slot = captured
    site = context.values.sites.get((str(caller), int(str(ordinal))))
    if site is None:
        return None
    walked = list(
        dict.fromkeys(
            reader(binding.slots.get(slot))
            for binding in resolve_site(context.workspace, site, context.values, identities)
        )
    )
    return walked or [(None, None, "unresolved")]


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
    url_argument = _url_argument(captures, context) if "url" in captures else None
    if "base" not in captures:
        if context.workspace is None or context.values is None:
            return _against_client_base(url_of(url_argument), captures, context)
        # **The PEER is its own question** (`OI-138` cause 3): the join above is handed no
        # identities, so the path is text the code states, and who is CALLED is asked
        # separately of the first operand — the user's ruling of 2026-10-17, "peer and path
        # from separate evidence".
        captured = (_address_read(captures.get("url"), context) or {}).get("captured_at")
        return _against_client_base(
            with_authority(
                url_of(url_argument),
                _address_read(captures.get("url"), context),
                str(captured[0]) if captured else None,
                context.workspace,
                context.values,
                context.catalog.value_model or (),
            ),
            captures,
            context,
        )
    base = _string_value(_address_read(captures.get("base"), context))
    if base is None:
        return None, None, "unresolved"
    if "url" not in captures:
        return _address_of(base)
    path = _string_value(url_argument)
    if path is None:
        return None, None, "unresolved"
    return _address_of(base + path)


def _against_client_base(
    address: tuple[str | None, str | None, str],
    captures: dict[str, Any],
    context: _ChainContext,
) -> tuple[str | None, str | None, str]:
    """`address` where the catalog says a relative address is relative to a base the
    executing CLIENT holds (`client_base`, spec 2026-10-26 §3c): Ktor joins
    `get("relative/path")` onto the client's `defaultRequest` base, and onto
    `http://localhost` where it has none (CP-54 rows 51-57).

    The base is `shapes.client_base.client_base`'s, read off the client the chain was
    issued on (`_hold_client`), and the join is the catalog's rule; the joined URL is split
    by CP-2 as a written one is. Where the base cannot be read — the client's construction
    is not reached, or the code setting the base is not read — or the join declines, the
    address the code states is a PATH and not the URL called: it keeps the path, peer NULL,
    at `unresolved`. A configuration base is carried, not joined (below).

    Only a relative address read in full moves. An absolute one is the whole address (Ktor
    ignores the base for it, CP-54 row 55); a `${…}` expression is configuration that may be
    absolute, read where the configuration join reads it; and a `partial` or `unresolved`
    address already says it was not read in full. Every catalog not declaring the key
    keeps its relative address as it always has."""
    peer, path, resolution = address
    if (
        context.client_base is None
        or peer is not None
        or path is None
        or resolution != str(Resolution.RESOLVED)
        or carries_expression(path)
    ):
        return address
    client = captures.get(_CLIENT)
    base = None
    if client is not None and context.workspace is not None:
        base, _ = client_base(context.workspace, context.values, client, context.client_base)
    if base is not None and carries_expression(base):
        # A configuration base (`${pricing.url}`), carried as the configuration convention
        # carries a `${…}` base — the whole address in `path`, peer NULL, for the
        # per-environment join to read — and `partial`, never joined: Ktor's join depends on
        # whether the base ends in `/`, which the key does not say.
        return None, f"{base.rstrip('/')}/{path.lstrip('/')}", str(Resolution.PARTIAL)
    joined = None if base is None else join_url(base, path, str(context.client_base["join"]))
    if joined is None:
        return None, path, str(Resolution.UNRESOLVED)
    return _address_of(joined)


def _url_argument(captures: dict[str, Any], context: _ChainContext) -> dict[str, Any] | None:
    """The `url` capture as the address readers should see it (A2 Task 8, spec §12):
    the captured argument itself, or — where that argument is not a string literal and
    the entry declared `url_via` — the string the linked call it names was handed, as a
    `string` argument, so `url_of` and the `base` composition read it exactly as a
    literal written at the capture.

    `url_via` is `channel_via`'s ladder applied to the `url` capture, verbatim: the JDK
    client's `uri(URI.create("https://…"))` reaches the step as `unresolved`+`source`,
    and the address lives on `URI.create`'s own argument, exactly as a JMS destination
    lives on `session.createQueue("q")`'s. Same order too — the literal argument first,
    the ladder only when the literal did not resolve — and the same `linked_channels`
    call, which follows `source` to a call site whose owner AND method a declared form
    names, and nothing else. A `field`-fed address is already a string expression by the
    time it gets here (`_address_read`), so the ladder never runs for it.

    A ladder that answers nothing — no `source`, a linked call no form names, a linked
    call whose own argument is not a literal (a `concat`) — leaves the captured argument
    as it was, so the row derives with `path` NULL at `unresolved` exactly as a direct
    read of that argument would: the ladder can only add an answer, never take one away.
    `arg` is one position (`_validate_channel_via_entries` refuses `all_strings` here):
    a URL is one string, where a topic list is several."""
    argument = _address_read(captures.get("url"), context)
    forms = captures.get("url_via") or []
    if _string_value(argument) is not None:
        return argument
    # **An ASSEMBLED address is not a hop, so it needs no `url_via`** (ruling 1,
    # 2026-10-17). `url_via` declares that the address lives on some OTHER call's
    # argument - `URI.create("...")` - and a catalog has to say so because following a
    # `source` to an undeclared producer is how a row publishes a destination its own
    # form never reached. A concat is neither: the catalog already pointed at THIS
    # position, and the operands are the concat site's own arguments in the same method
    # body. So the walk is asked with NO identity entries, which is what holds it to
    # plain value edges - it can join literals and it cannot conclude that a producer
    # means the destination.
    #
    # Same rule as the ladder below: one resolved answer is taken, anything else leaves
    # the capture as it was. The walk may ADD an answer and never take one away.
    #
    # **AND THE EMPTY LIST IS LOAD-BEARING FOR A SECOND REASON, found 2026-10-17.** An
    # `identified_by` entry says what a value STANDS FOR; a join publishes text as an
    # ADDRESS. Those are different claims, and they part company exactly where it matters:
    # `String.valueOf(x)` is `x.toString()` (read off the JDK's own bytecode), so for a
    # `URI` the identity and the text coincide while for a messaging destination whose
    # identity is `"orders"` the text is some vendor debug string. Joining an
    # identity-derived answer would therefore publish an address that never existed.
    # Consulting NO identity keeps this arm to text the code literally states, which is the
    # only thing a join may render. `OI-142` carries the finding and what it blocks.
    if isinstance(argument, dict) and argument.get("kind") == _CONCAT:
        # **Read with the URL reader, which is the whole of `OI-144`.** This arm asked
        # `channel_of_answer` until 2026-10-19, and that reader refuses a template ON
        # PURPOSE: a broker resolves a destination it is GIVEN, and half of one is not a
        # destination. An HTTP address is the other case — `single_call` has published the
        # half it read since `OI-143` — and `url_of_answer` exists for exactly it.
        #
        # Measured, one address written once each way: `single_call` published
        # `<host>/owners` at `partial` while this arm published `path` NULL at `unresolved`.
        # Two engines, two answers about one piece of evidence, which is the disease the
        # shared walk was built to end (spec 2026-09-22 §0a).
        assembled = _walked_with(argument, context, (), reader=_assembled_text)
        if assembled is not None:
            whole = {
                literal
                for _, literal, resolution in assembled
                if resolution == "resolved" and literal
            }
            if len(whole) == 1:
                return {"kind": "string", "value": whole.pop()}
            # A partly-known address, published as the EXPRESSION kind `url_of` reads: the
            # text is the template with its holes, and `url_of` decides peer and path from
            # it exactly as it does for `single_call`. Only where there is one — several
            # answers are several rows, which this engine's one-argument return cannot carry
            # (`OI-134`'s shape), so it leaves the capture as it was rather than choosing.
            partly = {
                literal
                for _, literal, resolution in assembled
                if resolution == "partial" and literal
            }
            if not whole and len(partly) == 1:
                return {"kind": EXPRESSION, "value": partly.pop()}
        return argument
    if not forms:
        return argument
    # **The backward walk, in place of the one-hop follow** (spec §2b, Task 9), reached
    # through the same `_captured_at` provenance the channel half uses. The order above is
    # untouched: a literal at the capture answers first, and a field-fed address is already
    # a string by the time it arrives (`_address_read`), so neither ever reaches here.
    walked = _walked_channels(argument, context, forms)
    if walked is None:
        return argument
    # **A URL is ONE string**, which is why `_validate_channel_via_entries` refuses
    # `all_strings` on `url_via` where `channel_via` allows it. The walk can legitimately
    # find SEVERAL — two callers handing different addresses into one chain is several
    # bindings by design (§1c) — where `linked_channels` could only ever answer one. Those
    # are not an address between them, and choosing one would fabricate the row's identity,
    # so the capture travels on unchanged and the row derives `path` NULL at `unresolved`.
    # That is the ladder's own rule stated in this function's docstring: it may ADD an
    # answer and never take one away.
    resolved = [
        literal for _, literal, resolution in walked if resolution == "resolved" and literal
    ]
    if len(resolved) != 1:
        return argument
    return {"kind": "string", "value": resolved[0]}


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


def _composed_field(
    halves: tuple[str, ...], join: str, captures: dict[str, Any], context: _ChainContext
) -> Any:
    """Spec 2026-09-21 §4's `compose:` — the field's value as ONE string
    argument joined from its halves in declared order, each half read through
    the field ladder exactly as an address capture is (a half held in a
    `@Value` field is its `${…}` expression, and the composition carries it
    whole). A half never captured, or captured and unreadable, leaves the
    whole field unresolved (§0b A3: the framework fills an unset half from
    defaults the walk does not read, so half an address is no address) —
    `_composed_address`'s own rule for `base`+`url`, restated for a
    destination.

    An EMPTY first half is the composite's own degenerate spelling and the
    field is then the tail alone — `single_call._paired_destination`'s rule,
    restated here for the same wire (§8.1 rule 1: an exchange name of `""` is
    AMQP's default exchange, and the routing key alone names the queue), so
    the DSL sink and the template publish the same address for the same
    call. As there, it holds while every protocol composing here reads an
    empty first half as "the default routing"; one that does not needs its
    own rule rather than this one widened."""
    parts = [_string_value(_address_read(captures.get(half), context)) for half in halves]
    if any(part is None for part in parts):
        return _UNRESOLVED_ARGUMENT
    if parts[0] == "":
        parts = parts[1:]
    return {"kind": "string", "value": join.join(str(part) for part in parts)}


def _string_value(argument: dict[str, Any] | None) -> str | None:
    """A captured argument's own string literal, or None for anything else —
    `url_of`'s own test, needed on its own here because composition works on
    the two halves' TEXT before either is read as an address. "Anything
    else" includes the catalog's own literal spellings (`none`, `{bean_via:
    …}`) and both poisons, none of which is a `string` argument."""
    if (
        isinstance(argument, dict)
        and argument.get("kind") == "string"
        and isinstance(argument.get("value"), str)
    ):
        return str(argument["value"])
    return None


def _handler_symbol(argument: Any, method_symbols: dict[str, str]) -> str | None:
    """The full method symbol a captured `handler` names (spec 2026-09-21
    §3c), or None. Only a `lambda` argument is read here — a bound method
    reference names the real method, an inline block the synthetic body the
    compiler emitted for it (D00 §5a), and a class-compiled lambda already
    arrives as one through `effective_call_sites` — and only where its bare
    name joins to a symbol fact: a handler nothing else in the graph could
    follow is no handler. `combinator._handler_of`, restated for a capture
    rather than a position. Everything else reads None and moves nothing (the
    `_derive` docstring)."""
    if not isinstance(argument, dict) or argument.get("kind") != "lambda":
        return None
    symbol = argument.get("symbol")
    return method_symbols.get(str(symbol)) if symbol is not None else None


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


def _matching_root(site: dict[str, Any], roots: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    """The first declared root `site` is a call to: its owner, its name, and — where
    the root declares a `descriptor` — its parameter types (`_same_overload`)."""
    return next(
        (
            root
            for root in roots
            if site["owner"] in root["owners"]
            and site["name"] == root["method"]
            and _same_overload(root, site)
        ),
        None,
    )


def _same_overload(entry: dict[str, Any], site: dict[str, Any]) -> bool:
    """Whether `site` is the overload `entry` declares — every overload where the
    entry declares no `descriptor`, else the one whose PARAMETER TYPES are the
    declared ones. The parameter portion alone, `single_call._matching_method`'s
    own rule (F2 §4.1): a method is identified by its name and parameter types,
    and a return type moves between framework releases without a caller's source
    changing — ten `spring-kafka-template` rows once matched nothing in a 2.x
    module for exactly that."""
    declared = entry["descriptor"]
    if declared is None:
        return True
    recorded = site.get("descriptor")
    return recorded is not None and parameter_types(declared) == parameter_types(str(recorded))


def _validated_descriptor(entry: dict[str, Any], catalog: Catalog, where: str) -> str | None:
    """An entry's optional `descriptor`, refused unless it is spelled the way the
    extractor records one — a string opening with `(` and closing its parameter
    list — because a descriptor no call site can ever equal matches nothing, and
    an overload declared that way silently derives nothing (the `single_call`
    refusal, for its reason). The message names no language: `descriptor` is
    whatever the module's own extractor records at `target.descriptor`."""
    declared = entry.get("descriptor")
    if declared is None:
        return None
    if not (isinstance(declared, str) and declared.startswith("(") and ")" in declared):
        raise CatalogError(
            f"loading catalog {catalog.source}: `{where}` entry `{entry.get('method')}` "
            f"declares `descriptor: {declared!r}`, which is not a method descriptor — its "
            f"parameter portion is compared against a call site's own `target.descriptor`, "
            f"so it must be spelled the way the extractor records one, opening with `(` "
            f"(spec 2026-09-21 §5)"
        )
    return declared


def _validated_receiver_arg(step: dict[str, Any], catalog: Catalog) -> int | None:
    """A step's optional `receiver_arg`, refused unless it is an argument index — a
    non-negative integer, and not a boolean, which Python counts as one. An index no call
    site can carry joins nothing, and a step declared that way would load and silently
    never be reached (spec 2026-10-26 §3c)."""
    declared = step.get("receiver_arg")
    if declared is None:
        return None
    if isinstance(declared, bool) or not isinstance(declared, int) or declared < 0:
        raise CatalogError(
            f"loading catalog {catalog.source}: step `{step.get('method')}` declares "
            f"`receiver_arg: {declared!r}`, which is not an argument index — it names the "
            f"argument the step's receiver arrives as, a non-negative integer (spec "
            f"2026-10-26 §3c)"
        )
    return declared


def _receiver_of(site: dict[str, Any], extension_steps: dict[str, list[dict[str, Any]]]) -> Any:
    """The value id `site` joins a chain through (spec 2026-10-26 §3c): its own `receiver`,
    or — where it matches a step declaring `receiver_arg: N` — argument N's value id. An
    extension function compiles to a STATIC method, so `HttpRequestKt.url(builder, "…")`
    has a null `receiver` and the builder it extends is argument 0, an `instance`
    whose `source` is the builder's id. The step's owner and descriptor still decide the
    match, so a same-named call anywhere else joins as it always did. An argument carrying
    no `source` joins nothing, as a null `receiver` does.

    The FORWARD walk's join: a step is reached from the chain it extends. The backward
    prefix walk (`_prefix_captures`) still reads each producer's own `receiver`, so it
    stops at an extension call, as it stops at any static call."""
    candidates = extension_steps.get(str(site["name"]))
    if candidates:
        step = _matching_step(site, candidates)
        if step is not None:
            argument = _arg_at(site["arguments"], step["receiver_arg"])
            return None if argument is None else argument.get("source")
    return site["receiver"]


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
            and _same_overload(step, site)
        ),
        None,
    )


def _validate_steps(steps: list[dict[str, Any]], catalog: Catalog) -> None:
    """Refuses a catalog where two step entries share a method name with no
    `owner` telling them apart — silent last-wins would hide exactly the bug
    it is meant to catch (`ports/catalogs.py`'s own discipline: an unchecked
    value does not stay in the file). Two entries are distinguishable only
    when BOTH declare an `owner` and the owners differ — or, sharing an
    owner, when BOTH declare a `descriptor` and the parameter types differ
    (spec 2026-09-21 §5); an owner-less entry matches every owner, and a
    descriptor-less one every overload, so either collides with any sibling
    regardless of what that sibling declares."""
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
        # could only collide by being equal. Two entries sharing an owner are
        # still distinguishable when BOTH declare a `descriptor` and the
        # descriptors differ (spec 2026-09-21 §5: the `handle` overloads on one
        # definition type); one of them declaring none would match every
        # overload, which is the same silent last-wins.
        overlapping = any(
            _overlapping_owners(first["owners"], second["owners"])
            and not _distinct_overloads(first, second)
            for index, first in enumerate(group)
            for second in group[index + 1 :]
        )
        if overlapping:
            raise CatalogError(
                f"loading catalog {catalog.source}: steps named `{method}` need distinct "
                f"`owner`s or distinct `descriptor`s to tell them apart (D02 §4's fluent "
                f"style)"
            )


def _overlapping_owners(first: tuple[str, ...] | None, second: tuple[str, ...] | None) -> bool:
    return first is None or second is None or bool(set(first) & set(second))


def _distinct_overloads(first: dict[str, Any], second: dict[str, Any]) -> bool:
    return (
        first["descriptor"] is not None
        and second["descriptor"] is not None
        and parameter_types(first["descriptor"]) != parameter_types(second["descriptor"])
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
            # `{bean_via: argN}` is a position too (spec 2026-09-21 §4): the
            # argument at it is read as a bean reference rather than as the
            # value itself — the container hop, `channel: {bean_via: arg0}`.
            if field in _ARGUMENT_FIELDS and not (
                _ARG_REFERENCE.match(str(value)) or _valid_bean_via(value)
            ):
                raise CatalogError(
                    f"loading catalog {catalog.source}: `{entry['method']}` captures "
                    f"`{field}: {value}`, which is not a call-site position — an argument "
                    f"capture reads `argN` or `{{{_BEAN_VIA}: argN}}` (D02 §4's fluent style)"
                )
            # Spec 2026-09-21 §4: the two consumer captures, each `argN` or its
            # one literal spelling — anything else is a typo that would
            # silently capture nothing, the same reason the check above exists.
            if field == "handler" and not (
                _ARG_REFERENCE.match(str(value)) or value == _HANDLER_NONE
            ):
                raise CatalogError(
                    f"loading catalog {catalog.source}: `{entry['method']}` captures "
                    f"`handler: {value}` — a handler reads `argN` or is the literal "
                    f"`{_HANDLER_NONE}` (spec 2026-09-21 §5's `discard`)"
                )
            if field in _CHANNEL_NAME_FIELDS and not (
                _ARG_REFERENCE.match(str(value)) or _valid_bean_via(value)
            ):
                raise CatalogError(
                    f"loading catalog {catalog.source}: `{entry['method']}` captures "
                    f"`{field}: {value!r}` — a channel name reads `argN` or "
                    f"`{{{_BEAN_VIA}: argN}}` (spec 2026-09-21 §4, §5)"
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
        # A composed field is written into the same running dict at derive
        # time (spec 2026-09-21 §4's `compose:`), so it is a declared capture
        # for this check exactly as a step's own would be.
        if entry.get("compose") is not None:
            fields.add(entry["compose"][0])
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


def _valid_bean_via(value: Any) -> bool:
    """Whether a capture value is exactly `{bean_via: argN}` (spec 2026-09-21
    §4) — the shape `_resolve_captures` holds as a bean reference and
    `_fold_bean_captures` resolves."""
    return (
        isinstance(value, dict)
        and set(value) == {_BEAN_VIA}
        and _ARG_REFERENCE.match(str(value[_BEAN_VIA])) is not None
    )


def _validated_direction(root: dict[str, Any], catalog: Catalog) -> str | None:
    """A root's own `direction:` (spec 2026-09-21 §4), checked against D00's
    closed set exactly as `single_call` checks a `methods` row's — or None for
    the root that declares none and keeps the catalog's."""
    direction = root.get("direction")
    if direction is not None and direction not in _DIRECTIONS:
        raise CatalogError(
            f"loading catalog {catalog.source}: root `{root['method']}` declares "
            f"`direction: {direction}`, which is not one of {', '.join(_DIRECTIONS)} "
            f"— D00's closed sets are closed (NFR-5)"
        )
    return None if direction is None else str(direction)


def _validated_compose(
    root: dict[str, Any], catalog: Catalog
) -> tuple[str, tuple[str, ...], str] | None:
    """A root's `compose:` as `(field, halves, join)` (spec 2026-09-21 §4):
    exactly one field naming a non-empty list of halves, beside a `join`
    string — or None for the root that declares none. Refused otherwise,
    because a malformed composition would derive `path` NULL on every chain
    from the root with nothing saying why."""
    compose = root.get("compose")
    if compose is None:
        return None
    fields = [key for key in compose if key != "join"] if isinstance(compose, dict) else []
    halves = compose.get(fields[0]) if len(fields) == 1 else None
    if (
        halves is None
        or not isinstance(compose.get("join"), str)
        or not isinstance(halves, list)
        or not halves
        or not all(isinstance(half, str) for half in halves)
    ):
        raise CatalogError(
            f"loading catalog {catalog.source}: root `{root['method']}` declares "
            f"`compose: {compose!r}`, which must be `{{<field>: [half, …], join: str}}` "
            f"exactly (spec 2026-09-21 §4)"
        )
    return str(fields[0]), tuple(str(half) for half in halves), str(compose["join"])


def _validated_method_annotation(
    root: dict[str, Any], catalog: Catalog
) -> tuple[str, str, str] | None:
    """A root's `method_annotation:` as `(annotation descriptor, arg, into)`
    (spec 2026-09-21 §4): the constructing method's own annotation, the
    attribute to read and the capture field it fills — exactly those three
    strings, or None for the root that declares none. `annotation` is
    converted to the SCIP form the annotation index is keyed in, once here."""
    declared = root.get("method_annotation")
    if declared is None:
        return None
    if (
        not isinstance(declared, dict)
        or set(declared) != {"annotation", "arg", "into"}
        or not all(isinstance(declared[key], str) and declared[key] for key in declared)
    ):
        raise CatalogError(
            f"loading catalog {catalog.source}: root `{root.get('method')}` declares "
            f"`method_annotation: {declared!r}`, which must be `{{annotation, arg, into}}` "
            f"exactly (spec 2026-09-21 §4)"
        )
    return _catalog_symbol(declared["annotation"]), declared["arg"], declared["into"]


def _method_annotation_capture(root: dict[str, Any], context: _ChainContext) -> dict[str, Any]:
    """The capture a root's `method_annotation` reads off the constructing
    method (spec 2026-09-21 §4): `{into: <string argument>}` where the method
    carries the annotation with that attribute as a string literal —
    `@ServiceActivator(inputChannel = "orders")` on the factory method that
    builds the outbound handler — and nothing at all otherwise. Absent is no
    claim: the chain then derives exactly as it would without the word."""
    if root["method_annotation"] is None:
        return {}
    annotation, arg, into = root["method_annotation"]
    for used, args in context.annotations.get(context.caller, []):
        if used == annotation and isinstance(args.get(arg), str):
            return {into: {"kind": "string", "value": args[arg]}}
    return {}


def _fold_bean_captures(captures: dict[str, Any], context: _ChainContext) -> None:
    """Replaces every captured value that is a bean REFERENCE (`_resolve_captures`'
    `bean_via` marker) with what the bean answers, in place (spec 2026-09-21
    §3a, §4): on `channel_link`, the bean's NAME as a string argument — the
    channel it is registered under, which is what a `read_by` edge names too;
    on any other field, the value the bean's own chain captured under that
    field (`_bean_chain_capture` — the container hop). A reference nothing
    resolves reads as the compiler's own `unresolved` kind, with the reason,
    which every downstream reader already answers as a read failure — and NOT
    as `_POISONED`: a bean the fold could not name is this setter's own
    failure, and a later `setOutputChannelName("x")` is the setter the
    framework honours, so it must be free to override it.

    One hop only: in the collecting context (`beans` None) a reference is not
    followed — the field is `_POISONED` there — and a container built in a
    third bean is unresolved (§4)."""
    for field, value in list(captures.items()):
        if not isinstance(value, dict) or value.get("kind") != _BEAN_VIA:
            continue
        if context.beans is None:
            # The second hop (§4): a statement about the chain, not a read
            # failure a later setter lifts — the container's own destination
            # lives in a third bean this walk does not reach.
            captures[field] = _POISONED
            continue
        if value.get("caller") != context.caller:
            captures[field] = _unresolved_bean("across_bodies")
            continue
        bean = _bean_reference(value.get("argument"), context)
        if isinstance(bean, Unresolved):
            captures[field] = _unresolved_bean(bean.reason)
        elif field in _CHANNEL_NAME_FIELDS:
            captures[field] = {"kind": "string", "value": bean.name}
        else:
            captures[field] = _bean_chain_capture(bean, field, context)


def _unresolved_bean(reason: str) -> dict[str, Any]:
    """The compiler's own `unresolved` shape (`_UNRESOLVED_ARGUMENT`), with the
    bean fold's reason — a fresh mapping, so `_fold` overwrites it as it does
    any read failure that is not a catalog poison."""
    return {"kind": "unresolved", "reason": f"bean_{reason}"}


def _bean_reference(
    argument: dict[str, Any] | None, context: _ChainContext
) -> BeanRef | Unresolved:
    """The bean one argument names (spec 2026-09-21 §3a), by the two shapes a
    reference takes in a factory method: the caller's own injected parameter —
    `{kind: parameter, value: i}`, read off the declared signature for its
    erased type, name and qualifier — or the RESULT of a direct call, in this
    same caller, to a declaring method (`bean_called`; the call's target joined
    to its symbol through `method_descriptor`, the same arithmetic every
    caller-to-callee join uses). Anything else — a field, a literal, a call to
    a method that declares no bean — is `none`. Only ever called with a bean
    table in hand (`_fold_bean_captures` answers the collecting context's
    case before reaching here); a context without one resolves nothing."""
    if context.beans is None or argument is None:
        return Unresolved("none")
    if argument.get("kind") == "parameter" and isinstance(argument.get("value"), int):
        index = int(argument["value"])
        parameters = context.facts.caller_parameters
        if index >= len(parameters):
            return Unresolved("none")
        declared = parameters[index]
        erased = declared.get("erased_symbol") or (declared.get("type") or {}).get("symbol")
        if not isinstance(erased, str):
            return Unresolved("none")
        name = declared.get("name")
        return context.beans.bean_of(
            Parameter(
                method=context.caller,
                index=index,
                erased_type=erased,
                name=str(name) if isinstance(name, str) else None,
                qualifier=qualifier_of(
                    list(declared.get("annotations") or []), context.catalog.bean_model
                ),
            )
        )
    source = argument.get("source")
    if source is None:
        return Unresolved("none")
    producer = next((site for site in context.sites if _chain_key(site) == source), None)
    if producer is None or producer.get("owner") is None or producer.get("descriptor") is None:
        return Unresolved("none")
    bare = method_descriptor(
        str(producer["owner"]), str(producer["name"]), str(producer["descriptor"])
    )
    full = context.method_symbols.get(bare)
    bean = context.beans.bean_called(full) if full is not None else None
    return bean if bean is not None else Unresolved("none")


def _bean_chain_capture(bean: BeanRef, field: str, context: _ChainContext) -> Any:
    """What a referenced bean's own chain captured under `field` (spec
    2026-09-21 §4's container hop): the bean's declaring method's sites,
    walked from each `beans:` root they hold with a fresh capture dict and a
    COLLECTING context — the same walk, the same steps and poisons, recording
    each chain end's captures instead of deriving — and the value under
    `field` where every end that captured one agrees. No declaring method, no
    root in it, no end capturing the field, or two ends disagreeing, is the
    `unresolved` kind with the reason: the adapter's destination is then unread
    (`path` NULL), never guessed from one of several containers' queues."""
    if bean.method is None:
        return _unresolved_bean("no_method")
    sites = context.by_caller.get(bare_descriptor(bean.method), [])
    by_receiver: dict[Any, list[dict[str, Any]]] = {}
    for site in sites:
        by_receiver.setdefault(site["receiver"], []).append(site)
    collected: list[dict[str, Any]] = []
    collecting = replace(
        context,
        caller=bean.method,
        sites=sites,
        by_receiver=by_receiver,
        facts=replace(
            context.facts,
            caller_call_sites=sites,
            caller_parameters=context.all_parameters.get(bean.method, ()),
        ),
        beans=None,
        collect=collected,
    )
    for site in sites:
        root = _matching_root(site, context.bean_roots)
        if root is None:
            continue
        captures = {
            **_prefix_captures(site, collecting),
            **_resolve_captures(root["captures"], site),
        }
        _fold_bean_captures(captures, collecting)
        _walk(site, captures, reached_terminal=False, context=collecting)
    values = [_literal_of(field, end, collecting) for end in collected if field in end]
    if not values:
        return _unresolved_bean("no_chain" if not collected else "field_uncaptured")
    if any(value != values[0] for value in values[1:]):
        return _unresolved_bean("chains_disagree")
    return values[0]


def _literal_of(field: str, end: dict[str, Any], context: _ChainContext) -> Any:
    """What one chain end of a referenced bean captured under `field`, READ IN
    THAT BEAN'S OWN METHOD (fix round 1, finding 1) and handed back as a
    literal-shaped argument carrying no value id: value ids are per method
    (D00 §5), so a `source` the container's chain captured must never reach
    the adapter's `_derive`, where the field ladder's getter join and the
    `channel_via` ladder would search the ADAPTER method's sites for it — a
    same-numbered value there is unrelated, and reading it fabricates.

    So the read `_derive` would do runs here, against the collecting
    context's own facts: the field ladder (`_address_read`), then for a
    destination the array read and the end's own `channel_via` ladder,
    exactly as `_derive` orders them. The answer is a `string`, an `array`
    whose elements are strings (an unreadable element stays an `unresolved`
    element, so the adapter's read degrades as `channels_of` always has), a
    catalog poison as itself, or `unresolved`."""
    value = end[field]
    if value is _POISONED:
        return _POISONED
    argument = _address_read(value, context)
    if field != "channel":
        text = _string_value(argument)
        return {"kind": "string", "value": text} if text is not None else _unresolved_bean("unread")
    found: Sequence[tuple[str | None, str | None, str]] = channels_of(argument)
    forms = end.get("channel_via") or []
    if found[0][2] != "resolved" and forms:
        # **The backward walk, in the COLLECTING context** (spec §2b, Task 9) — and the
        # context is the whole point of this function. `_captured_at` stamped the capture
        # with the site it was read at, which is a site of the method that COLLECTED it, so
        # the position resolved here is that method's and never the adapter's. Resolving it
        # in the adapter's context would read a same-numbered value of an unrelated method
        # and publish it as a destination; `test_a_same_numbered_value_in_the_ADAPTERS_
        # method_is_not_the_containers_queue` is the guard, and it was written before this
        # line changed for exactly that reason.
        found = _walked_channels(argument, context, forms) or found
    elements = [
        {"kind": "string", "value": path}
        if resolution == "resolved" and path is not None
        else _unresolved_bean("unread")
        for _, path, resolution in found
    ]
    return elements[0] if len(elements) == 1 else {"kind": "array", "elements": elements}


def _verb_fields(matches: dict[str, Any], catalog: Catalog) -> dict[tuple[str, str], str]:
    """`matches.verb_values.fields` as the table `static_field_value` reads (spec
    2026-10-26 §3a): the static fields that name a verb, `"<owner>#<field>": <verb>`, for a
    library whose builder is handed `HttpMethod.Put` as a `getstatic` and not a string.
    Empty for a catalog declaring none. A block holding anything but `fields`, or a key
    that is not one owner and one field, is a broken file (D02 §2's `fluent` style)."""
    declared = matches.get("verb_values", {})
    if not isinstance(declared, dict) or set(declared) - {"fields"}:
        raise CatalogError(
            f"loading catalog {catalog.source}: `verb_values` holds `fields` alone, got "
            f"{declared!r} (D02 §2's `fluent` style)"
        )
    fields = declared.get("fields", {})
    if not names_members(fields):
        raise CatalogError(
            f"loading catalog {catalog.source}: `verb_values.fields` is a mapping of "
            f"`<owner>#<field>` to a verb, got {fields!r} (D02 §2's `fluent` style)"
        )
    return member_table(fields)


def _undeclared_steps(
    matches: dict[str, Any], catalog: Catalog
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """`matches.undeclared_steps` as `(owners, poisons)` (spec 2026-09-21 §5:
    an undeclared member of a flow definition is a `divert`), both empty for
    a catalog declaring none. `owner` is one type or a list (§3.1), converted
    to SCIP form once here; `poisons` a non-empty list of field names,
    checked against the catalog's captures by `_validate_poisons`."""
    declared = matches.get("undeclared_steps")
    if declared is None:
        return (), ()
    poisons = declared.get("poisons") if isinstance(declared, dict) else None
    if (
        not isinstance(declared, dict)
        or set(declared) != {"owner", "poisons"}
        or not isinstance(poisons, list)
        or not poisons
        or not all(isinstance(field, str) for field in poisons)
    ):
        raise CatalogError(
            f"loading catalog {catalog.source}: `undeclared_steps` must be "
            f"`{{owner: <type|[types]>, poisons: [field, …]}}` exactly, got {declared!r} "
            f"(spec 2026-09-21 §5)"
        )
    owners = catalog_symbols(declared["owner"], f"{catalog.source}: undeclared_steps.owner")
    return owners, tuple(str(field) for field in poisons)


def _validate_poisons(
    roots: list[dict[str, Any]],
    steps: list[dict[str, Any]],
    undeclared_poisons: tuple[str, ...],
    catalog: Catalog,
) -> None:
    """Refuses a poison naming a field no root, step or composition of this
    catalog captures (spec 2026-09-21 §4's `poisons:`, on a step or under
    `undeclared_steps`): a field nobody captures cannot be made unreadable,
    so such a name is a typo the walk would carry silently as a key nothing
    reads. The same check also keeps a poison off the ladder keys
    (`channel_via`, `url_via`), whose readers iterate a list and cannot read
    a poison — the case `_step_captures`' guard-poisoning already had to
    step around."""
    captured: set[str] = set()
    for entry in (*roots, *steps):
        captured.update(field for field in entry["captures"] if field not in _VIA_KEYS)
        if entry.get("compose") is not None:
            captured.add(entry["compose"][0])
    declared: list[tuple[str, Any]] = [
        (step["method"], step["poisons"]) for step in steps if step["poisons"] is not None
    ]
    if undeclared_poisons:
        declared.append(("undeclared_steps", list(undeclared_poisons)))
    for where, poisons in declared:
        if not isinstance(poisons, list) or not all(isinstance(field, str) for field in poisons):
            raise CatalogError(
                f"loading catalog {catalog.source}: `{where}` declares `poisons: "
                f"{poisons!r}`, which must be a list of capture field names"
            )
        unknown = sorted(set(poisons) - captured)
        if unknown:
            raise CatalogError(
                f"loading catalog {catalog.source}: `{where}` declares `poisons` naming "
                f"`{'`, `'.join(unknown)}`, which no root or step of this catalog captures "
                f"(spec 2026-09-21 §4)"
            )


# The two linked-call ladders an entry may declare, each keyed to the capture
# it reads for: `channel_via` resolves `channel` (Task 12), `url_via` resolves
# `url` (A2 Task 8) — one grammar, `{owner, method, arg}`, two positions.
_VIA_KEYS = {"channel_via": "channel", "url_via": "url"}


def _merged_captures(entry: dict[str, Any]) -> dict[str, Any]:
    """An entry's own `captures` plus its `channel_via`/`url_via` ladder,
    when declared — folded into the SAME dict `_resolve_captures`/
    `_step_captures` already fold forward chain-wide, so a root's own
    `channel_via` forms travel alongside its `channel` capture through
    every later step exactly like `http_method`/`response_is` already do
    (neither is an `argN` position, so both take the same literal
    pass-through branch in `_resolve_captures`). Only ever called on an
    entry `_validate_channel_via_entries` already checked, at `run` start —
    `_channel_via_forms`'s own `_catalog_symbol` conversion is safe here."""
    captures = dict(entry.get("captures", {}))
    for key in _VIA_KEYS:
        if key in entry:
            captures[key] = _channel_via_forms(entry, key)
    return captures


def _validate_channel_via_entries(entries: list[dict[str, Any]], catalog: Catalog) -> None:
    """Refuses a broken `channel_via` or `url_via` ladder before any call
    site is matched, on the RAW (pre-`_catalog_symbol`) `roots`/`steps`
    entries — the same two-phase discipline `single_call._validate_methods`
    keeps for its own `channel_via` (shape checked here; `_channel_via_forms`'s
    symbol conversion only ever runs on an entry this already passed).
    A ladder without the capture it reads for (`channel_via` without
    `channel`, `url_via` without `url`) is missing the position it
    describes — the same `single_call` rule, `_merged_captures` never
    reaches it because this raises first."""
    for entry in entries:
        for key, field in _VIA_KEYS.items():
            # `url_via` reads ONE position: a URL is one string, where a topic
            # list is several — so `all_strings` is `channel_via`'s alone.
            arg_forms = 'int|"all_strings"' if key == "channel_via" else "int"
            for form in _channel_via_entries(entry, key):
                valid = (
                    isinstance(form, dict)
                    and isinstance(form.get("owner"), str)
                    and isinstance(form.get("method"), str)
                    and (
                        isinstance(form.get("arg"), int)
                        or (key == "channel_via" and form.get("arg") == "all_strings")
                    )
                    # `arity` is optional, and an int when declared: the linked
                    # call's argument count, which tells a one-string constructor from the
                    # four-argument constructor once owner and method agree.
                    and valid_via_arity(form)
                    # `descriptor` is optional too, and a string when declared: the
                    # linked call's whole JVM descriptor (spec 2026-09-21 §5), which
                    # tells `ContainerProperties(String...)` from `(Pattern)` where
                    # arity cannot — both take one argument.
                    and ("descriptor" not in form or isinstance(form["descriptor"], str))
                )
                if not valid:
                    raise CatalogError(
                        f"loading catalog {catalog.source}: `{entry.get('method')}` declares "
                        f"a `{key}` entry that must be `{{owner, method, arg: {arg_forms}, "
                        f"arity?: int, descriptor?: str}}`, "
                        f"got {form!r}"
                    )
            if key in entry and field not in entry.get("captures", {}):
                raise CatalogError(
                    f"loading catalog {catalog.source}: `{entry.get('method')}` declares "
                    f"`{key}` without a `{field}` capture — `{key}` says how to read an "
                    f"instance already named by `{field}`, never a position on its own "
                    f"(D02 §2's `fluent` style, mirroring single_call's own rule)"
                )


def _channel_via_entries(entry: dict[str, Any], key: str = "channel_via") -> list[Any]:
    """`channel_via`'s (or `url_via`'s — `key`) `{owner, method, arg}` |
    `[{...}, ...]` grammar, normalized to a list without touching the
    entries themselves — the `single_call`/`interface_implementation`
    precedent, shared in spirit rather than in code (this module owns its
    own root/step shape, never a `methods`/`registration` row)."""
    via = entry.get(key)
    if via is None:
        return []
    return via if isinstance(via, list) else [via]


def _channel_via_forms(entry: dict[str, Any], key: str = "channel_via") -> list[dict[str, Any]]:
    """`channel_via` (or `url_via` — `key`) entries, each declared `owner`
    converted to the SCIP symbol form once — only ever called on an entry
    `_validate_channel_via_entries` already passed, at `run` start."""
    return [
        {
            "owner": _catalog_symbol(form["owner"]),
            "method": form["method"],
            "arg": form["arg"],
            **({"arity": form["arity"]} if "arity" in form else {}),
            **({"descriptor": form["descriptor"]} if "descriptor" in form else {}),
        }
        for form in _channel_via_entries(entry, key)
    ]


def _terminal_index(
    entries: list[Any], catalog: Catalog
) -> tuple[set[str], dict[str, _JoinFilter | None]]:
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
    via_argument: dict[str, _JoinFilter | None] = {}
    for entry in entries:
        if isinstance(entry, str):
            plain.add(entry)
            continue
        marker = entry.get("terminal_via_argument")
        if not marker:
            plain.add(entry["method"])
            continue
        # `owner` may name SEVERAL types, and a scalar stays valid — the same widening
        # `matches.owner` already carries (§3.1). One library reaching a wire through two
        # clients is the ordinary case, not an exotic one: `SendMessageRequest` is handed
        # to `SqsClient` or to `SqsAsyncClient`, one builder chain, one address, two
        # receivers. Before this, two entries sharing a method name silently overwrote
        # each other in this dict and the FIRST one stopped deriving — which is how a
        # widening can remove coverage instead of adding it.
        # Spec 2026-09-21 §5's `continue: true`: only with an `{owner, method}`
        # marker — a bare `true` would continue the walk into ANY consumer of the
        # built value, a log statement included, which is the fabrication the
        # mapping form closes for the execute-join and would reopen here.
        continues = bool(entry.get("continue"))
        if continues and not isinstance(marker, dict):
            raise CatalogError(
                f"loading catalog {catalog.source}: terminal `{entry['method']}` declares "
                f"`continue: true` without an `{{owner, method}}` `terminal_via_argument` "
                f"naming the consumer to continue into (spec 2026-09-21 §5)"
            )
        via_argument[entry["method"]] = (
            _JoinFilter(
                owners=catalog_symbols(marker["owner"], "terminal_via_argument.owner"),
                methods=_method_names(marker["method"]),
                continues=continues,
            )
            if isinstance(marker, dict)
            else None
        )
    return plain, via_argument


def _validated_continuation(entry: dict[str, Any], catalog: Catalog) -> _JoinFilter | None:
    """A root's or step's `via_argument_of: {owner, method}` with `continue:
    true` (spec 2026-09-21 §5) as the continuing join, or None where the entry
    declares neither. The two go together: `via_argument_of` without
    `continue` would be an execute-join on a root, which `terminal_via_argument`
    already is, and `continue` without a consumer names nothing to continue
    into."""
    via = entry.get("via_argument_of")
    continues = entry.get("continue")
    if via is None and continues is None:
        return None
    if (
        continues is not True
        or not isinstance(via, dict)
        or set(via) != {"owner", "method"}
        or not isinstance(via["method"], str | list)
    ):
        raise CatalogError(
            f"loading catalog {catalog.source}: `{entry.get('method')}` declares "
            f"`via_argument_of: {via!r}` with `continue: {continues!r}` — the pair is "
            f"`via_argument_of: {{owner, method}}` with `continue: true` exactly "
            f"(spec 2026-09-21 §5)"
        )
    return _JoinFilter(
        owners=catalog_symbols(via["owner"], f"{catalog.source}: via_argument_of.owner"),
        methods=_method_names(via["method"]),
        continues=True,
    )


def _method_names(declared: Any) -> tuple[str, ...]:
    """`terminal_via_argument.method` as the executing call names it accepts: one name or
    a list of them (`[send, sendAsync]`), a scalar staying valid exactly as it does for
    `owner` (§3.1). An EMPTY list is refused rather than read as "joins to nothing" — a
    catalog that names no executing call has declared a terminal that can never be
    reached, and every chain on it would derive nothing with no error saying why."""
    if isinstance(declared, list):
        if not declared:
            raise CatalogError(
                "terminal_via_argument.method names an EMPTY list; name at least one method"
            )
        return tuple(str(name) for name in declared)
    return (str(declared),)


def _has_execute_join(
    site: dict[str, Any], sites: list[dict[str, Any]], join_filter: _JoinFilter | None
) -> bool:
    """Whether some row in this same caller carries an argument whose
    `source` names `site`'s own `result` — the OkHttp `build()` → `newCall()`
    split, joined through D00 §5's `arguments[].source` rather than through
    `receiver`/`result` chaining, because `newCall`'s own receiver is the
    client, not the request builder. `join_filter`, when the catalog
    declared one, additionally requires the joining row itself to be that
    exact owner+method — otherwise any consumer of the built value (a log
    statement, an equality check) would count as executing it.

    The value joined on is the row's CHAIN KEY (CP-3), not its `result`: a
    constructor's `result` is void and the constructed value's id is its
    `receiver`, which is what `execute`'s argument `source` names when the
    request is `new HttpPost("…")` handed straight over with no `build()`
    between — the Apache constructor form, a `<init>` root that is itself the
    terminal (A2 Task 8 fix round 1; reading `result` here made every such
    chain derive nothing). `_walk` and `_linked_constructor` already key a
    constructor the same way."""
    return bool(_consumers(site, sites, join_filter))


def _consumers(
    site: dict[str, Any], sites: list[dict[str, Any]], join_filter: _JoinFilter | None
) -> list[dict[str, Any]]:
    """The rows `_has_execute_join` asks after, themselves: every row in
    this caller carrying `site`'s chain key as an argument `source`, narrowed
    to the filter's owner+method where one is declared — in ordinal order,
    which is the walk's (NFR-1)."""
    result = _chain_key(site)
    if result is None:
        return []
    found: list[dict[str, Any]] = []
    for candidate in sites:
        if join_filter is not None and (
            candidate["owner"] not in join_filter.owners
            or candidate["name"] not in join_filter.methods
        ):
            continue
        if any(argument.get("source") == result for argument in candidate["arguments"]):
            found.append(candidate)
    return found


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
    left standing rather than replaced by a value nothing can interpret.

    A step's `poisons:` (spec 2026-09-21 §4) come first, under whichever of
    the three answers applies: the fields it names are unreadable from this
    step on whatever its captures did, and a step that both poisons and
    captures one field has the capture win, as an unguarded step's own
    last-wins would."""
    poisoned = dict.fromkeys(step.get("poisons") or (), _POISONED)
    when = step.get("when")
    if when is None:
        return {**poisoned, **_resolve_captures(step["captures"], site)}
    guard = _arg_at(site["arguments"], when["arg"])
    if guard is not None and guard.get("kind") == "string" and isinstance(guard.get("value"), str):
        if guard["value"] == when["equals"]:
            return {**poisoned, **_resolve_captures(step["captures"], site)}
        return poisoned
    return {
        **poisoned,
        **{
            field: _UNRESOLVED_ARGUMENT
            for field, value in step["captures"].items()
            if _reads_an_argument(field, value)
        },
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
        if _valid_bean_via(value):
            # Spec 2026-09-21 §4: the argument is a bean REFERENCE. Held with
            # the site's own caller until `_fold_bean_captures` resolves it —
            # a `parameter` argument is an index into THAT method's signature,
            # and a marker folded up out of a lambda body would otherwise be
            # read against the enclosing method's.
            resolved[field] = {
                "kind": _BEAN_VIA,
                "argument": _arg_at(site["arguments"], _arg_index(value[_BEAN_VIA])),
                "caller": site["caller"],
            }
        elif _reads_an_argument(field, value):
            slot = _arg_index(value)
            read = _own_parameter(_arg_at(site["arguments"], slot), site)
            # No slot, nothing to name: `_arg_index` answers None for a capture that is
            # not a positional read, and a position the walk cannot be told is one it must
            # not be asked about.
            resolved[field] = read if slot is None else _captured_at(read, site, slot)
        else:
            resolved[field] = value
    return resolved


def _captured_at(
    argument: dict[str, Any] | None, site: dict[str, Any], slot: int
) -> dict[str, Any] | None:
    """The site and slot a capture was READ AT, carried with the capture (Task 9).

    **The walk names a position by `(caller, ordinal, slot)`** — `values._of_site` builds
    exactly that origin — and the ordinal is not decoration: `values._used_at` reads it as
    "where a value is USED", which is what bounds the `escapes` window. A capture folds up
    out of a chain and loses the site it came from, so without this a hop could only be
    resolved with no ordinal at all, and `_through` reads that as the whole tail of the
    method: every value's escape window widens and destinations that resolve today answer
    `escapes` instead.

    Carried ON the argument rather than beside it because a capture travels through
    `_fold`, `_fold_lambda_captures` and `_fold_bean_captures` as a single value; anything
    kept alongside would have to be folded in step with it, in four places, and the first
    one missed would be silent.

    Every reader of these arguments selects the keys it wants (`kind`, `value`, `source`,
    `elements`), so an extra key travels harmlessly — the same way `_own_parameter`'s
    `caller` already does.
    """
    if argument is None:
        return None
    return {**argument, _CAPTURED_AT: (site["caller"], site["ordinal"], slot)}


def _own_parameter(argument: dict[str, Any] | None, site: dict[str, Any]) -> dict[str, Any] | None:
    """A `parameter`-kind argument with the site's own caller beside it (spec
    2026-09-21 §3c: a destination handed in as the constructing method's
    `@Value` parameter reads its expression through the field ladder's rung
    2a, which needs the declaration the index is an index INTO). The same
    discipline as the `bean_via` marker above, for the same reason: captures
    fold up out of lambda bodies, and a lambda's `parameter 1` is a captured
    variable of ITS signature — read against the enclosing method's it would
    fabricate that method's expression. Every other kind travels untouched."""
    if argument is None:
        return None
    if argument.get("kind") == "array":
        # Each element of a varargs slot is read on its own (`_address_read`),
        # so each parameter among them carries the caller too.
        return {
            **argument,
            "elements": [
                _own_parameter(element, site) for element in argument.get("elements") or []
            ],
        }
    if argument.get("kind") != "parameter":
        return argument
    return {**argument, "caller": site["caller"]}


def _reads_an_argument(field: str, value: Any) -> bool:
    """Whether one declared capture addresses a call-site position rather than
    stating a value. Spelled once because `_resolve_captures` and
    `_step_captures`'s guard-poisoning must agree exactly: a field poisoned in
    one and read as a literal in the other would write the poison mapping
    itself into the `method` column.

    An address field always does; any other field does exactly when its
    value is spelled `argN` (the comment above `_HANDLER_NONE` has the
    history) — no literal a catalog states on those fields is spelled that
    way, and a list (`channel_via`'s forms) or a mapping (`{bean_via: …}`)
    never matches the pattern."""
    return field in _ARGUMENT_FIELDS or _ARG_REFERENCE.match(str(value)) is not None


def _arg_index(value: Any) -> int | None:
    match = _ARG_REFERENCE.match(str(value))
    return int(match.group(1)) if match else None
