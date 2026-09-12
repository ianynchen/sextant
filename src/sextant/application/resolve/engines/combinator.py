"""`combinator` engine for endpoint derivation (D02 §2's `combinator` style).

Neither one call (`single_call`) nor one chain (`fluent`) carries the
declaration here: a router is a **tree** of calls, and every edge of that tree
is already in the facts (D00 §5) — a predicate argument links to its producing
call through `source`, a chain links through `result` → `receiver`, and a
subtree or a nested body arrives as one more linked argument. The derivation
is therefore a fold over that tree rather than a walk along a line.

`matches` declares three things and nothing about any framework:

- `entries` — where trees start, in two shapes. An **argument-rooted** entry
  (`{owner, methods: [...], handler_arg}`) is a call that takes a predicate and
  a handler. A **body-linked** entry (`{owner, method, body_arg}`) is a call
  whose `body_arg` names, as a `lambda`-kind argument, the method holding the
  routes: the walk roots ONLY at that call and jumps to the named method,
  recursing again through a prefix rule's own `body_arg`. Body methods are
  never rooted on their own — rooting every method that merely *contains* a
  vocabulary call double-derives every nested route, once prefixed and once
  bare (2E checkpoint F4). The entry owner and the vocabulary owner are
  routinely two different types, so the catalog declares both.
- `vocabulary` — owner+method to role: `verbs` (a verb plus the argument its
  path sits at, and, in the two-argument form, its handler), `prefixes` (a
  path contribution, plus optionally the `subtree_arg`/`body_arg` holding the
  routes it prefixes), `media` (which of `consumes`/`produces` the call fills),
  `media_values` (an enum type's member names to their wire values), and
  `composers` (`and` merges constraints, `or` duplicates the route per branch).
- `continuations` — the calls that merge route sets along `result` →
  `receiver`. A plain method name is owner-free, exactly like `fluent`'s
  steps; a mapping declares the same name with an `owner` that narrows it to
  one type, and — for the nest-shaped continuation — a `path_arg` and a
  `subtree_arg`, which make it fold its argument's whole router under its own
  prefix rather than reading a handler it does not have.

**Rooting.** A candidate — an entry call, or a continuation call whose catalog
entry declares an `owner` that the call site matches — is a root unless its own
`result` is consumed elsewhere in the same method: handed to another routing
call as an argument, or taken as a composer's or continuation's receiver. A
consumed routing value belongs to the tree that consumed it, so rooting at the
outermost unconsumed call derives each route exactly once. This is what tells
`route(...).and(...)` (rooted at the `and`, which nothing consumes) apart from
`nest(prefix, route(...).andRoute(...))` (rooted at the `nest` alone).

An owner-FREE continuation extends a walk that some real root reaches, but
never roots one on its own (`fluent`'s own steps discipline: an owner-free step
matches any owner, which is useful for reaching a step and reckless for
deciding a chain belongs to this catalog at all). A bare `and` matches a method
name half the libraries on a classpath declare, and rooting at every one of
them invents a router out of any two-argument call that happens to be named
that. The cost is stated rather than hidden: a chain whose OUTERMOST call is an
owner-free continuation is not rooted, so a catalog declares an `owner` on
every continuation that can end a chain.

**`caller`.** Every row of one tree carries the containing method of the tree's
ROOT call, never the body method a nested route was folded from. This matches
`fluent`, whose `caller` is likewise the method the walk started in, and it is
the honest provenance: the bodies of a body-linked entry are compiler-generated
containers for a block written inside the entry's own method, so naming one of
them would report a synthetic artifact as the declarer. One router, one
declarer.

**Honesty (spec §1c).** An unreadable part poisons exactly its own column: an
unreadable path leaves `path` NULL and the row unresolved; an unreadable media
constant leaves only that media column NULL, since the verb and path — the wire
identity — are intact; a second verb inside one `and` chain poisons the verb; a
routing expression the walk cannot read at all (a router composed from another
method's return, which the per-method walk does not follow) derives ONE
unresolved row rather than a silent absence. `request_shape`/`response_shape`
are always NULL: a functional handler's payloads live inside its body, not in
its signature.
"""

import json
from dataclasses import dataclass, replace
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.shapes.arguments import _arg_at, _expanded_arguments
from sextant.application.resolve.shapes.rooting import _catalog_symbol, catalog_symbols
from sextant.domain.paths import canonical_http_path, serves_urls
from sextant.domain.symbols import bare_descriptor, member_name, owner_of

# The two endpoint columns a failed read can poison. Both are wire identity,
# so poisoning either drops the row's own `resolution` (checkpoint ruling I1,
# shared with `single_call`/`fluent`) — unlike the media columns, which are
# carried data and go NULL on their own without touching resolution.
_METHOD = "method"
_PATH = "path"
_IDENTITY_POISON = (_METHOD, _PATH)

# The two roles a `media` rule may fill. Validated at load rather than
# discovered at derive time: a typo here silently mislabels every media value
# a catalog reads (`ports/catalogs.py`'s own discipline).
_MEDIA_FIELDS = ("consumes", "produces")

# Every row column except the two media lists — the grouping key for the
# within-batch union below (spec §4, mirroring `derive_endpoints.sql`'s own
# `GROUP BY ALL`): rows differing ONLY in declared media are one endpoint.
_GROUPED_FIELDS = (
    "protocol",
    "direction",
    "method",
    "path",
    "handler",
    "caller",
    "peer",
    "handler_signature",
    "resolution",
    "evidence",
    "catalog_id",
    "request_shape",
    "response_shape",
)


def run(workspace: Workspace, catalog: Catalog) -> None:
    """Derives one endpoint row per leaf route of every rooted tree, via the
    same `call_endpoints` insert-if-absent every style uses (D02 §5).
    `protocol`/`direction` are the catalog's own declared fields, `evidence` is
    `compiler`, `peer`/`handler_signature`/`request_shape`/`response_shape` are
    always NULL (an inbound route names no peer, and spec §1c leaves the
    payloads honestly unread), and `handler` is a symbol resolved against the
    facts or NULL — never fabricated."""
    _validate_matches(catalog)
    context = _context_of(workspace, catalog)
    rows: list[dict[str, Any]] = []
    for caller, sites in context.by_caller.items():
        scope = _scope_of(sites, context)
        # Sites arrive ordinal-ordered (the `call_sites` query), so the trees
        # of one method are rooted in source order and their rows accumulate
        # in that order too (NFR-1).
        for site in sites:
            if not _is_root_candidate(site, context):
                continue
            result = site["result"]
            if result is not None and result in scope.consumed:
                continue
            for route in _routes_of(site, scope):
                rows.append(_row_of(route, caller, catalog))
    workspace.derive("call_endpoints", rows=_emitted(rows, catalog))


@dataclass(frozen=True)
class _Route:
    """One route, or one partially folded constraint set on the way to one —
    the same shape either way, because a fold is exactly the merging of
    constraint sets until a handler is attached.

    `path_parts` are concatenated verbatim, outermost prefix first: the
    catalog's own declared literals, never re-punctuated, so a router whose
    prefixes do not start with a separator reads back exactly as written.
    `consumes`/`produces` are sorted, distinct tuples. `poisons` names the
    identity columns whose read failed — a non-empty `poisons` is what makes
    the row unresolved.
    """

    verb: str | None = None
    path_parts: tuple[str, ...] = ()
    consumes: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    handler: str | None = None
    poisons: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Continuation:
    """One declared continuation. `owner` is None for the owner-free form,
    which matches any owner and never roots (see the module docstring's
    Rooting note). `path_arg`/`subtree_arg` are both set or both None: together
    they make the continuation nest-shaped — it folds the router at
    `subtree_arg` under the prefix at `path_arg`, instead of reading a
    predicate and a handler."""

    name: str
    owner: str | None
    path_arg: int | None
    subtree_arg: int | None


@dataclass(frozen=True)
class _TreeContext:
    """Everything every tree in the run shares — the catalog's own vocabulary,
    already converted to the symbol forms the facts are keyed on, plus the two
    cross-method indexes (bodies by their bare caller descriptor, method
    symbols by their bare descriptor) a fold reaches for."""

    entries: tuple[dict[str, Any], ...]
    body_entries: tuple[dict[str, Any], ...]
    verbs: dict[tuple[str, str], dict[str, Any]]
    prefixes: dict[tuple[str, str], dict[str, Any]]
    media: dict[tuple[str, str], dict[str, Any]]
    media_owners: tuple[str, ...] | None
    media_values: dict[str, str]
    composers: dict[tuple[str, str], str]
    continuations: tuple[_Continuation, ...]
    # The handler positions a PLAIN continuation reads. A plain continuation is
    # the same declaration shape as an argument-rooted entry, only reached
    # through a chain rather than written on its own, so it reuses those
    # entries' declared positions rather than needing a second declaration of
    # the same fact. A continuation that carries no argument at any of them — a
    # router-composing `and(other)` — simply reads no handler. A nest-shaped
    # continuation never consults these at all: its second argument is a whole
    # router, and skipping it as a handler slot would drop that router's routes
    # on the floor while emitting a handler-less row in their place.
    continuation_handlers: frozenset[int]
    by_caller: dict[str, list[dict[str, Any]]]
    by_bare_caller: dict[str, list[dict[str, Any]]]
    method_symbols: dict[str, str]


@dataclass(frozen=True)
class _Scope:
    """One method's own routing calls. Value ids are meaningless across
    methods (D00 §5), so `by_result` and `consumed` are rebuilt per method —
    including for each body a body-linked entry jumps into, which is a method
    in its own right."""

    context: _TreeContext
    sites: tuple[dict[str, Any], ...]
    by_result: dict[int, dict[str, Any]]
    consumed: frozenset[int]


def _context_of(workspace: Workspace, catalog: Catalog) -> _TreeContext:
    matches = catalog.matches
    raw_entries = matches.get("entries", [])
    entries = tuple(
        {**entry, "owner": _catalog_symbol(entry["owner"])}
        for entry in raw_entries
        if "body_arg" not in entry
    )
    body_entries = tuple(
        {**entry, "owner": _catalog_symbol(entry["owner"])}
        for entry in raw_entries
        if "body_arg" in entry
    )
    vocabulary = matches.get("vocabulary", {})
    media_values = vocabulary.get("media_values", {})
    composers: dict[tuple[str, str], str] = {}
    for role, declared in vocabulary.get("composers", {}).items():
        for rule in declared:
            composers[(_catalog_symbol(rule["owner"]), rule["method"])] = role
    # Parsed once, as every other call-site engine does, for the same reason:
    # `call_sites` hands back `arguments` decoded (`_DECODED_COLUMNS`), and every
    # fold below reads that list.
    call_sites: list[dict[str, Any]] = workspace.query("call_sites")
    by_caller: dict[str, list[dict[str, Any]]] = {}
    for site in call_sites:
        by_caller.setdefault(str(site["caller"]), []).append(site)
    # A body-linked entry's own `lambda` argument names its body BARE (D00
    # §5a), while a `call_sites` row's `caller` carries the module coordinates,
    # so the jump joins on the bare form — the same key `method_symbols` below
    # is built on, for the same reason. One module is scanned at a time today;
    # two modules declaring the identical bare descriptor collide here, and
    # `setdefault` makes the first read win rather than the last, so the answer
    # does not depend on which module the loader happened to reach second
    # (NFR-1, Task 7's own first-writer precedent).
    by_bare_caller: dict[str, list[dict[str, Any]]] = {}
    for caller, sites in by_caller.items():
        by_bare_caller.setdefault(bare_descriptor(caller), sites)
    method_symbols: dict[str, str] = {}
    for row in workspace.query("method_symbols"):
        method_symbols.setdefault(bare_descriptor(str(row["symbol"])), str(row["symbol"]))
    return _TreeContext(
        entries=entries,
        body_entries=body_entries,
        verbs=_by_owner_method(vocabulary.get("verbs", [])),
        prefixes=_by_owner_method(vocabulary.get("prefixes", [])),
        media=_by_owner_method(vocabulary.get("media", [])),
        # A LIST or a scalar (§3.1): the enum carrying the wire values may be
        # reachable under more than one name. `media_owners` plural for the same
        # reason as every other widened owner — a stale `==` must not compile.
        media_owners=(
            catalog_symbols(media_values["owner"], f"{catalog.source}: media_values.owner")
            if "owner" in media_values
            else None
        ),
        media_values=dict(media_values.get("values", {})),
        composers=composers,
        continuations=_continuations_of(matches.get("continuations", [])),
        continuation_handlers=frozenset(
            entry["handler_arg"] for entry in entries if "handler_arg" in entry
        ),
        by_caller=by_caller,
        by_bare_caller=by_bare_caller,
        method_symbols=method_symbols,
    )


def _continuations_of(declared: list[Any]) -> tuple[_Continuation, ...]:
    """`continuations`' two forms, normalized to one: a plain method name is
    the owner-free continuation, a mapping carries the same `name` plus
    whichever of `owner`/`path_arg`/`subtree_arg` the catalog declared. Only
    ever called on entries `_validate_matches` already passed."""
    return tuple(
        _Continuation(name=entry, owner=None, path_arg=None, subtree_arg=None)
        if isinstance(entry, str)
        else _Continuation(
            name=entry["name"],
            owner=_catalog_symbol(entry["owner"]) if "owner" in entry else None,
            path_arg=entry.get("path_arg"),
            subtree_arg=entry.get("subtree_arg"),
        )
        for entry in declared
    )


def _by_owner_method(rules: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(_catalog_symbol(rule["owner"]), rule["method"]): rule for rule in rules}


def _scope_of(sites: list[dict[str, Any]], context: _TreeContext) -> _Scope:
    by_result: dict[int, dict[str, Any]] = {}
    consumed: list[int] = []
    for site in sites:
        result = site["result"]
        if result is not None:
            by_result.setdefault(result, site)
        # Only a call the catalog's own vocabulary claims can consume a
        # routing value. A value merely *observed* by something else — logged,
        # compared, handed to a `requireNonNull` the compiler inserted beside
        # every bound method reference (2E checkpoint (1a), ruling 5) — is not
        # part of anyone's tree, and counting it would silence the root that
        # produced it.
        if not _claimed(site, context):
            continue
        consumed.extend(
            int(argument["source"])
            for argument in site["arguments"]
            if argument.get("source") is not None
        )
        receiver = site["receiver"]
        # A composer's or continuation's receiver IS the expression it
        # extends, so that expression is not a tree of its own either.
        if receiver is not None and _extends_a_receiver(site, context):
            consumed.append(int(receiver))
    return _Scope(
        context=context,
        sites=tuple(sites),
        by_result=by_result,
        consumed=frozenset(consumed),
    )


def _claimed(site: dict[str, Any], context: _TreeContext) -> bool:
    """Whether any declared rule claims this call at all — including an
    owner-free continuation, which never roots but is genuinely part of the
    tree it extends, so the routing value it takes as its receiver is really
    consumed."""
    key = (str(site["owner"]), str(site["name"]))
    return (
        key in context.verbs
        or key in context.prefixes
        or key in context.media
        or key in context.composers
        or _matching_entry(site, context) is not None
        or _matching_body_entry(site, context) is not None
        or _matching_continuation(site, context) is not None
    )


def _extends_a_receiver(site: dict[str, Any], context: _TreeContext) -> bool:
    key = (str(site["owner"]), str(site["name"]))
    return key in context.composers or _matching_continuation(site, context) is not None


def _matching_continuation(site: dict[str, Any], context: _TreeContext) -> _Continuation | None:
    """The one declared continuation matching this call, or None — `fluent`'s
    own `_matching_step` rule verbatim: the name must match, and an entry's
    `owner`, where it declares one, narrows it to that type.
    `_validate_matches` already refused a catalog where two entries could match
    the same call, so at most one ever applies."""
    name = str(site["name"])
    return next(
        (
            continuation
            for continuation in context.continuations
            if continuation.name == name and continuation.owner in (None, site["owner"])
        ),
        None,
    )


def _is_root_candidate(site: dict[str, Any], context: _TreeContext) -> bool:
    """Whether this call could start a tree: an entry of either shape, or an
    OWNER-DECLARING continuation (which roots the chain it ends —
    `route(...).and(...)` is rooted at the `and`, since the `route` is consumed
    as its receiver).

    A vocabulary call is deliberately NOT a candidate. That is the whole of
    checkpoint F4: bodies hold nothing but vocabulary calls, and treating a
    method as a root because it merely contains one derives every nested route
    a second time, unprefixed.

    Nor is an owner-free continuation. Matching a bare method name against
    every owner is `fluent`'s steps discipline — right for REACHING a step
    inside a chain that is already known to be this catalog's, wrong for
    deciding a chain is this catalog's in the first place. A lone `and` on some
    unrelated type would otherwise be rooted and derive a row for a router
    nobody wrote.
    """
    continuation = _matching_continuation(site, context)
    return (
        _matching_entry(site, context) is not None
        or _matching_body_entry(site, context) is not None
        or (continuation is not None and continuation.owner is not None)
    )


def _matching_entry(site: dict[str, Any], context: _TreeContext) -> dict[str, Any] | None:
    return next(
        (
            entry
            for entry in context.entries
            if site["owner"] == entry["owner"] and site["name"] in entry["methods"]
        ),
        None,
    )


def _matching_body_entry(site: dict[str, Any], context: _TreeContext) -> dict[str, Any] | None:
    return next(
        (
            entry
            for entry in context.body_entries
            if site["owner"] == entry["owner"] and site["name"] == entry["method"]
        ),
        None,
    )


def _routes_of(site: dict[str, Any], scope: _Scope) -> list[_Route]:
    """The routes this call DECLARES — empty for a call that only contributes
    constraints (a bare prefix, a media predicate, a composer), which are
    folded by `_constraints_of` where they are reached instead.

    Dispatch order is significance order, not convenience: a prefix rule wins
    over an entry rule because one call is routinely both (a `nest` that both
    starts a tree and prefixes the subtree it holds), and an owner-qualified
    composer wins over an owner-free continuation because the same method name
    genuinely plays both roles on two different types.
    """
    context = scope.context
    key = (str(site["owner"]), str(site["name"]))
    prefix = context.prefixes.get(key)
    if prefix is not None:
        return _nested_routes(site, prefix, scope)
    verb = context.verbs.get(key)
    if verb is not None:
        # The two-argument verb form declares a whole route on its own; the
        # one-argument form is a predicate, and only becomes a route once some
        # entry attaches a handler to it.
        return _verb_routes(site, verb, scope) if "handler_arg" in verb else []
    if key in context.media or key in context.composers:
        return []
    entry = _matching_entry(site, context)
    if entry is not None:
        # `_validate_matches` already refused an argument-rooted entry without
        # one, so the key is always there.
        return _declared_routes(
            site, frozenset({entry["handler_arg"]}), scope, extends_receiver=False
        )
    body_entry = _matching_body_entry(site, context)
    if body_entry is not None:
        return _body_routes(_arg_at(site["arguments"], body_entry["body_arg"]), scope)
    continuation = _matching_continuation(site, context)
    if continuation is not None:
        if continuation.subtree_arg is not None:
            return _nest_continuation_routes(site, continuation, scope)
        return _declared_routes(site, context.continuation_handlers, scope, extends_receiver=True)
    return []


def _constraints_of(site: dict[str, Any], scope: _Scope) -> list[_Route]:
    """The constraint branches this call contributes to whatever route reaches
    it — one branch normally, several where an `or` fans the route out."""
    context = scope.context
    key = (str(site["owner"]), str(site["name"]))
    verb = context.verbs.get(key)
    if verb is not None:
        return _verb_constraints(site, verb, scope)
    prefix = context.prefixes.get(key)
    if prefix is not None:
        return _argument_constraints(
            _arg_at(site["arguments"], prefix["path_arg"]), scope, (_PATH,)
        )
    media = context.media.get(key)
    if media is not None:
        return [_media_constraints(site, media, context)]
    composer = context.composers.get(key)
    if composer is not None:
        return _composed_constraints(site, composer, scope)
    return []


def _declared_routes(
    site: dict[str, Any],
    handler_positions: frozenset[int],
    scope: _Scope,
    *,
    extends_receiver: bool,
) -> list[_Route]:
    """One entry's or continuation's own routes: the chain it extends (a
    continuation only), plus one route per branch of every argument that is
    not a handler position.

    An argument whose producing call already declares routes contributes those
    routes unchanged — that is a router composed into another router, and it
    keeps its own handlers. One that declares only constraints becomes THIS
    call's route, with this call's handler attached. One that names nothing
    readable is the spec §1c case that must never vanish: a single unresolved
    row.
    """
    arguments = site["arguments"]
    handler = _handler_of(arguments, handler_positions, scope.context.method_symbols)
    routes: list[_Route] = []
    if extends_receiver:
        routes.extend(_chained_routes(site, scope))
    for position, argument in enumerate(arguments):
        if position in handler_positions:
            continue
        for branch in _argument_routes(argument, scope):
            routes.append(
                branch if branch.handler is not None else replace(branch, handler=handler)
            )
    return routes


def _nest_continuation_routes(
    site: dict[str, Any], continuation: _Continuation, scope: _Scope
) -> list[_Route]:
    """The nest-shaped continuation: the routes of the chain it extends, PLUS
    the routes of the whole router at its `subtree_arg`, each carrying the
    prefix at its `path_arg`.

    The prefix lands on the SUBTREE's routes only — the chain to its left is
    already complete and was never inside this nest. A plain continuation's
    argument fold cannot serve here: it would read the second argument as a
    handler slot (skipping it entirely) and the first as this call's own
    predicate, which drops every route the subtree declares and emits a
    handler-less row where they should have been.
    """
    arguments = site["arguments"]
    routes = list(_chained_routes(site, scope))
    subtree = _subtree_routes(_arg_at(arguments, continuation.subtree_arg), scope)
    prefixes = _argument_constraints(_arg_at(arguments, continuation.path_arg), scope, (_PATH,))
    routes.extend(_merged(prefix, route) for prefix in prefixes for route in subtree)
    return routes


def _chained_routes(site: dict[str, Any], scope: _Scope) -> list[_Route]:
    """The routes of the chain a continuation extends. A receiver naming no
    routing call this method can see — its producing call is in another method,
    or is not a routing call at all — is one honest unresolved row rather than
    a silently shorter route set; a continuation with no receiver at all
    extends nothing and says nothing."""
    if site["receiver"] is None:
        return []
    extended = _producing_site(site["receiver"], scope, exclude=site)
    chained = _routes_of(extended, scope) if extended is not None else []
    return chained or [_Route(poisons=_IDENTITY_POISON)]


def _subtree_routes(argument: dict[str, Any] | None, scope: _Scope) -> list[_Route]:
    """The router one argument holds, by whichever of the two links it carries
    — the same recursion the entry-shaped `nest` makes. A `lambda`-kind
    argument names a method whose body holds the routes; anything else is an
    expression in this same method, reached through its `source`."""
    if argument is not None and argument.get("kind") == "lambda":
        return _body_routes(argument, scope)
    return _argument_routes(argument, scope)


def _nested_routes(site: dict[str, Any], rule: dict[str, Any], scope: _Scope) -> list[_Route]:
    """A prefix rule's routes: its own path contribution pushed onto every
    route of the subtree it holds — an argument (`subtree_arg`) where the
    subtree is an expression in this same method, a linked body (`body_arg`)
    where it is a block the compiler moved into a method of its own. A prefix
    holding neither declares no route at all; it is a constraint, folded where
    some predicate argument reaches it."""
    arguments = site["arguments"]
    if "subtree_arg" in rule:
        subtree = _argument_routes(_arg_at(arguments, rule["subtree_arg"]), scope)
    elif "body_arg" in rule:
        subtree = _body_routes(_arg_at(arguments, rule["body_arg"]), scope)
    else:
        return []
    prefixes = _argument_constraints(_arg_at(arguments, rule["path_arg"]), scope, (_PATH,))
    return [_merged(prefix, route) for prefix in prefixes for route in subtree]


def _body_routes(argument: dict[str, Any] | None, scope: _Scope) -> list[_Route]:
    """The routes declared by the method a `lambda`-kind argument names — the
    jump a body-linked entry and a body-linked prefix both make (checkpoint
    (1b): both arities carry the body's method symbol exactly, so no heuristic
    is involved).

    Inside that body every claimed, unconsumed call is folded: the body is a
    sequence of route declarations rather than an expression, so there is no
    single root to start from. A body the facts do not carry — the block
    compiled into a container this scan never saw — is one unresolved row.
    """
    if argument is None or argument.get("kind") != "lambda":
        return [_Route(poisons=_IDENTITY_POISON)]
    symbol = argument.get("symbol")
    sites = scope.context.by_bare_caller.get(str(symbol)) if symbol is not None else None
    if not sites:
        return [_Route(poisons=_IDENTITY_POISON)]
    body = _scope_of(sites, scope.context)
    routes: list[_Route] = []
    for site in body.sites:
        result = site["result"]
        if result is not None and result in body.consumed:
            continue
        routes.extend(_routes_of(site, body))
    return routes


def _verb_routes(site: dict[str, Any], rule: dict[str, Any], scope: _Scope) -> list[_Route]:
    handler = _handler_of(
        site["arguments"], frozenset({rule["handler_arg"]}), scope.context.method_symbols
    )
    return [
        replace(constraint, handler=handler) for constraint in _verb_constraints(site, rule, scope)
    ]


def _verb_constraints(site: dict[str, Any], rule: dict[str, Any], scope: _Scope) -> list[_Route]:
    verb = _Route(verb=str(rule["verb"]))
    return [
        _merged(verb, branch)
        for branch in _argument_constraints(
            _arg_at(site["arguments"], rule["path_arg"]), scope, (_PATH,)
        )
    ]


def _media_constraints(site: dict[str, Any], rule: dict[str, Any], context: _TreeContext) -> _Route:
    """A media predicate's contribution: every argument the catalog can read as
    a wire value, sorted and distinct.

    An argument nobody can read contributes nothing, and that is the whole of
    its effect — the media column goes NULL while the row's own resolution is
    untouched. The route's identity is its verb and path, both fully known;
    calling the row unresolved because a `produces` list could not be read
    would misreport a known endpoint as an unknown one (2E checkpoint F1's
    ruling).

    Every media predicate a framework declares is VARARGS
    (`accept(MediaType...)`), so the constants arrive as one `array` slot
    rather than as one argument each, and `_expanded_arguments` reads that
    slot's own `elements` (2O Task 13, on extractor capability 9.15). *The
    sentence that stood here — "vararg constants in particular reach the
    facts with no symbol at all, which is exactly this case" — described the
    pre-9.15 fact and was why every predicate-derived media column came back
    NULL.* It still describes a vararg array the extractor cannot read end to
    end, which stays an unreadable slot and still contributes nothing.
    """
    values: list[str] = []
    for argument in _expanded_arguments(site["arguments"]):
        value = _media_value(argument, context)
        if value is not None and value not in values:
            values.append(value)
    read = tuple(sorted(values))
    if rule["fills"] == "consumes":
        return _Route(consumes=read)
    return _Route(produces=read)


def _media_value(argument: dict[str, Any], context: _TreeContext) -> str | None:
    """One media argument as a wire value: an enum constant translated through
    the catalog's declared member-name table, or a string literal taken
    verbatim (some frameworks spell their media types inline). Anything else —
    including an enum whose member the catalog never declared — reads as
    nothing."""
    kind = argument.get("kind")
    if kind == "string" and isinstance(argument.get("value"), str):
        return str(argument["value"])
    if kind != "enum":
        return None
    symbol = argument.get("symbol")
    if symbol is None:
        return None
    symbol = str(symbol)
    if context.media_owners is not None and owner_of(symbol) not in context.media_owners:
        return None
    return context.media_values.get(member_name(symbol))


def _composed_constraints(site: dict[str, Any], composer: str, scope: _Scope) -> list[_Route]:
    """`and` merges its operands' constraints into one; `or` keeps them as
    alternatives, which the fold above turns into one route per branch — over
    ANY predicate kind, verbs and paths and media alike (spec §1a's
    `all_methods` precedent)."""
    groups: list[list[_Route]] = []
    # A composer written as a static call takes every operand as an argument
    # and has no receiver to read; one written as a method on the expression
    # it extends carries its left operand there.
    if site["receiver"] is not None:
        groups.append(
            _operand_constraints(_producing_site(site["receiver"], scope, exclude=site), scope)
        )
    groups.extend(
        _operand_constraints(_producing_site(argument.get("source"), scope), scope)
        for argument in site["arguments"]
    )
    if not groups:
        return [_Route(poisons=_IDENTITY_POISON)]
    if composer == "or":
        return [branch for group in groups for branch in group]
    merged = groups[0]
    for group in groups[1:]:
        merged = [_merged(left, right) for left in merged for right in group]
    return merged


def _operand_constraints(site: dict[str, Any] | None, scope: _Scope) -> list[_Route]:
    branches = _constraints_of(site, scope) if site is not None else []
    return branches or [_Route(poisons=_IDENTITY_POISON)]


def _argument_routes(argument: dict[str, Any] | None, scope: _Scope) -> list[_Route]:
    """A routing-position argument's own routes — or, where its producing call
    declares only constraints, those constraints, for the caller to attach its
    handler to. Nothing readable at all poisons the whole identity: this is
    the cross-method `RouterFunction` reference (the walk is per-method by
    design, checkpoint (1a) shows the facts would support following it), and
    spec §1c requires one unresolved row for it rather than silence."""
    if argument is None:
        return [_Route(poisons=_IDENTITY_POISON)]
    producing = _producing_site(argument.get("source"), scope)
    if producing is not None:
        folded = _routes_of(producing, scope) or _constraints_of(producing, scope)
        if folded:
            return folded
    return [_Route(poisons=_IDENTITY_POISON)]


def _argument_constraints(
    argument: dict[str, Any] | None, scope: _Scope, poisons: tuple[str, ...]
) -> list[_Route]:
    """A path/predicate-position argument's own constraints: a string literal
    is the path itself, a linked argument is whatever its producing call
    contributes, and anything else poisons only what this position was
    supposed to fill."""
    if argument is None:
        return [_Route(poisons=poisons)]
    if argument.get("kind") == "string" and isinstance(argument.get("value"), str):
        return [_Route(path_parts=(str(argument["value"]),))]
    producing = _producing_site(argument.get("source"), scope)
    if producing is not None:
        branches = _constraints_of(producing, scope)
        if branches:
            return branches
    return [_Route(poisons=poisons)]


def _handler_of(
    arguments: list[dict[str, Any]],
    positions: frozenset[int],
    method_symbols: dict[str, str],
) -> str | None:
    """The handler symbol at the first declared position that yields one.

    A `lambda`-kind argument names its target BARE — a bound method reference
    names the real method, an inline block names the synthetic body the
    compiler emitted for it (D00 §5a) — so the name is JOINED to the method
    symbols the facts carry and the module-prefixed symbol found there is
    written verbatim; a handler that joined to no symbol fact would be a column
    nothing else in the graph could follow. Anything else — an argument of
    another kind (an adapted function object arrives as an `instance` of a
    generated class, which is a type and not a method), a name no scanned
    document declares, no argument at that position at all — reads NULL. The
    route still derives; only its handler is unread, and never invented.
    """
    for position in sorted(positions):
        argument = _arg_at(arguments, position)
        if argument is None or argument.get("kind") != "lambda":
            continue
        symbol = argument.get("symbol")
        found = method_symbols.get(str(symbol)) if symbol is not None else None
        if found is not None:
            return found
    return None


def _producing_site(
    value_id: Any, scope: _Scope, exclude: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """The call in this same method whose `result` is `value_id` (D00 §5's ids
    are meaningless across methods). `exclude` keeps a call that reports its
    own receiver back as its result from folding into itself — the same
    self-link guard `fluent`'s walk keeps."""
    if value_id is None:
        return None
    site = scope.by_result.get(int(value_id))
    return None if site is exclude else site


def _merged(left: _Route, right: _Route) -> _Route:
    """Two constraint sets folded into one, `left` outermost: paths
    concatenate in declaration order, media unions, and the first handler
    declared wins.

    A verb declared on BOTH sides poisons the verb rather than picking one. A
    request carries exactly one verb, so two of them inside a single `and`
    chain is a constraint no route can satisfy — reporting either would be a
    guess presented as fact, and reporting the row's identity as fully known
    would be worse. (`or` never reaches here: its branches stay separate
    routes, which is precisely how two verbs on one path are expressed.)
    """
    poisons = _union(left.poisons, right.poisons)
    if _METHOD in poisons or (left.verb is not None and right.verb is not None):
        verb = None
        poisons = _union(poisons, (_METHOD,))
    else:
        verb = left.verb if left.verb is not None else right.verb
    return _Route(
        verb=verb,
        path_parts=left.path_parts + right.path_parts,
        consumes=_union(left.consumes, right.consumes),
        produces=_union(left.produces, right.produces),
        handler=left.handler if left.handler is not None else right.handler,
        poisons=poisons,
    )


def _union(left: tuple[str, ...], right: tuple[str, ...]) -> tuple[str, ...]:
    """Sorted and distinct — a tuple rather than a set, so every value the fold
    carries has one order and one order only (NFR-1)."""
    return tuple(sorted(set(left) | set(right)))


def _row_of(route: _Route, caller: str, catalog: Catalog) -> dict[str, Any]:
    """One folded route as an endpoint row, media still held as lists — the
    union below needs them comparable before they become JSON text."""
    return {
        "protocol": catalog.protocol,
        "direction": catalog.direction,
        "method": None if _METHOD in route.poisons else route.verb,
        "path": _path_of(route, catalog),
        "handler": route.handler,
        "caller": caller,
        "peer": None,
        "handler_signature": None,
        "resolution": "unresolved" if route.poisons else "resolved",
        "evidence": "compiler",
        "catalog_id": catalog.id,
        "request_shape": None,
        "response_shape": None,
        "consumes": list(route.consumes),
        "produces": list(route.produces),
    }


def _path_of(route: _Route, catalog: Catalog) -> str | None:
    """The folded route's own address, as the URL the framework serves it at.

    The canonicalization is `domain/paths.py`'s, called HERE — before
    `_emitted` dedups on `path` — because it is identity: two spellings of one
    URL must be one row, and a seam applied after the dedup key was built
    would leave both. It is INBOUND-HTTP-only for that module's stated reasons
    (ruling R8: a client's slashless mapping is resolved against its base
    address's path, so prefixing one rewrites an address rather than
    normalizing a spelling), and the gate is the CATALOG's protocol and
    direction rather than the row's: both are still the catalog's at this
    point (`protocol_hint` reclassifies later, which is how an SSE row
    inherits this without naming `sse` here, and D02 §3's merge mints `both`
    later still).
    """
    if _PATH in route.poisons or not route.path_parts:
        return None
    path = "".join(route.path_parts)
    return canonical_http_path(path) if serves_urls(catalog.protocol, catalog.direction) else path


def _emitted(rows: list[dict[str, Any]], catalog: Catalog) -> list[dict[str, Any]]:
    """The batch as it reaches the insert: media unioned within the batch, then
    deduplicated on wire identity, then serialized.

    The union comes first because it is what decides which rows are duplicates
    at all — two `or` branches differing only in the media they declare are one
    endpoint (spec §4, the same rule `derive_endpoints.sql` applies to
    annotation rows), and comparing them before folding would keep both.

    Only an identity-KNOWN row takes part in EITHER step, exactly as every
    other style: two routes whose paths nobody could read carry nothing to
    compare, so each stays its own row through the union and never enters the
    dedup key. That is `derive_call_endpoints.sql`'s own written contract —
    SQL's `NULL = NULL` is unknown rather than true, so two unresolved rows are
    two distinct "this method declares something" facts, and collapsing them
    here would hide one of them before the insert ever saw it.

    `handler` is part of the key rather than decoration — two handlers bound to
    one wire identity are two facts (the `interface_implementation` parity
    rule), and a key without it would silently discard the second.
    """
    seen: set[tuple[str, str, str, str, str]] = set()
    emitted: list[dict[str, Any]] = []
    for row in _media_unioned(rows):
        if row["path"] is not None:
            key = (
                catalog.protocol,
                catalog.direction,
                row["method"] or "",
                row["path"],
                row["handler"] or "",
            )
            if key in seen:
                continue
            seen.add(key)
        emitted.append(
            {
                **row,
                "consumes": _media_json(row["consumes"]),
                "produces": _media_json(row["produces"]),
            }
        )
    return emitted


def _media_unioned(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rows differing ONLY in their declared media folded into one, in
    first-seen order (NFR-1).

    A row with no readable path is passed through untouched and never grouped.
    Grouping compares columns for equality, and two rows whose identity columns
    are all NULL compare equal to each other while standing for two genuinely
    different unread declarations — `derive_call_endpoints.sql` keeps both for
    exactly that reason, and a union that collapsed them would contradict the
    contract this batch is written against.
    """
    grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
    unioned: list[dict[str, Any]] = []
    for row in rows:
        if row["path"] is None:
            unioned.append(dict(row))
            continue
        key = tuple(row[field] for field in _GROUPED_FIELDS)
        existing = grouped.get(key)
        if existing is None:
            fresh = dict(row)
            grouped[key] = fresh
            unioned.append(fresh)
            continue
        for field in _MEDIA_FIELDS:
            existing[field] = sorted(set(existing[field]) | set(row[field]))
    return unioned


def _media_json(values: list[str]) -> str | None:
    """A media column: a JSON array of the declared wire values, or NULL where
    nothing was derivable (spec §4) — the same text
    `derive_endpoints.sql`'s own `to_json` writes for annotation rows."""
    return json.dumps(values, separators=(",", ":")) if values else None


def _validate_matches(catalog: Catalog) -> None:
    """Refuses a broken catalog before any call site is matched (the
    `single_call._validate_methods`/`interface_implementation._validate_matches`
    precedent): an entry that is neither of the two declared shapes, and a
    media rule filling a column that does not exist, are both broken files
    rather than degraded runs — the second especially, since a typo there
    would silently file every value it reads under the wrong column.

    `continuations` is checked hardest, because it is the one block where two
    declarations can silently claim the same call: the same method name is
    routinely a composer on one type and a chain continuation on another, and
    only an `owner` tells them apart."""
    _validate_continuations(catalog)
    for entry in catalog.matches.get("entries", []):
        argument_rooted = "methods" in entry and "handler_arg" in entry
        body_linked = "method" in entry and "body_arg" in entry
        if "owner" not in entry or argument_rooted == body_linked:
            raise CatalogError(
                f"loading catalog {catalog.source}: every `entries` item is either "
                f"`{{owner, methods, handler_arg}}` or `{{owner, method, body_arg}}`, "
                f"got {entry!r} (D02 §2's `combinator` style)"
            )
    for rule in catalog.matches.get("vocabulary", {}).get("media", []):
        if rule.get("fills") not in _MEDIA_FIELDS:
            raise CatalogError(
                f"loading catalog {catalog.source}: `{rule.get('method')}` declares "
                f"`fills: {rule.get('fills')!r}` — a media rule fills `consumes` or "
                f"`produces` (D02 §2's `combinator` style)"
            )


def _validate_continuations(catalog: Catalog) -> None:
    """Refuses a `continuations` block that cannot be read unambiguously.

    Three ways it can be broken, all of them silent otherwise:

    - an entry that is neither a plain name nor a mapping carrying one, or a
      mapping declaring only half of the `path_arg`/`subtree_arg` pair — a
      nest-shaped continuation needs both, and half of it would fold as the
      plain shape and drop the subtree;
    - two entries sharing a name with no `owner` telling them apart — silent
      last-wins would hide exactly the bug the check exists for
      (`fluent._validate_steps`, same rule for the same reason);
    - a name that is ALSO a declared composer method on the same owner, or on
      any owner where the continuation declares none. Those two roles fold a
      call completely differently — one merges constraints, the other merges
      route sets — and dispatch order, not the catalog, would decide which
      won. The one shape deliberately allowed is the same name declared for
      BOTH roles on two DIFFERENT owners, which is the frozen reality this
      style was built for (checkpoint (1a): a predicate type and a router type
      each declare `and`), and there the owners make the reading exact.
    """
    composer_owners: dict[str, list[str]] = {}
    for role in catalog.matches.get("vocabulary", {}).get("composers", {}).values():
        for rule in role:
            composer_owners.setdefault(rule["method"], []).append(_catalog_symbol(rule["owner"]))
    by_name: dict[str, list[str | None]] = {}
    name: str
    owner: str | None
    positions: tuple[str, ...]
    for entry in catalog.matches.get("continuations", []):
        if isinstance(entry, str):
            name, owner, positions = entry, None, ()
        elif isinstance(entry, dict) and isinstance(entry.get("name"), str):
            name = entry["name"]
            owner = _catalog_symbol(entry["owner"]) if "owner" in entry else None
            positions = tuple(key for key in ("path_arg", "subtree_arg") if key in entry)
        else:
            raise CatalogError(
                f"loading catalog {catalog.source}: every `continuations` item is either a "
                f"method name or `{{name, owner?, path_arg?, subtree_arg?}}`, got {entry!r} "
                f"(D02 §2's `combinator` style)"
            )
        if len(positions) == 1:
            raise CatalogError(
                f"loading catalog {catalog.source}: continuation `{name}` declares "
                f"`{positions[0]}` alone — the nest-shaped continuation needs `path_arg` "
                f"and `subtree_arg` together (D02 §2's `combinator` style)"
            )
        if name in composer_owners and (owner is None or owner in composer_owners[name]):
            raise CatalogError(
                f"loading catalog {catalog.source}: `{name}` is declared as both a composer "
                f"and a continuation with no `owner` telling the two apart — the two roles "
                f"fold a call differently (D02 §2's `combinator` style)"
            )
        by_name.setdefault(name, []).append(owner)
    for name, owners in by_name.items():
        if len(owners) > 1 and (None in owners or len(set(owners)) != len(owners)):
            raise CatalogError(
                f"loading catalog {catalog.source}: continuations named `{name}` need "
                f"distinct `owner`s to tell them apart (D02 §2's `combinator` style)"
            )
