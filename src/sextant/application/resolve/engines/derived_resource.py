"""`derived_resource` engine for endpoint derivation (D02 §2's
`derived_resource` style, 2O design §2).

**The first style whose rows nobody declared.** Every other engine reads a
declaration and reports it: an annotation naming a path, a call naming an
address, a schema naming an operation. This one derives an HTTP API from an
interface that mentions no HTTP anywhere — Spring Data REST serves six routes
per exposed repository plus one per query method, and the module contains no
controller, no mapping annotation and no string that is a URL. The rule-table
shape is why this is not `annotation_driven` with `members:`: that style reads
a path and a verb OFF each member, while here the table is fixed BY FRAMEWORK
RULE per repository and only its CONDITIONS are read from the code.

**Which makes the precondition the whole safety property.** A rule of the form
*if the framework is present, these routes exist* derives nothing at all
without its antecedent — otherwise every plain Spring Data JPA module in every
analysed repository is reported as serving a REST API nobody wrote. The gate is
`resolve/dependencies.py` (`detect.coordinates`, ruling R9), applied before this
module is called, and its docstring states why it is not a deployment check and
why an unanswerable gate SKIPS rather than derives. Everything below is what
the framework does once the antecedent holds, verified live and recorded in
`scripts/probes/cp2_data_rest.md`.

**What the checkpoint changed about this engine** (CP-2, run live against
Boot 4.0.1 / spring-data-rest 5.0.1):

* **Which repositories are exposed is CONFIGURABLE**, and the spec did not say
  so. `spring.data.rest.detection-strategy` selects between four rules, and
  under `annotated` the un-annotated repositories this whole style exists to
  surface serve NOTHING. The default exposes every PUBLIC repository honouring
  `exported = false` — a package-private repository is exposed by no strategy
  but `all`, so an interface's own visibility is part of the rule, not a
  detail. Reading this key is not optional politeness: deriving the default
  route set for a module configured `annotated` would publish routes that do
  not exist.
* **Pluralization is NOT conditional on a second coordinate.**
  `spring-data-rest-core` depends on `org.atteo:evo-inflector` at compile
  scope, non-optionally, and an application without it dies at runtime rather
  than falling back to the unpluralized name. So a working Data REST
  application always pluralizes, and `domain/pluralize.py` is applied whenever
  the gate passes. (Checking for the coordinate as well would be actively
  wrong under Maven, whose recorded coordinates are DIRECT declarations only:
  a transitive evo-inflector would be absent from them, and the engine would
  derive `/order` — a path nobody serves.)
* **Item routes honour which CRUD interface is extended.** Since Spring Data 3
  `PagingAndSortingRepository` no longer extends `CrudRepository`, and a
  repository extending only it serves a collection GET and nothing else — not
  even an item GET. The catalog carries which operations each contract
  licenses; this module composes the table from them.
* **A declared method is a search route only if it is not a CRUD method.** An
  override of `findAll(Pageable)` gets no `/search/` route (observed 404).

**Where the entity type comes from, and the one shape it refuses.** The
collection path is the pluralized, first-character-uncapitalized simple name of
the ENTITY, which lives only in capability 9.14's `generic_interfaces` —
`interfaces` erases `CrudRepository<Order, Long>` to a bare symbol. The walk is
TOP-DOWN, from the hop that lands on the Spring Data contract back down to the
repository's own, taking the first type argument that is a real class: that
answers `CrudRepository<Order, Long>` directly, answers `BaseRepository<Note,
Long>` through a `@NoRepositoryBean` base whose own hop passes type VARIABLES
through, and answers a base that FIXES the entity with the entity the base
fixed. A base that PERMUTES its type parameters would defeat it, and no hop's
type-parameter list is in the facts to check against — a stated boundary
(COVERAGE), not a case this silently gets wrong in the common shapes.

**Chains through other jars are the other stated boundary** (2O design §2a):
the closure walk crosses interfaces DECLARED IN THIS MODULE only, because a
base repository shipped in a dependency has no facts here to walk.
"""

import json
from dataclasses import dataclass
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.domain.paths import canonical_http_path, serves_urls
from sextant.domain.pluralize import pluralize
from sextant.domain.symbols import (
    bare_descriptor,
    method_name,
    owner_of,
    simple_name,
    type_descriptor,
)

_REQUIRED_MATCHES = (
    "repositories",
    "routes",
    "item_segment",
    "search_segment",
    "resource_annotation",
    "member_annotation",
    "path_attribute",
    "exported_attribute",
    "no_repository_bean",
    "crud_methods",
    "base_path",
    "detection_strategy",
)

# The strategy flags the catalog's `detection_strategy.strategies` may name.
# A closed set, checked at load: a flag this module does not implement would
# read as a rule that is silently not applied.
_STRATEGY_FLAGS = frozenset({"public_only", "annotated_only", "honors_exported"})

# What the `default` strategy is when the key is absent — the framework's own
# default, named here as the fallback key rather than assumed as a flag set, so
# the flags themselves stay catalog data.
_DEFAULT_STRATEGY = "default"


@dataclass(frozen=True)
class _Repository:
    """One interface this module's facts show to BE a Spring Data repository,
    with everything the route table needs already read off it."""

    symbol: str
    # The collection path segment: `path=` when the annotation gave one, else
    # the pluralized uncapitalized entity simple name.
    collection: str
    # The CRUD operations the contracts it reaches license — which item routes
    # exist is a function of this and nothing else.
    operations: frozenset[str]
    # `{search path: query method symbol}`, one per exported query method.
    queries: dict[str, str]


@dataclass(frozen=True)
class _BasePath:
    """The configured base path, and whether configuration answered with ONE
    value.

    `prefix` is the literal to compose routes from — the resolved value, the
    empty string when nothing is configured (the framework's own default), or
    the `${key}` EXPRESSION verbatim when environments disagree. The expression
    is not a fabrication and not a guess: it is what D02 already does with an
    address it cannot resolve, and `domain/paths.py` leaves a placeholder-
    bearing path untouched precisely so an unresolved prefix cannot be
    canonicalized into a URL nobody serves.
    """

    prefix: str
    resolved: bool = True
    # `{environment: value}` for the divergent case, which is what the
    # `environment_divergence` question carries; empty otherwise.
    per_environment: dict[str, str | None] | None = None


def run(workspace: Workspace, catalog: Catalog) -> None:
    """One row per route in §2b's table, per exposed repository, plus one per
    exported query method.

    `handler` is NULL on every CRUD row and the query METHOD's own symbol on
    every search row, and the difference is the honest one: no code in this
    module serves `GET /orders` — the framework does — while
    `/orders/search/findByStatus` IS served by the method the repository
    declares. Inventing a handler for the first would name a symbol no fact
    emitted; dropping it from the second would discard one this style actually
    knows.

    `produces` carries the catalog's `default_produces` (D02's framework-
    contract default, D01 §4's evidence kind (b)): Data REST does not negotiate
    its representation the way an undeclared Spring MVC mapping does, it serves
    HAL. `consumes` stays NULL — the request side IS negotiated.
    """
    _validate_matches(catalog)
    repositories = _repositories(workspace, catalog)
    if not repositories:
        return
    base = _base_path(workspace, catalog)
    routes = list(catalog.matches["routes"])
    item_segment = str(catalog.matches["item_segment"])
    search_segment = str(catalog.matches["search_segment"])
    produces = _produces(catalog)

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None, str]] = set()
    for repository in repositories:
        for route in routes:
            needed = route.get("needs")
            if needed is not None and needed not in repository.operations:
                continue
            segments = [item_segment] if route.get("item") else []
            path = _path(catalog, base, repository.collection, *segments)
            _append(rows, seen, catalog, base, str(route["method"]), path, None, produces)
        for name, handler in sorted(repository.queries.items()):
            path = _path(catalog, base, repository.collection, search_segment, name)
            _append(rows, seen, catalog, base, "GET", path, handler, produces)
    workspace.derive("call_endpoints", rows=rows)


def gaps(workspace: Workspace, catalog: Catalog) -> list[dict[str, Any]]:
    """The `environment_divergence` question a base path that DIFFERS between
    environments earns (2O design §2b) — one per exposed repository, keyed to
    its collection route, because that is the identity whose prefix is in
    question.

    Filed from a separate pass rather than from `run`, for the reason
    `resolve/service_identity.py` states for its own three engines: the ledger
    is reset once, in the pipeline, AFTER `derive_endpoints` has run, so a
    write from inside an engine would be erased by that reset.
    """
    _validate_matches(catalog)
    base = _base_path(workspace, catalog)
    if base.resolved or not base.per_environment:
        return []
    key = str(catalog.matches["base_path"]["key"])
    candidates = json.dumps(
        [
            {
                "key": key,
                "values": {env: value for env, value in sorted(base.per_environment.items())},
            }
        ],
        sort_keys=True,
        separators=(",", ":"),
    )
    return [
        {
            "protocol": catalog.protocol,
            "method": "GET",
            "path": _path(catalog, base, repository.collection),
            "question": "environment_divergence",
            "candidates": candidates,
            "evidence": f"{key} differs between environments",
        }
        for repository in _repositories(workspace, catalog)
    ]


# --- the routes -----------------------------------------------------------


def _append(
    rows: list[dict[str, Any]],
    seen: set[tuple[str, str | None, str]],
    catalog: Catalog,
    base: _BasePath,
    method: str,
    path: str,
    handler: str | None,
    produces: str | None,
) -> None:
    """One row, unless this batch already carries its wire identity.

    Deduplicated HERE rather than by the insert (`derive_call_endpoints.sql`'s
    own header states why): DuckDB evaluates the statement's NOT EXISTS against
    the table as it stood before the statement began, so two same-identity rows
    in one batch would both insert. Two repositories CAN collide — an
    `@RepositoryRestResource(path = "orders")` on one while another's entity
    pluralizes to the same word — and the framework itself refuses to start in
    that case, so a single row is the closest honest answer available here.
    """
    key = (method, path, catalog.direction)
    if key in seen:
        return
    seen.add(key)
    rows.append(
        {
            "protocol": catalog.protocol,
            "direction": catalog.direction,
            "method": method,
            "path": path,
            "handler": handler,
            "caller": None,
            "peer": None,
            "handler_signature": None,
            # 2O design §2b: full confidence, because the mirrored rule IS the
            # framework's rule — the 2I `reversed_package` precedent (DR-6).
            # The one exception is a prefix configuration could not settle,
            # where the path carries an expression rather than a URL.
            "resolution": "resolved" if base.resolved else "unresolved",
            "evidence": "declared",
            "catalog_id": catalog.id,
            "request_shape": None,
            "response_shape": None,
            "consumes": None,
            "produces": produces,
        }
    )


def _path(catalog: Catalog, base: _BasePath, *segments: str) -> str:
    """The URL the framework serves, through Task 2's seam.

    The seam applies to INBOUND HTTP only (`serves_urls`, ruling R8) — which
    these rows are, being routes this module serves — and it leaves a
    placeholder-bearing path exactly as written, which is what keeps an
    unresolved prefix from being canonicalized into a URL nobody serves.
    """
    raw = "/".join([base.prefix, *segments])
    return canonical_http_path(raw) if serves_urls(catalog.protocol, catalog.direction) else raw


def _produces(catalog: Catalog) -> str | None:
    """D02's `default_produces` as the media column's own JSON-array text —
    the same shape `derive_endpoints.sql`'s `to_json` writes for an annotation
    row, sorted and de-duplicated for the same NFR-1 reason a catalog author
    never orders these by hand."""
    declared = sorted(set(catalog.default_produces))
    return json.dumps(declared, separators=(",", ":")) if declared else None


# --- which repositories are exposed ---------------------------------------


def _repositories(workspace: Workspace, catalog: Catalog) -> list[_Repository]:
    """Every interface the module declares that the configured detection
    strategy exposes, in symbol order (NFR-1).

    Returns nothing at all — never a partial guess — when the strategy cannot
    be read as one answer: a value the catalog does not enumerate (a typo, or a
    setting a later framework version added), or one that DIFFERS between
    environments. Which repositories are exposed is the precondition of every
    row below it, and an unanswered precondition produces no rows (GUIDELINES
    §8). COVERAGE carries the row so the silence is documented.
    """
    flags = _strategy(workspace, catalog)
    if flags is None:
        return []
    matches = catalog.matches
    contracts = {
        type_descriptor(str(fqn)): frozenset(str(op) for op in operations)
        for fqn, operations in dict(matches["repositories"]).items()
    }
    no_repository_bean = type_descriptor(str(matches["no_repository_bean"]))
    resource_annotation = type_descriptor(str(matches["resource_annotation"]))
    member_annotation = type_descriptor(str(matches["member_annotation"]))
    path_attribute = str(matches["path_attribute"])
    exported_attribute = str(matches["exported_attribute"])
    crud_methods = {str(name) for name in matches["crud_methods"]}

    declarations = _interface_declarations(workspace)
    annotations = _annotations(workspace)
    methods = _methods(workspace)

    repositories: list[_Repository] = []
    for descriptor, declaration in sorted(declarations.items()):
        if no_repository_bean in annotations.get(descriptor, {}):
            # A base repository is a template, never a bean of its own.
            continue
        if "public_only" in flags and declaration.visibility != "public":
            continue
        declared = annotations.get(descriptor, {}).get(resource_annotation)
        if "annotated_only" in flags and declared is None:
            continue
        if (
            "honors_exported" in flags
            and declared is not None
            and declared.get(exported_attribute) is False
        ):
            continue
        operations, hops = _reach(descriptor, declarations, contracts)
        if not hops:
            continue
        collection = _collection(declared, path_attribute, hops)
        if collection is None:
            # No readable entity type and no `path=` — nothing names the
            # resource, and composing a path from the REPOSITORY's own name
            # would be a spelling the framework never serves.
            continue
        repositories.append(
            _Repository(
                symbol=declaration.symbol,
                collection=collection,
                operations=operations,
                queries=_queries(
                    declaration.symbol,
                    methods,
                    annotations,
                    crud_methods,
                    member_annotation,
                    path_attribute,
                    exported_attribute,
                    flags,
                ),
            )
        )
    return repositories


def _collection(
    declared: dict[str, Any] | None, path_attribute: str, hops: list[dict[str, Any]]
) -> str | None:
    """`path=` when the annotation gave one, else the entity's own name as the
    framework derives it: uncapitalize the first character of the simple name,
    then pluralize (CP-2, live — `OrderItem` serves `/orderItems`, never a
    kebab- or snake-cased spelling)."""
    if declared is not None:
        overridden = declared.get(path_attribute)
        if isinstance(overridden, str) and overridden:
            return overridden
    entity = _entity_of(hops)
    if entity is None:
        return None
    name = simple_name(entity)
    if not name.isidentifier():
        # A NESTED entity type, whose simple name still carries the enclosing
        # type and the marker between them. What the framework serves for one
        # was not probed, and composing a path segment from a name no probe
        # covered would publish a URL that may not exist — so this derives
        # nothing and COVERAGE carries the boundary. (Ordinary names always
        # pass: an identifier in any language whose facts reach here is one
        # here too.)
        return None
    return pluralize(name[:1].lower() + name[1:])


def _entity_of(hops: list[dict[str, Any]]) -> str | None:
    """The entity type, taken TOP-DOWN: the first hop whose first type argument
    is a real class rather than a type variable (module docstring).

    None when no hop names one — a base repository whose every hop passes type
    variables through IS such a case, and it is correct that it derives
    nothing: an interface with an unbound entity type is not a repository bean.
    """
    for hop in hops:
        arguments = list(hop.get("arguments", []))
        if not arguments:
            continue
        symbol = str(arguments[0].get("symbol", ""))
        # A type reference's symbol is a type DESCRIPTOR (D00 §5a) and a type
        # VARIABLE is recorded by its own bare name (`T`), so asking the symbol
        # seam who OWNS this reference separates them: a descriptor owns
        # itself, a variable owns nothing.
        if owner_of(symbol) is not None:
            return symbol
    return None


def _reach(
    descriptor: str,
    declarations: "dict[str, _Declaration]",
    contracts: dict[str, frozenset[str]],
    seen: frozenset[str] = frozenset(),
) -> tuple[frozenset[str], list[dict[str, Any]]]:
    """The CRUD operations `descriptor` reaches, and the generic hops from the
    contract it reached back down to its own — ordered top-down, which is the
    order `_entity_of` reads them in.

    A repository may extend more than one contract (`CrudRepository` AND
    `PagingAndSortingRepository` is the ordinary shape), so operations are
    UNIONED across every path; the hops kept are the first path in declaration
    order that yields any, which is deterministic and is the same path for two
    runs over the same facts (NFR-1).

    `seen` guards the walk rather than trusting the source language: no
    language this reads facts from permits a cyclic interface hierarchy, but
    these are FACTS, and a fact stream that disagreed with its own language
    would hang this walk rather than report it.
    """
    declaration = declarations.get(descriptor)
    if declaration is None or descriptor in seen:
        return frozenset(), []
    operations: frozenset[str] = frozenset()
    hops: list[dict[str, Any]] = []
    for parent in declaration.interfaces:
        hop = declaration.generic.get(parent)
        if parent in contracts:
            operations |= contracts[parent]
            if not hops:
                hops = [hop] if hop is not None else []
            continue
        reached, above = _reach(parent, declarations, contracts, seen | {descriptor})
        if not above and not reached:
            continue
        operations |= reached
        if not hops:
            hops = [*above, *([hop] if hop is not None else [])]
    return operations, hops


def _queries(
    symbol: str,
    methods: dict[str, list[tuple[str, str]]],
    annotations: dict[str, dict[str, dict[str, Any]]],
    crud_methods: set[str],
    member_annotation: str,
    path_attribute: str,
    exported_attribute: str,
    flags: frozenset[str],
) -> dict[str, str]:
    """`{search path segment: the method's own symbol}` for every query method
    the repository exposes.

    A declared method is a query method only when it is not one of the CRUD
    interfaces' own method names — an override of `findAll(Pageable)` gets no
    search route (CP-2, observed 404) — and `@RestResource` renames it or
    removes it exactly as the class-level annotation does for the repository.
    Overloads of one name collapse to the one route the framework serves.
    """
    exposed: dict[str, str] = {}
    for name, method_symbol in methods.get(symbol, []):
        if name in crud_methods:
            continue
        declared = annotations.get(bare_descriptor(method_symbol), {}).get(member_annotation)
        if declared is not None:
            if "honors_exported" in flags and declared.get(exported_attribute) is False:
                continue
            overridden = declared.get(path_attribute)
            if isinstance(overridden, str) and overridden:
                exposed.setdefault(overridden, method_symbol)
                continue
        exposed.setdefault(name, method_symbol)
    return exposed


# --- configuration --------------------------------------------------------


def _strategy(workspace: Workspace, catalog: Catalog) -> frozenset[str] | None:
    """The configured detection strategy's own flags, or None when
    configuration did not name one answer.

    Boot binds a property to an enum with relaxed casing, so the value is
    lower-cased before it is looked up; anything the catalog does not enumerate
    is None rather than a default, because a value this engine cannot
    interpret is exactly the case where guessing "probably the default" would
    publish a route set the module does not serve.
    """
    declared = catalog.matches["detection_strategy"]
    strategies = dict(declared["strategies"])
    key = str(declared["key"])
    config = _config(workspace)
    # Absent and disagreeing are different answers here, unlike everywhere
    # `_agreed` alone is enough: a key no environment declares IS the
    # framework's default, while a key whose value differs between
    # environments means the module exposes different repositories in
    # different environments — which no single route set can state.
    configured = _DEFAULT_STRATEGY if key not in config else _agreed(config, key)
    if configured is None:
        return None
    flags = strategies.get(configured.strip().lower())
    return None if flags is None else frozenset(str(flag) for flag in flags)


def _base_path(workspace: Workspace, catalog: Catalog) -> _BasePath:
    """`spring.data.rest.base-path` as this run can answer it — read if
    present, never required (2O design §2b): the framework's own default is
    empty, so a module with no configuration derives its whole route set at
    `/`, and a catalog that named the capability in `requires` would be
    skipped on exactly those modules."""
    key = str(catalog.matches["base_path"]["key"])
    config = _config(workspace)
    per_environment = config.get(key)
    if not per_environment:
        return _BasePath(prefix="")
    agreed = _agreed(config, key)
    if agreed is not None:
        return _BasePath(prefix=agreed)
    return _BasePath(prefix="${" + key + "}", resolved=False, per_environment=per_environment)


def _config(workspace: Workspace) -> dict[str, dict[str, str | None]]:
    """`resolved_config` as `key -> {environment: value}` — the
    `config_join._config_values` shape, read the same way for the same reason:
    the whole table is one small answer and every lookup here is a membership
    test against it."""
    values: dict[str, dict[str, str | None]] = {}
    for row in workspace.query("resolved_config"):
        environments = values.setdefault(str(row["key"]), {})
        environments[str(row["environment"])] = None if row["value"] is None else str(row["value"])
    return values


def _agreed(config: dict[str, dict[str, str | None]], key: str) -> str | None:
    """The one value every environment gives `key`, or None — including for a
    key no environment declares. `config_join._agreed`'s rule, restated here
    rather than shared: that function is private to a different style, and the
    four cases it collapses are the same four this one needs."""
    per_environment = config.get(key)
    if not per_environment:
        return None
    distinct = set(per_environment.values())
    if len(distinct) != 1:
        return None
    return distinct.pop()


# --- the facts ------------------------------------------------------------


@dataclass(frozen=True)
class _Declaration:
    """One declared interface, as the three things this style asks of it."""

    symbol: str
    visibility: str
    # Superinterfaces as BARE descriptors, in declaration order.
    interfaces: tuple[str, ...]
    # `{bare superinterface descriptor: its generic reference}` — capability
    # 9.14 records only the parameterized ones, so a non-generic
    # superinterface is simply absent here.
    generic: dict[str, dict[str, Any]]


def _interface_declarations(workspace: Workspace) -> dict[str, _Declaration]:
    """Every interface this module declares, keyed by its BARE descriptor —
    which is the coordinate space `interfaces` entries and `generic_interfaces`
    symbols must be compared in: a symbol fact's own `symbol` is
    module-prefixed, its `interfaces` entries are module-prefixed too, and a
    generic reference's symbols are bare (D00 §5a). Stripping both sides once,
    here, is what keeps the closure walk from comparing two notations."""
    declarations: dict[str, _Declaration] = {}
    for row in workspace.query("interface_declarations"):
        symbol = str(row["symbol"])
        interfaces = [
            bare_descriptor(str(entry)) for entry in json.loads(str(row["interfaces"] or "[]"))
        ]
        generic = {
            str(reference["symbol"]): reference
            for reference in json.loads(str(row["generic_interfaces"] or "[]"))
        }
        declarations[bare_descriptor(symbol)] = _Declaration(
            symbol=symbol,
            visibility=str(row["visibility"]),
            interfaces=tuple(interfaces),
            generic=generic,
        )
    return declarations


def _annotations(workspace: Workspace) -> dict[str, dict[str, dict[str, Any]]]:
    """Every annotation in the workspace as `{bare target descriptor:
    {annotation: args}}` — targets keyed bare for the same reason
    `_interface_declarations` keys its own, so a class and a method are looked
    up the same way."""
    annotations: dict[str, dict[str, dict[str, Any]]] = {}
    for row in workspace.query("annotations"):
        target = bare_descriptor(str(row["target"]))
        args = row["args"]
        annotations.setdefault(target, {})[str(row["annotation"])] = (
            json.loads(str(args)) if args is not None else {}
        )
    return annotations


def _methods(workspace: Workspace) -> dict[str, list[tuple[str, str]]]:
    """`{enclosing type symbol: [(method name, method symbol)]}`, in symbol
    order (NFR-1) — the same `method_visibility` projection Task 5's style
    reads, for the one question this one asks of it: which methods does this
    interface itself declare."""
    methods: dict[str, list[tuple[str, str]]] = {}
    for row in workspace.query("method_visibility"):
        enclosing = row["enclosing"]
        if enclosing is None:
            continue
        symbol = str(row["symbol"])
        methods.setdefault(str(enclosing), []).append(
            (method_name(bare_descriptor(symbol)), symbol)
        )
    return methods


# --- catalog validation ---------------------------------------------------


def _validate_matches(catalog: Catalog) -> None:
    """Refuses a broken catalog before a single route is derived (the
    `interface_implementation._validate_matches` precedent). Every value below
    reaches a derived row's identity columns, and this style's rows are
    PREDICTIONS — a typo here is indistinguishable from a route the framework
    serves.

    The gate itself (`detect.coordinates` present at all) is checked in
    `resolve/dependencies.py`, which runs for a gated style whether or not this
    engine is reached.
    """
    matches = catalog.matches
    missing = [key for key in _REQUIRED_MATCHES if key not in matches]
    if missing:
        raise CatalogError(
            f"loading catalog {catalog.source}: `matches` is missing "
            f"{', '.join(missing)} — `derived_resource` needs every one of "
            f"{', '.join(_REQUIRED_MATCHES)} (2O design §2)"
        )
    for route in matches["routes"]:
        if "method" not in route:
            raise CatalogError(
                f"loading catalog {catalog.source}: every `routes` entry needs a `method` "
                f"— got {route!r} (2O design §2b)"
            )
    strategies = matches["detection_strategy"].get("strategies")
    if not isinstance(strategies, dict) or not strategies:
        raise CatalogError(
            f"loading catalog {catalog.source}: `detection_strategy.strategies` must map each "
            f"configured strategy to its flags — without it, which repositories are exposed "
            f"is unanswerable (CP-2(0))"
        )
    if _DEFAULT_STRATEGY not in strategies:
        raise CatalogError(
            f"loading catalog {catalog.source}: `detection_strategy.strategies` declares no "
            f"`{_DEFAULT_STRATEGY}` — a module that configures no strategy at all gets the "
            f"framework's default, and nothing else can name it (CP-2(0))"
        )
    unknown = sorted(
        {str(flag) for flags in strategies.values() for flag in flags} - _STRATEGY_FLAGS
    )
    if unknown:
        raise CatalogError(
            f"loading catalog {catalog.source}: `detection_strategy.strategies` names "
            f"{', '.join(unknown)}, which this style does not implement — one of "
            f"{', '.join(sorted(_STRATEGY_FLAGS))} (2O design §2a)"
        )
    if not catalog.default_produces:
        raise CatalogError(
            f"loading catalog {catalog.source}: `derived_resource` derives rows no mapping "
            f"declares a media type for, so the framework's own `default_produces` is the "
            f"only thing that can fill `produces` (D02, D01 §4's evidence kind (b))"
        )
