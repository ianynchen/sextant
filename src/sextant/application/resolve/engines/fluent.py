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
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from itertools import product
from typing import Any, cast

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.dispatch import dispatch_of
from sextant.application.resolve.open_questions import record_open_questions
from sextant.application.resolve.parameter_markers import (
    parameter_markers,
    producing_calls,
    recipe_sites,
)
from sextant.application.resolve.registration_conditions import (
    Alternatives,
    Conditions,
    conditions_of,
    environments_of,
    existence_rows,
)
from sextant.application.resolve.request_requirements import (
    ParameterReading,
    ParameterRules,
    body_field_requirement,
    parameter_rules,
    read_dependant,
    read_parameters,
    request_param_calls,
    request_param_rows,
)
from sextant.application.resolve.shapes.arguments import (
    _CAPTURED_AT,
    _HOLE,
    _UNREADABLE_HOST,
    QUERY_KIND,
    TYPE_FORM,
    CallFacts,
    CarrierRules,
    FieldFacts,
    _address_read,
    _arg_at,
    _capture_resolved,
    _holes,
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
    type_form_reference,
    url_of,
    with_authority,
)
from sextant.application.resolve.shapes.chains import (
    _ARG_REFERENCE,
    _COLLECTED,
    _COMPOSE,
    _DIRECTION,
    _EXECUTED_BY,
    _LINK_SENDER,
    _READS_LINK,
    _UNRESOLVED_ARGUMENT,
    VERBS_TO_READ,
    ChainEnd,
    _captured_at,
    _declared_entries,
    _matching_root,
    _method_symbols,
    _resolve_captures,
    _resolves_beans,
    _site_key,
    chain_ends,
    configuring_calls,
    respell_verb,
)
from sextant.application.resolve.shapes.client_base import (
    CLIENT_IS_RECEIVER,
    FILL_AUTHORITY,
    against_client_base,
    client_base_of,
    client_defaults,
    options_parts,
)
from sextant.application.resolve.shapes.contracts import (
    _body_type,
    _path_variables,
    body_calls_of,
    is_scalar,
    payload_descriptor,
)
from sextant.application.resolve.shapes.expansion import (
    ModelFields,
    _enum_symbols,
    _rules_of,
    model_fields,
)
from sextant.application.resolve.shapes.inbound_routes import (
    CONCATENATE,
    EMPTY_PATH,
    INVALID_RESPONSE_TYPE,
    NO_METHODS,
    UNROOTED_PATH,
    WORDS,
    fallback_word,
    file_refusal,
    is_unrooted,
    join_prefix,
    media_columns,
    refusal_rows,
    validated_verbless_serves,
    validated_word_fallback,
)
from sextant.application.resolve.shapes.member_values import (
    member_table,
    names_members,
    static_field_value,
)
from sextant.application.resolve.shapes.mounts import (
    ANY_ROUTER,
    CHAIN_RESULT,
    ROOT,
    UNREAD_PROGRAM,
    Mount,
    MountPath,
    MountReader,
    MountRule,
    MountRules,
    Place,
    Prefix,
    file_unread_prefix,
    mount_rules_of,
    programs_of,
    router_producers,
    same_router,
    unread_prefix_rows,
    weaker,
    with_heirs,
)
from sextant.application.resolve.shapes.pass_through import (
    ANSWERS,
    PASSES_ON,
    UNREADABLE,
    Handler,
    HandlerReader,
    PassThroughRule,
    exact_methods,
    file_unread,
    handler_outcomes,
    pass_through_of,
    unread_rows,
)
from sextant.application.resolve.shapes.rooting import _catalog_symbol, catalog_symbols
from sextant.application.resolve.values import (
    ABSENT,
    EXPRESSION,
    EXTERNAL,
    INT,
    LITERAL,
    NOT_READABLE,
    RECEIVER,
    STRING,
    SYMBOL,
    UNPACKED_SLOT,
    Answer,
    Path,
    ValueIndex,
    argument_slot,
    cached_value_index,
    called_function,
    decorators_passed,
    producer_paths,
    recipe_bodies,
    resolve_positions,
    undecorated_maker,
)
from sextant.domain.closed_sets import (
    PATH_KIND_PATTERN,
    Direction,
    Evidence,
    Resolution,
    RootKind,
)
from sextant.domain.paths import canonical_http_path, serves_urls
from sextant.domain.redaction import REDACTED, Redactor
from sextant.domain.symbols import (
    ANY_TYPE,
    UNION_TYPE,
    bare_descriptor,
    member_name,
    method_name,
    names_a_type,
    owner_of,
)

# D00 §5's kind for an address the code ASSEMBLES. Spelled here because `_url_arguments`
# treats it as the catalog's own declared position rather than as a hop - see there.
_CONCAT = "concat"
# D00 §5's kind for a value the method was HANDED: by a caller, or by the site that created
# the lambda whose captured value it is. Read in `_url_arguments` by the same no-identity walk.
_PARAMETER = "parameter"

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

# The captures that are parts of one address (2F design §4's base
# composition; `host` and `port`, Vert.x spec §3d) — `channel`'s alternative, and what
# `_validate_url_channel_exclusivity` weighs against it as a group.
_ADDRESS_FIELDS = ("base", "url", "host", "port", "options")
# The capture naming an options object a request is made FROM (Vert.x's `request(m,
# RequestOptions)`, spec §3d): read by the catalog's `client_base` setters, as the client's
# own options are, into the request's own parts.
_OPTIONS = "options"
# The parts of an options object that name a request's address, and the capture each fills
# where the chain captured none of its own.
_OPTION_CAPTURES = {"uri": "url", "host": "host", "port": "port"}

# A root's literal word saying where its chain is sent is not read here (`destination: unread`):
# the framework sends the request to an address the code hands it apart from the URL, so the
# row has no peer (Vert.x's `SocketAddress` forms, CP-56 rows 325-326).
_DESTINATION = "destination"
_UNREAD_DESTINATION = "unread"
# What a captured address IS (`url_is`, Vert.x spec §3a), a literal capture beside `url`, last
# wins: a regular expression the framework matches (`pattern`, the row's `path_kind`), or an
# address (`address`, the default), which a later step declares to undo an earlier pattern.
_URL_IS = {PATH_KIND_PATTERN: PATH_KIND_PATTERN, "address": None}
# A literal capture saying whether the chain serves at all (`serves`, Vert.x spec §3a): a
# step declaring `serves: false` (`disable()`) makes the chain derive nothing until a later
# step declares `serves: true`. A `poisons: [serves]` step ends it for good.
_SERVES = "serves"
# Which of several routes on one verb and path is tried first (Vert.x spec §3b): `order: argN`
# reads the literal order a route was given, `order: last` says it goes after every other.
_ORDER = "order"
_LAST = "last"
# An order the chain set that could not be read: it orders against nothing.
_UNREAD_ORDER = "unread"


# The capture names this engine's rows SHOW (the user's ruling of 2026-11-03, option A: a call on
# a branch that sets none of them is no split for the several-splits rule, `chain_ends`). Each is
# read into a column of `endpoints` or `endpoint_metadata` in `_derive`: the verb (`method`), the
# address (`path`, `peer`, `path_kind`, from the url, its parts, the options object a client was
# built from and the channel a messaging chain names), the payloads (`request_shape`,
# `response_shape`), the handler and its media (`consumes`, `produces`), whether and in which order
# the chain derives a row at all (`serves`, `order`), what a `collects` step gathers
# (`collected`, the metadata), and the recipes a route runs before its handler (`dependencies`,
# their parameters the metadata, plan 2026-11-08 N6). A column added to the row adds its
# capture here.
PUBLISHED_PARTS = frozenset(
    {
        "http_method",
        "url",
        "url_is",
        "base",
        "host",
        "port",
        "destination",
        "options",
        "channel",
        "channel_link",
        "channel_source",
        "routing_key",
        "exchange",
        "body",
        "response",
        "response_is",
        "handler",
        "consumes",
        "produces",
        "serves",
        "order",
        "collected",
        "dependencies",
    }
)
# The capture names a fluent step may carry that are no part of a row (review 3 re-review 2,
# m-3: every capture a step sets is in one set or the other, `tests/architecture/
# test_published_parts_are_complete.py`). Each says why:
UNPUBLISHED_PARTS = frozenset(
    {
        # The ladder a `url` capture is read through where its argument is a call
        # (`chains._VIA_KEYS`): an instruction for reading the `url` part, which the same entry
        # captures, never a value of its own.
        "url_via",
        # The same ladder for the `channel` part.
        "channel_via",
    }
)


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
    roots, bean_roots, steps = _declared_entries(catalog, workspace.once(dispatch_of))
    for root in matches.get("roots", []):
        _validated_direction(root, catalog)
    _validate_url_channel_exclusivity([*roots, *bean_roots], steps, catalog)
    verb_fields = _verb_fields(matches, catalog)
    refuses_unrooted = _refuses_unrooted_path(matches, catalog)
    verbless_serves = validated_verbless_serves(matches, catalog.source, "fluent")
    pathless_serves = _pathless_serves(matches, catalog)
    _validate_route_captures([*roots, *bean_roots, *steps], catalog)
    pass_through = pass_through_of(matches, catalog.source)
    mount_rules = mount_rules_of(matches, catalog.source, words=catalog.root_kind is not None)
    # A subclass that inherits a mount or a router constructor is called through its own name
    # and runs the declared owner's, as a root's heirs do (`chains._with_heirs`).
    if mount_rules is not None and catalog.root_kind is None:
        mount_rules = with_heirs(mount_rules, workspace.once(dispatch_of))
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
    walk_index = cached_value_index(
        workspace,
        catalog.not_hand_offs,
        catalog.hand_off_effects,
        catalog.bean_models,
        catalog.value_annotations,
        returns_arguments=catalog.returns_arguments,
    )
    client_base = client_base_of(matches, catalog.source)
    _validate_options_capture([*roots, *bean_roots, *steps], client_base, catalog)
    response_fallback = _response_fallback_of(matches, catalog, workspace)
    if catalog.root_kind is not None:
        _run_entry_points(
            workspace,
            catalog,
            matches,
            mount_rules,
            walk_index,
            refuses_unrooted,
            method_symbols,
            roots,
        )
        return
    if "path_fallback" in matches or any("path_fallback" in root for root in matches["roots"]):
        raise CatalogError(
            f"loading catalog {catalog.source}: `path_fallback` names a chain's word from its "
            f"handler, which only a `root_kind: entry_point` catalog reads"
        )
    # Checked here, at the run's start, so a broken entry is refused whether or not a row reads it.
    parameters = parameter_rules(catalog) if catalog.direction == "inbound" else None
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
    seen: dict[tuple[str, str, str, str, str | None, str | None, str | None], _Kept] = {}
    # The rows `seen` does not hold, by the call each came from (`_derive_captured`): the
    # paths of one chain are one row.
    exact: dict[tuple[Any, ...], _Kept] = {}
    # F5 §6.2 (W29). Accumulated across every caller and inserted once, the `rows`
    # discipline: a per-caller insert would be one statement per method in the module.
    caller_parameters = workspace.once(declared_parameters_of)
    metadata: list[dict[str, Any]] = []
    # The recipes a route's framework runs before its handler, one `roots` row each at the
    # route's address (plan 2026-11-08 N11), and the recipe calls each `dependencies=` written
    # on a route, a router or an include names, read once per place and path.
    recipe_roots: dict[tuple[str, str | None, str | None, str | None, str | None, str | None], None]
    recipe_roots = {}
    dependency_calls: dict[Any, tuple[Mapping[str, Any], ...]] = {}
    # DR-6: the declarations the framework would raise on, accumulated across every caller
    # and filed once, the `rows`/`metadata` discipline.
    refusals: dict[tuple[str, str | None, str | None], dict[str, Any]] = {}
    # Spec §3b: which handler on a chain answers, judged once for every handler the chains
    # name, before any row is derived — the chains are read whole first, because each
    # handler's outcome is one backward walk per `passes_on` call over the whole module.
    ends: Iterable[ChainEnd] = chain_ends(workspace, catalog, PUBLISHED_PARTS)
    judged: dict[Any, _Judged] | None = None
    candidates: list[_Candidate] | None = None
    unread: dict[tuple[str, str | None, str | None], dict[str, Any]] = {}
    # Spec §3c: the mounts are found among the chain ends too, before any route's prefix is
    # read.
    read_whole: list[ChainEnd] = []
    if pass_through is not None or mount_rules is not None:
        read_whole = list(ends)
        ends = read_whole
    if pass_through is not None:
        judged = _judge(read_whole, pass_through, walk_index, method_symbols, workspace)
        candidates = []
    mounts: MountReader | None = None
    mounted: dict[tuple[str, int], Mount] = {}
    ways: dict[int, int] = {}
    # Why a row's path holds `<prefix>` (`mount_prefix`), filed once the rows are settled.
    unread_prefixes: dict[tuple[str, str | None, str], dict[str, Any]] = {}
    if mount_rules is not None:
        mounts, mounted, ways = _mounts(
            read_whole, mount_rules, walk_index, workspace, refuses_unrooted, catalog
        )
    # Which router each held-back route is made on (`_settle`): the mount reader's own reads
    # where the module mounts, one with no mounts where it does not.
    routers = mounts
    if routers is None and candidates is not None and mount_rules is not None:
        routers = _router_reader(walk_index, workspace, mount_rules, [], refuses_unrooted, catalog)
    # A model marked as a set of request parameters is read by the shape model (R25), once.
    models = None if parameters is None else model_fields(workspace, catalog)
    # OI-368: the tests the module's calls run under, read once per resolve; an inbound row
    # whose registering calls all run under one exists "not evaluated".
    conditions: Conditions | None = None
    registrations: list[tuple[dict[str, Any], Alternatives]] = []
    if catalog.direction == "inbound":
        conditions = conditions_of(workspace)
        if not conditions.guards:
            conditions = None
    context: _DeriveContext | None = None
    for end in ends:
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
                exact=exact,
                metadata=metadata,
                method_symbols=method_symbols,
                bindings=bindings,
                verb_fields=verb_fields,
                client_base=client_base,
                refuses_unrooted=refuses_unrooted,
                refusals=refusals,
                roots=roots,
                verbless_serves=verbless_serves,
                pathless_serves=pathless_serves,
                judged=judged,
                candidates=candidates,
                unread=unread,
                mounts=mounts,
                routers=routers,
                unread_prefixes=unread_prefixes,
                response_fallback=response_fallback,
                parameter_rules=parameters,
                recipe_roots=recipe_roots,
                dependency_calls=dependency_calls,
                model_fields=models,
                conditions=conditions,
                registrations=registrations,
            )
        # A mount's chain (spec §3c) is not a route: what Vert.x refuses of it is recorded,
        # and it derives a row only where it was given a handler as well.
        mount = mounted.get(_site_key(end.terminal)) if end.terminal is not None else None
        if mount is not None and mounts is not None:
            # This end's own way to the mount call: a refusal is filed for the way it was read
            # on, under that way's root verb.
            for way, path, reason in mounts.refusals(mount):
                if way != ways.get(id(end)):
                    continue
                file_refusal(
                    refusals,
                    protocol=catalog.protocol,
                    method=_root_verb(end, context),
                    method_kind=_root_method_kind(end, context),
                    path=path,
                    reason=reason,
                    caller=end.caller,
                    handler=None,
                )
            if "handler" not in end.captures:
                continue
        # A chain walked back across methods is read on the path it took (ruling 5), and a
        # client sitting at the root's receiver is read off that root.
        held = context
        if end.path is not None:
            held = replace(held, path=end.path)
        if client_base is not None and client_base["client_arg"] == CLIENT_IS_RECEIVER:
            held = replace(held, root=end.root)
        _derive(end, held)

    if candidates is not None:
        _settle(candidates, rows, metadata, unread)
    # A mount made by a call of its own (`prefix_arg`) is no chain: its refusals are filed
    # here, under no verb, as the route the framework builds for it names none.
    if mounts is not None:
        for mount in mounted.values():
            if mount.rule.prefix_arg is None:
                continue
            for _, path, reason in mounts.refusals(mount):
                file_refusal(
                    refusals,
                    protocol=catalog.protocol,
                    method=None,
                    method_kind=verbless_serves,
                    path=path,
                    reason=reason,
                    caller=str(mount.site["caller"]),
                    handler=None,
                )
        # A router construction whose held prefix the framework refuses (`router_holds`):
        # filed the same way, under no verb.
        for site, path, reason in mounts.held_refusals():
            file_refusal(
                refusals,
                protocol=catalog.protocol,
                method=None,
                method_kind=verbless_serves,
                path=path,
                reason=reason,
                caller=str(site["caller"]),
                handler=None,
            )
    workspace.derive("call_endpoints", rows=rows)
    if registrations:
        # After the rows, never before: each entry is bound to its row's `row_id` as it is
        # written (`insert_endpoint_existence.sql`), the `endpoint_metadata` discipline.
        existence = existence_rows(registrations, environments_of(workspace))
        if existence:
            workspace.derive("endpoint_existence_insert", rows=existence)
    if recipe_roots:
        # Written beside the endpoint rows, and kept by `record_roots` as the entry points are.
        workspace.derive(
            "roots_insert",
            rows=[
                {
                    "handler": handler,
                    "root_kind": str(RootKind.INBOUND_ENDPOINT),
                    "protocol": protocol,
                    "method": method,
                    "path": path,
                    "method_kind": method_kind,
                    "path_kind": path_kind,
                }
                for handler, protocol, method, path, method_kind, path_kind in sorted(
                    recipe_roots,
                    key=lambda key: tuple((part is not None, part or "") for part in key),
                )
            ],
        )
    if bindings:
        workspace.derive("channel_bindings_insert", rows=bindings)
    # After the endpoints, never before: an entry names the endpoint it belongs to by that
    # row's own columns, so the row has to exist for the pair to mean anything to a reader
    # joining them. The RESET is the pipeline's, once per resolve, for the
    # `open_questions` reason — several catalogs write this table and a reset owned by any
    # one of them would erase whichever ran first.
    if metadata:
        workspace.derive("endpoint_metadata_insert", rows=metadata)
    # The ledger's reset is the pipeline's, for the `open_questions` reason above.
    record_open_questions(
        workspace,
        [
            *refusal_rows(refusals),
            *unread_rows(unread),
            *unread_prefix_rows(unread_prefixes, rows),
        ],
    )


@dataclass(frozen=True)
class _EntryPoints:
    """What a `root_kind: entry_point` catalog's chains read beside the walk (design
    2026-11-06-reading-decorators §3c, §4): the catalog's `path_fallback` and each root's
    own, the method symbols a handler's bare name joins to, and the programs the module's
    build names (`programs_of`)."""

    fallback: dict[str, Any] | None
    # `(owners, method, fallback)` of each root entry declaring a `path_fallback` of its own.
    root_fallbacks: tuple[tuple[tuple[str, ...], str, dict[str, Any]], ...]
    method_symbols: Mapping[str, str]
    programs: Mapping[tuple[str, int], str]

    def fallback_of(self, root: Mapping[str, Any]) -> dict[str, Any] | None:
        """The `path_fallback` of the first root entry the call `root` matches, where that
        entry declares one, else the catalog's."""
        for owners, method, fallback in self.root_fallbacks:
            if root.get("owner") in owners and root.get("name") == method:
                return fallback
        return self.fallback


def _run_entry_points(
    workspace: Workspace,
    catalog: Catalog,
    matches: Mapping[str, Any],
    mount_rules: MountRules | None,
    index: ValueIndex,
    refuses_unrooted: bool,
    method_symbols: Mapping[str, str],
    registrations: Sequence[dict[str, Any]],
) -> None:
    """A `root_kind: entry_point` catalog (design 2026-11-06-reading-decorators §5): each
    chain that reaches its terminal is a program entry point, one `roots` row per command
    path that reaches its handler, `protocol`, `method` and the two markers NULL; and each
    decorator its handler passed that a `request_params` entry names is one
    `endpoint_metadata` row against it (`caller` the handler, `row_id` NULL: there is no
    `endpoints` row).

    - **The handler** is the terminal's `handler` capture, followed back with the producer
      walk as a call of it would be (`functions`): through each decorator a value model
      states hands the function back (`result_returns`), into module code, and to the
      function. Where no path names a function (a library decorator no value model states),
      the command's row keeps its path with `handler` NULL: it is registered, and which code
      runs is not read. It gets no parameter rows.
    - **The words**: the root's `url` capture, else the handler's name respelled by
      `path_fallback`; behind each group mount's word (`router_arg: chain_result`), joined
      by one space; the outermost router's word is the program's name (`MountReader`).
    - **The rows are this engine's own**, written to `roots` beside the two kinds
      `record_roots` derives, which keeps them (`roots.record_roots`)."""
    where = f"loading catalog {catalog.source}"
    entry_points = _EntryPoints(
        fallback=validated_word_fallback(matches.get("path_fallback"), where),
        root_fallbacks=tuple(
            (
                catalog_symbols(root.get("owner"), f"{where}: roots[].owner"),
                str(root["method"]),
                fallback,
            )
            for root in matches["roots"]
            if (fallback := validated_word_fallback(root.get("path_fallback"), where)) is not None
        ),
        method_symbols=method_symbols,
        programs=programs_of(workspace, index),
    )
    params = request_param_calls(catalog)
    # Each handler's own parameter names (`request_param_rows`): a string a parameter
    # decorator writes that is one of them names the parameter, not an input anyone types.
    declared = workspace.once(declared_parameters_of)

    def parameter_names(handler: str) -> frozenset[str] | None:
        """The handler's parameter names; None where it takes `**kwargs`, which may receive
        any name, so no string can be told to be a parameter's rather than a spelling."""
        parameters = declared.get(handler, ())
        if any(parameter.get("kind") == "var_keyword" for parameter in parameters):
            return None
        return frozenset(
            str(parameter["name"]) for parameter in parameters if parameter.get("name") is not None
        )

    ends = list(chain_ends(workspace, catalog, PUBLISHED_PARTS))
    mounts: MountReader | None = None
    mounted: dict[tuple[str, int], Mount] = {}
    if mount_rules is not None:
        mounts, mounted, _ = _mounts(
            ends, mount_rules, index, workspace, refuses_unrooted, catalog, entry_points
        )
    roots: dict[tuple[str | None, str | None], None] = {}
    metadata: list[dict[str, Any]] = []
    for end in ends:
        terminal = end.terminal
        if terminal is None or _site_key(end.root) in mounted or _site_key(terminal) in mounted:
            # A group's chain makes the router its commands are mounted on: no row of its own.
            continue
        # A chain end is a command only where its root is a declared registration, matched as
        # the walk matches one (`_matching_root`: a subclass's call is its base's, as a
        # `class MyGroup(click.Group)`'s `command` is). The walk also hands back ends with no
        # declared root (a `__call__` walked back to nothing), which register nothing.
        if _matching_root(dict(end.root), list(registrations)) is None:
            continue
        captured = end.captures.get("handler")
        at = captured.get(_CAPTURED_AT) if isinstance(captured, dict) else None
        site = index.sites.get((str(at[0]), int(str(at[1])))) if at is not None else None
        if site is None or at is None:
            continue
        handlers = _entry_handlers(index, site, int(at[2]), entry_points.method_symbols)
        if not handlers:
            # The walk ended at a library decorator no value model states (`pass_context`,
            # `with_appcontext`): the command is registered, and which function runs is not
            # read. Its row keeps its path with no handler, and no parameter row, since no
            # decorator can be linked to a function nothing names.
            for path in _entry_paths(end, None, mounts, entry_points, workspace, index):
                roots.setdefault((None, path))
            continue
        decorators = decorators_passed(index, site, int(at[2]))
        for handler in handlers:
            for path in _entry_paths(end, handler, mounts, entry_points, workspace, index):
                roots.setdefault((handler, path))
                for maker in decorators:
                    row = index.sites[maker]
                    entry = params.get((str(row.get("owner")), str(row["name"])))
                    if entry is None:
                        continue
                    for kind, name, requirement, resolution in request_param_rows(
                        entry, list(row["arguments"] or []), parameter_names(handler)
                    ):
                        metadata.append(
                            {
                                "protocol": None,
                                "direction": "inbound",
                                "method": None,
                                "path": path,
                                "caller": handler,
                                "kind": kind,
                                "name": name,
                                "value": None,
                                "resolution": resolution,
                                "evidence": str(Evidence.DECLARED),
                                "requirement": requirement,
                            }
                        )
    rows = [
        {
            "handler": handler,
            "root_kind": str(RootKind.ENTRY_POINT),
            "protocol": None,
            "method": None,
            "path": path,
            "method_kind": None,
            "path_kind": None,
        }
        for handler, path in sorted(
            roots, key=lambda key: (key[0] is not None, key[0] or "", key[1] or "")
        )
    ]
    if rows:
        workspace.derive("roots_insert", rows=rows)
    if metadata:
        workspace.derive("endpoint_metadata_insert", rows=metadata)


def _entry_handlers(
    index: ValueIndex,
    site: Mapping[str, Any],
    slot: int,
    method_symbols: Mapping[str, str],
    within: Path | None = None,
) -> tuple[str, ...]:
    """The function each path of the handler argument at `site`'s `slot` reaches, as a call of
    it would (`producer_paths(..., functions=True)`), joined to its full method symbol; in
    path order, each once. Only the paths agreeing with `within`, where one is given: the
    handler one call hands a factory, read on that call (M-1)."""
    found: list[str] = []
    for producer, path in producer_paths(index, site, slot, frozenset(), functions=True):
        if within is not None and path.joined(within) is None:
            continue
        body = None if producer.ended_at is None else called_function(producer.ended_at)
        symbol = None if body is None else method_symbols.get(body)
        if symbol is not None and symbol not in found:
            found.append(symbol)
    return tuple(found)


def _entry_paths(
    end: ChainEnd,
    handler: str | None,
    mounts: MountReader | None,
    entry_points: _EntryPoints,
    workspace: Workspace,
    index: ValueIndex,
) -> tuple[str | None, ...]:
    """Every command path `end` registers `handler` at: its own word (the `url` capture, else
    `path_fallback` over the handler's name) behind each prefix its router is served under,
    words joined by one space, the outermost word the program's name. NULL where the
    command's own word was not read."""
    words = _own_words(end, handler, entry_points, workspace, index)
    prefixes = mounts.of_route(end.root, end.path) if mounts is not None else (ROOT,)
    terminal = end.terminal
    program = (
        None if terminal is None else entry_points.programs.get(_site_key(terminal), UNREAD_PROGRAM)
    )
    found: list[str | None] = []
    for prefix in prefixes:
        for word in words:
            path: str | None
            if word is None:
                path = None
            elif prefix.text is not None:
                path = join_prefix(prefix.text, word, WORDS)
            elif mounts is not None and any(place[-1][0] for place in prefix.places):
                path = mounts.outermost(prefix, word)
            elif _made_on_something(end.root):
                # Registered ON an object the router walk could not pin to a call (a group a
                # subclass's constructor made): there is a router, and which program it is
                # cannot be read, so the command's word stays behind the hole.
                path = join_prefix(UNREAD_PROGRAM, word, WORDS)
            else:
                # No router: the command is the program, started by its installed name.
                path = program
            if path not in found:
                found.append(path)
    return tuple(found)


def _made_on_something(site: Mapping[str, Any]) -> bool:
    """Whether a call is made on a receiver at all (D00 §5: a value id, a field or a
    parameter), rather than on nothing, as a module function is called."""
    return any(
        site.get(key) is not None for key in ("receiver", "receiver_field", "receiver_parameter")
    )


def _own_words(
    end: ChainEnd,
    handler: str | None,
    entry_points: _EntryPoints,
    workspace: Workspace,
    index: ValueIndex,
) -> tuple[str | None, ...]:
    """A command's own word(s): each string the root's `url` capture reads on the chain's
    path, or, where the root writes no argument for it, the handler's name as the
    `path_fallback` respells it; None where neither gives a word."""
    url = end.captures.get("url")
    if url is None:
        fallback = entry_points.fallback_of(end.root)
        # A word from the handler's name needs a handler: an unread one names no word.
        if fallback is None or handler is None:
            return (None,)
        return (fallback_word(fallback, method_name(bare_descriptor(handler))),)
    at = url.get(_CAPTURED_AT) if isinstance(url, dict) else None
    site = index.sites.get((str(at[0]), int(str(at[1])))) if at is not None else None
    if site is None or at is None:
        return (None,)
    words: list[str | None] = []
    for answers in resolve_positions(
        workspace, {"url": (site, int(at[2]))}, index, within=end.path
    ):
        answer = answers["url"]
        word = (
            str(answer.value)
            if answer.kind == LITERAL and answer.literal_kind == STRING and not answer.inexact
            else None
        )
        if word not in words:
            words.append(word)
    return tuple(words) or (None,)


def _fallback_word(end: ChainEnd, entry_points: _EntryPoints) -> str | None:
    """A mount chain's own word from its handler's name (`path_fallback`), or None where its
    handler is not a function this module names or no fallback is declared."""
    fallback = entry_points.fallback_of(end.root)
    handler = _handler_symbol(end.captures.get("handler"), dict(entry_points.method_symbols))
    if fallback is None or handler is None:
        return None
    return fallback_word(fallback, method_name(bare_descriptor(handler)))


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
    seen: dict[tuple[str, str, str, str, str | None, str | None, str | None], "_Kept"]
    # The rows of no identity `seen` holds, by the call each came from (`_derive_captured`).
    exact: dict[tuple[Any, ...], "_Kept"]
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
    # DR-6 (Vert.x spec §3a). `matches.refuses_unrooted_path`: the framework THROWS on a
    # served path that is empty or has no leading `/`, where another repairs it, so a
    # resolved path of that shape is filed in `refusals` and derives no row. False for
    # every catalog not declaring it, whose paths are repaired as they always were.
    refuses_unrooted: bool = False
    refusals: dict[tuple[str, str | None, str | None], dict[str, Any]] | None = None
    # The catalog's roots, so a refusal is filed under the verb its ROOT named
    # (`_root_verb`): the framework throws when the route is made, before any later step.
    roots: Sequence[dict[str, Any]] = ()
    # Vert.x spec §3a. `matches.verbless_serves`: what a chain that never captured a verb
    # serves — `any` (`ANY_METHOD`) for a framework whose route with no verb answers every
    # verb, written on the row as `method_kind` beside its NULL method. None for every
    # catalog not declaring it, whose verbless row says nothing about verbs.
    verbless_serves: str | None = None
    # `matches.pathless_serves`: the path a chain that never captured an address serves, in
    # the framework's own spelling (`/*`). None for every catalog not declaring it, whose
    # address-less chain reads as an unread address.
    pathless_serves: str | None = None
    # The workspace and the walk's index, for the hop ladders (Task 9), shared with the
    # walk (`values.cached_value_index`).
    workspace: "Workspace | None" = None
    values: "ValueIndex | None" = None
    # The path the end being derived was walked back across methods by (`ChainEnd.path`,
    # ruling 5, spec 2026-10-30): its captures are read on that path alone, so each caller
    # of a shared helper reads its own arguments. None for a chain walked from its root.
    path: Path | None = None
    # Vert.x spec §3b, for a catalog declaring `passes_on`: each handler argument's outcome
    # (`_judge`), the inbound rows held back until every chain is read so that the routes on
    # one verb and path are ordered (`_settle`), and the `handler_pass_through` questions of
    # the rows whose handler is not readable here. None, None and None for every other
    # catalog, whose rows are written as they are derived, the first handler answering.
    judged: "dict[Any, _Judged] | None" = None
    candidates: "list[_Candidate] | None" = None
    unread: dict[tuple[str, str | None, str | None], dict[str, Any]] | None = None
    # Vert.x spec §3c, for a catalog declaring `mount`: the prefixes each route's router is
    # served under (`shapes.mounts`). None for every other catalog, and for a module with no
    # mount, whose routes serve at their root as read.
    mounts: MountReader | None = None
    # Which router a held-back route is made on and through which mounts it is served
    # (`Prefix.places`), for `_settle`: the mount reader where there is one, one reading
    # routers alone otherwise. None for a catalog declaring no `mount`, whose routes are
    # ordered as if on one router.
    routers: MountReader | None = None
    unread_prefixes: dict[tuple[str, str | None, str], dict[str, Any]] | None = None
    # The root call of the end being derived (`ChainEnd.root`), for a `client_base` whose client
    # is that call's receiver (`client_arg: receiver`, Vert.x spec §3d). None otherwise.
    root: Mapping[str, Any] | None = None
    # `matches.response_fallback` (N9): where an inbound chain's `response` capture writes no
    # argument, the response is read from the handler. None for every catalog not declaring
    # it, whose unwritten response capture reads as unread, as it always has.
    response_fallback: "_ResponseFallback | None" = None
    # The prefixes the end being derived serves under, read once (`_derive`); None until then.
    prefixes: tuple[Prefix, ...] | None = None
    # `matches.request_params` on an inbound catalog whose entries name the marker calls a
    # handler's parameters carry (plan 2026-11-08-python-fastapi-inbound N3, N4), read on each
    # row with the request body (`_row_parameters`). None for every other catalog.
    parameter_rules: ParameterRules | None = None
    # The recipes the rows' framework runs before their handlers (`_row_parameters`), as
    # `roots` rows to write (N11), and the recipe calls a `dependencies=` position names,
    # read once (`_dependency_calls`). None for a catalog that reads no parameters.
    recipe_roots: (
        dict[tuple[str, str | None, str | None, str | None, str | None, str | None], None] | None
    ) = None
    dependency_calls: dict[Any, tuple[Mapping[str, Any], ...]] | None = None
    # A model's fields as its shape model names them, for a model marked as a set of request
    # parameters (R25, `expansion.ModelFields`). None where the catalog reads no parameters or
    # its shape model reads no names off calls.
    model_fields: "ModelFields | None" = None
    # OI-368: where the calls that register a row run (`registration_conditions`), and each
    # inbound row with the alternatives of the calls that made it, written to
    # `endpoint_existence` once the rows are. None where no call of the module is under a test.
    conditions: Conditions | None = None
    registrations: list[tuple[dict[str, Any], Alternatives]] | None = None


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
    row.

    **Each prefix is read on its own call** (M-1): where the route's prefixes were reached on
    several paths — a factory building a router per call, included per call — the route is
    derived once per path, its captures (path, verbs, handler) read on that path alone and
    with that path's prefixes, so one call's prefix never pairs with another call's capture."""
    if (
        context.prefixes is None
        and context.routers is not None
        and end.root
        and end.captures.get(_DIRECTION, context.catalog.direction) == "inbound"
    ):
        prefixes = context.routers.of_route(end.root, end.path)
        for path, served in _per_call(prefixes, context.path):
            _derive(end, replace(context, path=path, prefixes=served))
        return
    captures = dict(end.captures)
    if _COMPOSE in captures:
        composed_field, halves, join = captures[_COMPOSE]
        captures = {**captures, composed_field: _composed_field(halves, join, captures, context)}
    if _OPTIONS not in captures:
        _derive_captured(end, captures, context)
        return
    # A request made from an options object (spec 2026-11-02 rule 4): one reading per path the
    # object is read on, each its own row, never one merged answer. An inexact path is no surer
    # than `partial`, as a chain the walk back reached inexactly is.
    for filled, exact in _with_request_options(captures, context):
        _derive_captured(end if exact else replace(end, inexact=True), filled, context)


def _derive_captured(end: ChainEnd, captures: dict[str, Any], context: "_DeriveContext") -> None:
    """`_derive`'s row for one reading of the chain's captures."""
    # Spec 2026-09-21 §4: the root's own direction where it declared one,
    # the catalog's otherwise — read once, because every column and key
    # below that names a direction names this one.
    direction = captures.get(_DIRECTION, context.catalog.direction)
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
    # Spec §3b: the chain's handlers run in order until one does not pass the request on; that
    # one names the row. None where every one passes on: middleware, no row.
    answering = _answering(captures.get("handler"), context)
    last_handler = answering.symbol if answering is not None else None
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
                _answering_symbol(captures[_LINK_SENDER], context)
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
    # A verb list the call does not write as literals (N8): read through the value walk.
    if _unread_verbs(declared_verb):
        declared_verb = _walked_verbs(declared_verb, context)
    # Several verbs accumulated on one chain (`repeats`) are one row each (Vert.x spec §3f:
    # `method(GET).method(DELETE)` serves both), in call order, a repeated verb once. One
    # nobody could read is a row of its own, `unresolved` with `method` NULL, so the list
    # never claims to be complete.
    verbs = list(
        dict.fromkeys(
            _verb_of(each, context)
            for each in (declared_verb if isinstance(declared_verb, tuple) else (declared_verb,))
        )
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
    # A verbless route of a framework that serves it for every verb says so on the row
    # (`method_kind`, Vert.x spec §3a), never by the NULL method alone, which reads as "nobody
    # read the verb".
    method_kind = context.verbless_serves if verbless and direction == "inbound" else None
    # What the address is (`url_is`): a pattern is published verbatim and linked by nothing.
    path_kind = _URL_IS.get(str(captures.get("url_is")))
    # `disable()` without a later `enable()`, or `remove()`: the framework serves nothing.
    serving = captures.get(_SERVES, True) is True
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
            destinations = (
                _walked_channels(channel_argument, context, channel_via_forms, context.path)
                or literal
            )
        else:
            destinations = literal
    elif (
        context.pathless_serves is not None
        and direction == "inbound"
        and not any(field in captures for field in _ADDRESS_FIELDS)
    ):
        # A route that never named a path serves every path, in the framework's own spelling
        # (`pathless_serves`), read in full: the framework stores no path, and that is exact.
        destinations = [(None, context.pathless_serves, str(Resolution.RESOLVED))]
    else:
        # One per url argument, and per path the client's defaults are read on (rule 4): a
        # destination two paths give alike is one.
        destinations = list(
            dict.fromkeys(
                destination
                for url_argument in (
                    _url_arguments(captures, context) if "url" in captures else [None]
                )
                for destination in _composed_address(captures, context, url_argument)
            )
        )
    # Computed once, outside the destinations loop — the same
    # `single_call` reasoning: neither depends on peer/path/resolution, and
    # `argument_descriptor` appends to the shared `referenced` accumulator,
    # so calling it once per row rather than once per destination keeps
    # that list from carrying the same shape root once per channel.
    request_shape = argument_descriptor(body_argument, context.facts, context.carrier_rules)
    # A response type the call names through a module name (`response_model=Out`, `Out` imported
    # from another file) is the class that name holds, read through the value walk.
    response_argument = _class_named(response_argument, context)
    response_shape = _response_descriptor(
        response_argument, captures.get("response_is"), context.facts, context.carrier_rules
    )
    # Checkpoint ruling I1: a declared response capture that was not read drops the row.
    response = _Response(
        response_shape,
        _capture_resolved("response" in captures, response_argument, response_shape),
    )
    # N9: a response capture that writes nothing is read from the handler instead.
    if (
        context.response_fallback is not None
        and "response" in captures
        and response_argument is None
        and direction == "inbound"
    ):
        response = _handler_response(answering, context.response_fallback, context)
        response_shape = response.shape
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
            _answering_symbol(captures[_LINK_SENDER], context)
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
    # The media a served route declares; an outbound row serves nothing, so it carries none.
    consumes, produces = media_columns(captures) if direction == "inbound" else (None, None)
    # DR-6: a registration the framework raises on derives no row, and is filed once per
    # address it names: a verb list written empty (N8, ruling R1), or a response type the
    # framework cannot build (N9).
    refused = (
        NO_METHODS
        if declared_verb == ()
        else INVALID_RESPONSE_TYPE
        if response is _REFUSED_RESPONSE
        else None
    )
    if refused is not None:
        if direction == "inbound" and context.refusals is not None:
            for verb, (_, path, _) in product(verbs or [None], destinations):
                file_refusal(
                    context.refusals,
                    protocol=context.catalog.protocol,
                    method=verb,
                    method_kind=method_kind,
                    path=path,
                    reason=refused,
                    caller=context.caller,
                    handler=handler,
                )
        return
    # Vert.x throws at `route("bad")`, before any `method(…)` on the route runs: a refused path
    # is ONE refusal, under the verb the root named, however many verbs the chain went on to
    # add (`file_refusal` keeps one row per address).
    refused_verb = _root_verb(end, context) if context.refuses_unrooted else None
    # Spec §3c: every prefix the route's router is served under, one row each; the root alone
    # where no mount received it. Read by the router reader of a module that mounts nothing
    # too, for the router each prefix places the route on (`_settle`).
    prefixes: tuple[Prefix, ...] = (ROOT,)
    if context.prefixes is not None and direction == "inbound":
        prefixes = context.prefixes
    elif context.routers is not None and direction == "inbound" and end.root:
        prefixes = context.routers.of_route(end.root, end.path)
    # OI-368: where the calls making the row run, per prefix (the includes and mounts it is
    # served through), read once per prefix.
    existing: dict[int, Alternatives | None] = {}
    for verb, (peer, path, url_resolution), prefix in product(verbs, destinations, prefixes):
        # An address nobody read takes no prefix: one row for it, not one per prefix.
        if path is None and prefix is not prefixes[0]:
            continue
        if id(prefix) not in existing:
            existing[id(prefix)] = _existence(end, prefix, direction, context)
        alternatives = existing[id(prefix)]
        # 2O design §8, folded in from single_call: identity is the URL the
        # framework serves, canonicalized before the dedup key below is built
        # from it (`domain/paths.py`). Inert for every fluent catalog shipped
        # today, all of which are outbound — R8's exclusion, stated here
        # rather than left implicit, because a future inbound fluent catalog
        # would need it and would otherwise have to rediscover it.
        if path is not None and serves_urls(context.catalog.protocol, direction):
            # DR-6: a path the framework refuses is recorded and never reaches the
            # canonicaliser, whose leading-slash repair would serve an address the
            # framework does not. The framework looks at the first character alone, so a
            # partly read path is refused too where that character was read (`"bad" + id`);
            # one whose first piece is unread (`prefix + "/x"`) is undecided and keeps
            # today's behaviour (`inbound_routes.is_unrooted`).
            if (
                context.refuses_unrooted
                and direction == "inbound"
                and context.refusals is not None
                and url_resolution in (str(Resolution.RESOLVED), str(Resolution.PARTIAL))
                # A pattern is never checked: Vert.x skips `checkPath` for a regex route.
                and path_kind != PATH_KIND_PATTERN
                and is_unrooted(path, url_resolution == str(Resolution.RESOLVED))
            ):
                file_refusal(
                    context.refusals,
                    protocol=context.catalog.protocol,
                    method=refused_verb,
                    method_kind=_root_method_kind(end, context),
                    path=path,
                    reason=UNROOTED_PATH,
                    caller=context.caller,
                    handler=handler,
                )
                continue
            # A framework joining by plain concatenation serves the path as written
            # (`path_join: concatenate`, ruling R23): nothing is cleaned.
            if context.catalog.matches.get("path_join") != CONCATENATE:
                path = canonical_http_path(path, path_kind)
        # A route the framework does not serve derives nothing — below a refusal, which the
        # framework raises when the route is made, before any `disable()` could run.
        if not serving:
            continue
        # Every handler passes the request on (spec §3b): middleware serves nothing of its own.
        # Below a refusal too, which the framework raises before any handler runs.
        if answering is None:
            continue
        # **The query string is not part of the address** (`OI-151`), and it comes off HERE —
        # after the canonicaliser and before the dedup key below, which is built from the
        # path and must be built from the one the row publishes. `single_call` makes the same
        # call at the same point in its own loop; one function answers for both, which is
        # `OI-144`'s lesson about two engines and one piece of evidence.
        # A pattern's `?` is a quantifier, not a query string: it keeps every character.
        path, query = (path, ()) if path_kind == PATH_KIND_PATTERN else query_entries(path)
        # The mount's prefix goes in front of the address the route itself named and the
        # framework accepted (spec §3c), at the weaker of the two words.
        if context.mounts is not None and path is not None:
            path = context.mounts.joined(prefix, path, path_kind == PATH_KIND_PATTERN)
            # A mount with an empty prefix of a route whose path below it is empty too is one
            # the framework refuses (`empty_path`, plan 2026-11-08 N7): no row, the refusal
            # filed. Decided only on a route path read whole.
            if (
                context.refusals is not None
                and url_resolution == str(Resolution.RESOLVED)
                and any(not path[offset:] for offset in prefix.empty_after)
            ):
                file_refusal(
                    context.refusals,
                    protocol=context.catalog.protocol,
                    method=verb,
                    method_kind=method_kind,
                    path=path,
                    reason=EMPTY_PATH,
                    caller=context.caller,
                    handler=handler,
                )
                continue
            url_resolution = weaker(url_resolution, prefix.resolution)
            # A prefix not read whole says where it was not read (`mount_prefix`), filed for
            # the rows the run keeps.
            if prefix.unread and context.unread_prefixes is not None:
                file_unread_prefix(
                    context.unread_prefixes,
                    protocol=context.catalog.protocol,
                    method=verb,
                    method_kind=method_kind,
                    path=path,
                    path_kind=path_kind,
                    prefix=prefix,
                    caller=context.caller,
                )
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
        # What the handler's parameters demand of a request on THIS row's path (N3, N4), and the
        # body among them: read per row, since a path variable a prefix adds is the path's.
        row_request_shape = request_shape
        parameter_entries: list[dict[str, Any]] = []
        recipes: tuple[str, ...] = ()
        if context.parameter_rules is not None and direction == "inbound" and handler is not None:
            refused_by, row_request_shape, parameter_entries, recipes = _row_parameters(
                handler,
                verb,
                path,
                url_resolution,
                context.parameter_rules,
                context,
                captures.get("dependencies"),
                prefix,
            )
            # A refused route is never published, whether or not this run files questions.
            if refused_by is not None:
                if context.refusals is not None:
                    file_refusal(
                        context.refusals,
                        protocol=context.catalog.protocol,
                        method=verb,
                        method_kind=method_kind,
                        path=path,
                        reason=refused_by,
                        caller=context.caller,
                        handler=handler,
                    )
                continue
        captures_read = (
            (verb is not None or verbless)
            # What the captures PRODUCED, the `single_call` change one engine along
            # (`OI-77`, W43's review): a body capture that filled its column did not fail.
            and _capture_resolved("body" in captures, body_argument, request_shape)
            and response.read
        )
        resolution = (
            url_resolution
            if captures_read and url_resolution != str(Resolution.UNRESOLVED)
            else str(Resolution.UNRESOLVED)
        )
        # N9: a response read from the handler that names no one type leaves the row's address
        # read and its response not, so the row is no surer than `partial`.
        if not response.whole and resolution == str(Resolution.RESOLVED):
            resolution = str(Resolution.PARTIAL)
        # A handler not readable here (spec §3b): its identity is read, whether it passes the
        # request on is decided in code this analysis does not read, so the row is `partial`
        # and a `handler_pass_through` question names that code.
        # A chain the walk back reached on an inexact path (spec 2026-11-02 rule 9, review 3
        # re-review M-B) is kept, never surer than `partial`.
        if end.inexact and resolution == str(Resolution.RESOLVED):
            resolution = str(Resolution.PARTIAL)
        read_resolution = resolution
        unreadable = answering.outcome == UNREADABLE
        if unreadable and resolution == str(Resolution.RESOLVED):
            resolution = str(Resolution.PARTIAL)
        # An inbound row of a catalog declaring `passes_on` is held back (`_settle`): which of
        # the routes on its verb and path answers is decided once every chain is read, and the
        # dedup key below is applied there, among the routes that answer.
        ranked = (
            context.candidates is not None
            and direction == "inbound"
            and path is not None
            and (verb is not None or verbless)
        )
        # Through `_metadata_row` like every other entry this engine writes, so the value is
        # masked by the same redactor on the same rule — a query parameter named
        # `access_token` is exactly the shape that matters.
        entries = [
            *(
                _metadata_row(entry, context, direction, verb, path)
                for entry in captures.get(_COLLECTED) or ()
            ),
            *(
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
                for name, value in query
            ),
            *parameter_entries,
        ]
        kept: _Kept | None = None
        if path is not None and (verb is not None or verbless) and not ranked:
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
            #
            # **An INBOUND row is keyed on what it serves instead**: `(protocol, verb,
            # path, handler)`, with no `caller` and no `peer`. The method that registered a
            # route is not part of the route's wire identity, so the same route answered by
            # the same handler, registered from two methods, is one consumer registered
            # twice; the same handler on two routes, or two handlers on one route, stay two
            # rows. A NULL handler is a valid part: two handler-less registrations of one
            # route are one row. The outbound key is unchanged.
            inbound = direction == "inbound"
            key = (
                context.catalog.protocol,
                direction,
                verb or "",
                path,
                None if inbound else context.caller,
                None if inbound else peer,
                handler if inbound else None,
            )
            # **Rule 4 for rows of one identity** (review 3 re-review 2, m-2). Every column this
            # row publishes beside its identity, with its metadata: two chains equal in all of
            # it are one request, and the row keeps the more exact resolution of the two; two
            # that differ in any of it are two requests the table cannot hold apart (one row
            # per identity, its metadata keyed to it), so the one row is true of neither alone
            # and no surer than `partial`.
            published = (
                handler,
                row_request_shape,
                response_shape,
                consumes,
                produces,
                path_kind,
                method_kind,
                entries,
            )
            seen = context.seen.get(key)
            _recipe_roots(context, recipes, verb, path, method_kind, path_kind)
            if seen is not None:
                seen.merged(published, resolution)
                _registered(context, seen.rows, alternatives)
                continue
            kept = _Kept(published)
            context.seen[key] = kept
        elif not ranked:
            # **One call gives one row** (ruled by the user 2026-11-05). A row the key above
            # does not hold (no path, or a verb not read) is not merged with another call's row
            # that reads the same: two requests whose address is not read are two rows. The
            # paths of ONE chain (rule 9) are one request, so the key is the call itself (its
            # root, its terminal, the call that sends it) with what identifies a row (verb,
            # path, caller, peer) and the channels its edges name, so no edge is dropped.
            # Paths that differ only in a published part (a body, a header) are one `partial`
            # row, the rule for rows of one identity above (round 4, ruled by the user
            # 2026-11-03); a verb or an address read on a branch stays a row of its own.
            one_call = (
                _site_key(end.root) if end.root else None,
                None if end.terminal is None else _site_key(end.terminal),
                None if end.sent_at is None else _site_key(end.sent_at),
                context.catalog.protocol,
                direction,
                verb,
                path,
                context.caller,
                peer,
                source,
                link,
                read,
            )
            published = (
                handler,
                row_request_shape,
                response_shape,
                consumes,
                produces,
                path_kind,
                method_kind,
                entries,
            )
            seen = context.exact.get(one_call)
            _recipe_roots(context, recipes, verb, path, method_kind, path_kind)
            if seen is not None:
                seen.merged(published, resolution)
                _registered(context, seen.rows, alternatives)
                continue
            kept = _Kept(published)
            context.exact[one_call] = kept
        metadata: list[dict[str, Any]] = [] if ranked else context.metadata
        # Below the dedup `continue` on purpose: a row the key already saw writes no second
        # copy of its own metadata either.
        metadata.extend(entries)
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
        row = {
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
            "request_shape": row_request_shape,
            "response_shape": response_shape,
            "consumes": consumes,
            "produces": produces,
            "path_kind": path_kind if path is not None else None,
            "method_kind": method_kind,
        }
        # Dispatch that can run several bodies (`_Judged.alternatives`) is the narrowed case
        # several handlers on one route already are: one row per answering body, each judged
        # on its own, `narrowed` among them (`_settle`). The route's metadata goes with the
        # first, since every one is the same registration.
        variants = answering.alternatives or (answering,)
        for position, variant in enumerate(variants):
            variant_row = row
            if len(variants) > 1:
                variant_resolution = read_resolution
                if variant.outcome == UNREADABLE and variant_resolution == str(Resolution.RESOLVED):
                    variant_resolution = str(Resolution.PARTIAL)
                variant_row = {**row, "handler": variant.symbol, "resolution": variant_resolution}
            variant_unread = variant.unread if variant.outcome == UNREADABLE else None
            _registered(context, [variant_row], alternatives)
            if ranked and context.candidates is not None:
                context.candidates.append(
                    _Candidate(
                        row=variant_row,
                        metadata=metadata if position == 0 else [],
                        registered=_registered_at(end),
                        unread=variant_unread,
                        places=_placed(
                            prefix, _registered_at(end), _order_of(captures.get(_ORDER))
                        ),
                    )
                )
                continue
            if len(variants) > 1 and variant_row["resolution"] == str(Resolution.RESOLVED):
                variant_row = {**variant_row, "resolution": str(Resolution.NARROWED)}
            context.rows.append(variant_row)
            if kept is not None:
                kept.rows.append(variant_row)
            if variant_unread is not None and context.unread is not None:
                file_unread(context.unread, variant_row, variant_unread)


def _existence(
    end: ChainEnd, prefix: Prefix, direction: str, context: "_DeriveContext"
) -> Alternatives | None:
    """Where the calls making an inbound row run (OI-368, `registration_conditions`): its root
    and terminal calls, and every include or mount on one serving place of `prefix` — OR-ed
    across the places. None for an outbound row, and where no call of the module is under a
    test."""
    if context.conditions is None or direction != "inbound":
        return None
    own = [_site_key(site) for site in (end.root, end.terminal) if site]
    found: set[frozenset[Any]] = set()
    for place in prefix.places or (ANY_ROUTER,):
        mounts = [at[0] for _, at in place if at is not None]
        found |= context.conditions.of_sites([*own, *mounts])
    return frozenset(found)


def _registered(
    context: "_DeriveContext", rows: Iterable[dict[str, Any]], alternatives: Alternatives | None
) -> None:
    """Each of `rows` made by calls that run where `alternatives` say (`_existence`)."""
    if alternatives is None or context.registrations is None:
        return
    context.registrations.extend((row, alternatives) for row in rows)


def _root_verb(end: ChainEnd, context: "_DeriveContext") -> str | None:
    """The verb the chain's ROOT call named — `get("bad")`'s GET, `route(PUT, "bad")`'s PUT —
    or None for a root naming none (`route("bad")`), read as the root walk read it."""
    root = _matching_root(dict(end.root), context.roots) if end.root else None
    if root is None or "http_method" not in root["captures"]:
        return None
    captured = _resolve_captures({"http_method": root["captures"]["http_method"]}, dict(end.root))
    verb = captured["http_method"]
    # A verb list (N8) names the root's verb only where it holds exactly one.
    if isinstance(verb, tuple):
        verb = verb[0] if len(verb) == 1 else None
    return _verb_of(verb, context)


def _root_method_kind(end: ChainEnd, context: "_DeriveContext") -> str | None:
    """`_root_verb`'s marker (Vert.x spec §3a): `verbless_serves` for a root that names no verb
    (`route("bad")` answers every verb), None for one that names a verb, read or not, and for
    a root the catalog's roots do not match, whose verb nobody read."""
    root = _matching_root(dict(end.root), context.roots) if end.root else None
    if root is None or "http_method" in root["captures"]:
        return None
    return context.verbless_serves


def _verb_of(argument: Any, context: "_DeriveContext") -> str | None:
    """One verb a chain captured: a literal the catalog spelled is that literal; one read off
    an argument (`A-C2`) is the string it reads as, or the static field `verb_values` names,
    and None where nothing could read it — the honest gap, not the root's default."""
    if isinstance(argument, str):
        return argument
    return _string_value(argument) or static_field_value(argument, context.verb_fields)


class _Kept:
    """The row(s) one identity published (`_derive`'s dedup key), with what the first chain to
    reach it published beside the key: a later chain of the same identity changes their
    resolution, never adds a row (review 3 re-review 2, m-2)."""

    def __init__(self, published: tuple[Any, ...]) -> None:
        self.published = published
        self.differs = False
        self.rows: list[dict[str, Any]] = []

    def merged(self, published: tuple[Any, ...], resolution: str) -> None:
        """Another chain of this identity: equal in every published column, a row keeps the
        more exact resolution of the two (a row one of several handlers answers stays
        `narrowed`); different in any, every row is no surer than `partial`."""
        if published != self.published:
            self.differs = True
        for row in self.rows:
            if self.differs:
                row["resolution"] = weaker(row["resolution"], str(Resolution.PARTIAL))
            elif (
                row["resolution"] != str(Resolution.NARROWED)
                and weaker(resolution, row["resolution"]) == row["resolution"]
            ):
                row["resolution"] = resolution


@dataclass(frozen=True)
class _Judged:
    """One handler argument's outcome (Vert.x spec §3b) and the handler a row names for it:
    the method the framework runs, or None for an object nothing in the module runs."""

    symbol: str | None
    outcome: str
    # Why an `unreadable` handler is, `(reason, detail)` each (`pass_through.Unread`), for
    # its question.
    unread: tuple[tuple[str, str], ...] = ()
    # Where dispatch can run several bodies and none passes on: each answering body, judged
    # on its own. One row each, `narrowed` (`_settle`) — the case several handlers on one
    # route already are. Empty where one body runs.
    alternatives: tuple["_Judged", ...] = ()


@dataclass(frozen=True)
class _Candidate:
    """An inbound row held back until every chain is read (`_settle`), with what orders it
    against the other routes on its verb and path."""

    row: dict[str, Any]
    metadata: list[dict[str, Any]]
    # The root call that made the route, `(method, ordinal)`: Vert.x numbers its routes as
    # they are made, so within one method the ordinal order IS the registration order.
    registered: tuple[str, int]
    unread: tuple[tuple[str, str], ...] | None
    # Where the route stands (`Place`): each router it is served from, outermost first, with
    # the mount route's place there, and its own `(registered, order)` last. Vert.x orders
    # routes within one router only (`OI-263`), and a mounted router's at its mount route.
    places: frozenset[Place] = frozenset({ANY_ROUTER})


def _judge(
    ends: Sequence[ChainEnd],
    rule: PassThroughRule,
    index: ValueIndex,
    method_symbols: dict[str, str],
    workspace: Workspace,
) -> dict[Any, _Judged]:
    """Every handler argument the chains name, judged once (Vert.x spec §3b): what it runs
    (`HandlerReader`, one producer read per argument that is not a lambda, and its declared
    static type where that read reaches no construction) and then whether that passes the
    request on (`handler_outcomes`, one backward walk per `passes_on` call)."""
    arguments: dict[Any, dict[str, Any]] = {}
    for end in ends:
        captured = end.captures.get("handler")
        for argument in captured if isinstance(captured, tuple) else (captured,):
            if isinstance(argument, dict):
                arguments.setdefault(_handler_key(argument), argument)
    # A module with the framework on its classpath and no route reads nothing more.
    if not arguments:
        return {}
    reader = HandlerReader(
        index,
        rule,
        method_symbols,
        workspace.once(declared_parameters_of),
        lambda: workspace.once(_field_types),
        workspace.once(dispatch_of),
        workspace.once(exact_methods),
    )
    read = {
        key: reader.of(argument, argument.get(_CAPTURED_AT)) for key, argument in arguments.items()
    }
    contexts = {symbol: handler.context for handler in read.values() for symbol in handler.symbols}
    outcomes, unread = handler_outcomes(index, rule.calls, contexts)
    return {key: _judged_of(handler, outcomes, unread) for key, handler in read.items()}


def _mounts(
    ends: Sequence[ChainEnd],
    rules: MountRules,
    index: ValueIndex,
    workspace: Workspace,
    refuses_unrooted: bool,
    catalog: Catalog,
    entry_points: "_EntryPoints | None" = None,
) -> tuple[MountReader | None, dict[tuple[str, int], Mount], dict[int, int]]:
    """The module's mounts (Vert.x spec §3c), by the mount call's site, the reader of the
    prefixes they give, and which way to its mount each mount chain end is (by `id`, for
    filing its refusals); None and nothing where the module mounts nothing, so its routes
    read nothing more.

    A `prefix_from: receiver_path` mount is a chain end whose terminal is the mount call: its
    path is the route's own `url` capture, read at the position the capture carries, and the
    router it mounts on is its root's receiver. A mount call in a helper walked back to each
    caller's route is one chain end per caller, and each is a way of its own (`MountPath`),
    read on its own path. A `prefix_arg` mount is a call of its own, found in one pass over
    the sites."""
    found: dict[tuple[str, int], tuple[MountRule, Mapping[str, Any], list[MountPath]]] = {}
    ways: dict[int, int] = {}
    for end in ends:
        terminal = end.terminal
        # A `chain_result` mount is matched on the chain's ROOT, and the router it mounts is
        # what the chain's terminal returns (design 2026-11-06-reading-decorators §4).
        rule = next(
            (
                rule
                for rule in rules.mounts
                if rule.prefix_arg is None
                and terminal is not None
                and rule.matches(end.root if rule.router_arg == CHAIN_RESULT else terminal)
            ),
            None,
        )
        if rule is None or terminal is None:
            continue
        mounted_by = end.root if rule.router_arg == CHAIN_RESULT else terminal
        url = end.captures.get("url")
        at = url.get(_CAPTURED_AT) if isinstance(url, dict) else None
        read = index.sites.get((str(at[0]), int(str(at[1])))) if at is not None else None
        # The mount's own word from its handler, where its route writes none
        # (`path_fallback`, design §3c): the argument is absent, not unread.
        named = (
            _fallback_word(end, entry_points)
            if entry_points is not None and "url" in end.captures and url is None
            else None
        )
        way = MountPath(
            end.root or None,
            None if read is None or at is None else (read, int(at[2])),
            pattern=_URL_IS.get(str(end.captures.get("url_is"))) == PATH_KIND_PATTERN,
            within=end.path,
            unread="url" in end.captures and read is None and named is None,
            order=_order_of(end.captures.get(_ORDER)),
            made=terminal if rule.router_arg == CHAIN_RESULT else None,
            named=named,
        )
        paths = found.setdefault(_site_key(mounted_by), (rule, mounted_by, []))[2]
        if way not in paths:
            paths.append(way)
        ways[id(end)] = paths.index(way)
    for site in index.sites.values():
        for rule in rules.mounts:
            if rule.prefix_arg is not None and rule.matches(site):
                slot = argument_slot(site["arguments"] or [], rule.prefix_arg)
                read_at = None if slot is None or slot == UNPACKED_SLOT else (site, slot)
                # A prefix argument the call does not write is the parameter's default, the
                # empty prefix: the router mounts at the parent's root. One that may be in an
                # unpacked value is not read.
                found.setdefault(
                    _site_key(site),
                    (rule, site, [MountPath(site, read_at, unread=slot == UNPACKED_SLOT)]),
                )
    # A catalog whose routers hold a prefix of their own (`router_holds`) reads it even where
    # the module mounts nothing.
    if not found and not rules.holds:
        return None, {}, {}
    mounts = {key: Mount(rule, site, tuple(paths)) for key, (rule, site, paths) in found.items()}
    reader = _router_reader(
        index,
        workspace,
        rules,
        list(mounts.values()),
        refuses_unrooted,
        catalog,
        None if entry_points is None else entry_points.programs,
    )
    return reader, mounts, ways


def _router_reader(
    index: ValueIndex,
    workspace: Workspace,
    rules: MountRules,
    mounts: Sequence[Mount],
    refuses_unrooted: bool,
    catalog: Catalog,
    programs: Mapping[tuple[str, int], str] | None = None,
) -> MountReader:
    """The reader of which router a route is made on and what serves it, over `mounts`."""
    configuring = configuring_calls(catalog, index.sites.values())
    dispatch = workspace.once(dispatch_of)
    declared = router_producers(index, rules.router_types, dispatch.ancestors, configuring)
    return MountReader(
        workspace,
        index,
        rules,
        declared,
        mounts,
        refuses_unrooted,
        configuring,
        programs,
        dispatch if rules.holds else None,
    )


def _judged_of(
    handler: Handler,
    outcomes: Mapping[str, str],
    unread: Mapping[str, tuple[tuple[str, str], ...]],
) -> _Judged:
    """One handler argument's outcome from its methods' (`handler_outcomes`): it passes on if
    any of them does, is not readable here if any is (a method with no body among them
    included), and answers otherwise. Where dispatch can run several bodies, each is judged
    on its own as an alternative, with its own reasons alone."""
    if handler.outcome is not None:
        return _Judged(None, handler.outcome, (handler.unread,) if handler.unread else ())
    found = {outcomes[symbol] for symbol in handler.symbols}
    names = {entry for symbol in handler.symbols for entry in unread.get(symbol, ())}
    # A handler method with no body among them (`HandlerReader._runs`) is not readable here
    # unless another of them passes on.
    if handler.unread is not None:
        found.add(UNREADABLE)
        names.add(handler.unread)
    alternatives: tuple[_Judged, ...] = ()
    if len(handler.alternatives) > 1:
        # The no-body reason belongs to the method that has no body, never to an alternative
        # whose own body was read.
        bodiless = handler.bodiless
        alternatives = tuple(
            _Judged(
                symbol,
                UNREADABLE if symbol == bodiless else outcomes[symbol],
                tuple(
                    sorted(
                        {
                            *unread.get(symbol, ()),
                            *((handler.unread,) if symbol == bodiless and handler.unread else ()),
                        }
                    )
                ),
            )
            for symbol in handler.alternatives
        )
    return _Judged(
        handler.symbols[0],
        next(o for o in (PASSES_ON, UNREADABLE, ANSWERS) if o in found),
        tuple(sorted(names)),
        alternatives,
    )


def _field_types(workspace: Workspace) -> dict[str, str]:
    """Each field's declared type, by bare field descriptor — the `Workspace.once` builder the
    pass-through reader asks only where a handler comes from a field."""
    found: dict[str, str] = {}
    for row in workspace.query("fields"):
        returns = row.get("returns")
        declared = json.loads(returns) if isinstance(returns, str) else returns
        if isinstance(declared, dict) and declared.get("symbol"):
            found[bare_descriptor(str(row["symbol"]))] = str(declared["symbol"])
    return found


def _handler_key(argument: dict[str, Any]) -> tuple[Any, ...]:
    """A handler argument's identity: what it names and the site and slot it was read at."""
    return (argument.get("kind"), str(argument.get("symbol")), argument.get(_CAPTURED_AT))


def _answering(captured: Any, context: "_DeriveContext") -> _Judged | None:
    """The handler a chain's row names (Vert.x spec §3b): the first of its handlers, in call
    order, that does not pass the request on, or None where every one does. A catalog
    declaring no `passes_on` has none that passes on, so its first handler answers."""
    arguments = captured if isinstance(captured, tuple) else (captured,)
    if context.judged is None:
        first = arguments[0] if arguments else None
        walked = _walked_handler(first, context)
        if walked is not None:
            return walked
        return _Judged(_handler_symbol(first, context.method_symbols), ANSWERS)
    for argument in arguments:
        judged = context.judged.get(_handler_key(argument)) if isinstance(argument, dict) else None
        if judged is None:
            return _Judged(_handler_symbol(argument, context.method_symbols), ANSWERS)
        if judged.outcome != PASSES_ON:
            return judged
    return None


def _answering_symbol(captured: Any, context: "_DeriveContext") -> str | None:
    answering = _answering(captured, context)
    return answering.symbol if answering is not None else None


def _registered_at(end: ChainEnd) -> tuple[str, int]:
    root = end.root
    return (str(root["caller"]), int(str(root["ordinal"]))) if root else (end.caller, -1)


def _order_of(captured: Any) -> int | str | None:
    """The order a chain set (`order: argN` or `order: last`, last call wins): a literal
    integer, `last`, None where none was set, or `_UNREAD_ORDER` where the argument is not a
    literal."""
    if captured is None:
        return None
    if captured == _LAST:
        return _LAST
    if isinstance(captured, dict) and isinstance(captured.get("value"), int):
        return int(captured["value"])
    return _UNREAD_ORDER


def _placed(
    prefix: Prefix, registered: tuple[str, int], order: int | str | None
) -> frozenset[Place]:
    """Where a route stands (`_Candidate.places`): the places its prefix was reached on, or a
    router nothing names, each ending with the route's own registration and order."""
    return frozenset(
        (*place[:-1], (place[-1][0], (registered, order)))
        for place in prefix.places or (ANY_ROUTER,)
    )


def _runs_before(first: _Candidate, then: _Candidate) -> bool:
    """Whether Vert.x certainly tries `first` before `then` (spec §3b): wherever either
    stands, the other stands on a router it meets, and every meeting tries `first` first
    (`_meets`). A router orders its own routes alone; a route on a router the other is not
    certainly on is in no known order against it."""
    met = [[_meets(one, other) for other in then.places] for one in first.places]
    return (
        all(any(meeting is not None for meeting in row) for row in met)
        and all(any(meeting is not None for meeting in column) for column in zip(*met))
        and all(meeting is not False for row in met for meeting in row)
    )


def _meets(first: Place, then: Place) -> bool | None:
    """Where two routes' places meet, whether `first` is certainly tried there before `then`;
    None where they never do — two routers made by two calls. A route served through a mount
    competes with the parent's own routes at the mount route's place, so they meet on the
    outermost router both are served from, and through one mount route on the next."""
    for (router, at), (other, other_at) in zip(first, then):
        if router is not None and other is not None and not same_router(router, other):
            return None
        if at != other_at:
            return at is not None and other_at is not None and _tried_before(at, other_at)
    return False


def _tried_before(
    first: tuple[tuple[str, int], int | str | None], then: tuple[tuple[str, int], int | str | None]
) -> bool:
    """Whether one router certainly tries the route at `first` before the one at `then`, each
    `(registered, order)`. Routes run by order; a route's own order is the router's count when
    it was made, so two routes nobody ordered are in root-call order within one method and in
    no known order across two. A literal `order(int)` orders against another literal, `last()`
    puts a route after every route not last, and equal orders fall back to registration. A
    route with an unread order, or one ordered against an unordered one, is in no known
    order."""
    (registered, order), (then_registered, then_order) = first, then
    if _UNREAD_ORDER in (order, then_order):
        return False
    if (order == _LAST) != (then_order == _LAST):
        return then_order == _LAST
    if isinstance(order, int) and isinstance(then_order, int) and order != then_order:
        return order < then_order
    if (order is None) != (then_order is None):
        return False
    return registered[0] == then_registered[0] and registered[1] < then_registered[1]


def _settle(
    candidates: list[_Candidate],
    rows: list[dict[str, Any]],
    metadata: list[dict[str, Any]],
    unread: dict[tuple[str, str | None, str | None], dict[str, Any]],
) -> None:
    """The held-back inbound rows that answer (Vert.x spec §3b), written once every chain is
    read. Routes on one verb and path are one wire identity, tried in order: a route some
    other route certainly precedes never runs, since the one before it answers. Of those
    left, one handler is one row (Task 6's key, `resolved`); several handlers are each a row,
    `narrowed` — one of them answers, the code does not say which. Only where they can be on
    one router (`_may_share_router`): each router answers its own requests, so two routers'
    routes on one verb and path are each their router's answer (`OI-263`)."""
    groups: dict[tuple[Any, ...], list[_Candidate]] = {}
    for candidate in candidates:
        row = candidate.row
        groups.setdefault((row["protocol"], row["method"] or "", row["path"]), []).append(candidate)
    for group in groups.values():
        # One handler is one row; two handler objects nothing names (handler NULL) are two
        # registrations, each with its own reason, never merged on the NULL.
        standing = [
            candidate
            for candidate in group
            if not any(_runs_before(other, candidate) for other in group if other is not candidate)
        ]
        kept: dict[Any, _Candidate] = {}
        rivalled: set[Any] = set()
        for candidate in standing:
            key = _row_key(candidate)
            kept.setdefault(key, candidate)
            if any(
                _row_key(other) != key and _may_share_router(other, candidate) for other in standing
            ):
                rivalled.add(key)
        for key, candidate in kept.items():
            row = candidate.row
            if key in rivalled and row["resolution"] == str(Resolution.RESOLVED):
                row = {**row, "resolution": str(Resolution.NARROWED)}
            rows.append(row)
            metadata.extend(candidate.metadata)
            if candidate.unread is not None:
                file_unread(unread, row, candidate.unread)


def _row_key(candidate: _Candidate) -> Any:
    """`_settle`'s row key: the handler, or the registration for a handler nothing names."""
    handler = candidate.row["handler"]
    return handler if handler is not None else candidate.registered


def _may_share_router(first: _Candidate, then: _Candidate) -> bool:
    """Whether two routes can meet on one router (`_meets`): unless every place of each is on
    routers made by other calls than the other's."""
    return any(_meets(one, other) is not None for one in first.places for other in then.places)


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


def _row_parameters(
    handler: str,
    verb: str | None,
    path: str | None,
    address: str,
    rules: ParameterRules,
    context: "_DeriveContext",
    dependencies: Any = None,
    prefix: Prefix = ROOT,
) -> tuple[str | None, str | None, list[dict[str, Any]], tuple[str, ...]]:
    """What the handler's parameters demand of a request on one row (plan
    2026-11-08-python-fastapi-inbound N3, N4): the reason the framework refuses the registration
    (None where it does not), the request body's descriptor, and one `endpoint_metadata` entry
    per request parameter (`request_requirements.read_parameters`), `caller` the handler as on
    every inbound entry. The body is the parameter the catalog's `request_body` rule picks with
    each parameter's marker call and kind beside its signature (`contracts._body_parameter`).
    A handler whose parameters were not read demands nothing that can be said.

    **The recipes the framework runs first** (N5, N6), last: each a handler parameter's marker
    names, and each the row's `dependencies=` name (the route's own, `dependencies`, and every
    router's and include's it is served through, `MountReader.dependencies_of` on `prefix`).
    Their own parameters join the row's, recursively (`request_requirements.read_dependant`),
    and the bodies that run are returned for the row's `roots` (N11)."""
    workspace, index = context.workspace, context.values
    if workspace is None or index is None:
        return None, None, [], ()
    declared = workspace.once(declared_parameters_of)
    parameters = declared.get(handler)
    if parameters is None:
        return None, None, [], ()
    markers = parameter_markers(index)
    carrier = context.carrier_rules
    dispatch = workspace.once(dispatch_of)

    def kind_of(reference: Mapping[str, Any]) -> bool | None:
        return is_scalar(
            reference,
            carrier.rules.known_types,
            carrier.enums,
            lambda symbol: symbol in dispatch.scanned or symbol in dispatch.headers,
        )

    variables = _path_variables(frozenset() if path is None else frozenset({path}))
    models = None if context.model_fields is None else context.model_fields.of
    reading = read_parameters(
        rules,
        parameters,
        lambda position: markers.get((handler, position), ()),
        variables,
        kind_of,
        weaker(str(Resolution.RESOLVED), address),
        models,
    )
    if reading.refused is not None:
        return reading.refused, None, [], ()
    recipe_calls = index.recipes.calls
    rows = list(reading.rows)
    recipes: tuple[str, ...] = ()
    if recipe_calls:
        calls: list[tuple[Mapping[str, Any], tuple[str, int] | None]] = [
            (site, (handler, position))
            for position in range(len(parameters))
            for site in recipe_sites(markers.get((handler, position), ()), recipe_calls)
        ]
        calls.extend((site, None) for site in _dependency_calls(dependencies, prefix, context))
        dependant = read_dependant(
            rules,
            calls,
            lambda call, parameter: recipe_bodies(index, call, parameter),
            declared.get,
            lambda method, position: markers.get((method, position), ()),
            lambda found: recipe_sites(found, recipe_calls),
            variables,
            kind_of,
            weaker(str(Resolution.RESOLVED), address),
            models,
        )
        rows.extend(row for row in dependant.rows if row not in reading.rows)
        recipes = dependant.recipes
    every: list[tuple[int, dict[str, Any]]] = []
    body = _body_type(
        {"parameters": list(parameters)},
        context.catalog,
        owner=handler,
        paths=frozenset() if path is None else frozenset({path}),
        index={},
        members={},
        calls=reading.calls,
        scalars={
            position: kind_of(parameter["type"]) for position, parameter in enumerate(parameters)
        },
        every=every,
    )
    declared_body = context.catalog.matches.get("request_body") or {}
    shape: str | None
    if len(every) > 1 or (
        len(every) == 1 and _embeds_one(every[0][0], every[0][1], reading, declared_body, context)
    ):
        shape = _embedded_body(every, reading, declared_body, context)
    else:
        shape = payload_descriptor(
            body, carrier.rules, carrier.enums, context.facts.referenced, carrier.rules.wrappers
        )
    entries = [
        {
            "protocol": context.catalog.protocol,
            "direction": "inbound",
            "method": verb,
            "path": path,
            "caller": handler,
            "kind": kind,
            "name": name,
            "value": None,
            "resolution": resolution,
            "evidence": str(Evidence.DECLARED),
            "requirement": requirement,
        }
        for kind, name, requirement, resolution in rows
    ]
    return None, shape, entries, recipes


def _dependency_calls(
    dependencies: Any, prefix: Prefix, context: "_DeriveContext"
) -> tuple[Mapping[str, Any], ...]:
    """The recipe calls the `dependencies=` a row runs name (N6): the route's own captured
    argument, read on the row's path, then every router's and include's it is served through
    (`MountReader.dependencies_of`), each element of a list its own call, each position read
    once per path (`_DeriveContext.dependency_calls`)."""
    index = context.values
    if index is None:
        return ()
    positions: list[tuple[Mapping[str, Any], int, Path | None]] = []
    at = dependencies.get(_CAPTURED_AT) if isinstance(dependencies, dict) else None
    site = None if at is None else index.sites.get((str(at[0]), int(str(at[1]))))
    if site is not None and at is not None:
        positions.append((site, int(at[2]), context.path))
    reader = context.mounts or context.routers
    if reader is not None:
        positions.extend(reader.dependencies_of(prefix))
    found: dict[tuple[str, int], Mapping[str, Any]] = {}
    cache = context.dependency_calls if context.dependency_calls is not None else {}
    for written, slot, path in positions:
        key = (str(written["caller"]), int(str(written["ordinal"])), slot, path)
        if key not in cache:
            cache[key] = tuple(
                call
                for call in producing_calls(index, written, slot, within=path)
                if (str(call.get("owner")), str(call["name"])) in index.recipes.calls
            )
        for call in cache[key]:
            found.setdefault((str(call["caller"]), int(str(call["ordinal"]))), call)
    return tuple(found.values())


def _recipe_roots(
    context: "_DeriveContext",
    recipes: Sequence[str],
    verb: str | None,
    path: str | None,
    method_kind: str | None,
    path_kind: str | None,
) -> None:
    """One `roots` row per recipe the row's framework runs before its handler (N11): at the
    row's own address, `inbound_endpoint`, so the trace from that address starts at each."""
    if context.recipe_roots is None:
        return
    for recipe in recipes:
        context.recipe_roots.setdefault(
            (
                recipe,
                context.catalog.protocol,
                verb,
                path,
                method_kind,
                path_kind if path is not None else None,
            )
        )


def _embeds_one(
    position: int,
    parameter: Mapping[str, Any],
    reading: ParameterReading,
    declared: Mapping[str, Any],
    context: "_DeriveContext",
) -> bool:
    """Whether the framework embeds its ONE body parameter in an object (FastAPI's
    `_should_embed_body_fields`): its marker writes `request_body.embed_arg` as the literal
    `True` (`Body(embed=True)`), or its marker is one of `embed_markers.calls` (`Form`, `File`)
    and its type is no subtype of an `embed_markers.unless_subtype_of` type (a model is read
    whole; a form field is a key of the form) by the module's type hierarchy."""
    marker = reading.marked.get(position)
    if marker is None:
        return False
    arguments = list(marker.site.get("arguments") or [])
    reference = declared.get("embed_arg")
    written = None if reference is None else _arg_at(arguments, reference)
    if written is not None and written.get("kind") == "boolean" and written.get("value") is True:
        return True
    markers = declared.get("embed_markers")
    if markers is None or (str(marker.site.get("owner")), str(marker.site["name"])) not in (
        body_calls_of(markers["calls"])
    ):
        return False
    if context.workspace is None:
        return False
    ancestors = context.workspace.once(dispatch_of).ancestors
    models = frozenset(_catalog_symbol(name) for name in markers["unless_subtype_of"])
    return not _subtype_of(str(parameter["type"].get("symbol")), models, ancestors)


def _embedded_body(
    every: list[tuple[int, dict[str, Any]]],
    reading: ParameterReading,
    declared: Mapping[str, Any],
    context: "_DeriveContext",
) -> str:
    """The body a framework assembles from its body parameters (FastAPI's
    `_should_embed_body_fields`: several, or one it embeds, `_embeds_one`): an object with one
    field per parameter, in declared order, named by the string its marker writes at
    `request_body.name_arg` (the alias; NULL where written as anything but a string) else by the
    parameter's own name, typed by the descriptor its type roots at (NULL for none), and
    required as `body_field_requirement` reads it."""
    carrier = context.carrier_rules
    fields: list[dict[str, Any]] = []
    for position, parameter in every:
        marker = reading.marked.get(position)
        written = (
            None
            if marker is None or declared.get("name_arg") is None
            else _arg_at(list(marker.site.get("arguments") or []), declared["name_arg"])
        )
        name = (
            str(parameter["name"])
            if written is None
            else (written.get("value") if written.get("kind") == "string" else None)
        )
        described = payload_descriptor(
            parameter["type"],
            carrier.rules,
            carrier.enums,
            context.facts.referenced,
            carrier.rules.wrappers,
        )
        fields.append(
            {
                "name": name,
                "required": body_field_requirement(declared, marker, parameter),
                "type": None if described is None else json.loads(described),
            }
        )
    return json.dumps(
        {"wire_type": "object", "wire_format": None, "nullable": False, "fields": fields},
        sort_keys=True,
        separators=(",", ":"),
    )


def _subtype_of(
    symbol: str, types: frozenset[str], ancestors: Mapping[str, Sequence[tuple[str, str, bool]]]
) -> bool:
    """Whether `symbol` is one of `types` or a subtype of one, by the module's type hierarchy
    (a type whose supertypes were not read is neither)."""
    seen: set[str] = set()
    pending = [symbol]
    while pending:
        current = pending.pop()
        if current in types:
            return True
        if current in seen:
            continue
        seen.add(current)
        pending.extend(ancestor for ancestor, _, _ in ancestors.get(current, ()))
    return False


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
    captures: dict[str, Any], context: _DeriveContext, url_argument: dict[str, Any] | None
) -> list[tuple[str | None, str | None, str]]:
    """One chain's peer/path/resolution from its `base` and `url` captures
    together (2F design §4's base composition), `url_argument` being one of
    the addresses `_url_arguments` reads the `url` capture as (None without one).

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
    carrying an expression stays whole.

    One answer, except where a client's defaults fill the address (`fill_authority`): one per
    path the defaults are read on (spec 2026-11-02 rule 4, `_with_client_defaults`)."""
    if "base" not in captures:
        if context.workspace is None or context.values is None:
            read = url_of(url_argument)
        else:
            # **The PEER is its own question** (`OI-138` cause 3): the join above is handed no
            # identities, so the path is text the code states, and who is CALLED is asked
            # separately of the first operand — the user's ruling of 2026-10-17, "peer and
            # path from separate evidence".
            captured = (_address_read(captures.get("url"), context) or {}).get("captured_at")
            read = with_authority(
                url_of(url_argument),
                _address_read(captures.get("url"), context),
                str(captured[0]) if captured else None,
                context.workspace,
                context.values,
                context.catalog.value_model or (),
            )
        # A chain whose destination the framework takes from somewhere this analysis does not
        # read (`destination: unread`, a root's word: Vert.x's `SocketAddress` forms, CP-56
        # rows 325-326) names no peer, whatever its URL's authority or a later host or port
        # step says, and no client base is joined to it. The path is the address's own.
        if captures.get(_DESTINATION) == _UNREAD_DESTINATION:
            return [(None, read[1], read[2])]
        if context.client_base is not None and context.client_base["join"] == FILL_AUTHORITY:
            found = []
            for filled, exact in _with_client_defaults(read, captures, context):
                peer, path, resolution = _with_stated_authority(
                    read, captures if filled is None else filled, context
                )
                # A default the request takes was set and not read, or is not known on this
                # path: WHO is called is not known — peer NULL, the path kept, `partial` (rule 4).
                if filled is None:
                    peer, resolution = None, weaker(resolution, str(Resolution.PARTIAL))
                # A path rule 9 cannot call exact is no surer than `partial`.
                if not exact:
                    resolution = weaker(resolution, str(Resolution.PARTIAL))
                found.append((peer, path, resolution))
            return found
        return [
            _against_client_base(_with_stated_authority(read, captures, context), captures, context)
        ]
    base = _string_value(_address_read(captures.get("base"), context))
    if base is None:
        return [(None, None, "unresolved")]
    if "url" not in captures:
        return [_address_of(base)]
    path = _string_value(url_argument)
    if path is None:
        return [(None, None, "unresolved")]
    return [_address_of(base + path)]


def _with_stated_authority(
    address: tuple[str | None, str | None, str],
    captures: dict[str, Any],
    context: _DeriveContext,
) -> tuple[str | None, str | None, str]:
    """`address` with the `host` and `port` the call states apart from its path composed into
    ONE peer (Vert.x spec §3d): `host`, or `host:port` where a port is stated — the authority
    CP-2 splits an absolute URL into, so `client.get(8080, "inventory", "/stock")` and
    `getAbs("http://inventory:8080/stock")` have one peer.

    Each part replaces that part of the authority the address already holds, and only that
    part: the framework applies a request's own host and port at send time over what an
    absolute URL parsed (Vert.x: CP-56 rows 129-130), so `getAbs("http://a:1/x").host("b")`
    goes to `b:1`. A port with no host stated and none in the address is no peer: the host is
    then a client default, and an unset default is never published (spec §2a).

    Each part is traced to its source as the `url` is (`_stated_part`). The parts are then
    the address the absolute form of the same call carries and are read by that form's reader,
    so the two forms publish one row: a host that is a configuration key gives the peer
    `getAbs("http://${search.host}:9200/q")` gives. A part captured and not read leaves WHO is called unread: peer NULL and the row
    `partial`, the path kept, because the path is evidence of its own (the user's ruling of
    2026-10-17, "peer and path from separate evidence").

    A path whose FIRST piece went unread was written `<host>` by `url_of`, which reads a
    leading hole as the authority. With the host stated, that piece is a piece of the path, so
    it is the hole the reader writes for an unread piece behind a known authority (`url_of`
    on `http://h/{}/x`), and the row stays `partial`."""
    if "host" not in captures and "port" not in captures:
        return address
    peer, path, resolution = address
    host, port = _authority_parts(peer)
    for field in ("host", "port"):
        if field not in captures:
            continue
        stated = _stated_part(captures, field, context)
        if stated is None:
            partly = weaker(resolution, str(Resolution.PARTIAL))
            return None, path, (partly if path is not None else resolution)
        host, port = (stated, port) if field == "host" else (host, stated)
    if host is None:
        return address
    if path is not None and path.startswith(_UNREADABLE_HOST):
        path = _HOLE + path.removeprefix(_UNREADABLE_HOST)
    # One peer per call, whichever form (coordinator ruling 2026-10-31): the parts are the
    # address the absolute form of the same call carries, scheme-relative, read by the reader
    # that reads that form (`url_of`), so the two publish the same row.
    authority = host if port is None else f"{host}:{port}"
    tail = path if path is not None and path.startswith("/") else ""
    stated_peer, _, _ = url_of({"kind": "string", "value": f"//{authority}{tail}"})
    return stated_peer, path, resolution


def _stated_part(captures: dict[str, Any], field: str, context: _DeriveContext) -> str | None:
    """The text of a captured `host` or `port`, read as the `url` capture is: the literal at
    the call (a port is an integer literal, CP-56 row 317), the configuration expression the
    field ladder names (`_address_read`), and otherwise the backward walk the assembled `url`
    takes (`_url_arguments`), with no identity entries and within the chain's path, so a host
    handed in as a parameter is the literal its callers pass. None where it was not read
    whole: no answer, several, or one with an unread hole."""
    argument = _address_read(captures.get(field), context)
    if not isinstance(argument, dict):
        return None
    read = _part_text(argument)
    if read is not None:
        return read
    walked = _walked_with(argument, context, (), reader=_part_answer, within=context.path)
    texts = {text for _, text, resolution in walked or () if resolution == "resolved" and text}
    return texts.pop() if len(texts) == 1 else None


def _part_text(argument: dict[str, Any]) -> str | None:
    """A `host` or `port` argument's own literal text: a string, or a port's integer."""
    value = argument.get("value")
    if argument.get("kind") == "int" and isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return _string_value(argument)


def _part_answer(answer: "Answer | None") -> tuple[str | None, str | None, str]:
    """One walk answer for a `host` or `port`, as `(None, text, resolution)`: a string or an
    integer literal is read; a configuration expression with no unread hole is the key it
    names; every other answer, a branch among several included, is not read."""
    if answer is None or answer.narrowed or answer.inexact:
        return None, None, str(Resolution.UNRESOLVED)
    if answer.kind == LITERAL and answer.literal_kind in (STRING, INT):
        return None, str(answer.value), str(Resolution.RESOLVED)
    if answer.kind == EXPRESSION and not _holes(str(answer.value)):
        return None, str(answer.value), str(Resolution.RESOLVED)
    return None, None, str(Resolution.UNRESOLVED)


def _authority_parts(peer: str | None) -> tuple[str | None, str | None]:
    """A peer as its host and port (`inventory:8080` → `inventory`, `8080`); a peer with no
    port is all host, and no peer is neither. A bracketed IPv6 host keeps its colons."""
    if peer is None:
        return None, None
    head, colon, tail = peer.rpartition(":")
    if colon and tail.isdigit() and head:
        return head, tail
    return peer, None


def _with_client_defaults(
    address: tuple[str | None, str | None, str],
    captures: dict[str, Any],
    context: _DeriveContext,
) -> list[tuple[dict[str, Any] | None, bool]]:
    """`captures` with the client's default host and port filling the parts the request does
    not name — the `fill_authority` join, Vert.x's (CP-56 row group (e)): `x(uri)` takes both,
    `x(host, uri)` the port only, `x(port, host, uri)` neither, and a `host(…)` or `port(…)`
    step is the request's own and wins. An absolute address (`xAbs`, its authority read by the
    url reader) takes neither, and neither does an address whose path was not read and which
    names no host of its own, since nothing then says it was not absolute.

    **One reading per path** (spec 2026-11-02 rule 4), each `(captures, exact)`: the defaults
    are the client's options object's, read per path (`client_defaults`), never merged — two
    factories, one setting port 8080 and one setting none, are two readings. On a path a default
    is the text a setter was handed, the framework's own value where the path proves the part
    unset (`localhost`, 80; rule 5), or not known; a default the request takes that is not
    known is None in place of the captures, and that row keeps its path with no peer, `partial`
    (D02, final review I3), never the other part alone. The filled parts are then composed into
    one peer by `_with_stated_authority`, as a request's own parts are. `exact` is False where
    rule 9 makes the path inexact."""
    peer, path, _ = address
    if peer is not None or context.workspace is None:
        return [(captures, True)]
    # An unread path may have been absolute, unless the request names its own host: the
    # `x(host, uri)` form is never absolute, so its port is still the default.
    if path is None and "host" not in captures:
        return [(captures, True)]
    missing = [part for part in ("host", "port") if part not in captures]
    if not missing:
        return [(captures, True)]
    client = _client_of(captures, context)
    # A client the chain holds no executing call for is not reached: its defaults are unknown.
    if client is None:
        return [(None, True)]
    readings: list[tuple[dict[str, Any] | None, bool]] = []
    for defaults in client_defaults(
        context.workspace, context.values, client, context.client_base or {}, context.path
    ):
        texts = [defaults.parts.get(part) for part in missing]
        if any(text is None for text in texts):
            readings.append((None, defaults.exact))
            continue
        readings.append(
            (
                {
                    **captures,
                    **{part: _part_argument(str(text)) for part, text in zip(missing, texts)},
                },
                defaults.exact,
            )
        )
    return readings


def _with_request_options(
    captures: dict[str, Any], context: _DeriveContext
) -> list[tuple[dict[str, Any], bool]]:
    """`captures` with the options object a request is made from read into the request's own
    parts (Vert.x's `request(m, RequestOptions)`, spec §3d), ONE reading per path the object is
    read on (spec 2026-11-02 rule 4), each `(captures, exact)`: its `uri` the address, its
    `host` and `port` the request's own, each only where no step after the root captured that
    part (a step on the request runs later, so it wins). The object is read by the catalog's
    `client_base` setters, the reader of a client's own options. A part proven unset on a path is
    left to the client's defaults (CP-56 row 126); one set to a value not read here, or not known
    on that path (an object built from JSON, one the walk did not reach), is captured unread, so
    the row says who is called went unread. A read uri makes the chain a row (`serves`), where
    the root alone named no address, and so does a uri set and not read or not known: the row
    then carries the address reader's word for it."""
    if context.workspace is None or context.client_base is None:
        return [(captures, True)]
    readings: list[tuple[dict[str, Any], bool]] = []
    for each in options_parts(
        context.workspace, context.values, captures[_OPTIONS], context.client_base, context.path
    ):
        filled = dict(captures)
        for part, field in _OPTION_CAPTURES.items():
            if part not in each.parts or field in captures:
                continue
            text = each.parts[part]
            filled[field] = _UNRESOLVED_ARGUMENT if text is None else _part_argument(text)
            if field == "url":
                # The object names an address whether or not it was read here: an unread one is
                # a row the address reader marks, never a request dropped.
                filled[_SERVES] = True
        readings.append((filled, each.exact))
    return readings


def _part_argument(text: str) -> dict[str, Any]:
    """A part read off an options object as the argument a capture would hold: a port's
    digits as an `int`, everything else a string — what `_stated_part` and `url_of` read."""
    if text.isdigit():
        return {"kind": "int", "value": int(text)}
    return {"kind": "string", "value": text}


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
    if context.client_base is None:
        return None
    if context.client_base["client_arg"] == CLIENT_IS_RECEIVER:
        # The client the root call is made ON (`client.get(…)`), read where the root reads it.
        root = context.root
        if root is None:
            return None
        return {"captured_at": (root["caller"], root["ordinal"], RECEIVER)}
    executing = captures.get(_EXECUTED_BY)
    if executing is None:
        return None
    slot = int(context.client_base["client_arg"])
    return _captured_at(_arg_at(executing["arguments"], slot), executing, slot)


def _url_arguments(
    captures: dict[str, Any], context: _DeriveContext
) -> list[dict[str, Any] | None]:
    """The `url` capture as the address readers should see it (A2 Task 8, spec §12), one per
    address it may be (a parameter handed several values, below; one everywhere else):
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
        return [argument]
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
    #
    # **A PARAMETER is the same position, one value edge further** (`OI-265`): the catalog
    # pointed at this slot and the method was handed the value, by a caller or by the site
    # that created the lambda that captured it. The same no-identity walk crosses that edge
    # and can only reach what the code states. Before this, `get(path)` in a helper, or on
    # a path local a lambda captured, published `path` NULL beside a handler that resolved
    # the same way. A parameter the walk does not read falls on to the `url_via` ladder.
    if isinstance(argument, dict) and argument.get("kind") in (_CONCAT, _PARAMETER):
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
        assembled = _walked_with(argument, context, (), reader=_assembled_text, within=context.path)
        # **Every caller's value is part of the set** (final review I2, enumerable is exact):
        # a parameter handed `"/a"` by one caller and a value nobody reads by another is two
        # addresses, `"/a"` at `resolved` and one whose path is unread. Taking the literal
        # alone would publish it as the whole answer. The concat arm keeps one address.
        if assembled is not None and argument.get("kind") == _PARAMETER:
            several = _each_callers_url(assembled, argument)
            if several is not None:
                return several
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
                    argument,
                    context,
                    (),
                    reader=_assembled_text,
                    branches=False,
                    within=context.path,
                )
                address = None if unbranched is None else _one_assembled(unbranched)
            if address is not None:
                return [address]
        if argument.get("kind") == _CONCAT:
            return [argument]
    if not forms:
        return [argument]
    # **The backward walk, in place of the one-hop follow** (spec §2b, Task 9), reached
    # through the same `_captured_at` provenance the channel half uses. The order above is
    # untouched: a literal at the capture answers first, and a field-fed address is already
    # a string by the time it arrives (`_address_read`), so neither ever reaches here.
    walked = _walked_channels(argument, context, forms, context.path)
    if walked is None:
        return [argument]
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
        return [argument]
    return [{"kind": "string", "value": resolved[0]}]


def _each_callers_url(
    assembled: "Sequence[tuple[str | None, str | None, str]]", argument: dict[str, Any]
) -> list[dict[str, Any] | None] | None:
    """A url parameter's addresses, one per value its callers hand it: each literal as a
    string, each template as the expression `url_of` reads, and the parameter itself, which
    `url_of` reads as unread, where some caller's value is not read. None where the callers
    agree on one address (`_one_assembled` answers then) or a value is one branch of several
    (`NARROWED`, which the caller below reads again unbranched)."""
    if any(resolution == str(Resolution.NARROWED) for _, _, resolution in assembled):
        return None
    found: list[dict[str, Any] | None] = []
    for _, literal, resolution in assembled:
        if resolution == str(Resolution.RESOLVED) and literal:
            found.append({"kind": "string", "value": literal})
        elif resolution == str(Resolution.PARTIAL) and literal:
            found.append({"kind": EXPRESSION, "value": literal})
        else:
            found.append(argument)
    distinct = list(
        {json.dumps(each, sort_keys=True, default=str): each for each in found}.values()
    )
    return distinct if len(distinct) > 1 else None


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


@dataclass(frozen=True)
class _Response:
    """What a row's response capture read: its descriptor (None for no response), whether the
    capture was read at all (`read`: checkpoint ruling I1, False drops the row to `unresolved`),
    and whether it named one type (`whole`: N9, False leaves the row no surer than `partial`)."""

    shape: str | None
    read: bool
    whole: bool = True


# A response type the framework refuses to build a response from (N9): the route is refused.
_REFUSED_RESPONSE = _Response(None, False)


@dataclass(frozen=True)
class _ResponseFallback:
    """`matches.response_fallback` (N9): the response of a route whose response capture writes
    nothing is read from the handler's return (`from: handler_return`). `none_types` are the
    types that are no response model, each with its subtypes; `ancestors` the module's type
    hierarchy they are looked up in, and `returns` each method's declared return type."""

    none_types: frozenset[str]
    ancestors: Mapping[str, Sequence[tuple[str, str, bool]]]
    returns: Mapping[str, Any]


# A construction's name at a call site (D00 §5).
_INIT = "<init>"
# `response_fallback.from`'s one word: the handler's own return.
_HANDLER_RETURN = "handler_return"


def _response_fallback_of(
    matches: Mapping[str, Any], catalog: Catalog, workspace: Workspace
) -> _ResponseFallback | None:
    """`matches.response_fallback`, checked (D02 §2's `fluent` style): `from: handler_return`
    and a non-empty `none_types` list of types, and nothing else. None where it is not
    declared. Anything else is a broken file, never read as absent."""
    declared = matches.get("response_fallback")
    if declared is None:
        return None
    none_types = declared.get("none_types") if isinstance(declared, dict) else None
    if (
        not isinstance(declared, dict)
        or set(declared) != {"from", "none_types"}
        or declared["from"] != _HANDLER_RETURN
        or not isinstance(none_types, list)
        or not none_types
        or not all(isinstance(each, str) and each for each in none_types)
    ):
        raise CatalogError(
            f"loading catalog {catalog.source}: `response_fallback` is `{{from: "
            f"{_HANDLER_RETURN}, none_types: [<type>, ...]}}`, got {declared!r} (D02 §2's "
            f"`fluent` style)"
        )
    return _ResponseFallback(
        none_types=frozenset(_catalog_symbol(each) for each in none_types),
        ancestors=workspace.once(dispatch_of).ancestors,
        returns=workspace.once(_declared_returns),
    )


def _declared_returns(workspace: Workspace) -> dict[str, Any]:
    """Each declared method's written return type (D00 §5a), by full symbol; None where the
    method writes none. The `Workspace.once` builder `_handler_response` reads."""
    return {
        str(row["symbol"]): cast(dict[str, Any], row["signature"] or {}).get("returns")
        for row in workspace.query("method_declarations")
    }


def _handler_response(
    answering: _Judged | None, fallback: _ResponseFallback, context: "_DeriveContext"
) -> _Response:
    """The response of a route whose response capture writes nothing (N9), from the handler:
    - its written return type: none for a `none_types` type or a subtype of one, refused for a
      union naming one beside other types, unread for a union or the unknown type (several
      types, or any), and otherwise the descriptor the type roots at (none for a type that
      reaches no wire: `None`, a generator's iterator);
    - with none written, the one type every value it returns is (`return_flow`'s values):
      unread where they are several types or one is not read.
    A handler that is not read reads no response."""
    handler = None if answering is None else answering.symbol
    if handler is None:
        return _Response(None, True, whole=False)
    written = fallback.returns.get(handler)
    if isinstance(written, dict):
        symbol = str(written.get("symbol"))
        if symbol == UNION_TYPE:
            members = [str(member.get("symbol")) for member in written.get("arguments") or ()]
            if any(_is_none_type(member, fallback) for member in members):
                return _REFUSED_RESPONSE
            return _Response(None, True, whole=False)
        if symbol == ANY_TYPE:
            return _Response(None, True, whole=False)
        if _is_none_type(symbol, fallback):
            return _Response(None, True)
        rules = context.carrier_rules
        return _Response(
            payload_descriptor(
                written, rules.rules, rules.enums, context.facts.referenced, rules.rules.wrappers
            ),
            True,
        )
    returned = () if context.values is None else context.values.returned_values.get(handler, ())
    typed = [_constructed(handler, entry, context.values) for _, entry in returned]
    # A returned value of a `none_types` class (a `RedirectResponse`) is no response model, as
    # the annotation of one is: every value one gives no response; some one and some another
    # name no one type.
    none = [
        entry.get("kind") == "instance" and _is_none_type(str(entry.get("symbol")), fallback)
        for entry in typed
    ]
    if none and all(none):
        return _Response(None, True)
    if any(none):
        return _Response(None, True, whole=False)
    shapes = {argument_descriptor(entry, context.facts, context.carrier_rules) for entry in typed}
    if len(shapes) != 1 or None in shapes:
        return _Response(None, True, whole=False)
    return _Response(shapes.pop(), True)


def _constructed(
    method: str, entry: Mapping[str, Any], index: "ValueIndex | None"
) -> dict[str, Any]:
    """A value `method` returns, as an `instance` of its class where a construction in the
    method made it (`<init>`, D00 §5), which is the value's type; the value as written
    otherwise."""
    source = entry.get("source")
    if index is None or entry.get("kind") != "unresolved" or source is None:
        return dict(entry)
    made = index.producers.get((method, int(str(source))))
    site = index.sites.get((method, min(made))) if made else None
    if site is None or site["name"] != _INIT or site.get("owner") is None:
        return dict(entry)
    return {**entry, "kind": "instance", "symbol": str(site["owner"])}


def _is_none_type(symbol: str, fallback: _ResponseFallback) -> bool:
    """Whether `symbol` is one of the `none_types` or a subtype of one, by the module's type
    hierarchy (a type whose supertypes were not read is neither)."""
    return _subtype_of(symbol, fallback.none_types, fallback.ancestors)


def _class_named(argument: Any, context: "_DeriveContext") -> Any:
    """A captured argument that is a module name (`field`) holding a class, as that class
    (`class`): the value walk reads the name on the chain's own path, and only where every
    path answers the same type is it that type. A value a call made, where it is a type form
    (`ListResource[Order]`, `list[Order]`), is the type it names, with its arguments (R24,
    `type_form_reference`). Every other argument is returned as it is."""
    if (
        isinstance(argument, dict)
        and argument.get("kind") == "unresolved"
        and argument.get("source") is not None
        and context.values is not None
    ):
        at = argument.get(_CAPTURED_AT)
        site = context.values.sites.get((str(at[0]), int(str(at[1])))) if at is not None else None
        if site is None or at is None:
            return argument
        dispatch = context.workspace.once(dispatch_of) if context.workspace is not None else None
        known = context.carrier_rules.rules.known_types

        def is_class(symbol: str) -> bool:
            return (dispatch is not None and symbol in dispatch.scanned) or symbol in known

        reference = type_form_reference(
            context.values, site, int(at[2]), is_class, within=context.path
        )
        return (
            argument
            if reference is None
            else {**argument, "kind": TYPE_FORM, "reference": reference}
        )
    if (
        not isinstance(argument, dict)
        or argument.get("kind") != "field"
        or context.workspace is None
        or context.values is None
    ):
        return argument
    at = argument.get(_CAPTURED_AT)
    site = context.values.sites.get((str(at[0]), int(str(at[1])))) if at is not None else None
    if site is None or at is None:
        return argument
    named = {
        answers["type"].value
        if answers["type"].kind == LITERAL and answers["type"].literal_kind == SYMBOL
        else None
        for answers in resolve_positions(
            context.workspace, {"type": (site, int(at[2]))}, context.values, within=context.path
        )
    }
    if len(named) != 1:
        return argument
    (symbol,) = named
    if symbol is None or not names_a_type(str(symbol)):
        return argument
    return {**argument, "kind": "class", "symbol": str(symbol)}


def _walked_handler(argument: Any, context: "_DeriveContext") -> "_Judged | None":
    """The function a handler argument that is not itself a function names (design
    2026-11-06-reading-decorators §3d): followed back as a call of it would be, through each
    decorator a value model states hands the function back and into module code, to each
    function a path reaches — one answering handler, or one alternative each. Where no path
    reaches a function because a library call no value model states made the value, the
    handler is not read here (`external`, the call named). None otherwise, and for an
    argument the walk cannot be asked about, which reads as it always has."""
    if not isinstance(argument, dict) or argument.get("kind") == "lambda" or context.values is None:
        return None
    at = argument.get(_CAPTURED_AT)
    site = context.values.sites.get((str(at[0]), int(str(at[1])))) if at is not None else None
    if site is None or at is None:
        return None
    slot = int(at[2])
    handlers = _entry_handlers(
        context.values, site, slot, context.method_symbols, context.path
    ) or (_bound_methods(argument, context))
    if handlers:
        alternatives = tuple(_Judged(symbol, ANSWERS) for symbol in handlers)
        return _Judged(handlers[0], ANSWERS, (), alternatives if len(handlers) > 1 else ())
    # Only a value a library call made OF a function the module defines (a decorator applied to
    # it, a wrapper handed it): any other object a library builds is no function at all, and
    # its handler reads as it always has.
    if argument.get("kind") == "unresolved" and argument.get("source") is None:
        # A value the facts state nothing about (an attribute of a local object, `s.h`):
        # which function it is, is not read here.
        return _Judged(
            None,
            UNREADABLE,
            ((NOT_READABLE, "the handler is a value whose source the scanned facts do not state"),),
        )
    if argument.get("kind") == "field" and not _written(argument, context.values):
        return _Judged(
            None,
            UNREADABLE,
            (
                (
                    NOT_READABLE,
                    (
                        f"the handler is {argument.get('symbol')}, which nothing writes and no "
                        "class of its namespace defines as a method"
                    ),
                ),
            ),
        )
    made = undecorated_maker(context.values, site, slot)
    if made is None:
        return None
    made_with, maker = made
    if maker.get("owner") is None or not any(
        argument.get("kind") == "lambda" for argument in made_with["arguments"] or ()
    ):
        return None
    ended = {
        producer.reason
        for producer, _ in producer_paths(context.values, site, slot, frozenset(), functions=True)
    }
    if ended != {EXTERNAL}:
        return None
    return _Judged(
        None,
        UNREADABLE,
        (
            (
                EXTERNAL,
                (
                    f"the function is what the library call {maker['owner']}{maker['name']} "
                    "returns, which no value model states"
                ),
            ),
        ),
    )


def _written(argument: Mapping[str, Any], index: "ValueIndex") -> bool:
    """Whether anything in the module writes the binding a `field` argument reads."""
    symbol = str(argument.get("symbol"))
    return bool(
        index.writers.get(symbol) or index.constants.get(symbol) or index.produced.get(symbol)
    )


def _bound_methods(argument: Mapping[str, Any], context: "_DeriveContext") -> tuple[str, ...]:
    """The methods a `field` argument nothing writes names on its class (`self.endpoint`, a
    method read through its receiver's type, rulings R29 and R33): for the class and each of
    its subtypes, the first type of its lookup order defining a method of that name, each
    once. Empty for any other argument, and where no class of the namespace defines one."""
    if (
        argument.get("kind") != "field"
        or context.values is None
        or context.workspace is None
        or _written(argument, context.values)
    ):
        return ()
    symbol = str(argument.get("symbol"))
    owner, name = owner_of(symbol), member_name(symbol)
    if owner is None:
        return ()
    dispatch = context.workspace.once(dispatch_of)
    by_type: dict[str, list[str]] = {}
    for bare, full in context.method_symbols.items():
        if method_name(bare) == name and (declaring := owner_of(bare)) is not None:
            by_type.setdefault(declaring, []).append(full)
    found: list[str] = []
    for type_ in (owner, *dispatch.subtypes.get(owner, ())):
        for candidate in dispatch.lookup_order(type_):
            if candidate in by_type:
                found.extend(full for full in by_type[candidate] if full not in found)
                break
    return tuple(found)


def _unread_verbs(declared: Any) -> bool:
    """Whether an `http_method` capture is a verb list the call did not write as literals
    (`chains._listed_verbs`), which the value walk reads."""
    return isinstance(declared, dict) and VERBS_TO_READ in declared


def _walked_verbs(declared: Any, context: "_DeriveContext") -> Any:
    """A verb list read through the value walk (N8, M1): one verb per value the walk reads
    (a module constant's elements, a parameter's arguments), respelled; the `absent` verb for
    an explicit `None`; no verb at all where every value is an empty list (a refusal); and an
    unread argument (no verb) for each value not read, beside the rest."""
    case, absent = declared[VERBS_TO_READ]
    at = declared.get(_CAPTURED_AT)
    site = (
        None
        if at is None or context.values is None
        else context.values.sites.get((str(at[0]), int(str(at[1]))))
    )
    if site is None or at is None or context.workspace is None:
        return None
    verbs: list[Any] = []
    for answers in resolve_positions(
        context.workspace, {"verb": (site, int(at[2]))}, context.values, within=context.path
    ):
        answer = answers["verb"]
        if answer.kind == LITERAL and answer.literal_kind == STRING and not answer.inexact:
            verbs.append(respell_verb(str(answer.value), case))
        elif answer.kind == ABSENT and answer.null:
            verbs.append(absent)
        elif answer.kind == ABSENT:
            continue
        else:
            verbs.append(None)
    return tuple(dict.fromkeys(verbs))


def _per_call(
    prefixes: tuple[Prefix, ...], within: Path | None
) -> list[tuple[Path | None, tuple[Prefix, ...]]]:
    """The paths a route is derived on, each with the prefixes served on it (`_derive`): one
    per distinct path the prefixes' routers were reached on (`Prefix.places`), where there are
    several; otherwise the one path the end was walked on, with every prefix. A prefix whose
    router was reached on no path of its own is served on every one."""
    paths: dict[Path, list[Prefix]] = {}
    anywhere: list[Prefix] = []
    for prefix in prefixes:
        reached = {router[1] for place in prefix.places if (router := place[-1][0]) is not None}
        if not reached:
            anywhere.append(prefix)
        for path in reached:
            paths.setdefault(path, []).append(prefix)
    if len(paths) < 2:
        return [(within, prefixes)]
    return [
        (path, (*served, *anywhere))
        for path, served in sorted(paths.items(), key=lambda item: repr(item[0]))
    ]


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


def _refuses_unrooted_path(matches: dict[str, Any], catalog: Catalog) -> bool:
    """`matches.refuses_unrooted_path` (DR-6): true for a framework that throws on a served
    path with no leading `/`, absent for one that repairs it. Anything but a boolean is a
    broken file (D02 §2's `fluent` style), never read as absent."""
    declared = matches.get("refuses_unrooted_path", False)
    if not isinstance(declared, bool):
        raise CatalogError(
            f"loading catalog {catalog.source}: `refuses_unrooted_path` is true or false, "
            f"got {declared!r} (D02 §2's `fluent` style)"
        )
    return declared


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


def _pathless_serves(matches: dict[str, Any], catalog: Catalog) -> str | None:
    """`matches.pathless_serves` (Vert.x spec §3a): the path a route that names none serves,
    in the framework's own spelling (`/*`). Anything but a non-empty string is a broken file,
    never read as absent."""
    declared = matches.get("pathless_serves")
    if declared is not None and not (isinstance(declared, str) and declared):
        raise CatalogError(
            f"loading catalog {catalog.source}: `pathless_serves` is a path, got {declared!r} "
            f"(D02 §2's `fluent` style)"
        )
    return declared


def _validate_route_captures(entries: list[dict[str, Any]], catalog: Catalog) -> None:
    """Refuses a `url_is` capture outside its closed set and a `serves` capture that is not a
    boolean (Vert.x spec §3a): either would load, read as some other answer, and publish a
    route the framework does not serve, or none it does."""
    for entry in entries:
        captures = entry["captures"]
        if "url_is" in captures and captures["url_is"] not in _URL_IS:
            raise CatalogError(
                f"loading catalog {catalog.source}: `{entry['method']}` captures "
                f"`url_is: {captures['url_is']!r}`, which is one of "
                f"{', '.join(sorted(_URL_IS))} (D02 §2's `fluent` style)"
            )
        if _ORDER in captures and not (
            captures[_ORDER] == _LAST or _ARG_REFERENCE.match(str(captures[_ORDER]))
        ):
            raise CatalogError(
                f"loading catalog {catalog.source}: `{entry['method']}` captures "
                f"`order: {captures[_ORDER]!r}`, which reads `argN` or is `{_LAST}` (D02 §2's "
                f"`fluent` style)"
            )
        if _DESTINATION in captures and captures[_DESTINATION] != _UNREAD_DESTINATION:
            raise CatalogError(
                f"loading catalog {catalog.source}: `{entry['method']}` captures "
                f"`{_DESTINATION}: {captures[_DESTINATION]!r}`, which is only "
                f"`{_UNREAD_DESTINATION}` (D02 §2's `fluent` style)"
            )
        if _SERVES in captures and not isinstance(captures[_SERVES], bool):
            raise CatalogError(
                f"loading catalog {catalog.source}: `{entry['method']}` captures "
                f"`serves: {captures[_SERVES]!r}`, which is true or false (D02 §2's `fluent` "
                f"style)"
            )


def _validate_options_capture(
    entries: list[dict[str, Any]], client_base: Mapping[str, Any] | None, catalog: Catalog
) -> None:
    """Refuses an `options` capture in a catalog whose `client_base` declares no `setters`:
    the options object is read by them, and with none it would load and read nothing."""
    if client_base is not None and "setters" in client_base:
        return
    for entry in entries:
        if _OPTIONS in entry["captures"]:
            raise CatalogError(
                f"loading catalog {catalog.source}: `{entry['method']}` captures `options`, "
                f"which is read by the `setters` of an options-object `client_base` this "
                f"catalog does not declare (D02 §2's `fluent` style)"
            )
