"""single_call engine for endpoint derivation (D02 §2's `single_call` style).

One call carries the whole outbound declaration — a `RestTemplate.postForObject`,
a `.exchange` — so this pass reads `call_sites` directly rather than joining
annotation facts: it matches each site against the catalog's declared
`methods` by name, resolves the verb (a literal or an `enum` argument's own
symbol), splits the url argument into peer and path (CP-2) — or, for a
`channel_arg` destination, keeps it whole and peerless — and resolves the
request/response descriptors from the call's own arguments through
`shapes.arguments.argument_descriptor` (D02 §2h). Framework knowledge — the
owner type, which argument is which, the PTR/call-wrapper rules — arrives as
catalog data; this module never names a framework.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.shapes.arguments import (
    CallFacts,
    CarrierRules,
    FieldFacts,
    _arg_at,
    _bare_reference,
    _capture_resolved,
    _linked_constructor,
    address_argument,
    argument_descriptor,
    channel_of,
    channels_of,
    declared_parameters_of,
    field_facts,
    linked_channels,
    parameter_index,
    peer_of,
    supertypes_of,
    url_of,
)
from sextant.application.resolve.shapes.contracts import _payload_descriptor
from sextant.application.resolve.shapes.expansion import _enum_symbols, _rules_of
from sextant.application.resolve.shapes.rooting import (
    _catalog_symbol,
    catalog_symbols,
    names_a_type,
)
from sextant.domain.closed_sets import Direction
from sextant.domain.paths import canonical_http_path, serves_urls
from sextant.domain.symbols import bare_descriptor, member_name, owner_of, parameter_types

_DIRECTIONS = sorted(member.value for member in Direction)

# 2I design §4, form 1's catalog key — spelled once because the run loop tests
# for it, normalizes it and reads it.
_IDENTITY = "path_from_argument_type"

# The keys form 1 may carry, split by whether the rule means anything without
# them. `arg` is the position handed over, `annotation` the type-level
# annotation carrying the identity, `name_from` the attribute holding the
# name; `qualifier_from` and `format` are the optional PAIR that scopes it.
_IDENTITY_REQUIRED = frozenset({"arg", "annotation", "name_from"})
_IDENTITY_OPTIONAL = frozenset({"qualifier_from", "format"})

# How a scope composes with the name it qualifies (2I design §2, word 1's own
# closed vocabulary, restated for the rule that reads a scope off a TYPE's
# annotation rather than off a declaration's). One word today, and the same
# word: `{scope}name`, one bracketed token with no separator equivalent.
_IDENTITY_FORMATS = frozenset({"qname"})

# 2I design §4, form 2's catalog key and its two required parts.
_DEFAULT_ADDRESS = "default_address"
_DEFAULT_ADDRESS_KEYS = frozenset({"method", "arg"})

# 2O Task 7's PAIRED destination (D02 §2's single_call style). Some protocols
# name a destination with TWO values at the call, neither of which is the
# identity on its own — AMQP's wire identity is the exchange AND the routing
# key, and a row publishing either alone names a different destination from
# the one the call reaches. `address_arg_2` is the second capture's position,
# declared on the row beside `channel_arg`; `address_separator` is the single
# character the framework's own rendering of the pair puts between them, and
# it is CATALOG data rather than row data because how a protocol spells its
# composite identity is a property of the protocol, not of one overload.
_ADDRESS_ARG_2 = "address_arg_2"
_ADDRESS_SEPARATOR = "address_separator"

# 2O Task 7 review, Critical 1: the OVERLOAD DISCRIMINATOR. `name` + `arity`
# cannot tell `convertAndSend(String routingKey, Object message)` from
# `convertAndSend(Object message, MessagePostProcessor after)` — both are
# `convertAndSend` at arity 2 on the same owner — so a row declaring an
# address position read the SECOND call's payload as its destination. The
# call site already carries the one value that separates them, the target's
# own erased JVM descriptor (`storage/duckdb/schema.sql:243`, projected onto
# every `call_sites` row), and a row declaring `descriptor` is matched on it
# exactly.
_DESCRIPTOR = "descriptor"


def run(workspace: Workspace, catalog: Catalog) -> None:
    """Derives one endpoint row per matching call site, via `call_endpoints`
    — a parameterised insert-if-absent on the same wire identity every other
    style uses (D02 §5). `caller` is the calling method symbol, unless the
    matched row's own `direction` is `inbound`, in which case it lands in
    `handler` instead (D02 §2); `peer` is NULL unless the row declares
    `url_arg` and that argument is itself an absolute URL (CP-2) — a
    `channel_arg` destination is never split, so its `peer` is always NULL;
    `method` is NULL where the verb itself
    could not be read (I2) or the row is verbless by declaration; `protocol`
    is the catalog's own declared field, exactly as `annotation_driven`
    forwards it, and `direction` is the catalog's own declared field unless
    the matched row overrides it."""
    matches = catalog.matches
    # A catalog may name ONE library under several names (§3.1): `JmsTemplate`
    # and the `JmsOperations` interface a codebase more often declares its field
    # as, or a type under its old package. A scalar stays valid and every shipped
    # catalog still writes one, so this is a widening rather than a migration.
    owners = catalog_symbols(matches["owner"], f"{catalog.source}: matches.owner")
    # A list, not a dict-by-name (Task 6): `arity` lets two rows share a
    # `name` — `send(topic, payload)` and `send(topic, key, payload)` — and a
    # dict keyed by name would let the second overwrite the first.
    # `_matching_method` scans it per call site instead.
    methods = list(matches["methods"])
    _validate_methods(methods, catalog)
    # Read once per run, beside `_validate_methods`, because it is checked
    # against the rows: a separator with no paired row, or a paired row with
    # no separator, is a file that cannot be honoured either way.
    address_separator = _address_separator(matches, methods, catalog)
    # `channel_via`'s declared `owner`s converted to the SCIP symbol form
    # once, at run start, rather than once per matched call site — the
    # `record_wrapper_args` precedent below, and the same binding-seam
    # discipline `call_wrappers`/`record_wrappers` keep. A copied row, never
    # the catalog's own dict: `matches` is the loaded file, and a normalizing
    # pass must not rewrite it in place.
    methods = [
        {**row, "channel_via": _channel_via_forms(row)} if "channel_via" in row else row
        for row in methods
    ]
    # 2I design §4, form 1: the identity rule's declared annotation converted
    # to the SCIP symbol form once, at run start — the `channel_via` treatment
    # above, and the same binding-seam discipline.
    methods = [
        {
            **row,
            _IDENTITY: {
                **row[_IDENTITY],
                # A LIST or a scalar (§3.1). `annotations` plural, so a consumer
                # still doing a single dict lookup fails rather than looking up a
                # tuple and finding nothing. This key is NOT one of F2 §3.1's
                # twenty-one — the design's list missed it, the same way it missed
                # `matches.steps[].owner` — and it is the one the javax/jakarta
                # SOAP gap needed: `spring-ws-template.yml` reads the operation
                # off `@XmlRootElement`, which moved packages, and a codebase on
                # the old spelling got a SOAP endpoint with no operation on it
                # (W11, `scripts/probes/w11_javax_jakarta.md` finding 3).
                "annotations": catalog_symbols(
                    row[_IDENTITY]["annotation"],
                    f"{catalog.source}: {_IDENTITY}.annotation",
                ),
            },
        }
        if _IDENTITY in row
        else row
        for row in methods
    ]
    # 2I design §4, form 2: how this client type is CONFIGURED with the
    # address its address-less calls use. Catalog-level rather than per-row
    # because it describes the owner, not one of its methods.
    default_address = _default_address(matches, catalog)
    record_wrappers = list(matches.get("record_wrappers", []))
    _validate_record_wrappers(record_wrappers, catalog)
    carrier_rules = CarrierRules(
        rules=_rules_of(catalog),
        enums=_enum_symbols(workspace),
        type_carriers=tuple(_catalog_symbol(t) for t in matches.get("type_carriers", [])),
        call_wrappers={
            _catalog_symbol(wrapper["type"]): wrapper["payload_ctor_arg"]
            for wrapper in matches.get("call_wrappers", [])
        },
    )
    # `record_arg`'s own lookup (D02 §2, Task 7): the record's type keys a
    # `(channel_ctor_arg, payload_ctor_arg)` pair, converted once here rather
    # than per call site, exactly as `call_wrappers` above is.
    record_wrapper_args = {
        _catalog_symbol(wrapper["type"]): (wrapper["channel_ctor_arg"], wrapper["payload_ctor_arg"])
        for wrapper in record_wrappers
    }
    supertypes = supertypes_of(workspace)
    # Read once per run, the same `_rules_of`/`_enum_symbols` precedent (2F
    # design §4) — None for a catalog declaring no `field_sources` block, in
    # which case no address argument ever consults the field ladder.
    field_sources = field_facts(workspace, catalog)
    # `OI-77`. Read once per run beside `field_sources`, and separately from it: a catalog
    # with no `field_sources` block gets `None` above, and a payload handed through from
    # the caller's signature has nothing to do with the field ladder.
    caller_parameters = declared_parameters_of(workspace)
    # `arguments` is parsed once, here, rather than once per reader: the
    # `call_sites` query returns it as raw JSON text, and both the matching
    # loop below and the `call_wrappers` one-hop (over a *different* call
    # site's own arguments, `contracts._linked_constructor`) need the parsed
    # list, never the text.
    call_sites = [
        {**site, "arguments": json.loads(str(site["arguments"]))}
        for site in workspace.query("call_sites")
    ]
    by_caller: dict[str, list[dict[str, Any]]] = {}
    for site in call_sites:
        by_caller.setdefault(str(site["caller"]), []).append(site)
    # Both read once per run, the `field_facts`/`_rules_of` precedent, and
    # both empty-and-inert for every catalog declaring neither word.
    identity_facts = (
        _identity_facts(workspace) if any(_IDENTITY in row for row in methods) else None
    )

    # A list, not a set: the order call sites reach a shape decides the
    # order shape rows are written (NFR-1) — the same discipline
    # derive_endpoint_shapes keeps for its own `referenced` accumulator.
    referenced: list[str] = []
    configured_addresses = _configured_addresses(
        owners, default_address, call_sites, by_caller, field_sources, supertypes
    )
    rows: list[dict[str, Any]] = []
    # Only a row whose identity is known dedups here: two calls whose paths
    # nobody could read carry nothing to compare, and SQL's `NULL = NULL` is
    # unknown rather than true, so each stays its own row (D02 §2's
    # unresolved-is-an-answer). The key is the identity columns, never the
    # `resolution` column — a row can be `unresolved` because some OTHER
    # declared capture failed (I1) and still dedup on the path it did read.
    seen: set[tuple[str, str, str, str, str | None, str | None]] = set()
    for site in call_sites:
        if site["owner"] not in owners:
            continue
        arguments = site["arguments"]
        method = _matching_method(methods, site["name"], site[_DESCRIPTOR], arguments)
        if method is None:
            continue
        # A row declaring neither `http_method` nor `method_arg` is verbless
        # by declaration (D02 §2) — a topic has no verb. Its `verb` reads
        # None too (`_verb_of` finds neither key), but that must not read as
        # I2's "the verb could not be captured": `verbless` tells the two
        # apart wherever `verb is not None` alone would otherwise stand in
        # for "a verb was declared and read".
        verbless = "http_method" not in method and "method_arg" not in method
        # NULL rather than dropped (I2): a call site matching the catalog's
        # own `owner` and `methods` IS an outbound call, and a verb the
        # scanner could not read — an `HttpMethod` arriving as a parameter
        # rather than as an enum constant — is one capture failing, exactly
        # like an unreadable url. Dropping the row would make "this method
        # calls something over HTTP" disappear on the strength of the one
        # column nobody could fill; `method` NULL on an `unresolved` row
        # says it instead (D02 §2's unresolved-is-an-answer).
        verb = _verb_of(method, arguments)
        caller = str(site["caller"])
        facts = CallFacts(
            supertypes=supertypes,
            caller_call_sites=by_caller.get(caller, []),
            referenced=referenced,
            caller_parameters=caller_parameters.get(caller, ()),
        )
        if "record_arg" in method:
            # `record_arg` names an argument whose *linked constructor*
            # carries both identity and payload (D02 §2, Task 7) —
            # `send(ProducerRecord)`'s one argument is the record, not the
            # topic or the value. `_validate_methods` already refused a row
            # declaring `record_arg` alongside `url_arg`/`channel_arg`/
            # `body_arg`/`response_arg`, so this is the row's only source
            # for both.
            record = _arg_at(arguments, method["record_arg"])
            url_argument, body_argument = _record_arguments(record, record_wrapper_args, facts)
            # `record_arg` is always a declared position (the row is only
            # reached here because it has one) — always True, the same
            # sentinel a `body_arg` row's own presence check collapses to.
            body_declared = True
        else:
            # `channel_arg` is `url_arg`'s alias for a destination-shaped
            # identity (D02 §2) — `_validate_methods` already refused a row
            # declaring both, so at most one of the two is ever present
            # here.
            url_argument = _arg_at(arguments, method.get("url_arg", method.get("channel_arg")))
            body_argument = _arg_at(arguments, method.get("body_arg"))
            body_declared = method.get("body_arg") is not None
        # 2I design §4, form 2: a row that names no address position at all
        # takes the one this client type was CONFIGURED with — the address is
        # a property of the receiver, set once, and the call carrying none is
        # not a call without an address. Only where the catalog declares the
        # word AND the row names no position of its own: a declared position
        # is the call's own answer and always wins.
        configured = default_address is not None and not (
            {"url_arg", "channel_arg", "record_arg"} & method.keys()
        )
        if configured:
            declaring = _declaring_type(caller)
            url_argument = None if declaring is None else configured_addresses.get(declaring)
        address_declared = configured or bool({"url_arg", "channel_arg"} & method.keys())
        # `channel_arg` aliases `url_arg` in the grammar but not in the
        # READER (final review, IMPORTANT): a destination is an opaque
        # expression, never a URL to split. SQS's canonical destination is a
        # whole queue URL, and `url_of` would turn it into a fabricated peer
        # plus a truncated path. `_validate_methods` already refused a row
        # naming both, so this test is unambiguous.
        #
        # `channel_via` (Task 7) reads the destination off the call that
        # PRODUCED the argument instead of the argument's own position —
        # `session.createProducer(session.createQueue("raw-audit"))`'s topic
        # lives on `createQueue`'s own argument, never `createProducer`'s —
        # and it may read several channel identities off that one linked
        # call (`all_strings`). `linked_channels` always returns a list, so
        # this collapses to the same one-tuple list the non-`channel_via`
        # case builds by hand.
        #
        # The ladder is a LADDER, not an either/or (2E-prep Task 12 fix
        # round 1, unifying this with `interface_implementation`'s own
        # ladder, D02 §2's own new `channel_via` paragraph): a
        # `channel_via`-declared row still tries the
        # literal read FIRST, through the SAME reader (`channel_of`/`url_of`)
        # the non-`channel_via` branch below uses — some APIs genuinely
        # overload a destination-taking method with both a literal-string
        # and a linked-instance form — and only falls back to the linked
        # call when the literal itself did not resolve. Fixture-neutral for
        # every catalog shipped so far: `jakarta-jms.yml`/`kafka-consumer.yml`'s
        # own `channel_arg` positions are never themselves string literals
        # (a `Queue`/`Collection` instance, always linked), so the ladder's
        # first rung never fires there and every frozen row is unchanged.
        #
        # An address argument the scanner read as a FIELD (D00 §5, 2F) climbs
        # the field ladder first (`address_argument`, 2F design §4): where the
        # catalog's own `field_sources` block lets it name the configuration
        # expression behind that field, the argument is replaced by that
        # expression as a string literal, and every rung below — the literal
        # read, `channel_via`, CP-2's split — behaves exactly as it does for a
        # url written at the call site. Where it cannot, the argument is
        # untouched and this is the pre-2F path unchanged.
        url_argument = address_argument(url_argument, field_sources, facts, caller)
        destinations: Sequence[tuple[str | None, str | None, str]]
        read_destination = channel_of if "channel_arg" in method else url_of
        # 2I design §4, form 1: THE IDENTITY IS NOT AT THE CALL. Some
        # protocols name the operation on the payload rather than in the
        # address — the declared type of the argument the call hands over
        # carries it, on an annotation this catalog names. Where a row asks
        # for that, the address stops being an identity and becomes the peer
        # alone (`peer_of`), and the `path` it would have filled is the
        # identity's to fill instead. The two captures are independent: an
        # unreadable address still leaves the operation named, and an
        # unreadable operation still leaves the peer.
        identity_type: str | None = None
        if _IDENTITY in method:
            peer, address_resolution = peer_of(url_argument)
            path, identity_type = _argument_type_identity(
                arguments, method[_IDENTITY], caller, identity_facts
            )
            resolved = path is not None and (
                not address_declared or address_resolution == "resolved"
            )
            destinations = [(peer, path, "resolved" if resolved else "unresolved")]
        elif _ADDRESS_ARG_2 in method:
            # THE PAIRED DESTINATION. `_validate_methods` already refused this
            # row alongside `url_arg`, `record_arg` and `channel_via`, so the
            # first half is always `channel_arg`'s verbatim read and the
            # second is read the same way — a routing key is an opaque
            # destination fragment exactly as an exchange is, and CP-2's
            # peer/path split has nothing to say about either.
            destinations = [
                _paired_destination(
                    read_destination(url_argument),
                    address_argument(
                        _arg_at(arguments, method[_ADDRESS_ARG_2]), field_sources, facts, caller
                    ),
                    str(address_separator),
                )
            ]
        elif "channel_via" in method:
            literal = read_destination(url_argument)
            forms = method["channel_via"]
            if literal[2] != "resolved" and forms:
                destinations = linked_channels(url_argument, facts, forms)
            else:
                destinations = [literal]
        else:
            # A `channel_arg` slot may hold a whole ARRAY of destinations —
            # `addHandler(handler, String... paths)` registers one handler at
            # several dispatch paths in one call — and since extractor
            # capability 9.15 that array carries its own `elements` (2O Task
            # 13). `channels_of` reads them, one destination tuple per
            # registered path, and answers `channel_of`'s single verbatim
            # tuple for every slot that is not an array; the loop below
            # already mints one row per tuple.
            #
            # `url_arg` deliberately does NOT get the same treatment: an
            # address is one URL per call in every catalog shipped, no
            # `url_arg` position is varargs, and CP-2's peer/path split has no
            # meaning applied element-wise to an array nobody has measured.
            destinations = (
                channels_of(url_argument)
                if "channel_arg" in method
                else [read_destination(url_argument)]
            )
        response_argument = _arg_at(arguments, method.get("response_arg"))
        # `direction` on a row overrides the catalog's own declared
        # direction (D02 §2) — Pub/Sub's `subscribe` is inbound even inside
        # an otherwise outbound file.
        row_direction = method.get("direction", catalog.direction)
        # An inbound row's deriving method is the consumer, not the caller
        # (D02 §2): it lands in `handler`, and `caller` stays NULL — the
        # same handler/caller split `derive_endpoints.sql` keeps for the
        # annotation-driven styles, applied here per row rather than per
        # catalog.
        inbound = row_direction == "inbound"
        # Computed once, outside the destinations loop: neither depends on
        # `peer`/`path`/`url_resolution`, and `argument_descriptor` appends
        # to the shared `referenced` accumulator (deduped downstream,
        # `contracts.py`'s own `list(dict.fromkeys(...))`), so calling it
        # once per row rather than once per destination tuple keeps that
        # list from carrying the same shape root once per topic.
        request_shape = argument_descriptor(body_argument, facts, carrier_rules)
        # The identity rule already resolved the DECLARED type of the argument
        # handed over, so the payload is known even though the argument itself
        # is a bare `parameter` naming no value (`_UNREAD_KINDS`). Describing
        # it here rather than declaring `body_arg` beside the rule is what
        # keeps the row `resolved`: a declared `body_arg` over a parameter is
        # a capture that failed (I1), and it would fail on exactly the rows
        # whose payload this pass DID read.
        if request_shape is None and identity_type is not None:
            request_shape = _payload_descriptor(
                _bare_reference(identity_type), carrier_rules.rules, carrier_rules.enums, referenced
            )
        response_shape = argument_descriptor(response_argument, facts, carrier_rules)
        # One row per destination tuple (the same multi-topic precedent
        # `annotation_driven._derive_replies` already keeps for a listener's
        # declared reply destinations) — every row shares the same verb/body
        # /response captures; only the destination itself varies.
        for peer, path, url_resolution in destinations:
            # 2O design §8: identity is the URL the framework serves, so the
            # path is canonicalized HERE — before the dedup key below is built
            # from it, and before the row is written. `domain/paths.py` states
            # the rule, what it refuses to touch (a whole address, a
            # placeholder-bearing composition), and why the gate is INBOUND
            # `http` alone (ruling R8).
            #
            # `row_direction`, never `catalog.direction`: a `methods` row may
            # override its catalog's direction (above, and live vocabulary —
            # `jakarta-jms.yml` declares both in one file, `spring-pubsub.yml`
            # makes `subscribe` inbound inside an outbound catalog), and the
            # direction this row is WRITTEN with is the one R8 rules on. The
            # column below and the dedup key both read `row_direction`; a gate
            # reading anything else would answer about a different row than
            # the one being minted.
            if path is not None and serves_urls(catalog.protocol, row_direction):
                path = canonical_http_path(path)
            # Checkpoint ruling I1: any DECLARED capture that failed to
            # resolve drops the *row's* resolution, even when the url itself
            # read fine — `path` still carries the known template regardless
            # (it is the url's own answer, untouched by a body/response
            # capture's own failure), but a resolved row promises every
            # declared capture was read, not only the url. `path` stays
            # NULL-safe: this only ever narrows resolution from `resolved`
            # to `unresolved`, never the other way. A `record_arg` row's own
            # payload is exactly as "declared" as a `body_arg` row's
            # (`body_declared` stands in for either), so a linked
            # constructor whose payload slot could not be read narrows this
            # row's resolution the same way.
            resolution = (
                "resolved"
                if (verb is not None or verbless)
                and url_resolution == "resolved"
                # The descriptors are what these captures PRODUCED, and passing them is
                # what stops a row claiming a read failure over a column that was read
                # (`OI-77`, W43's review).
                and _capture_resolved(body_declared, body_argument, request_shape)
                and _capture_resolved(
                    method.get("response_arg") is not None, response_argument, response_shape
                )
                else "unresolved"
            )
            # Only a *whole* resolved wire identity dedups, so an unreadable
            # verb keeps each row its own for the same reason an unreadable
            # url does: `NULL = NULL` is unknown in the table this batch is
            # inserted into, and two calls whose verbs nobody could read are
            # not known to be the same call. A verbless row dedups on
            # `(protocol, row_direction, path)` alone — there is no method to
            # distinguish them by — hence `verb or ""` rather than `verb`:
            # every shipped HTTP row declares `http_method` or `method_arg`,
            # so `verbless` is always False and `verb` is never None
            # wherever this key is built for them, making `verb or ""` equal
            # to `verb` and this change a no-op for those catalogs; likewise
            # no shipped row declares its own `direction`, so `row_direction`
            # is always `catalog.direction` there too.
            if path is not None and (verb is not None or verbless):
                # F5 §6.1 rule 1 (W27 fix): `caller` and `peer` are IN the key. Without
                # them `seen` spans the whole module, so a second caller reaching one
                # path was dropped outright — measured on a two-caller probe, two hosts
                # (`alpha.internal`, `bravo.internal`) and one path derived ONE row with
                # `bravo` gone: no row, no peer, no gap, no question. That is the RC-5
                # defect W27 removed from the inbound/outbound merge, in this engine, and
                # with a worse failure mode — the merge at least carried the caller onto
                # the surviving row.
                #
                # "Collapse only within one caller, where both sides are observable"
                # (§6.1): one method calling one target twice is still one row, because
                # the caller and the peer are equal there.
                key = (catalog.protocol, row_direction, verb or "", path, caller, peer)
                if key in seen:
                    continue
                seen.add(key)
            rows.append(
                {
                    "protocol": catalog.protocol,
                    "direction": row_direction,
                    "method": verb,
                    "path": path,
                    "handler": caller if inbound else None,
                    "caller": None if inbound else caller,
                    "peer": peer,
                    "handler_signature": None,
                    "resolution": resolution,
                    "evidence": "compiler",
                    "catalog_id": catalog.id,
                    "request_shape": request_shape,
                    "response_shape": response_shape,
                    "consumes": None,
                    "produces": None,
                }
            )

    workspace.derive("call_endpoints", rows=rows)


def _matching_method(
    rows: list[dict[str, Any]], name: str, descriptor: Any, arguments: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """The one `methods` row matching a call site's own name, argument count
    (D02 §2's `arity`) and, where any candidate row declares one, the target's
    own JVM `descriptor` — first match wins. A row without `arity` matches
    every overload, which is what kept the 2C catalogs parsing unchanged when
    the key arrived. *No shipped catalog relies on that any more: every
    `matches.methods` row declares both `arity` and `descriptor` — 96 declared
    descriptors across the 14 catalogs that declare any, recounted by F2 §4.1's own
    collision sweep (this said "75 rows across the 55 shipped catalogs", which was
    stale in the count and wrong in the denominator: descriptors have never appeared
    in more than a quarter of the catalogs), and
    `tests/architecture/test_catalog_descriptor_coverage.py` is the ratchet that
    keeps it so. This sentence claimed the opposite until the 2O documentation
    sweep (`A-Mi13`). The ratchet reaches this grammar only; the other
    call-matching grammars are `A-Mi19`.* The permissive branch stays because a
    hand-built catalog in a test may still omit the key; a catalog that needs to
    tell `send(topic, payload)` from `send(topic, key, payload)` apart writes
    one row per arity instead, and
    this is the scan that replaces the old dict-by-name (`:40` before Task 6),
    which could only ever keep one row per name.

    **Arity alone cannot separate same-arity overloads, and where it cannot,
    an unmatched call derives NOTHING** (2O Task 7 review, Critical 1).
    `RabbitTemplate.convertAndSend` overloads at arity 2 as both
    `(String routingKey, Object message)` and `(Object message,
    MessagePostProcessor after)`; first-match-wins on name+arity handed the
    second call's PAYLOAD to a row declaring `channel_arg: 0`, publishing a
    message body as a destination at `resolved`/`compiler`. So once ANY
    candidate row for this name and arity declares `descriptor`, that arity is
    CLAIMED: a call whose own descriptor matches none of them falls through to
    no row at all rather than to a descriptor-less sibling, because falling
    through is exactly the fabrication the key exists to stop. The cost is a
    stated under-report — the unclaimed overloads derive nothing where they
    used to derive an `unresolved` row — which is §8's honest direction and a
    `docs/COVERAGE.md` boundary, not a silent miss.

    `descriptor`'s PARAMETER PORTION is compared against the call's own
    `target.descriptor` (`storage/duckdb/schema.sql:243`), which is the ERASED
    JVM descriptor: it discriminates the declared parameter types of an
    overload, never the payload's own type (`_IdentityFacts` below reads the
    caller's signature for that, and says why). *This said "compared verbatim"
    until F2 §4.1 — the return type is in the descriptor and is NOT part of
    method identity (JLS 8.4.2), and comparing it tied every row to a library
    version by accident.*"""
    candidates = [
        row for row in rows if row["name"] == name and row.get("arity") in (None, len(arguments))
    ]
    # PARAMETER TYPES only, not the whole descriptor (F2 §4.1, JLS 8.4.2). A method is
    # identified by its name and parameter types; the return type is in the JVM
    # descriptor and is not part of the signature. Comparing whole descriptors made
    # every row version-dependent by accident — a library changing a return type changes
    # nothing in its callers' source and the descriptor entirely, which is why every
    # Spring Kafka 2.x producer derived NOTHING: ten rows here declare
    # `CompletableFuture`, the 3.x return, and 2.x returns `ListenableFuture`.
    #
    # Measured before the change, over all 96 declared descriptors in the 14 catalogs
    # that declare any: dropping the return type creates **zero** collisions — no two
    # rows share a catalog, owner, name and parameter list while differing only in what
    # they return. A covariant-return bridge does put two such methods in one class
    # file, but call sites are disambiguated by OWNER, which is already part of this
    # match, and both are semantically one method because the bridge delegates.
    wanted = parameter_types(str(descriptor)) if descriptor is not None else None
    for row in candidates:
        if _DESCRIPTOR in row and parameter_types(str(row[_DESCRIPTOR])) == wanted:
            return row
    if any(_DESCRIPTOR in row for row in candidates):
        return None
    return candidates[0] if candidates else None


def _validate_methods(rows: list[dict[str, Any]], catalog: Catalog) -> None:
    """Refuses a broken `methods` row before any call site is matched — the
    `fluent._validate_steps` precedent: an unchecked value does not stay in
    the file (`ports/catalogs.py`'s own discipline), so this runs once, at
    `run` start, over every declared row, rather than lazily on whichever
    row a call site happens to reach first.

    `url_arg` and `channel_arg` name the same capture (D02 §2); a row
    declaring both is a broken catalog, not two pieces of evidence. A row's
    own `direction`, where declared, still has to be one of D00's closed
    Direction values — the catalog-level `direction` is checked at load time
    (`yaml_source.py`'s `_closed`), but a row's override lives inside
    `matches`, opaque to that loader-level check, so it is checked here
    instead. `record_arg` (Task 7) IS the channel+payload source — a row
    declaring it alongside `url_arg`/`channel_arg`/`body_arg`/`response_arg`
    is contradictory evidence, not a richer row. `channel_via` (Task 7's
    linked-call follow) says HOW to read an instance already named by
    `channel_arg` — it is not itself a position, so a row declaring it
    without one is missing the position it describes; each declared form
    must be `{owner, method, arg: int|"all_strings"}`, the same shape
    discipline `record_wrappers` entries keep.

    `channel_via` alongside `url_arg` is refused too (final review, minor
    10): `linked_channels` reads a linked call's own argument through
    `channel_of` — verbatim, `peer` unconditionally NULL — which is
    `channel_arg`'s reader, while `url_arg` asks for CP-2's peer/path split.
    A row declaring both asks for one destination to be read two
    incompatible ways depending on which rung of the ladder answered, and
    the ladder's own fallback would silently drop the split the row asked
    for. No shipped catalog declares the pair; this refuses the file rather
    than letting the contradiction pick a reader at derive time."""
    for row in rows:
        if "url_arg" in row and "channel_arg" in row:
            raise CatalogError(
                f"loading catalog {catalog.source}: `{row['name']}` declares both "
                f"`url_arg` and `channel_arg` — they name the same capture (D02 §2's "
                f"single_call style)"
            )
        if "channel_via" in row and "channel_arg" not in row and "url_arg" not in row:
            raise CatalogError(
                f"loading catalog {catalog.source}: `{row['name']}` declares `channel_via` "
                f"without `channel_arg`/`url_arg` — `channel_via` says how to read an "
                f"instance already named by one of those, never a destination position on "
                f"its own (D02 §2's single_call style)"
            )
        if "channel_via" in row and "url_arg" in row:
            raise CatalogError(
                f"loading catalog {catalog.source}: `{row['name']}` declares `channel_via` "
                f"together with `url_arg` — `channel_via` pairs with `channel_arg`'s "
                f"verbatim destination reader, and `url_arg`'s CP-2 peer/path splitter "
                f"cannot be mixed with it on one row (D02 §2's single_call style)"
            )
        for entry in _channel_via_entries(row):
            valid = (
                isinstance(entry, dict)
                and isinstance(entry.get("owner"), str)
                and isinstance(entry.get("method"), str)
                and (entry.get("arg") == "all_strings" or isinstance(entry.get("arg"), int))
            )
            if not valid:
                raise CatalogError(
                    f"loading catalog {catalog.source}: `{row['name']}` declares a "
                    f"`channel_via` entry that must be `{{owner, method, "
                    f'arg: int|"all_strings"}}`, got {entry!r}'
                )
        if _ADDRESS_ARG_2 in row:
            # The second half of a PAIR, so it means nothing without the
            # first. Read as "no pair", a stray `address_arg_2` would publish
            # the exchange alone as the whole identity — a destination the
            # broker does not route to, at `resolved` where nothing downstream
            # can tell it from an observation.
            if "channel_arg" not in row:
                raise CatalogError(
                    f"loading catalog {catalog.source}: `{row['name']}` declares "
                    f"`{_ADDRESS_ARG_2}` without `channel_arg` — it names the SECOND half of a "
                    f"composite destination, never a position on its own (D02 §2's single_call "
                    f"style)"
                )
            # `url_arg` asks for CP-2's peer/path split and `channel_via` for a
            # linked-call read; neither has an answer for half of a pair, so a
            # row declaring either with this one states two incompatible
            # readers for one destination. Refused rather than resolved by a
            # precedence nobody wrote down — the `channel_via`/`url_arg`
            # precedent above, for the same reason.
            paired_conflicts = [key for key in ("url_arg", "channel_via") if key in row]
            if paired_conflicts:
                raise CatalogError(
                    f"loading catalog {catalog.source}: `{row['name']}` declares "
                    f"`{_ADDRESS_ARG_2}` together with {', '.join(paired_conflicts)} — a paired "
                    f"destination is read verbatim on both halves, and neither of those readers "
                    f"can answer for half of one (D02 §2's single_call style)"
                )
        if _DESCRIPTOR in row and not (
            isinstance(row[_DESCRIPTOR], str)
            and row[_DESCRIPTOR].startswith("(")
            # `)` as well as `(` since F2 §4.1: the match now PARSES the parameter
            # portion out, so a value with no `)` raises where it used to merely fail
            # to match — and it would raise from `domain/symbols.py`, naming neither
            # the catalog nor the row. A load-time refusal names both.
            and ")" in row[_DESCRIPTOR]
        ):
            # Checked rather than trusted, because the failure is INVISIBLE:
            # a `descriptor` that no call site can ever equal claims its arity
            # all the same (`_matching_method` above), so the whole overload
            # set silently derives nothing. A target descriptor always opens
            # its parameter list with `(`, which is the cheapest check that
            # separates a real one from a source-level signature someone wrote
            # from memory.
            #
            # The MESSAGE names no language, deliberately (ARCHITECTURE §10,
            # and `test_jvm_names_stay_in_the_jvm_extractor` enforces it on
            # string literals): `descriptor` is whatever the extractor for the
            # module's own language records at `target.descriptor`, and this
            # engine may not assume which one that is.
            raise CatalogError(
                f"loading catalog {catalog.source}: `{row['name']}` declares "
                f"`{_DESCRIPTOR}: {row[_DESCRIPTOR]!r}`, which is not a method "
                f"descriptor — its parameter portion is compared against a call site's own "
                f"`target.descriptor`, so it must be spelled the way the extractor "
                f"records one, opening with `(` (D02 §2's single_call style)"
            )
        if "record_arg" in row:
            conflicts = [
                key
                for key in ("url_arg", "channel_arg", _ADDRESS_ARG_2, "body_arg", "response_arg")
                if key in row
            ]
            if conflicts:
                raise CatalogError(
                    f"loading catalog {catalog.source}: `{row['name']}` declares "
                    f"`record_arg` together with {', '.join(conflicts)} — the record IS "
                    f"the channel+payload source (D02 §2's `record_arg`)"
                )
        _validate_identity(row, catalog)
        direction = row.get("direction")
        if direction is not None and direction not in _DIRECTIONS:
            raise CatalogError(
                f"loading catalog {catalog.source}: `{row['name']}` declares "
                f"`direction: {direction}`, which is not one of {', '.join(_DIRECTIONS)} "
                f"— D00's closed sets are closed (NFR-5)"
            )


@dataclass(frozen=True)
class _IdentityFacts:
    """What form 1's join reads, both loaded once per run rather than once per
    call site (the `field_facts` precedent).

    - `signatures` — every declared method's own signature, keyed by the FULL
      symbol, which is what a call site's `caller` holds. The declared type of
      the argument handed over lives here and nowhere else: the call's own
      `target.descriptor` is the ERASED one every such API declares
      (`(Ljava/lang/Object;)…`), so it names no payload at all.
    - `annotations` — every annotation's arguments, keyed by its target's BARE
      descriptor and its own fqn, because a signature's type reference carries
      no module coordinates while an annotation target does (D00 §5a).
    """

    signatures: dict[str, dict[str, Any]]
    annotations: dict[tuple[str, str], dict[str, Any]]


def _identity_facts(workspace: Workspace) -> _IdentityFacts:
    signatures: dict[str, dict[str, Any]] = {}
    for row in workspace.query("method_declarations"):
        signatures[str(row["symbol"])] = json.loads(str(row["signature"] or "{}")) or {}
    annotations: dict[tuple[str, str], dict[str, Any]] = {}
    for row in workspace.query("annotations"):
        # First use wins, in the query's own (target, annotation) order: a
        # target cannot carry one annotation twice, so this is a total key and
        # the `setdefault` only guards against a duplicated fact.
        annotations.setdefault(
            (bare_descriptor(str(row["target"])), str(row["annotation"])),
            json.loads(str(row["args"] or "{}")) or {},
        )
    return _IdentityFacts(signatures=signatures, annotations=annotations)


def _argument_type_identity(
    arguments: list[dict[str, Any]],
    rule: dict[str, Any],
    caller: str,
    facts: _IdentityFacts | None,
) -> tuple[str | None, str | None]:
    """Form 1's whole resolution: the wire identity a call's payload argument
    names, and the declared type it named it through.

    Four steps, each of which may honestly answer nothing:

    1. the argument at the declared position must be a BARE parameter
       reference (`parameter_index`) — a merged or computed value names no
       single declared type, and the checkpoint's own ruling is that this
       narrowness is the soundness rule;
    2. the caller's own declared signature gives that parameter's type;
    3. that type's own catalog-named annotation gives the name, and — where
       the rule asks for one — the scope;
    4. the two compose in the declared format.

    The type is returned even when the identity is not — but only once the
    catalog's own annotation has been FOUND on it. That is what makes the type
    a payload rather than merely the thing at a declared position: an
    annotated type whose attributes are absent is a payload nobody named, and
    describing its shape while leaving the operation unresolved is the honest
    pair. A type carrying no such annotation at all is not evidence of a
    payload, and the row describes nothing rather than describing whatever
    happened to sit there.

    NO DEFAULTS ARE SYNTHESISED FOR AN ABSENT ATTRIBUTE, and that is a
    decision rather than an omission (DR-6, and the checkpoint's item 5).
    A framework whose annotation defaults the name to something derived from
    the type, or the scope to whatever the surrounding schema declares, is
    stating that default somewhere these facts do not reach — the schema is
    not in the class file, and an attribute left at its default is simply
    absent from the bytecode (item 4). Deriving a plausible one would publish
    an operation nobody serves at `resolved`/`compiler`; the honest answer is
    an unresolved identity, and it is the answer this returns."""
    if facts is None:
        return None, None
    index = parameter_index(_arg_at(arguments, rule["arg"]))
    if index is None:
        return None, None
    parameters = facts.signatures.get(caller, {}).get("parameters") or []
    if index >= len(parameters):
        return None, None
    # The DESCRIPTOR's symbol: this looks annotations up ON the named type, and a
    # type variable names no type. `<T extends OrderEvent> handle(T)` resolves
    # through `OrderEvent` — its erasure, a real type carrying real annotations —
    # where `T` resolves through nothing.
    symbol = parameters[index].get("erased_symbol") or (parameters[index].get("type") or {}).get(
        "symbol"
    )
    if not symbol:
        return None, None
    payload_type = bare_descriptor(str(symbol))
    # FIRST match, not a merge: a list is several spellings of ONE annotation
    # (§3.1), and merging two would invent a declaration nobody made.
    #
    # "At most one is ever written" is the ordinary case, not an invariant — a
    # half-migrated Boot 2-to-3 module can legally carry both
    # `@jakarta.xml.bind.annotation.XmlRootElement` and its `javax` spelling on
    # one type, with different `name`s. This takes the one the catalog lists
    # first, so the answer is deterministic and the catalog's order decides it.
    # Deliberate rather than accidental: the alternative is refusing the type
    # outright, which loses a readable operation over a shape that is itself a
    # migration artefact.
    args = next(
        (
            found
            for name in rule["annotations"]
            if (found := facts.annotations.get((payload_type, name))) is not None
        ),
        None,
    )
    if args is None:
        return None, None
    name = _attribute(args, str(rule["name_from"]))
    if name is None:
        return None, payload_type
    if "qualifier_from" not in rule:
        return name, payload_type
    qualifier = _attribute(args, str(rule["qualifier_from"]))
    if qualifier is None:
        return None, payload_type
    return _composed(str(rule["format"]), qualifier, name), payload_type


def _composed(declared: str, qualifier: str, name: str) -> str | None:
    """The scope and the name joined in the DECLARED format — branching on the
    word rather than assuming today's only one, the same shape
    `derive_endpoints.sql` gives `$qualifier_format`.

    `_validate_identity` already refused any word outside `_IDENTITY_FORMATS`,
    so the fallthrough is unreachable today; it returns None rather than
    composing anyway, so a second word added to the set but not here derives no
    identity instead of silently deriving a `qname` one — an unresolved
    operation rather than a wrong address."""
    if declared == "qname":
        return "{" + qualifier + "}" + name
    return None


def _attribute(args: dict[str, Any], name: str) -> str | None:
    """One annotation attribute, read scalar-or-array — the Python mirror of
    `derive_endpoints.sql`'s own `coalesce(a.args -> n ->> 0, a.args ->> n)`,
    so a framework that arrays an attribute needs no second rule here either.
    None where the attribute is absent, which is the only shape a defaulted
    one can take (checkpoint item 4)."""
    value = args.get(name)
    if isinstance(value, list):
        return str(value[0]) if value else None
    return None if value is None else str(value)


def _declaring_type(caller: str) -> str | None:
    """The type whose body makes a call — the scope form 2's lookup is
    confined to. None for a free function, which declares nothing to
    configure."""
    return owner_of(bare_descriptor(caller))


def _configured_addresses(
    owners: tuple[str, ...],
    setup: dict[str, Any] | None,
    call_sites: list[dict[str, Any]],
    by_caller: dict[str, list[dict[str, Any]]],
    field_sources: FieldFacts | None,
    supertypes: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any] | None]:
    """Form 2's answer for every type that configures one of these clients:
    the address argument its own calls to the declared setup method hand over,
    read through the field ladder exactly as an address written at a call site
    is.

    CONFINED TO THE DECLARING TYPE, and that boundary is the whole soundness
    argument. The facts carry no link from a call's receiver to the field
    holding it — a receiver is a value id, meaningless outside its own method
    (D00 §5) — so nothing can prove that THIS call's client is the one THAT
    setup call configured. What can be said is narrower and true: the type
    that makes the call also holds the client and configures it in its own
    body. A client configured in one class and used from another is outside
    this, honestly, and reads `unresolved`.

    AMBIGUITY REFUSES. A type whose setup calls hand over two different
    addresses, or one the ladder could not read at all, resolves to None — two
    candidate addresses are not an address, and picking either would publish a
    peer the code does not state. Empty for a catalog declaring no form 2."""
    if setup is None:
        return {}
    candidates: dict[str, set[str | None]] = {}
    for site in call_sites:
        if site["owner"] not in owners or site["name"] != setup["method"]:
            continue
        caller = str(site["caller"])
        declaring = _declaring_type(caller)
        if declaring is None:
            continue
        # `referenced` is EMPTY here rather than the run's own accumulator: the
        # field ladder roots no payload, so nothing is ever appended, and
        # threading the shared list in would suggest this pass contributes to
        # shape order when it does not.
        facts = CallFacts(
            supertypes=supertypes, caller_call_sites=by_caller.get(caller, []), referenced=[]
        )
        argument = address_argument(
            _arg_at(site["arguments"], setup["arg"]), field_sources, facts, caller
        )
        value = (
            str(argument["value"])
            if argument is not None
            and argument.get("kind") == "string"
            and isinstance(argument.get("value"), str)
            else None
        )
        candidates.setdefault(declaring, set()).add(value)
    return {
        declaring: (
            {"kind": "string", "value": next(iter(values))}
            if len(values) == 1 and None not in values
            else None
        )
        for declaring, values in candidates.items()
    }


def _default_address(matches: dict[str, Any], catalog: Catalog) -> dict[str, Any] | None:
    """Form 2's declaration, refused at run start where its shape cannot be
    honoured — the `_validate_methods` discipline. A block naming no method,
    or naming a position that is not one, would silently resolve every
    address-less call to nothing, which is indistinguishable from the catalog
    never declaring the word at all."""
    declared = matches.get(_DEFAULT_ADDRESS)
    if declared is None:
        return None
    valid = (
        isinstance(declared, dict)
        and set(declared) == _DEFAULT_ADDRESS_KEYS
        and isinstance(declared.get("method"), str)
        and isinstance(declared.get("arg"), int)
        and not isinstance(declared.get("arg"), bool)
    )
    if not valid:
        raise CatalogError(
            f"loading catalog {catalog.source}: `{_DEFAULT_ADDRESS}` must be "
            f"`{{method: str, arg: int}}`, got {declared!r} (2I design §4)"
        )
    return dict(declared)


def _address_separator(
    matches: dict[str, Any], methods: list[dict[str, Any]], catalog: Catalog
) -> str | None:
    """The character joining the two halves of a PAIRED destination, checked
    against the rows that need it — the `_validate_methods` discipline, and
    the same stakes `annotation_driven.py::_validate_naming` names for
    `path_separator`.

    Declared with no row naming `address_arg_2` is a key this catalog never
    reads, refused rather than ignored: a file whose author believed they had
    asked for a composite identity would otherwise get the first half alone,
    with nothing saying so. Declared as anything but exactly one STRING
    character is refused for `path_separator`'s reason — a YAML int or bool
    coerces to text and would join two halves with a character nobody wrote,
    composing a destination the broker does not route to.
    """
    declared = matches.get(_ADDRESS_SEPARATOR)
    if not any(_ADDRESS_ARG_2 in row for row in methods):
        if declared is not None:
            raise CatalogError(
                f"loading catalog {catalog.source}: `{_ADDRESS_SEPARATOR}: {declared!r}` is "
                f"declared with no `methods` row naming `{_ADDRESS_ARG_2}` — it describes how a "
                f"composite destination composes, and this catalog reads none (D02 §2's "
                f"single_call style)"
            )
        return None
    if not isinstance(declared, str) or len(declared) != 1:
        raise CatalogError(
            f"loading catalog {catalog.source}: `{_ADDRESS_SEPARATOR}: {declared!r}` is not a "
            f"single character — what joins the two halves of a composite destination is catalog "
            f"data, and a value that isn't exactly one character would compose a destination "
            f"nothing routes to (D02 §2's single_call style)"
        )
    return declared


def _paired_destination(
    head: tuple[str | None, str | None, str],
    tail_argument: dict[str, Any] | None,
    separator: str,
) -> tuple[str | None, str | None, str]:
    """One destination from the TWO captures a composite identity needs.

    Both halves must read, or the row is `unresolved` with no path at all —
    and that is the rule rather than a conservatism. Half of a composite
    identity is not a partial answer, it is a DIFFERENT destination: an
    exchange published without its routing key names everything bound to that
    exchange, and a routing key published without its exchange names whatever
    the default exchange routes it to. Either would be a confidently-wrong
    address at `resolved`/`compiler`, which is the one failure D02 §2's
    unresolved-is-an-answer exists to prevent.

    An EMPTY first half is the composite's own degenerate spelling, and the
    identity is then the second half alone — the framework mirroring §8.1
    rule 1 asks for, rather than the approximation `'' + separator + tail`
    would be. This holds as long as the protocols reaching here treat an empty
    first half as "the default routing", which AMQP's default exchange does;
    a protocol whose empty first half means something else needs its own rule
    here rather than this one widened.

    `peer` is unconditionally NULL, `channel_of`'s contract: a destination
    fragment is an opaque expression the broker resolves, never a URL with an
    authority to split off.
    """
    _, first, first_resolution = head
    _, second, second_resolution = channel_of(tail_argument)
    if first_resolution != "resolved" or second_resolution != "resolved":
        return None, None, "unresolved"
    if first == "":
        return None, second, "resolved"
    return None, f"{first}{separator}{second}", "resolved"


def _validate_identity(row: dict[str, Any], catalog: Catalog) -> None:
    """Refuses a form 1 rule whose shape the resolution cannot honour — the
    `_validate_methods` discipline, and the same stakes `annotation_driven.py::
    _validate_naming` names: every check here catches a file that would derive
    a quietly WRONG identity rather than fail, and a wrong one is published at
    `resolved`/`compiler` where nothing downstream can tell it from an
    observation.

    A missing or misspelled key would leave the rule reading NULL and naming
    nothing, which is indistinguishable from a catalog that never asked. An
    unrecognised `format` would fall through to the bare name, silently
    dropping the scope the file asked for. And a `format` without a
    `qualifier_from` — or the reverse — states half a composition: the two
    are declared together or not at all, exactly as `qualifier_format` and
    `qualifier_from` are on the annotation-driven side."""
    rule = row.get(_IDENTITY)
    if rule is None:
        return
    if "record_arg" in row:
        raise CatalogError(
            f"loading catalog {catalog.source}: `{row['name']}` declares `{_IDENTITY}` "
            f"together with `record_arg` — the record IS the payload source, so the two "
            f"name one capture twice (D02 §2's single_call style)"
        )
    keys = set(rule) if isinstance(rule, dict) else set()
    valid = (
        isinstance(rule, dict)
        and _IDENTITY_REQUIRED <= keys <= (_IDENTITY_REQUIRED | _IDENTITY_OPTIONAL)
        and isinstance(rule.get("arg"), int)
        and not isinstance(rule.get("arg"), bool)
        and names_a_type(rule.get("annotation"))
        and isinstance(rule.get("name_from"), str)
        and isinstance(rule.get("qualifier_from", ""), str)
    )
    if not valid:
        raise CatalogError(
            f"loading catalog {catalog.source}: `{row['name']}` declares `{_IDENTITY}` that "
            f"must name `arg` (int), `annotation` (a type or a list of them) and "
            f"`name_from`, optionally "
            f"`qualifier_from` and `format`, got {rule!r} (2I design §4)"
        )
    fmt = rule.get("format")
    if ("qualifier_from" in rule) != ("format" in rule):
        raise CatalogError(
            f"loading catalog {catalog.source}: `{row['name']}` declares one of "
            f"`qualifier_from`/`format` on `{_IDENTITY}` without the other — a scope and "
            f"how it composes are one declaration (2I design §4)"
        )
    if fmt is not None and fmt not in _IDENTITY_FORMATS:
        raise CatalogError(
            f"loading catalog {catalog.source}: `{row['name']}` declares "
            f"`{_IDENTITY}.format: {fmt}`, which is not one of "
            f"{', '.join(sorted(_IDENTITY_FORMATS))} (2I design §4)"
        )


def _channel_via_entries(method: dict[str, Any]) -> list[Any]:
    """`channel_via`'s `{owner, method, arg}` | `[{...}, ...]` grammar,
    normalized to a list without touching the entries themselves — shared by
    `_validate_methods` (which must not crash reading `owner`/`method` off a
    malformed entry) and `_channel_via_forms` below (which converts each
    `owner` once a row is already known-valid)."""
    via = method.get("channel_via")
    if via is None:
        return []
    return via if isinstance(via, list) else [via]


def _channel_via_forms(method: dict[str, Any]) -> list[dict[str, Any]]:
    """Task 7's `channel_via` entries, each declared `owner` converted to
    the SCIP symbol form once. Only ever called on a row `_validate_methods`
    already passed, from the `methods` normalization at `run` start."""
    return [
        {"owner": _catalog_symbol(entry["owner"]), "method": entry["method"], "arg": entry["arg"]}
        for entry in _channel_via_entries(method)
    ]


def _validate_record_wrappers(rows: list[dict[str, Any]], catalog: Catalog) -> None:
    """Refuses a broken `record_wrappers` block before any call site is
    matched — the same `_validate_methods` discipline, applied to the
    catalog-level block a `record_arg` row's lookup depends on. Each entry
    must be `{type, channel_ctor_arg, payload_ctor_arg}`: `type` a string,
    `channel_ctor_arg` an int, and `payload_ctor_arg` either an int or the
    literal string `"last"` (the constructor's own final argument) —
    anything else is a broken catalog, never a silent no-op once a call site
    reaches it."""
    for wrapper in rows:
        payload_ctor_arg = wrapper.get("payload_ctor_arg")
        valid = (
            isinstance(wrapper.get("type"), str)
            and isinstance(wrapper.get("channel_ctor_arg"), int)
            and (isinstance(payload_ctor_arg, int) or payload_ctor_arg == "last")
        )
        if not valid:
            raise CatalogError(
                f"loading catalog {catalog.source}: a `record_wrappers` entry must be "
                f'`{{type, channel_ctor_arg: int, payload_ctor_arg: int|"last"}}`, got '
                f"{wrapper!r}"
            )


def _record_arguments(
    record: dict[str, Any] | None,
    record_wrapper_args: dict[str, tuple[int, int | str]],
    facts: CallFacts,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """A `record_arg` row's channel and payload arguments (D02 §2's
    `record_wrappers`, Task 7): the record argument's own linked
    constructor — the same one-hop `contracts._linked_constructor` already
    gives `call_wrappers` — read at the catalog's declared
    `channel_ctor_arg`/`payload_ctor_arg` positions, `"last"` meaning the
    constructor's own final argument. Returns the two raw argument dicts,
    fed straight back into `url_of`/`argument_descriptor` exactly as a
    direct `url_arg`/`body_arg` row's own arguments are — the record path
    invents no second resolution rule.

    `(None, None)` wherever the chain breaks: the record itself was not
    captured as a constructed `instance`, its type names no
    `record_wrappers` entry, or no `<init>` call site in this same caller
    links to it. Each of these is I1's declared-capture failure, not a
    crash — the caller derives the row regardless, `resolution:
    unresolved`.

    The payload position is also None whenever it resolves to the SAME ctor
    slot `channel_ctor_arg` already claims — a 1-arg linked constructor with
    `channel_ctor_arg: 0` and `payload_ctor_arg: "last"` is exactly this
    collision (Task 7 review, MAJOR). Reporting the topic string back as
    the payload would be silently wrong rather than an honest capture
    failure; the channel argument itself is untouched by this guard, so
    `path` still carries whatever it read (I1: only the declared payload
    capture failed)."""
    if record is None or record.get("kind") != "instance" or record.get("symbol") is None:
        return None, None
    symbol = str(record["symbol"])
    wrapper = record_wrapper_args.get(symbol)
    if wrapper is None:
        return None, None
    channel_ctor_arg, payload_ctor_arg = wrapper
    constructor = _linked_constructor(symbol, record.get("source"), facts)
    if constructor is None:
        return None, None
    ctor_arguments = constructor.get("arguments") or []
    channel_argument = _arg_at(ctor_arguments, channel_ctor_arg)
    if isinstance(payload_ctor_arg, int):
        payload_index: int | None = payload_ctor_arg
    else:
        payload_index = len(ctor_arguments) - 1 if ctor_arguments else None
    if payload_index is None or payload_index == channel_ctor_arg:
        payload_argument = None
    else:
        payload_argument = _arg_at(ctor_arguments, payload_index)
    return channel_argument, payload_argument


def _verb_of(method: dict[str, Any], arguments: list[dict[str, Any]]) -> str | None:
    """D02 §2's two ways a `methods` row states the verb: `http_method` is a
    literal the catalog already knows (`postForObject` is always a POST, so
    the catalog states it once); `method_arg` is a position the call site
    carries instead (`exchange`'s verb is its own `HttpMethod` argument, an
    `enum`-kind entry) — the tail of the constant's symbol, after `#` and its
    trailing `.` (checkpoint-verified against the real emitted grammar:
    `org/springframework/http/HttpMethod#POST.` reads as `POST`).

    None where the declared `method_arg` slot holds anything else — a verb
    passed in as a parameter, the compiler's `unresolved`. The caller keeps
    the row with `method` NULL and `resolution: unresolved` (I2)."""
    literal = method.get("http_method")
    if literal is not None:
        return str(literal)
    arg = _arg_at(arguments, method.get("method_arg"))
    if arg is None or arg.get("kind") != "enum" or not arg.get("symbol"):
        return None
    return member_name(str(arg["symbol"]))
