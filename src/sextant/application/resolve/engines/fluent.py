"""fluent engine for endpoint derivation (D02 §2's `fluent` style).

No single call carries the declaration here — the request is assembled
across several calls on a builder, so the derivation is a walk over one
caller's own `call_sites` (`shapes/chains.py`, which documents the walk:
roots, steps, terminals, the backward prefix). This engine turns each
executable chain's end the walk yields into its endpoint row — one endpoint
per path that ever reached a terminal; a chain that never reaches a terminal
derives nothing (D02 §4's "the true answer").

Shares `argument_descriptor`, `url_of` and `supertypes_of` verbatim with
`single_call` (`shapes.arguments`) — the same D00 §5 argument grammar,
resolved here off a captured step argument rather than a `methods` row's
positional slot.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.shapes.arguments import (
    QUERY_KIND,
    CallFacts,
    CarrierRules,
    FieldFacts,
    _address_read,
    _arg_at,
    _capture_resolved,
    _string_value,
    _walked_channels,
    _walked_with,
    argument_descriptor,
    call_site_index,
    carries_expression,
    channels_of,
    declared_parameters_of,
    field_facts,
    query_entries,
    split_url,
    supertypes_of,
    url_of,
    with_authority,
)
from sextant.application.resolve.shapes.chains import (
    _COLLECTED,
    _COMPOSE,
    _DIRECTION,
    _EXECUTED_BY,
    _LINK_SENDER,
    _READS_LINK,
    _UNRESOLVED_ARGUMENT,
    ChainEnd,
    _captured_at,
    _declared_entries,
    _method_symbols,
    _resolves_beans,
    chain_ends,
)
from sextant.application.resolve.shapes.client_base import against_client_base, client_base_of
from sextant.application.resolve.shapes.expansion import _enum_symbols, _rules_of
from sextant.application.resolve.shapes.member_values import (
    member_table,
    names_members,
    static_field_value,
)
from sextant.application.resolve.shapes.rooting import _catalog_symbol
from sextant.application.resolve.values import (
    EXPRESSION,
    LITERAL,
    STRING,
    Answer,
    ValueIndex,
    cached_value_index,
)
from sextant.domain.closed_sets import Direction, Resolution
from sextant.domain.paths import canonical_http_path, serves_urls
from sextant.domain.redaction import REDACTED, Redactor

# D00 §5's kind for an address the code ASSEMBLES. Spelled here because `_url_argument`
# treats it as the catalog's own declared position rather than as a hop - see there.
_CONCAT = "concat"

# The `read_by` end of the channel edge (spec 2026-09-21 §3b). The names the channel
# index already holds under it are read for the bean fold's name rung by
# `beans.known_channels`.
_READ_BY = "read_by"
# The edge's third role (§3b's reserved slot), and its first writer (fix round
# 1, finding 3): a `channel_link` captured AFTER a handler is that handler's
# OUTPUT channel, not the wire's feed.
_SENDS_TO = "sends_to"

_DIRECTIONS = sorted(member.value for member in Direction)

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
    (`_own_method`, `_address_read`).

    The walk is `shapes.chains.chain_ends`, which validates and reads the chain's own
    keys; this engine checks its own words first — a root's `direction:`, the
    `url`/`channel` exclusivity, `verb_values`, `client_base` — and derives from each
    end the walk yields."""
    matches = catalog.matches
    roots, bean_roots, steps = _declared_entries(catalog)
    for root in matches.get("roots", []):
        _validated_direction(root, catalog)
    _validate_url_channel_exclusivity([*roots, *bean_roots], steps, catalog)
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
    supertypes = workspace.once(supertypes_of)
    # Read once per run, the same `_rules_of`/`_enum_symbols` precedent —
    # None for a catalog declaring no `field_sources` block, which is exactly
    # what keeps such a catalog's rows what they were before 2F.
    field_sources = field_facts(workspace, catalog)
    by_caller = workspace.once(call_site_index).by_caller
    # The method symbols a `handler` capture joins a lambda's bare body name to
    # (spec 2026-09-21 §3c), read where the walk reads them (`chain_ends`) and
    # shared with it through `Workspace.once`.
    method_symbols: dict[str, str] = {}
    if _resolves_beans(roots, bean_roots, steps) or any(
        "handler" in entry["captures"] for entry in (*roots, *steps)
    ):
        method_symbols = workspace.once(_method_symbols)
    # A list, not a set — NFR-1, the same reason single_call's own
    # `referenced` accumulator is one.
    referenced: list[str] = []
    walk_index = cached_value_index(workspace)
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
    context: _DeriveContext | None = None
    for end in chain_ends(workspace, catalog):
        # Ends arrive caller by caller, so the caller's own facts are built once per
        # caller, as the walk builds its own.
        if context is None or context.caller != end.caller:
            context = _DeriveContext(
                workspace=workspace,
                values=walk_index,
                caller=end.caller,
                catalog=catalog,
                facts=CallFacts(
                    supertypes=supertypes,
                    caller_call_sites=by_caller[end.caller],
                    referenced=referenced,
                    # `OI-77`, the same fix `single_call` takes: a body handed straight
                    # through from the caller's own signature names its type there and
                    # nowhere else.
                    caller_parameters=caller_parameters.get(end.caller, ()),
                    sites_by_caller=by_caller,
                    parameters_by_caller=caller_parameters,
                ),
                carrier_rules=carrier_rules,
                field_sources=field_sources,
                rows=rows,
                seen=seen,
                metadata=metadata,
                method_symbols=method_symbols,
                bindings=bindings,
                verb_fields=verb_fields,
                client_base=client_base,
            )
        _derive(end, context)

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


@dataclass(frozen=True)
class _DeriveContext:
    """Everything deriving one caller's chain ends shares — the endpoint half of what the
    walk's own context held before the walk moved to `shapes/chains.py`."""

    caller: str
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
    # Spec 2026-09-21 §3c: the module's method symbols by bare descriptor, what a
    # captured `handler` lambda's body name is joined to — empty for a catalog declaring
    # no `handler` capture, which never reads it.
    method_symbols: dict[str, str]
    # §3b: the `fed_by` edges this run's chains wrote, one per chain that captured a
    # readable `channel_link`; inserted once by `run`, the `rows` discipline.
    bindings: list[dict[str, Any]]
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
    # The workspace and the walk's index, for the hop ladders (Task 9), shared with the
    # walk (`values.cached_value_index`).
    workspace: "Workspace | None" = None
    values: "ValueIndex | None" = None


def _derive(end: ChainEnd, context: "_DeriveContext") -> None:
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
    captures = dict(end.captures)
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
    context: _DeriveContext,
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
    context: "_DeriveContext",
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


def _one_assembled(
    assembled: "Sequence[tuple[str | None, str | None, str]]",
) -> dict[str, Any] | None:
    """The one address the assembled answers agree on, as an argument `url_of` reads — or
    None where there is none or several."""
    whole = {
        literal for _, literal, resolution in assembled if resolution == "resolved" and literal
    }
    if len(whole) == 1:
        return {"kind": "string", "value": whole.pop()}
    # A partly-known address, published as the EXPRESSION kind `url_of` reads: the
    # text is the template with its holes, and `url_of` decides peer and path from
    # it exactly as it does for `single_call`. Only where there is one — several
    # answers are several rows, which this engine's one-argument return cannot carry
    # (`OI-134`'s shape), so it leaves the capture as it was rather than choosing.
    partly = {
        literal for _, literal, resolution in assembled if resolution == "partial" and literal
    }
    if not whole and len(partly) == 1:
        return {"kind": EXPRESSION, "value": partly.pop()}
    return None


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
    # A NARROWED answer is one branch of several (ruling 7) and is never the one address
    # this arm hands on — whole or partly read, so it is told apart from both here.
    if answer.narrowed and (
        answer.kind == EXPRESSION or (answer.kind == LITERAL and answer.literal_kind == STRING)
    ):
        return None, str(answer.value), str(Resolution.NARROWED)
    if answer.kind == LITERAL and answer.literal_kind == STRING:
        return None, str(answer.value), str(Resolution.RESOLVED)
    if answer.kind == EXPRESSION:
        return None, str(answer.value), str(Resolution.PARTIAL)
    return None, None, str(Resolution.UNRESOLVED)


def _composed_address(
    captures: dict[str, Any], context: _DeriveContext
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
    context: _DeriveContext,
) -> tuple[str | None, str | None, str]:
    """`address` where the catalog says a relative address is relative to a base the
    executing CLIENT holds (`client_base`, spec 2026-10-26 §3c): Ktor joins
    `get("relative/path")` onto the client's `defaultRequest` base (CP-54 rows 51-56). A
    client with no declared base is not assumed to send to `http://localhost` (rows 50, 57):
    absence cannot be proven from the bytecode, so its relative call stays unresolved.

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
    client = _client_of(captures, context)
    # The decision is the shared one (`shapes.client_base.against_client_base`), which
    # `single_call`'s WebSocket and SSE rows make too. A configuration base (`${pricing.url}`)
    # comes back rendered exactly as a `base` capture fed by configuration is
    # (`_composed_address`: `base + path`, the two concatenated as written, peer NULL; the
    # `${billing.url}/invoices` pins) — and `partial`, never joined.
    joined, resolution = against_client_base(
        context.workspace, context.values, client, context.client_base, path
    )
    if resolution != str(Resolution.RESOLVED):
        return None, joined, resolution
    return _address_of(joined)


def _client_of(captures: dict[str, Any], context: _DeriveContext) -> dict[str, Any] | None:
    """The client the chain's request is issued on (spec 2026-10-26 §3c): the executing
    call's `client_base.client_arg` argument, stamped with where it was read — Ktor's
    `HttpStatement(builder, client)`. None for a catalog not declaring `client_base`, and
    for a chain the walk held no executing call for (`chains._hold_executing_call`: it
    reached its terminal through no argument join, or through one with two executing
    calls, whose clients would be two)."""
    executing = captures.get(_EXECUTED_BY)
    if context.client_base is None or executing is None:
        return None
    slot = int(context.client_base["client_arg"])
    return _captured_at(_arg_at(executing["arguments"], slot), executing, slot)


def _url_argument(captures: dict[str, Any], context: _DeriveContext) -> dict[str, Any] | None:
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
            address = _one_assembled(assembled)
            # **Several branch literals are several rows, and this engine carries ONE**
            # (`OI-134`). The walk may never take an answer away: before ruling 7 a branch
            # between literals was an unfilled hole, and the template it left — `/x{}` at
            # `partial` — is what this arm published. Read that again rather than nothing.
            if address is None and any(
                resolution == str(Resolution.NARROWED) for _, _, resolution in assembled
            ):
                unbranched = _walked_with(
                    argument, context, (), reader=_assembled_text, branches=False
                )
                address = None if unbranched is None else _one_assembled(unbranched)
            if address is not None:
                return address
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
    halves: tuple[str, ...], join: str, captures: dict[str, Any], context: _DeriveContext
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
