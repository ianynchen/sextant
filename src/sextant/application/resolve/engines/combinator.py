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
  bare (2E checkpoint F4) — and the root scan enforces that by skipping every
  method some linking call names as its body (`linked_bodies`), not by
  trusting bodies to hold only vocabulary calls: a Supplier body holds a
  whole chain, and its `build()` would root (A1 final review, I-1). The entry
  owner and the vocabulary owner are routinely two different types, so the
  catalog declares both.
- `vocabulary` — owner+method to role: `verbs` (a verb plus whichever of a
  literal-path `path_arg`, a `path` the rule states itself — the empty string,
  for an overload that serves exactly the prefix it sits under — a
  `predicate_arg` whose producing call's constraints fold in, and a
  `handler_arg` the overload carries), `prefixes` (a path
  contribution, plus optionally the `subtree_arg`/`body_arg` holding the
  routes it prefixes), `media` (which of `consumes`/`produces` the call fills),
  `media_values` (an enum type's member names to their wire values), and
  `composers` (`and` merges constraints, `or` duplicates the route per branch).
  `verbs` and `prefixes` are scanned lists, so one name may carry several
  rules: `arity` and `arg_types` (position to dotted type, compared against the
  call's own erased descriptor) tell same-name overloads apart, a call the
  vocabulary names but no rule accepts is one unresolved row, and two rules
  that could both accept one call are refused at load (spec §3).
- `continuations` — the calls that merge route sets along `result` →
  `receiver`. A plain method name is owner-free, exactly like `fluent`'s
  steps; a mapping declares the same name with an `owner` that narrows it to
  one type, and — for the nest-shaped continuation — a `path_arg` and a
  `subtree_arg`, which make it fold its argument's whole router under its own
  prefix rather than reading a handler it does not have. A mapping declaring
  `pass_through: true` carries the chain on and reads NO argument: a filter, an
  attribute, an error handler is never a route (spec §4b).
- `origins` — the calls a builder chain STARTS at, `{owner, method}` plus the
  same `arity`/`arg_types` a verb rule takes, because the argument-less
  builder factory shares its name with the two-argument route it is not: a
  receiver produced by an origin contributes zero routes and poisons nothing,
  which is the difference between "the chain starts here" and "I could not
  read the receiver" — a distinction nothing needed until a builder made every
  chain start somewhere (spec §4b).
- `path_join` — how the framework joins the segments its prefixes and verbs
  are handed, applied to every literal path the fold reads. Absent, segments
  concatenate verbatim, exactly as written. `leading_slash` is the join a
  framework that normalises each segment itself performs — a `/` is put in
  front of a segment unless it already starts with one, is empty, or is the
  bare `*` — so `path("api", …)` over `get("x", h)` reads `/api/x`, the
  address that framework serves, never `apix`. A catalog declares it because
  the join is the framework's rule, measured from its own prefix code, not
  this engine's guess (A2 Task 3 fix round 1).

**The builder chain (spec §4).** `route().GET("/a", h).POST("/b", h).build()`
is a chain whose every verb both declares its own route AND carries the chain
onward. A verb or prefix rule declaring `extends_receiver: true` folds the
routes of the call producing its receiver in front of its own, exactly as a
continuation does; `build()` is a declared continuation and, being consumed by
nothing, is where the walk roots. A verb rule declaring `handler: none` in
place of `handler_arg` is a route served with no handler method — a static
resource (spec §6).

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
from sextant.domain.symbols import (
    bare_descriptor,
    descriptor_parameter_types,
    member_name,
    owner_of,
)

# The two endpoint columns a failed read can poison. Both are wire identity,
# so poisoning either drops the row's own `resolution` (checkpoint ruling I1,
# shared with `single_call`/`fluent`) — unlike the media columns, which are
# carried data and go NULL on their own without touching resolution.
_METHOD = "method"
_PATH = "path"
_IDENTITY_POISON = (_METHOD, _PATH)

# The address of a route that constrains no path at all — the framework's
# any-path pattern, which is what a catch-all serves (spec §7 case 3).
_ANY_PATH = "/**"

# The one `path_join` a catalog may declare, beside "absent" (verbatim). Named
# here so a typo in a catalog is refused at load rather than silently read as
# verbatim — which would publish the glued address the word exists to prevent.
_LEADING_SLASH = "leading_slash"

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
        # A linked body is folded by the root that reaches its linking call,
        # and never scanned for roots of its own (`linked_bodies`).
        if bare_descriptor(caller) in context.linked_bodies:
            continue
        scope = _scope_of(sites, context)
        # Sites arrive ordinal-ordered (the `call_sites` query), so the trees
        # of one method are rooted in source order and their rows accumulate
        # in that order too (NFR-1).
        for site in sites:
            if not _is_root_candidate(site, scope):
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
    predicate and a handler. `pass_through` is the third shape: the chain
    carried on and no argument read at all (spec §4b), which never combines
    with the nest-shaped pair."""

    name: str
    owner: str | None
    path_arg: int | None
    subtree_arg: int | None
    pass_through: bool


@dataclass(frozen=True)
class _TreeContext:
    """Everything every tree in the run shares — the catalog's own vocabulary,
    already converted to the symbol forms the facts are keyed on, plus the two
    cross-method indexes (bodies by their bare caller descriptor, method
    symbols by their bare descriptor) a fold reaches for."""

    entries: tuple[dict[str, Any], ...]
    body_entries: tuple[dict[str, Any], ...]
    verbs: tuple[dict[str, Any], ...]
    prefixes: tuple[dict[str, Any], ...]
    # Every (owner, name) any verb or prefix rule names — what makes a call CLAIMED
    # even when no overload rule accepts it (spec §3's G-13 guard).
    verb_names: frozenset[tuple[str, str]]
    prefix_names: frozenset[tuple[str, str]]
    media: dict[tuple[str, str], dict[str, Any]]
    media_owners: tuple[str, ...] | None
    media_values: dict[str, str]
    composers: dict[tuple[str, str], str]
    continuations: tuple[_Continuation, ...]
    # The rules a chain may START at without poisoning (spec §4b) — the argument-
    # less builder factory, and nothing else either shipped catalog names. Rules,
    # not names: the factory shares its name with the two-argument route form, and
    # `arity: 0` is what tells them apart (spec §3). `origin_names` is the claimed
    # set, as `verb_names` is for verbs.
    origins: tuple[dict[str, Any], ...]
    origin_names: frozenset[tuple[str, str]]
    # `matches.path_join`: None for verbatim concatenation, `leading_slash` for the
    # framework-side normalisation `_literal_path` applies to every literal read.
    path_join: str | None
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
    # The bare symbol of every method some LINKING call names as its body — a
    # body-linked entry's or a prefix rule's `body_arg`, a nest-shaped
    # continuation's `subtree_arg`. The root scan skips these methods whole: a
    # body is folded exactly once, by whichever root reaches the call that
    # links it, and is never scanned for roots of its own. The chain-head test
    # in `_is_root_candidate` protects only receiver-extending verbs and
    # prefixes; a Supplier body holds a whole chain whose `build()` — an
    # owner-declaring continuation — nothing in the body consumes, and an
    # `add(router)` inside a Consumer body is the same shape. Both rooted and
    # derived their route a second time, bare, with the lambda as `caller`
    # (A1 final review, I-1).
    linked_bodies: frozenset[str]


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
    verbs = _rules_of(vocabulary.get("verbs", []))
    prefixes = _rules_of(vocabulary.get("prefixes", []))
    origins = _rules_of(matches.get("origins", []))
    context = _TreeContext(
        entries=entries,
        body_entries=body_entries,
        verbs=verbs,
        prefixes=prefixes,
        verb_names=frozenset((rule["owner"], rule["method"]) for rule in verbs),
        prefix_names=frozenset((rule["owner"], rule["method"]) for rule in prefixes),
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
        origins=origins,
        origin_names=frozenset((rule["owner"], rule["method"]) for rule in origins),
        path_join=matches.get("path_join"),
        continuation_handlers=frozenset(
            entry["handler_arg"] for entry in entries if "handler_arg" in entry
        ),
        by_caller=by_caller,
        by_bare_caller=by_bare_caller,
        method_symbols=method_symbols,
        linked_bodies=frozenset(),
    )
    # Read off the call sites the catalog claims, so the matchers above decide
    # which calls link a body — the same matchers the fold jumps through.
    return replace(context, linked_bodies=_linked_bodies(call_sites, context))


def _linked_bodies(call_sites: list[dict[str, Any]], context: _TreeContext) -> frozenset[str]:
    """The bare symbol of every `lambda`-kind argument at a linking position: a
    body-linked entry's `body_arg`, a prefix rule's `body_arg`, a nest-shaped
    continuation's `subtree_arg`. Only a LINKING call names a body; a lambda
    handed to a method the catalog does not claim is a method like any other,
    and the root scan reaches it as before."""
    bodies: set[str] = set()
    for site in call_sites:
        positions: list[int] = []
        entry = _matching_body_entry(site, context)
        if entry is not None:
            positions.append(entry["body_arg"])
        if (str(site["owner"]), str(site["name"])) in context.prefix_names:
            rule = _matching_rule(site, context.prefixes)
            if rule is not None and "body_arg" in rule:
                positions.append(rule["body_arg"])
        continuation = _matching_continuation(site, context)
        if continuation is not None and continuation.subtree_arg is not None:
            positions.append(continuation.subtree_arg)
        for position in positions:
            argument = _arg_at(site["arguments"], position)
            if argument is not None and argument.get("kind") == "lambda":
                symbol = argument.get("symbol")
                if symbol is not None:
                    bodies.add(str(symbol))
    return frozenset(bodies)


def _continuations_of(declared: list[Any]) -> tuple[_Continuation, ...]:
    """`continuations`' two forms, normalized to one: a plain method name is
    the owner-free continuation, a mapping carries the same `name` plus
    whichever of `owner`/`path_arg`/`subtree_arg`/`pass_through` the catalog
    declared. Only ever called on entries `_validate_matches` already passed."""
    return tuple(
        _Continuation(name=entry, owner=None, path_arg=None, subtree_arg=None, pass_through=False)
        if isinstance(entry, str)
        else _Continuation(
            name=entry["name"],
            owner=_catalog_symbol(entry["owner"]) if "owner" in entry else None,
            path_arg=entry.get("path_arg"),
            subtree_arg=entry.get("subtree_arg"),
            pass_through=bool(entry.get("pass_through", False)),
        )
        for entry in declared
    )


def _by_owner_method(rules: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(_catalog_symbol(rule["owner"]), rule["method"]): rule for rule in rules}


def _rules_of(rules: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    """A list, not a dict keyed on (owner, name) — the shape `single_call` moved to
    for the same reason (its `methods` block, Task 6): a dict lets a second rule for
    the same name silently overwrite the first, and a builder declares four `GET`s."""
    return tuple({**rule, "owner": _catalog_symbol(rule["owner"])} for rule in rules)


def _matching_rule(
    site: dict[str, Any], rules: tuple[dict[str, Any], ...]
) -> dict[str, Any] | None:
    """The one rule that accepts this call: owner and name equal, `arity` equal where
    the rule declares one, and every position in `arg_types` carrying that type in
    the call's own erased descriptor. Positions a rule does not type are unconstrained.
    At most one rule can accept a call — `_validate_overloads` refused any catalog
    where two could — so the first found is the only one."""
    owner, name = str(site["owner"]), str(site["name"])
    arguments = site["arguments"]
    types: tuple[str, ...] | None = None
    for rule in rules:
        if rule["owner"] != owner or rule["method"] != name:
            continue
        if rule.get("arity") not in (None, len(arguments)):
            continue
        wanted: dict[int, str] = rule.get("arg_types") or {}
        if wanted:
            if types is None:
                types = descriptor_parameter_types(str(site["descriptor"]))
            if any(
                position >= len(types) or types[position] != typed
                for position, typed in wanted.items()
            ):
                continue
        return rule
    return None


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
    consumed; and a declared origin, which declares nothing and is never a
    root, but is the head of a chain and so part of that chain's tree."""
    key = (str(site["owner"]), str(site["name"]))
    return (
        key in context.verb_names
        or key in context.prefix_names
        or key in context.media
        or key in context.composers
        or key in context.origin_names
        or _matching_entry(site, context) is not None
        or _matching_body_entry(site, context) is not None
        or _matching_continuation(site, context) is not None
    )


def _extends_a_receiver(site: dict[str, Any], context: _TreeContext) -> bool:
    """Whether this call's receiver is the expression it extends — a composer,
    a continuation, or a verb/prefix rule declaring `extends_receiver` (a
    builder verb, spec §4). The receiver of such a call is consumed by it, so
    the call producing that receiver is not a tree of its own: without this,
    every verb of a builder body would root beside the chain that already
    folds it, and derive its route a second time."""
    key = (str(site["owner"]), str(site["name"]))
    if key in context.composers or _matching_continuation(site, context) is not None:
        return True
    if key in context.verb_names:
        rule = _matching_rule(site, context.verbs)
    elif key in context.prefix_names:
        rule = _matching_rule(site, context.prefixes)
    else:
        return False
    return rule is not None and bool(rule.get("extends_receiver"))


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


def _is_root_candidate(site: dict[str, Any], scope: _Scope) -> bool:
    """Whether this call could start a tree: an entry of either shape, an
    OWNER-DECLARING continuation (which roots the chain it ends —
    `route(...).and(...)` is rooted at the `and`, since the `route` is consumed
    as its receiver), or a receiver-extending verb whose receiver a call in
    THIS method produced — the statement form of a builder (spec §4 as ruled):
    the builder is mutable and every method returns it, so `b.GET("/a", h);
    b.POST("/b", h); return b.build();` leaves each verb's own result consumed
    by nothing, and each roots and derives its route where before only
    `build()` rooted and derived nothing. In the chained form every
    intermediate verb's result IS consumed, so the root scan skips it and
    `build()` alone roots, unchanged. A receiver-extending PREFIX (the
    builder's `path`/`nest`) is a candidate on the same terms.

    A vocabulary call inside a BODY is deliberately NOT a candidate. That is
    the whole of checkpoint F4: bodies hold nothing but vocabulary calls, and
    treating a method as a root because it merely contains one derives every
    nested route a second time, unprefixed. A body's chain sits on the body's
    own parameter: its head carries `receiver_parameter` and no producing
    call — and a body chains its verbs too (`b.GET(…).DELETE(…)`, the second
    verb's receiver a call in the same method), so the test is on the chain's
    HEAD, not on the verb's own receiver. `_body_routes` alone folds them.
    That head test covers the verbs and prefixes a body's builder parameter
    carries; a body holding a chain of its OWN (a Supplier body's `route()…
    build()`, an `add(router)` on the body's parameter) passes it, and `run`
    is what keeps such a body out of the root scan altogether
    (`linked_bodies`).

    Nor is an owner-free continuation. Matching a bare method name against
    every owner is `fluent`'s steps discipline — right for REACHING a step
    inside a chain that is already known to be this catalog's, wrong for
    deciding a chain is this catalog's in the first place. A lone `and` on some
    unrelated type would otherwise be rooted and derive a row for a router
    nobody wrote.
    """
    context = scope.context
    continuation = _matching_continuation(site, context)
    return (
        _matching_entry(site, context) is not None
        or _matching_body_entry(site, context) is not None
        or (continuation is not None and continuation.owner is not None)
        or _is_statement_verb_or_prefix(site, scope)
    )


def _is_statement_verb_or_prefix(site: dict[str, Any], scope: _Scope) -> bool:
    """A receiver-extending verb OR prefix rule accepting this call — a builder's
    `path`/`nest` are prefixes and are written as statements exactly as its verbs
    are — whose receiver a call in this same method produced (never itself), and
    whose chain does not begin on one of this method's own parameters: that
    head is a builder body's, and the body walk folds it (checkpoint F4)."""
    key = (str(site["owner"]), str(site["name"]))
    if key in scope.context.verb_names:
        rule = _matching_rule(site, scope.context.verbs)
    elif key in scope.context.prefix_names:
        rule = _matching_rule(site, scope.context.prefixes)
    else:
        return False
    if rule is None or not rule.get("extends_receiver"):
        return False
    extended = _producing_site(site["receiver"], scope, exclude=site)
    return extended is not None and _chain_head(extended, scope).get("receiver_parameter") is None


def _chain_head(site: dict[str, Any], scope: _Scope) -> dict[str, Any]:
    """The first call of the receiver chain `site` ends — the one whose receiver
    no call in this method produced."""
    while (previous := _producing_site(site["receiver"], scope, exclude=site)) is not None:
        site = previous
    return site


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
    if key in context.prefix_names:
        prefix = _matching_rule(site, context.prefixes)
        if prefix is None:
            return [_Route(poisons=_IDENTITY_POISON)]
        return _nested_routes(site, prefix, scope)
    if key in context.verb_names:
        verb = _matching_rule(site, context.verbs)
        if verb is None:
            # Spec §3, the G-13 guard: the vocabulary names this call and no overload
            # rule accepts it. One row that says so, never silence — silence is the
            # one outcome this engine's doctrine forbids, and reading positions off a
            # sibling overload is the wrong row it forbids next.
            return [_Route(poisons=_IDENTITY_POISON)]
        # The declaring forms carry a handler position — or `handler: none`, a
        # route served with no handler method (spec §6); a bare predicate factory
        # becomes a route only once some entry attaches a handler to it.
        return _verb_routes(site, verb, scope) if _declares_a_route(verb) else []
    if key in context.media:
        # A media call is a constraint contributor — it declares no route, and reaching
        # it here (unconsumed) is nothing to report. UNLESS it was handed a handler: a
        # `lambda`-kind argument on a call whose rule reads media values is the
        # route-declaring overload of that name (a builder DSL's `accept(MediaType,
        # Function1)`, measured on both routing stacks), and a declared route absent
        # with nothing saying so is spec §3's forbidden outcome. One unresolved row, no
        # handler — the handler position is not one this rule declares. Reading it
        # properly (the media value as the route's own constraint, plus its handler) is
        # a catalog word this grammar does not have yet; tracked on the register as
        # `dsl-media-route`.
        if _carries_a_handler(site):
            return [_Route(poisons=_IDENTITY_POISON)]
        return []
    if key in context.composers:
        # A composer is excluded from that check on evidence: no measured `and`/`or`
        # overload on any owner carries a handler (each takes two predicates, or a
        # predicate and a path string), so a `lambda`-kind operand on one is a
        # predicate, not a handler, and poisoning it would invent a route.
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
        if continuation.pass_through:
            # Declared to carry the chain and read nothing: its arguments are
            # filters, attributes, error handlers — never a route (spec §4b, §5).
            return _chained_routes(site, scope)
        if continuation.subtree_arg is not None:
            return _nest_continuation_routes(site, continuation, scope)
        return _declared_routes(site, context.continuation_handlers, scope, extends_receiver=True)
    return []


def _carries_a_handler(site: dict[str, Any]) -> bool:
    """Whether any argument of this call is a `lambda`-kind one — a handler, on a call
    whose rule has no handler position to read it at."""
    return any(argument.get("kind") == "lambda" for argument in site["arguments"])


def _is_pass_through(site: dict[str, Any], context: _TreeContext) -> bool:
    continuation = _matching_continuation(site, context)
    return continuation is not None and continuation.pass_through


def _declares_a_route(rule: dict[str, Any]) -> bool:
    """Whether a verb rule declares a whole route on its own — it names where
    the handler sits, or says there is none — rather than a bare predicate."""
    return "handler_arg" in rule or rule.get("handler") == "none"


def _constraints_of(site: dict[str, Any], scope: _Scope) -> list[_Route]:
    """The constraint branches this call contributes to whatever route reaches
    it — one branch normally, several where an `or` fans the route out."""
    context = scope.context
    key = (str(site["owner"]), str(site["name"]))
    if key in context.verb_names:
        verb = _matching_rule(site, context.verbs)
        return _verb_constraints(site, verb, scope) if verb else [_Route(poisons=_IDENTITY_POISON)]
    if key in context.prefix_names:
        prefix = _matching_rule(site, context.prefixes)
        if prefix is None:
            return [_Route(poisons=_IDENTITY_POISON)]
        return _prefix_constraints(site, prefix, scope)
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
                branch if branch.handler is not None else replace(_served(branch), handler=handler)
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
    """The routes of the chain a continuation or a receiver-extending verb
    carries on. A receiver naming no routing call this method can see — its
    producing call is in another method, or is not a routing call at all — is
    one honest unresolved row rather than a silently shorter route set; a call
    with no receiver at all extends nothing and says nothing (a builder body's
    verbs sit on the body's own parameter, which is exactly this case); and a
    receiver produced by a DECLARED ORIGIN contributes nothing and poisons
    nothing — that is the difference between "the chain starts here" and "I
    could not read the receiver", which nothing could draw until a builder made
    every chain start somewhere (spec §4b). A pass-through in between is
    stepped THROUGH before deciding: it contributes nothing by definition, so
    its own empty route set must never read as an unread receiver —
    `route().filter(f).GET(…)` starts at the origin, clean."""
    if site["receiver"] is None:
        return []
    extended = _producing_site(site["receiver"], scope, exclude=site)
    while extended is not None and _is_pass_through(extended, scope.context):
        if extended["receiver"] is None:
            return []
        extended = _producing_site(extended["receiver"], scope, exclude=extended)
    if extended is not None and _matching_rule(extended, scope.context.origins) is not None:
        return []
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
    """A prefix rule's routes: its own contribution pushed onto every route of
    the subtree it holds — an argument (`subtree_arg`) where the subtree is an
    expression in this same method, a linked body (`body_arg`) where it is a
    block the compiler moved into a method of its own. A prefix holding neither
    declares no route at all; it is a constraint, folded where some predicate
    argument reaches it. A prefix declaring `extends_receiver` (a builder's
    `path`/`nest`, spec §5) carries the chain on as well, and the chain's routes
    come first: they were complete before this prefix and were never under it.

    Inside a body the builder is the body's own parameter, so its verbs carry
    no receiver this method can see; their chain contributes nothing (never a
    poison), and the body's routes fold cleanly under this prefix.
    """
    arguments = site["arguments"]
    if "subtree_arg" in rule:
        subtree = _argument_routes(_arg_at(arguments, rule["subtree_arg"]), scope)
    elif "body_arg" in rule:
        subtree = _body_routes(_arg_at(arguments, rule["body_arg"]), scope)
    else:
        return []
    routes = list(_chained_routes(site, scope)) if rule.get("extends_receiver") else []
    prefixes = _prefix_constraints(site, rule, scope)
    routes.extend(_merged(prefix, route) for prefix in prefixes for route in subtree)
    return routes


def _prefix_constraints(site: dict[str, Any], rule: dict[str, Any], scope: _Scope) -> list[_Route]:
    """What a prefix rule contributes: a literal path at `path_arg`, or the
    constraints of the predicate at `predicate_arg` — a path prefix or a media
    guard alike, whatever the predicate's producing call folds in."""
    position = rule["path_arg"] if "path_arg" in rule else rule["predicate_arg"]
    return _argument_constraints(_arg_at(site["arguments"], position), scope, (_PATH,))


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
    """A route-declaring verb's routes: its own constraints with its handler
    attached — NULL for `handler: none`, a route served with no handler method
    (spec §6) — and, when the rule extends its receiver, the routes of the
    chain to its left in front of them: a builder verb declares its own route
    AND carries the chain onward, so the routes to its left are as much its
    tree as its own (spec §4)."""
    handler = (
        None
        if rule.get("handler") == "none"
        else _handler_of(
            site["arguments"], frozenset({rule["handler_arg"]}), scope.context.method_symbols
        )
    )
    own = [
        replace(_served(constraint), handler=handler)
        for constraint in _verb_constraints(site, rule, scope)
    ]
    if rule.get("extends_receiver"):
        return [*_chained_routes(site, scope), *own]
    return own


def _served(route: _Route) -> _Route:
    """A route that is about to become a row and folded NO path part without
    its path being poisoned is a catch-all — a verb with only a handler, a
    media-only predicate — and it serves EVERY path: the framework's any-path
    pattern is its address (spec §7 case 3 as ruled). Contributed HERE, by the
    route that read no path, so a prefix over it composes as `/api/**` rather
    than `/api` — `_merged` puts the prefix in front of whatever the route
    carries, and by the time `_path_of` runs the prefix is already folded in.
    Anything with a path part, or a poisoned path, is returned as it is."""
    if route.path_parts or _PATH in route.poisons:
        return route
    return replace(route, path_parts=(_ANY_PATH,))


def _verb_constraints(site: dict[str, Any], rule: dict[str, Any], scope: _Scope) -> list[_Route]:
    """The verb, merged with whatever its declared positions contribute: a literal path
    at `path_arg`, a predicate's own constraints at `predicate_arg`, both, or neither —
    a verb naming no position at all is a catch-all, and it is RESOLVED: nothing was
    poisoned, the author wrote the route open (spec §7 case 3). A rule may instead
    state its path ITSELF, `path: ""` — a literal contribution the call carries no
    argument for, which is how a framework whose path-less overload registers the
    enclosing prefix plus the empty string is told apart from a catch-all: the route
    read a path, the empty one, so `_served` leaves it alone and the prefix folds in
    front of nothing (A2 Task 3). A rule whose `verb` is null names no verb of its
    own — the builder's `route(predicate, handler)` — and the predicate supplies one,
    or none; `method` then reads NULL without being poisoned."""
    verb = rule.get("verb")
    branches = [_Route(verb=None if verb is None else str(verb))]
    arguments = site["arguments"]
    if "path" in rule:
        branches = [_merged(branch, _Route(path_parts=(str(rule["path"]),))) for branch in branches]
    if "path_arg" in rule:
        paths = _argument_constraints(_arg_at(arguments, rule["path_arg"]), scope, (_PATH,))
        branches = [_merged(branch, path) for branch in branches for path in paths]
    if "predicate_arg" in rule:
        predicates = _argument_constraints(
            _arg_at(arguments, rule["predicate_arg"]), scope, (_PATH,)
        )
        branches = [_merged(branch, predicate) for branch in branches for predicate in predicates]
    return branches


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
        return [_Route(path_parts=(_literal_path(str(argument["value"]), scope.context),))]
    producing = _producing_site(argument.get("source"), scope)
    if producing is not None:
        branches = _constraints_of(producing, scope)
        if branches:
            return branches
    return [_Route(poisons=poisons)]


def _literal_path(literal: str, context: _TreeContext) -> str:
    """One literal path segment as the framework will join it — the catalog's
    `path_join` applied, or the literal untouched when none is declared. Every
    literal the fold reads for a path position passes through here, so a join
    declared once holds for prefixes, verbs and (when they are read) array
    elements alike; a rule's own `path: ""` does not, since the empty segment is
    exactly one the join leaves alone. `leading_slash` is the framework's own
    three exceptions, verbatim: a segment that already starts with `/`, the
    empty segment, and the bare `*` stay as written; every other segment gains
    a leading `/`. Two spellings of one registration must be one row, and the
    join is what makes `path("api", …)` and `path("/api", …)` the same address
    here as they are in the framework."""
    if (
        context.path_join == _LEADING_SLASH
        and literal not in ("", "*")
        and not literal.startswith("/")
    ):
        return "/" + literal
    return literal


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

    Two DIFFERENT verbs poison the verb rather than picking one. A request
    carries exactly one verb, so two of them inside a single `and` chain is a
    constraint no route can satisfy — reporting either would be a guess
    presented as fact, and reporting the row's identity as fully known would
    be worse. Two EQUAL verbs are that one verb (spec §4 as ruled): a
    handler-less `resource(GET("/favicon.ico"), r)` folds its rule's `GET`
    against the predicate's, and `GET` and `GET` is `GET`. (`or` never reaches
    here: its branches stay separate routes, which is precisely how two verbs
    on one path are expressed.)
    """
    poisons = _union(left.poisons, right.poisons)
    if _METHOD in poisons or (
        left.verb is not None and right.verb is not None and left.verb != right.verb
    ):
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

    A route that folded NO path part and was not poisoned is a catch-all — a
    verb with only a handler, or a media-only predicate — and it serves EVERY
    path, so its address is the framework's own any-path pattern, `/**`
    (spec §7 case 3 as ruled). Not NULL: on this side a resolved NULL path is
    what `derive_call_endpoints.sql`'s addresses-nothing gate drops by
    doctrine — "the address was read, and there is none" — which is the
    opposite of what a catch-all declares, so this engine never emits a
    resolved row with a NULL path. A poisoned path stays NULL: that row is
    unresolved, and the gate lets it through as the "something unreadable is
    declared here" fact it is.
    """
    if _PATH in route.poisons:
        return None
    path = "".join(route.path_parts) if route.path_parts else _ANY_PATH
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
    only an `owner` tells them apart.

    A verb rule says where its handler sits OR that there is none — both is
    two answers, and `extends_receiver` on a rule saying neither is a builder
    verb that declares no route, which is a continuation misfiled. An origin
    names an owner and a method, or it names nothing a receiver could match. A
    `path_join` is `leading_slash` or absent — a misspelt one read as absent
    would glue every slashless segment to its parent, the address the word
    exists to prevent."""
    _validate_continuations(catalog)
    for rule in catalog.matches.get("vocabulary", {}).get("verbs", []):
        handler_less = rule.get("handler") == "none"
        if "handler" in rule and not handler_less:
            raise CatalogError(
                f"loading catalog {catalog.source}: `{rule.get('method')}` declares "
                f"`handler: {rule.get('handler')!r}` — the only value is `none`, a route "
                f"served with no handler method (D02 §2's `combinator` style)"
            )
        if handler_less and "handler_arg" in rule:
            raise CatalogError(
                f"loading catalog {catalog.source}: `{rule.get('method')}` declares both "
                f"`handler_arg` and `handler: none` (D02 §2's `combinator` style)"
            )
        if rule.get("extends_receiver") and not _declares_a_route(rule):
            raise CatalogError(
                f"loading catalog {catalog.source}: `{rule.get('method')}` declares "
                f"`extends_receiver` without `handler_arg` or `handler: none` — a verb "
                f"that carries a chain declares a route of its own (D02 §2's `combinator` "
                f"style)"
            )
    if catalog.matches.get("path_join", _LEADING_SLASH) != _LEADING_SLASH:
        raise CatalogError(
            f"loading catalog {catalog.source}: `path_join: "
            f"{catalog.matches.get('path_join')!r}` — the only value is `{_LEADING_SLASH}`; "
            f"leave it out for verbatim concatenation (D02 §2's `combinator` style)"
        )
    for origin in catalog.matches.get("origins", []):
        if not isinstance(origin, dict) or "owner" not in origin or "method" not in origin:
            raise CatalogError(
                f"loading catalog {catalog.source}: every `origins` item is "
                f"`{{owner, method}}`, got {origin!r} (D02 §2's `combinator` style)"
            )
    # Last, once every rule is known to have the shape it reads.
    _validate_overloads(catalog)
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


def _validate_overloads(catalog: Catalog) -> None:
    """Spec §3c: never file order. Two rules that could both accept one call are
    refused here, naming both. Two rules sharing owner, method and arity are
    distinguishable only if some position BOTH of them type carries a different type
    in each — a call has one type per position, so then at most one can match. A rule
    with no `arity` accepts every arity and so collides with every other rule of its
    name; `arg_types` without `arity`, or a typed position at or beyond the arity, is a
    rule that cannot mean what it says. `origins` are rules of the same shape and are
    held to the same two checks."""
    vocabulary = catalog.matches.get("vocabulary", {})
    roles = {
        "verbs": vocabulary.get("verbs", []),
        "prefixes": vocabulary.get("prefixes", []),
        # Origins are matched by the same rule, so the same two checks bind them: the
        # argument-less factory is told from the route of the same name by `arity`.
        "origins": catalog.matches.get("origins", []),
    }
    for role, declared in roles.items():
        rules = list(declared)
        for rule in rules:
            typed = rule.get("arg_types") or {}
            arity = rule.get("arity")
            if typed and arity is None:
                raise CatalogError(
                    f"loading catalog {catalog.source}: `{rule.get('method')}` declares "
                    f"`arg_types` without `arity` (D02 §2's `combinator` style)"
                )
            for position in typed:
                if not isinstance(position, int) or arity is not None and position >= arity:
                    raise CatalogError(
                        f"loading catalog {catalog.source}: `{rule.get('method')}` types "
                        f"position {position} but declares arity {arity} "
                        f"(D02 §2's `combinator` style)"
                    )
        for index, left in enumerate(rules):
            for right in rules[index + 1 :]:
                # Compared in the symbol form `_matching_rule` compares — two spellings
                # of one owner are one owner to the matcher, so they are one here.
                if (_catalog_symbol(left["owner"]), left["method"]) != (
                    _catalog_symbol(right["owner"]),
                    right["method"],
                ):
                    continue
                if (
                    None not in (left.get("arity"), right.get("arity"))
                    and left["arity"] != right["arity"]
                ):
                    continue
                shared = set(left.get("arg_types") or {}) & set(right.get("arg_types") or {})
                if any(left["arg_types"][p] != right["arg_types"][p] for p in shared):
                    continue
                raise CatalogError(
                    f"loading catalog {catalog.source}: two `{role}` rules for "
                    f"`{left['method']}` at arity {left.get('arity')} could both accept one "
                    f"call — {left.get('arg_types') or {}} and {right.get('arg_types') or {}} "
                    f"type no shared position differently; a rule must type enough "
                    f"positions to be unambiguous (spec §3c)"
                )


def _validate_continuations(catalog: Catalog) -> None:
    """Refuses a `continuations` block that cannot be read unambiguously.

    Three ways it can be broken, all of them silent otherwise:

    - an entry that is neither a plain name nor a mapping carrying one, or a
      mapping declaring only half of the `path_arg`/`subtree_arg` pair — a
      nest-shaped continuation needs both, and half of it would fold as the
      plain shape and drop the subtree — or declaring that pair beside
      `pass_through`, which reads nothing and so cannot fold a subtree;
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
                f"method name or `{{name, owner?, path_arg?, subtree_arg?, pass_through?}}`, "
                f"got {entry!r} (D02 §2's `combinator` style)"
            )
        if len(positions) == 1:
            raise CatalogError(
                f"loading catalog {catalog.source}: continuation `{name}` declares "
                f"`{positions[0]}` alone — the nest-shaped continuation needs `path_arg` "
                f"and `subtree_arg` together (D02 §2's `combinator` style)"
            )
        if positions and isinstance(entry, dict) and entry.get("pass_through"):
            raise CatalogError(
                f"loading catalog {catalog.source}: continuation `{name}` declares "
                f"`pass_through` beside `path_arg`/`subtree_arg` — a pass-through reads "
                f"no argument (D02 §2's `combinator` style)"
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
