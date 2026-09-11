"""Tests for the `derived_resource` engine (D02 §2's `derived_resource` style,
2O design §2, Task 6).

**Every expected route here is a route a LIVE Spring Data REST application was
observed serving** (`scripts/probes/cp2_data_rest.md`, Boot 4.0.1 /
spring-data-rest 5.0.1): the six-route table per CRUD interface, the
`PagingAndSortingRepository`-only case that serves a collection GET and nothing
else, `path=`/`exported=`, the `/search/` routes, the four detection
strategies, and `/orderItems` for an entity named `OrderItem`. Facts are
hand-built to the shapes the extractor really emits — checked against
`fixtures/orders-service`'s own committed `OrderRepository.jsonl`, where
`interfaces` entries are MODULE-PREFIXED and a `generic_interfaces` reference's
symbols are BARE.

**Half of this file is near-misses** (GUIDELINES §10), and that is the point.
This style derives an entire REST API from an interface that mentions no HTTP,
so what matters at least as much as firing correctly is declining correctly:
no Data REST on the build, nothing recorded to check, an ordinary interface
hierarchy, a package-private repository, a `@NoRepositoryBean` base, a
strategy that exposes nothing. Each asserts that NOTHING was produced.
"""

import json
from pathlib import Path

import pytest

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.application.resolve.engines import derived_resource
from sextant.application.resolve.environment_divergence import record_environment_divergence
from sextant.application.resolve.open_questions import reset_open_questions
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    AnnotationFact,
    AnnotationUse,
    Document,
    ModuleFact,
    Signature,
    SymbolFact,
    TypeRef,
)
from sextant.storage.duckdb.workspace import DuckDbWorkspace

CAPABILITIES = {"annotation_args", "implemented_interfaces", "generic_interfaces"}

# The module-coordinates prefix every real symbol fact carries (D00 §5a) —
# `test_interface_engine.py`'s own `_MODULE` precedent.
_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "

# The framework's own names, spelled here as the catalog spells them (dotted)
# and as the facts spell them (SCIP) where a fact needs one.
CRUD = "org/springframework/data/repository/CrudRepository#"
PAGING = "org/springframework/data/repository/PagingAndSortingRepository#"
# The bare marker. It declares no methods at all — measured with `javap` at
# spring-data-commons 3.2.5 and 4.0.1, both interface bodies empty
# (`scripts/probes/w53_data_rest_collection_read.md`).
MARKER = "org/springframework/data/repository/Repository#"
REPOSITORY_REST_RESOURCE = "org/springframework/data/rest/core/annotation/RepositoryRestResource#"
REST_RESOURCE = "org/springframework/data/rest/core/annotation/RestResource#"
NO_REPOSITORY_BEAN = "org/springframework/data/repository/NoRepositoryBean#"

ORDER = "com/acme/orders/Order#"
LONG = "java/lang/Long#"
ORDER_REPOSITORY = "com/acme/orders/data/OrderRepository#"

# The coordinate `spring-data-rest.yml` gates on. One of the three it names —
# the gate is satisfied by any.
DATA_REST = "org.springframework.data:spring-data-rest-core"

# An OBSERVED inbound-http style, deliberately invented rather than Spring:
# the ordering under test is a property of the engine registry, and a test
# spelled with `@GetMapping` in it would pin a framework instead.
_OBSERVED_CONTROLLER = Catalog(
    id="test-observed",
    style="annotation_driven",
    protocol="http",
    direction="inbound",
    requires=("annotation_args",),
    # The filename sorts AFTER the derived catalog's on purpose: within-group
    # order is `(runs_last, derives_rows, direction, source filename)`, so a
    # name sorting first would let this catalog win the shared identity by
    # accident of the alphabet and the ordering test would pass with
    # `derived_resource` removed from `_RUNS_LAST` (verified by mutation).
    source=Path("zz-test-observed.yml"),
    matches={
        "type_annotation": "com.acme.web.Endpoint",
        "mapping": {
            "path_from": ["value"],
            "prefix_from": ["value"],
            "prefix_annotation": None,
            "method_from": "method",
            "all_methods": ["GET"],
            "annotations": [{"fqn": "com.acme.web.Get", "method": ["GET"]}],
        },
    },
)

# CP-2's own observed route table for a `CrudRepository`, at the default base
# path. Named once because five tests compare against it or against a subset.
FULL_ROUTES = {
    ("GET", "/orders"),
    ("POST", "/orders"),
    ("GET", "/orders/{id}"),
    ("PUT", "/orders/{id}"),
    ("PATCH", "/orders/{id}"),
    ("DELETE", "/orders/{id}"),
}


def _document(document_id: str = "doc_1", relative_path: str = "Repo.java") -> Document:
    return Document(
        document_id=document_id,
        relative_path=relative_path,
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )


def _repository(
    descriptor: str = ORDER_REPOSITORY,
    *,
    extends: str = CRUD,
    entity: str = ORDER,
    visibility: str = "public",
    queries: tuple[str, ...] = (),
    statics: tuple[str, ...] = (),
) -> list[SymbolFact]:
    """One repository interface, in the shape the extractor really emits: the
    superinterface ERASED and module-prefixed in `interfaces`, its type
    arguments surviving only in capability 9.14's `generic_interfaces`, whose
    own symbols are bare.

    `statics` declares methods carrying the `static` modifier the extractor
    really emits for them (`ClassScanner.methodModifiersJson`) — a helper bound
    to the interface rather than a member of the repository's instance
    contract."""
    facts: list[SymbolFact] = [
        SymbolFact(
            document_id="doc_1",
            symbol=_MODULE + descriptor,
            construct_kind=ConstructKind.INTERFACE,
            visibility=visibility,
            interfaces=[_MODULE + extends],
            generic_interfaces=[
                TypeRef(
                    symbol=extends,
                    arguments=[TypeRef(symbol=entity), TypeRef(symbol=LONG)],
                )
            ],
        )
    ]
    facts.extend(
        SymbolFact(
            document_id="doc_1",
            symbol=f"{_MODULE}{descriptor}{name}(sig).",
            construct_kind=ConstructKind.METHOD,
            enclosing=_MODULE + descriptor,
            signature=Signature(),
        )
        for name in queries
    )
    facts.extend(
        SymbolFact(
            document_id="doc_1",
            symbol=f"{_MODULE}{descriptor}{name}(sig).",
            construct_kind=ConstructKind.METHOD,
            enclosing=_MODULE + descriptor,
            signature=Signature(),
            modifiers={"static": True, "synthetic": False},
        )
        for name in statics
    )
    return facts


def _annotation(target: str, annotation: str, **args: object) -> AnnotationFact:
    return AnnotationFact(
        document_id="doc_1",
        target=_MODULE + target,
        use=AnnotationUse(annotation=annotation, args=args),
        retention="runtime",
    )


def _catalog(*, matches: dict[str, object] | None = None, **overrides: object) -> Catalog:
    """The shipped `spring-data-rest.yml`'s own shape, built by hand — the
    `test_supertype_derived.py` precedent: a test pins the ENGINE, and the
    shipped catalog's live answer belongs to a fixture."""
    declared = {
        "repositories": {
            # `Repository` licenses NOTHING — not even the collection read. It
            # declares no methods at all, so Spring Data REST's `exposesFindAll()`
            # is false for it and the collection carries OPTIONS only (W53, `G-46`,
            # measured in `scripts/probes/w53_data_rest_collection_read.md`).
            "org.springframework.data.repository.Repository": [],
            "org.springframework.data.repository.CrudRepository": [
                "collection_read",
                "item_read",
                "save",
                "delete",
            ],
            "org.springframework.data.repository.PagingAndSortingRepository": ["collection_read"],
        },
        "routes": [
            {"method": "GET", "item": False, "needs": "collection_read"},
            {"method": "POST", "item": False, "needs": "save"},
            {"method": "GET", "item": True, "needs": "item_read"},
            {"method": "PUT", "item": True, "needs": "save"},
            {"method": "PATCH", "item": True, "needs": "save"},
            {"method": "DELETE", "item": True, "needs": "delete"},
        ],
        "item_segment": "{id}",
        "search_segment": "search",
        "resource_annotation": "org.springframework.data.rest.core.annotation.RepositoryRestResource",
        "member_annotation": "org.springframework.data.rest.core.annotation.RestResource",
        "path_attribute": "path",
        "exported_attribute": "exported",
        "no_repository_bean": "org.springframework.data.repository.NoRepositoryBean",
        "crud_methods": ["save", "findAll", "findById", "delete", "count"],
        "base_path": {"key": "spring.data.rest.base-path"},
        "detection_strategy": {
            "key": "spring.data.rest.detection-strategy",
            "strategies": {
                "default": ["public_only", "honors_exported"],
                "all": [],
                "annotated": ["annotated_only", "honors_exported"],
                "visibility": ["public_only"],
            },
        },
    }
    fields: dict[str, object] = {
        "id": "test-spring-data-rest",
        "style": "derived_resource",
        "protocol": "http",
        "direction": "inbound",
        "requires": tuple(sorted(CAPABILITIES)),
        "matches": matches if matches is not None else declared,
        "source": Path("test-spring-data-rest.yml"),
        "detect_coordinates": (DATA_REST,),
        "default_produces": ("application/hal+json",),
    }
    fields.update(overrides)
    return Catalog(**fields)  # type: ignore[arg-type]


def _workspace(
    tmp_path: Path,
    facts: list[object],
    *,
    coordinates: tuple[str, ...] | None = (DATA_REST,),
    config: list[tuple[str, str, str]] | None = None,
) -> DuckDbWorkspace:
    """A workspace holding `facts`, a module fact declaring `coordinates`, and
    any already-resolved configuration.

    `coordinates=None` writes NO module fact at all — the "this analysis
    recorded nothing" case, which is a different answer from an empty tuple
    (a build that declares no dependencies) and is treated differently by the
    gate.
    """
    write_fact_file(tmp_path / "facts" / "Repo.jsonl", _document(), facts)  # type: ignore[arg-type]
    if coordinates is not None:
        write_fact_file(
            tmp_path / "facts" / "module.jsonl",
            _document("doc_module", "module"),
            [
                ModuleFact(
                    document_id="doc_module",
                    module_id="com.acme:orders-service",
                    module_kind="service",
                    languages=["java"],
                    source_roots=["src/main/java"],
                    output_dirs=["target/classes"],
                    dependency_coordinates=list(coordinates),
                )
            ],
        )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    if config:
        workspace.derive(
            "resolved_config_insert",
            rows=[
                {
                    "key": key,
                    "value": value,
                    "source": "invented.yml",
                    "environment": environment,
                    "unresolved_reason": None,
                }
                for key, environment, value in config
            ],
        )
    return workspace


def _resolve(
    tmp_path: Path,
    facts: list[object],
    catalog: Catalog | None = None,
    **kwargs: object,
) -> tuple[DuckDbWorkspace, list[object]]:
    workspace = _workspace(tmp_path, facts, **kwargs)  # type: ignore[arg-type]
    skipped = derive_endpoints(workspace, [catalog or _catalog()], capabilities=CAPABILITIES)
    return workspace, list(skipped)


def _routes(workspace: DuckDbWorkspace) -> set[tuple[str, str]]:
    return {(str(row["method"]), str(row["path"])) for row in workspace.query("endpoints")}


# --- (a) the route table --------------------------------------------------


def test_an_exported_repository_derives_the_full_route_set(tmp_path: Path):
    """CP-2(b), observed: a `CrudRepository` serves the six-route table plus
    one `/search/` route per query method."""
    workspace, skipped = _resolve(tmp_path, _repository(queries=("findByStatus",)))
    routes = _routes(workspace)
    workspace.close()

    assert skipped == []
    assert routes == FULL_ROUTES | {("GET", "/orders/search/findByStatus")}


def test_the_derived_rows_publish_at_full_confidence_with_declared_evidence(tmp_path: Path):
    """2O design §2b: the mirrored rule IS the framework's rule (DR-6, the 2I
    `reversed_package` precedent), so these rows are not hedged."""
    workspace, _ = _resolve(tmp_path, _repository(queries=("findByStatus",)))
    rows = {(row["method"], row["path"]): row for row in workspace.query("endpoints")}
    workspace.close()

    row = rows[("GET", "/orders/search/findByStatus")]
    assert row["resolution"] == "resolved"
    assert row["evidence"] == "declared"
    assert row["protocol"] == "http" and row["direction"] == "inbound"
    # D02's `default_produces`, implemented on this catalog: Data REST serves
    # HAL rather than negotiating its representation.
    assert row["produces"] == '["application/hal+json"]'
    assert row["consumes"] is None


def test_a_search_row_carries_the_query_method_and_a_crud_row_carries_no_handler(tmp_path: Path):
    """The honest split: `/orders/search/findByStatus` IS served by the method
    the repository declares, while `GET /orders` is served by framework code no
    fact in this module emitted — so inventing a handler for it would name a
    symbol that does not exist."""
    workspace, _ = _resolve(tmp_path, _repository(queries=("findByStatus",)))
    rows = {(row["method"], row["path"]): row for row in workspace.query("endpoints")}
    workspace.close()

    assert rows[("GET", "/orders/search/findByStatus")]["handler"] == (
        f"{_MODULE}{ORDER_REPOSITORY}findByStatus(sig)."
    )
    assert rows[("GET", "/orders")]["handler"] is None


def test_the_collection_path_is_the_pluralized_uncapitalized_entity_name(tmp_path: Path):
    """CP-2(a), observed live: entity `OrderItem` serves `/orderItems` — the
    FIRST character is uncapitalized and the result pluralized, never
    kebab-cased and never the repository's own name."""
    workspace, _ = _resolve(
        tmp_path,
        _repository("com/acme/orders/data/ItemRepository#", entity="com/acme/orders/OrderItem#"),
    )
    routes = _routes(workspace)
    workspace.close()

    assert ("GET", "/orderItems") in routes


def test_item_routes_honour_which_crud_interface_is_extended(tmp_path: Path):
    """CP-2(b), observed: since Spring Data 3 `PagingAndSortingRepository` no
    longer extends `CrudRepository`, and a repository extending only it serves
    a collection GET and NOTHING else — `/boxes/1` answered 405, not 404, so
    the resource exists and the item route does not.

    Since W53 this also guards the other side of `G-46`'s measurement: the
    collection read now needs `collection_read`, and this contract must still
    have it. `PagingAndSortingRepository` declares `findAll(Pageable)` and
    `findAll(Sort)` — both read with `javap` — so `exposesFindAll()` holds. A
    fix that took the collection GET away from every contract would pass the
    bare-marker test above and fail this one."""
    workspace, _ = _resolve(tmp_path, _repository(extends=PAGING))
    routes = _routes(workspace)
    workspace.close()

    assert routes == {("GET", "/orders")}


def test_a_bare_repository_marker_derives_nothing_not_even_the_collection_read(tmp_path: Path):
    """`G-46`, measured in W53 by opening the framework rather than by running it.

    This file used to derive `GET /orders` here, because the collection read
    carried no `needs:` at all and the catalog said in so many words that it is
    "the one route every exposed repository serves, whatever it extends". It is
    not. `CrudMethodsSupportedHttpMethods.getMethodsFor` (spring-data-rest-core
    5.0.1) adds GET to a collection only when `exposesFindAll()` holds, which
    resolves to a `findMethod` lookup for `findAll` over the repository
    interface and everything it extends — and `Repository` declares zero
    methods. Such a repository serves OPTIONS on its collection and nothing
    else.

    CP-2 could not have caught this: every contract it exercised live declares
    or inherits a `findAll`, so the missing `needs:` never produced a wrong row
    on a real repository. The near-miss is the whole point of the test."""
    workspace, skipped = _resolve(tmp_path, _repository(extends=MARKER))
    routes = _routes(workspace)
    workspace.close()

    assert routes == set()
    # And it is DERIVED-AND-EMPTY rather than skipped: the framework is present,
    # the repository is exposed, and the answer is that it carries no route we
    # publish. A skip would say something different and weaker.
    assert skipped == []


def test_a_path_override_replaces_the_derived_collection_path(tmp_path: Path):
    workspace, _ = _resolve(
        tmp_path,
        [
            *_repository(),
            _annotation(ORDER_REPOSITORY, REPOSITORY_REST_RESOURCE, path="gadgets"),
        ],
    )
    routes = _routes(workspace)
    workspace.close()

    assert routes == {(method, path.replace("/orders", "/gadgets")) for method, path in FULL_ROUTES}


def test_exported_false_removes_the_repository_entirely(tmp_path: Path):
    """Observed: every route of an `exported = false` repository answers 404,
    including the collection — the repository is not exposed at all."""
    workspace, _ = _resolve(
        tmp_path,
        [
            *_repository(),
            _annotation(ORDER_REPOSITORY, REPOSITORY_REST_RESOURCE, exported=False),
        ],
    )
    routes = _routes(workspace)
    workspace.close()

    assert routes == set()


def test_a_query_method_is_renamed_and_removed_by_rest_resource(tmp_path: Path):
    """Observed: `@RestResource(path = ...)` renames the search route and
    `exported = false` removes it, leaving the repository's other routes."""
    workspace, _ = _resolve(
        tmp_path,
        [
            *_repository(queries=("findByStatus", "findByCustomer")),
            _annotation(f"{ORDER_REPOSITORY}findByStatus(sig).", REST_RESOURCE, path="by-status"),
            _annotation(f"{ORDER_REPOSITORY}findByCustomer(sig).", REST_RESOURCE, exported=False),
        ],
    )
    routes = _routes(workspace)
    workspace.close()

    assert routes == FULL_ROUTES | {("GET", "/orders/search/by-status")}


def test_a_crud_method_the_repository_overrides_is_not_a_search_route(tmp_path: Path):
    """Observed 404: `BoxRepository` declares `Page<Box> findAll(Pageable)`,
    an override of a CRUD method, and `/boxes/search` does not exist — so a
    declared method is a query method only when its NAME is not one of the CRUD
    interfaces' own."""
    workspace, _ = _resolve(tmp_path, _repository(queries=("findAll",)))
    routes = _routes(workspace)
    workspace.close()

    assert routes == FULL_ROUTES


def test_a_repository_reached_through_a_module_local_base_derives_the_full_set(tmp_path: Path):
    """2O design §2a's within-module closure walk, observed live: a
    `@NoRepositoryBean BaseRepository<T, ID> extends CrudRepository<T, ID>`
    passes its type parameters through, and its child's own hop names the
    entity. The base itself exposes nothing (next test)."""
    base = "com/acme/orders/data/BaseRepository#"
    facts = [
        SymbolFact(
            document_id="doc_1",
            symbol=_MODULE + base,
            construct_kind=ConstructKind.INTERFACE,
            interfaces=[_MODULE + CRUD],
            generic_interfaces=[
                TypeRef(symbol=CRUD, arguments=[TypeRef(symbol="T"), TypeRef(symbol="ID")])
            ],
        ),
        _annotation(base, NO_REPOSITORY_BEAN),
        *_repository(extends=base),
    ]
    workspace, _ = _resolve(tmp_path, facts)
    routes = _routes(workspace)
    workspace.close()

    assert routes == FULL_ROUTES


def test_a_base_repository_whose_entity_is_a_type_variable_derives_nothing(tmp_path: Path):
    """The near-miss inside the closure walk: an interface whose every hop
    passes type VARIABLES through has no entity, so nothing names a resource —
    and an interface with an unbound entity type is not a repository bean in
    the first place. No `@NoRepositoryBean` here, deliberately: the entity rule
    alone must decline it."""
    base = "com/acme/orders/data/BaseRepository#"
    facts = [
        SymbolFact(
            document_id="doc_1",
            symbol=_MODULE + base,
            construct_kind=ConstructKind.INTERFACE,
            interfaces=[_MODULE + CRUD],
            generic_interfaces=[
                TypeRef(symbol=CRUD, arguments=[TypeRef(symbol="T"), TypeRef(symbol="ID")])
            ],
        )
    ]
    workspace, _ = _resolve(tmp_path, facts)
    routes = _routes(workspace)
    workspace.close()

    assert routes == set()


def test_a_no_repository_bean_base_that_fixes_its_entity_still_exposes_nothing(tmp_path: Path):
    """A base repository is a template, never a bean — so even one that names
    a concrete entity derives no routes of its own."""
    base = "com/acme/orders/data/BaseOrderRepository#"
    facts = [
        *_repository(base),
        _annotation(base, NO_REPOSITORY_BEAN),
    ]
    workspace, _ = _resolve(tmp_path, facts)
    routes = _routes(workspace)
    workspace.close()

    assert routes == set()


# --- (b) the near-misses: nothing produced --------------------------------


def test_a_module_whose_build_does_not_declare_the_framework_derives_nothing(tmp_path: Path):
    """THE near-miss this whole style is gated for (ruling R9): the facts are a
    perfectly ordinary Spring Data JPA repository, and without Spring Data REST
    on the build there is no API. The catalog is SKIPPED — visibly, in the
    manifest — rather than deriving or falling silent."""
    workspace, skipped = _resolve(
        tmp_path,
        _repository(queries=("findByStatus",)),
        coordinates=("org.springframework.boot:spring-boot-starter-data-jpa",),
    )
    routes = _routes(workspace)
    workspace.close()

    assert routes == set()
    assert [entry.catalog_id for entry in skipped] == ["test-spring-data-rest"]  # type: ignore[attr-defined]
    reason = skipped[0].missing_capabilities[0]  # type: ignore[attr-defined]
    assert "declares and inherits none of them" in reason
    # Fix round 3, I-2, narrowed by F1: an INHERITED starter is now recorded,
    # so the caveat is down to one case — a framework reaching the classpath
    # only as another artifact's own transitive. It has to be in the string a
    # manifest reader sees, not only in the documents behind it: a flat
    # "declares none of them" is a confident negative the evidence does not
    # support.
    assert "own transitive" in reason


def test_an_analysis_that_recorded_no_coordinates_skips_rather_than_deriving(tmp_path: Path):
    """The unanswerable case: a workspace whose facts predate the module fact
    records nothing at all. Deriving would fabricate an API; omitting silently
    would read exactly like a module that has none."""
    workspace, skipped = _resolve(tmp_path, _repository(), coordinates=None)
    routes = _routes(workspace)
    workspace.close()

    assert routes == set()
    assert "recorded no dependency coordinates" in skipped[0].missing_capabilities[0]  # type: ignore[attr-defined]


def test_a_module_fact_carrying_no_coordinates_key_skips_rather_than_crashing(tmp_path: Path):
    """Fix round 3, M-1: a module fact whose payload has no
    `dependency_coordinates` KEY reads as SQL NULL, and the gate used to run
    `json.loads("None")` on it and abort the whole resolve. Sextant's own
    emitter always writes the key, so this is a hand-authored or third-party
    fact file at the same `fact_schema_version` — the exact case the gate's
    SKIPPED path exists for. It must degrade to that, not take the resolve
    down with it."""
    write_fact_file(tmp_path / "facts" / "Repo.jsonl", _document(), _repository())  # type: ignore[arg-type]
    module = tmp_path / "facts" / "module.jsonl"
    write_fact_file(
        module,
        _document("doc_module", "module"),
        [
            ModuleFact(
                document_id="doc_module",
                module_id="com.acme:orders-service",
                module_kind="service",
                languages=["java"],
                source_roots=["src/main/java"],
                output_dirs=["target/classes"],
            )
        ],
    )
    lines = [json.loads(line) for line in module.read_text().splitlines()]
    del lines[1]["dependency_coordinates"]
    module.write_text("".join(json.dumps(line, sort_keys=True) + "\n" for line in lines))

    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    skipped = derive_endpoints(workspace, [_catalog()], capabilities=CAPABILITIES)
    routes = _routes(workspace)
    workspace.close()

    assert routes == set()
    assert "recorded no dependency coordinates" in skipped[0].missing_capabilities[0]  # type: ignore[attr-defined]


def test_a_static_helper_on_a_repository_is_not_a_query_method(tmp_path: Path):
    """The near-miss inside a repository that IS exposed (fix round 3, I-3).
    Every other conjunct holds — the framework is on the build, the interface
    reaches `CrudRepository`, the method name is not a CRUD name — and the one
    that fails is the only one that matters: a `static` helper is bound to the
    interface, never to the repository's instance contract, so Spring Data
    never puts it in `RepositoryInformation.getQueryMethods()` and no
    `/search/` route exists for it. The assertion is that NOTHING was produced
    for it: the six-route table is untouched and there is no search row.
    """
    workspace, skipped = _resolve(tmp_path, _repository(statics=("newest",)))
    routes = _routes(workspace)
    workspace.close()

    assert skipped == []
    assert routes == FULL_ROUTES
    assert not any("/search/" in path for _, path in routes)


def test_an_ordinary_interface_hierarchy_derives_nothing(tmp_path: Path):
    """The other near-miss, and the one Task 5 shipped a defect for at gRPC's
    scale: an interface extending a module-local GENERIC interface is ordinary
    Java. Every conjunct of the rule holds except the one that matters — the
    chain reaches no Spring Data contract — so nothing is produced."""
    plain = "com/acme/orders/data/Cache#"
    facts = [
        SymbolFact(
            document_id="doc_1",
            symbol=_MODULE + plain,
            construct_kind=ConstructKind.INTERFACE,
            generic_interfaces=[],
        ),
        *_repository("com/acme/orders/data/OrderCache#", extends=plain),
    ]
    workspace, skipped = _resolve(tmp_path, facts)
    routes = _routes(workspace)
    workspace.close()

    assert skipped == []
    assert routes == set()


def test_a_package_private_repository_derives_nothing_under_the_default_strategy(tmp_path: Path):
    """CP-2(0), observed: `HiddenRepository`, identical to the others but
    package-private, is exposed by no strategy except `all`. Visibility is part
    of the default rule, and the spec never said so."""
    workspace, _ = _resolve(tmp_path, _repository(visibility="other"))
    routes = _routes(workspace)
    workspace.close()

    assert routes == set()


# --- (c) the detection strategy (CP-2(0)) ---------------------------------


@pytest.mark.parametrize(
    "strategy, expected",
    [
        # Each row is one observed application run (CP-2(0)'s table).
        ("default", {"public exported"}),
        ("all", {"public exported", "public unexported", "hidden"}),
        ("annotated", {"public exported"}),
        ("visibility", {"public exported", "public unexported"}),
    ],
)
def test_the_configured_detection_strategy_decides_which_repositories_are_exposed(
    tmp_path: Path, strategy: str, expected: set[str]
):
    """The most load-bearing half of CP-2. One configuration line — a key this
    analysis already reads — empties or widens the whole derived route set, and
    deriving the default table regardless would publish routes the module does
    not serve.

    `annotated` exposes only the annotated repository; here that is the same
    one `default` exposes, since an annotation carrying only `path=` neither
    hides nor reveals.
    """
    exported = "com/acme/orders/data/ExportedRepository#"
    unexported = "com/acme/orders/data/UnexportedRepository#"
    hidden = "com/acme/orders/data/HiddenRepository#"
    facts = [
        *_repository(exported, entity="com/acme/orders/Alpha#"),
        _annotation(exported, REPOSITORY_REST_RESOURCE, path="alphas"),
        *_repository(unexported, entity="com/acme/orders/Beta#"),
        _annotation(unexported, REPOSITORY_REST_RESOURCE, exported=False),
        *_repository(hidden, entity="com/acme/orders/Gamma#", visibility="other"),
    ]
    workspace, _ = _resolve(
        tmp_path,
        facts,
        config=[("spring.data.rest.detection-strategy", "prod", strategy)],
    )
    routes = _routes(workspace)
    workspace.close()

    names = {
        "public exported": ("GET", "/alphas"),
        "public unexported": ("GET", "/betas"),
        "hidden": ("GET", "/gammas"),
    }
    assert {path for label, path in names.items() if label in expected} <= routes
    assert {path for label, path in names.items() if label not in expected}.isdisjoint(routes)


def test_a_strategy_value_the_catalog_does_not_enumerate_derives_nothing(tmp_path: Path):
    """Absent evidence, produce nothing (GUIDELINES §8): which repositories are
    exposed is the precondition of every row, and a value this engine cannot
    interpret is exactly where guessing "probably the default" would publish a
    route set the module does not serve."""
    workspace, _ = _resolve(
        tmp_path,
        _repository(),
        config=[("spring.data.rest.detection-strategy", "prod", "some-future-strategy")],
    )
    routes = _routes(workspace)
    workspace.close()

    assert routes == set()


def test_a_strategy_that_differs_between_environments_derives_nothing(tmp_path: Path):
    """A module exposing different repositories per environment has no single
    route set to state, and stating one environment's would be a claim about
    the other."""
    workspace, _ = _resolve(
        tmp_path,
        _repository(),
        config=[
            ("spring.data.rest.detection-strategy", "prod", "annotated"),
            ("spring.data.rest.detection-strategy", "staging", "default"),
        ],
    )
    routes = _routes(workspace)
    workspace.close()

    assert routes == set()


# --- (d) the base path ----------------------------------------------------


def test_a_configured_base_path_prefixes_every_derived_route(tmp_path: Path):
    workspace, _ = _resolve(
        tmp_path,
        _repository(queries=("findByStatus",)),
        config=[("spring.data.rest.base-path", "prod", "/api")],
    )
    routes = _routes(workspace)
    workspace.close()

    assert routes == {
        ("GET", "/api/orders"),
        ("POST", "/api/orders"),
        ("GET", "/api/orders/{id}"),
        ("PUT", "/api/orders/{id}"),
        ("PATCH", "/api/orders/{id}"),
        ("DELETE", "/api/orders/{id}"),
        ("GET", "/api/orders/search/findByStatus"),
    }


def test_a_base_path_without_a_leading_separator_serves_the_same_url(tmp_path: Path):
    """CP-1's rule, through Task 2's seam: `api` and `/api` are one URL, and
    the seam is where that is decided so no engine can drift from it."""
    workspace, _ = _resolve(
        tmp_path, _repository(), config=[("spring.data.rest.base-path", "prod", "api")]
    )
    routes = _routes(workspace)
    workspace.close()

    assert ("GET", "/api/orders") in routes


def test_a_base_path_that_differs_between_environments_leaves_the_prefix_unresolved(
    tmp_path: Path,
):
    """2O design §2b: one row, prefix unresolved, question filed. The path
    carries the configuration EXPRESSION rather than either environment's URL —
    picking one would state a URL the other environment does not serve — and
    `domain/paths.py` leaves a placeholder-bearing path untouched, so it is
    never canonicalized into one."""
    config = [
        ("spring.data.rest.base-path", "prod", "/v1"),
        ("spring.data.rest.base-path", "staging", "/v2"),
    ]
    workspace, _ = _resolve(tmp_path, _repository(), config=config)
    rows = {(row["method"], row["path"]): row for row in workspace.query("endpoints")}
    workspace.close()

    identity = ("GET", "${spring.data.rest.base-path}/orders")
    assert identity in rows
    assert rows[identity]["resolution"] == "unresolved"
    assert not any("/v1" in str(path) for _, path in rows)


def test_the_divergent_base_path_files_an_environment_divergence_question(tmp_path: Path):
    """The 2K hand-off (2G design §6): what the pass refused to guess is
    carried out with the per-environment values that would settle it, in the
    shape the renderer already reads."""
    config = [
        ("spring.data.rest.base-path", "prod", "/v1"),
        ("spring.data.rest.base-path", "staging", "/v2"),
    ]
    workspace = _workspace(tmp_path, _repository(), config=config)  # type: ignore[arg-type]
    reset_open_questions(workspace)
    record_environment_divergence(workspace, [_catalog()], CAPABILITIES)
    questions = workspace.query("open_questions")
    workspace.close()

    assert [question["question"] for question in questions] == ["environment_divergence"]
    assert json.loads(str(questions[0]["candidates"])) == [
        {"key": "spring.data.rest.base-path", "values": {"prod": "/v1", "staging": "/v2"}}
    ]
    assert questions[0]["evidence"] == "spring.data.rest.base-path differs between environments"


def test_an_agreed_base_path_files_no_question(tmp_path: Path):
    workspace = _workspace(
        tmp_path,
        _repository(),  # type: ignore[arg-type]
        config=[
            ("spring.data.rest.base-path", "prod", "/api"),
            ("spring.data.rest.base-path", "staging", "/api"),
        ],
    )
    reset_open_questions(workspace)
    record_environment_divergence(workspace, [_catalog()], CAPABILITIES)
    questions = workspace.query("open_questions")
    workspace.close()

    assert questions == []


def test_a_capability_skipped_catalog_files_no_question_either(tmp_path: Path):
    """Fix round 3, I-4: the CAPABILITY gate is re-applied here too. A scan
    that did not report `generic_interfaces` leaves `derive_endpoints` skipping
    this catalog and deriving no route at all — so a question about
    `${spring.data.rest.base-path}/orders` would be a question about a route
    with nothing behind it, filed from a catalog the manifest already reports
    as skipped."""
    config = [
        ("spring.data.rest.base-path", "prod", "/v1"),
        ("spring.data.rest.base-path", "staging", "/v2"),
    ]
    workspace = _workspace(tmp_path, _repository(), config=config)  # type: ignore[arg-type]
    without = CAPABILITIES - {"generic_interfaces"}
    skipped = derive_endpoints(workspace, [_catalog()], capabilities=without)
    reset_open_questions(workspace)
    record_environment_divergence(workspace, [_catalog()], without)
    questions = workspace.query("open_questions")
    routes = _routes(workspace)
    workspace.close()

    assert routes == set()
    assert [entry.catalog_id for entry in skipped] == ["test-spring-data-rest"]  # type: ignore[attr-defined]
    assert questions == []


def test_a_gated_out_module_files_no_question_either(tmp_path: Path):
    """The gate is re-applied to the question pass: a module with no Spring
    Data REST on its build must not file questions about the base path of an
    API it does not serve."""
    config = [
        ("spring.data.rest.base-path", "prod", "/v1"),
        ("spring.data.rest.base-path", "staging", "/v2"),
    ]
    workspace = _workspace(
        tmp_path,
        _repository(),  # type: ignore[arg-type]
        coordinates=("org.springframework.boot:spring-boot-starter-data-jpa",),
        config=config,
    )
    reset_open_questions(workspace)
    record_environment_divergence(workspace, [_catalog()], CAPABILITIES)
    questions = workspace.query("open_questions")
    workspace.close()

    assert questions == []


# --- (e) ordering: a prediction never displaces an observation -------------


def test_a_predicted_route_never_displaces_an_observed_controller_row(tmp_path: Path):
    """Ruling R3's load-bearing half, pinned. `derived_resource` is in
    `_RUNS_LAST`, so every observed-endpoint style has already written by the
    time these rows meet `derive_call_endpoints.sql`'s insert-if-absent guard —
    and the row that survives at a shared identity is the real controller's,
    with its handler, not the prediction's NULL."""
    # Both catalogs in ONE run, which is the only way the ordering is under
    # test at all: `derive_endpoints` empties the table before any engine runs,
    # so a row planted beforehand would prove nothing.
    handler = f"{_MODULE}com/acme/orders/OrderController#list()."
    facts = [
        *_repository(),
        SymbolFact(
            document_id="doc_1",
            symbol=f"{_MODULE}com/acme/orders/OrderController#",
            construct_kind=ConstructKind.CLASS,
        ),
        SymbolFact(
            document_id="doc_1",
            symbol=handler,
            construct_kind=ConstructKind.METHOD,
            enclosing=f"{_MODULE}com/acme/orders/OrderController#",
            signature=Signature(),
        ),
        _annotation("com/acme/orders/OrderController#", "com/acme/web/Endpoint#"),
        _annotation(
            "com/acme/orders/OrderController#list().", "com/acme/web/Get#", value="/orders"
        ),
    ]
    workspace = _workspace(tmp_path, facts)  # type: ignore[arg-type]
    derive_endpoints(workspace, [_catalog(), _OBSERVED_CONTROLLER], capabilities=CAPABILITIES)
    rows = {(row["method"], row["path"]): row for row in workspace.query("endpoints")}
    workspace.close()

    assert rows[("GET", "/orders")]["handler"] is not None
    assert rows[("GET", "/orders")]["catalog_id"] == "test-observed"
    # The routes the controller did NOT serve are still derived.
    assert ("POST", "/orders") in rows


def test_the_style_runs_after_every_observed_endpoint_style(tmp_path: Path):
    """The ordering itself, pinned where it lives rather than only through its
    consequence: membership in `_RUNS_LAST` is what makes insert-if-absent mean
    "a prediction never displaces an observation"."""
    from sextant.application.resolve.endpoints import _ENGINES, _RUNS_LAST

    assert "derived_resource" in _ENGINES
    assert "derived_resource" in _RUNS_LAST


# --- (f) catalog validation -----------------------------------------------


def test_a_catalog_of_this_style_with_no_coordinates_is_refused(tmp_path: Path):
    """A `derived_resource` catalog with an empty `detect.coordinates` would
    derive every repository in every module unconditionally — the fabrication
    the gate exists to prevent, and the worst possible thing to discover
    silently."""
    workspace = _workspace(tmp_path, _repository())  # type: ignore[arg-type]
    with pytest.raises(CatalogError, match="detect.coordinates"):
        derive_endpoints(workspace, [_catalog(detect_coordinates=())], capabilities=CAPABILITIES)
    workspace.close()


def test_a_catalog_missing_a_matches_key_is_refused(tmp_path: Path):
    workspace = _workspace(tmp_path, _repository())  # type: ignore[arg-type]
    with pytest.raises(CatalogError, match="is missing"):
        derive_endpoints(
            workspace, [_catalog(matches={"repositories": {}})], capabilities=CAPABILITIES
        )
    workspace.close()


def test_a_catalog_declaring_no_default_produces_is_refused(tmp_path: Path):
    """This style's rows have no mapping to read a media type off, so the
    framework contract is the only thing that can fill `produces`."""
    workspace = _workspace(tmp_path, _repository())  # type: ignore[arg-type]
    with pytest.raises(CatalogError, match="default_produces"):
        derive_endpoints(workspace, [_catalog(default_produces=())], capabilities=CAPABILITIES)
    workspace.close()


def test_a_catalog_naming_an_unimplemented_strategy_flag_is_refused(tmp_path: Path):
    """A flag this engine does not implement would read as a rule that is
    silently not applied — the exact shape of a rule that is "already being
    violated" (GUIDELINES §8)."""
    matches = dict(_catalog().matches)
    matches["detection_strategy"] = {
        "key": "spring.data.rest.detection-strategy",
        "strategies": {"default": ["public_only", "by_annotation_or_something"]},
    }
    workspace = _workspace(tmp_path, _repository())  # type: ignore[arg-type]
    with pytest.raises(CatalogError, match="does not implement"):
        derive_endpoints(workspace, [_catalog(matches=matches)], capabilities=CAPABILITIES)
    workspace.close()


def test_the_engine_declines_a_workspace_with_no_repositories_at_all(tmp_path: Path):
    """The empty case: a module with Spring Data REST on the build and no
    repository interface derives nothing, and does so without touching the
    endpoints table."""
    workspace, skipped = _resolve(tmp_path, [])
    routes = _routes(workspace)
    workspace.close()

    assert skipped == []
    assert routes == set()


def test_the_shipped_catalog_declares_a_gate_and_a_framework_default(tmp_path: Path):
    """The shipped file itself, not a hand-built stand-in: a `derived_resource`
    catalog that lost its `detect.coordinates` or its `default_produces` in an
    edit is a catalog that would fabricate."""
    from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
    from sextant.resources import catalogs_dir

    shipped = {catalog.id: catalog for catalog in YamlCatalogSource(catalogs_dir()).load()}
    catalog = shipped["spring-data-rest"]
    assert catalog.style == "derived_resource"
    assert catalog.detect_coordinates
    assert catalog.default_produces == ("application/hal+json",)
    assert catalog.media_formats == {"application/hal+json": "json"}
    derived_resource._validate_matches(catalog)


def test_no_shipped_route_claims_every_contract_serves_it(tmp_path: Path):
    """W53, `G-46`. A `routes` entry with no `needs:` asserts the framework serves
    that route for EVERY contract the catalog enumerates, whatever the contract
    licenses. That is the strongest claim this style can make, and until W53
    nothing checked it: `spring-data-rest.yml`'s collection GET carried no
    `needs:` and the claim was false for a bare `Repository`, whose interface body
    is empty at spring-data-commons 3.2.5 and 4.0.1.

    The loader REFUSES such a route now, so this reads the shipped file to show
    the refusal reaches it — the hand-built catalog above pins the engine, and a
    catalog defect can walk straight past an engine test. Deleting `needs:
    collection_read` from `spring-data-rest.yml` fails here."""
    from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
    from sextant.resources import catalogs_dir

    shipped = {catalog.id: catalog for catalog in YamlCatalogSource(catalogs_dir()).load()}
    for catalog in shipped.values():
        if catalog.style != "derived_resource":
            continue
        unconditional = [route for route in catalog.matches["routes"] if "needs" not in route]
        assert unconditional == [], (
            f"{catalog.id} declares a route no contract has to license: {unconditional}"
        )


def test_a_route_without_needs_is_refused_at_load():
    """The other half: the rule is a REFUSAL, not a preference, so a catalog
    carrying such a route never loads at all."""
    matches = dict(_catalog().matches)
    matches["routes"] = [{"method": "GET", "item": False}]
    with pytest.raises(CatalogError, match="names no `needs:`"):
        derived_resource._validate_matches(_catalog(matches=matches))


# --- `A-M13` (principles sweep §3.3): an interface's methods are inherited ---


def _base_with_query(base: str, query: str) -> list[SymbolFact]:
    """A `@NoRepositoryBean` base that passes its type parameters through AND
    declares a query method of its own — the shape every shared-base repository
    layer in a real codebase has."""
    return [
        SymbolFact(
            document_id="doc_1",
            symbol=_MODULE + base,
            construct_kind=ConstructKind.INTERFACE,
            interfaces=[_MODULE + CRUD],
            generic_interfaces=[
                TypeRef(symbol=CRUD, arguments=[TypeRef(symbol="T"), TypeRef(symbol="ID")])
            ],
        ),
        SymbolFact(
            document_id="doc_1",
            symbol=f"{_MODULE}{base}{query}(sig).",
            construct_kind=ConstructKind.METHOD,
            enclosing=_MODULE + base,
            signature=Signature(),
        ),
        _annotation(base, NO_REPOSITORY_BEAN),
    ]


def test_a_query_method_inherited_from_a_module_local_base_is_still_a_search_route(
    tmp_path: Path,
):
    """`A-M13`, the positive half. The query methods a repository exposes were
    taken to be the ones it DECLARES (`_methods` keys on `enclosing`), so
    `interface OrderRepository extends BaseRepo<Order, Long> {}` — declaring
    nothing of its own — exposed no search routes at all, silently and with no
    COVERAGE row.

    JLS 9.2/9.4.1: an interface inherits the methods of its superinterfaces.
    And the FRAMEWORK agrees, measured rather than assumed:
    `RepositoryInformationSupport.calculateQueryMethods` is
    `getRepositoryInterface().getMethods()` — `getMethods()`, which returns
    inherited interface methods, never `getDeclaredMethods()` (`javap -p -c`,
    spring-data-commons 3.2.5, CP-13).

    The base itself still exposes nothing: its entity is a type variable, which
    the test below this one already pins."""
    base = "com/acme/orders/data/BaseRepository#"
    facts = [*_base_with_query(base, "findByTenant"), *_repository(extends=base)]
    workspace, _ = _resolve(tmp_path, facts)
    routes = _routes(workspace)
    workspace.close()

    assert routes == FULL_ROUTES | {("GET", "/orders/search/findByTenant")}


def test_the_inherited_walk_stops_at_the_frameworks_own_contract(tmp_path: Path):
    """`A-M13`'s near-miss, and the conjunct that keeps a widened walk from
    turning CRUD into search routes. `save` is one of the framework's own base
    methods, so an INHERITED `save` on a module-local base is still not a query
    method — the framework serves it as the collection POST that already has a
    row, never as `/orders/search/save`.

    Identical to the positive in every other cell; the one difference is the
    base method's name. It discriminates: dropping `_queries`' `crud_methods`
    filter makes this fail with exactly that fabricated route, which is what
    makes the widened walk safe rather than merely wider.

    It does NOT exercise the `contracts` skip in `_exposed_methods`: every
    contract the catalog names lives in a jar, so the walk ends there anyway.
    That guard is stated in the engine and inert today."""
    base = "com/acme/orders/data/BaseRepository#"
    facts = [*_base_with_query(base, "save"), *_repository(extends=base)]
    workspace, _ = _resolve(tmp_path, facts)
    routes = _routes(workspace)
    workspace.close()

    assert routes == FULL_ROUTES


def _fragment_repository(fragment: str, method: str) -> list[SymbolFact]:
    """`interface OrderRepository extends CrudRepository<Order, Long>,
    OrderRepositoryCustom` beside the fragment interface itself — the shape
    every hand-written repository method in a real codebase takes.

    The fragment carries NO `@NoRepositoryBean`, which is the whole of what
    tells it from a shared base (CP-13 Q7), and it extends nothing: a fragment
    interface is an ordinary interface whose `…Impl` supplies the body."""
    return [
        SymbolFact(
            document_id="doc_1",
            symbol=_MODULE + fragment,
            construct_kind=ConstructKind.INTERFACE,
        ),
        SymbolFact(
            document_id="doc_1",
            symbol=f"{_MODULE}{fragment}{method}(sig).",
            construct_kind=ConstructKind.METHOD,
            enclosing=_MODULE + fragment,
            signature=Signature(),
        ),
        SymbolFact(
            document_id="doc_1",
            symbol=_MODULE + ORDER_REPOSITORY,
            construct_kind=ConstructKind.INTERFACE,
            visibility="public",
            interfaces=[_MODULE + CRUD, _MODULE + fragment],
            generic_interfaces=[
                TypeRef(symbol=CRUD, arguments=[TypeRef(symbol=ORDER), TypeRef(symbol=LONG)])
            ],
        ),
    ]


@pytest.mark.pins("derived_resource.inherited-interfaces-are-no-repository-beans")
def test_a_custom_fragment_method_is_not_a_search_route(tmp_path: Path):
    """`A-M13`'s regression, and CRITICAL 2 of the round-1 review. The widened
    walk crossed EVERY module-local superinterface, so
    `OrderRepositoryCustom#searchByFullText` — a hand-written fragment method
    whose body lives in `OrderRepositoryCustomImpl` — was published as
    `GET /orders/search/searchByFullText`. Spring Data REST serves no such
    route. **Before `A-M13` that input derived no search route at all.**

    The framework's rule, MEASURED in both halves this time (CP-13 Q6/Q7,
    identical bytecode at spring-data-commons 3.2.5 and 4.1.1):
    `calculateQueryMethods` filters `getMethods()` through `isCustomMethod`,
    which is `RepositoryComposition.getMethod(m) != null` — a method the
    FRAGMENT composition resolves is a custom method and therefore not a query
    method; and `FragmentMetadata.getFragmentInterfaces` is the repository
    interface's own `getInterfaceNames()` filtered to those NOT carrying
    `@NoRepositoryBean`. Q1 recorded `isCustomMethod` by name and the fix read
    only the enumeration beside it — §5.4 exactly.

    Its paired positive is `test_a_query_method_inherited_from_a_module_local_
    base_is_still_a_search_route` above: the same shape with `@NoRepositoryBean`
    on the superinterface, where the route IS served and DOES derive. The full
    CRUD set is asserted here rather than emptiness, because the repository
    itself is exposed exactly as before — what must be absent is the one
    `/search/` row."""
    facts = _fragment_repository("com/acme/orders/data/OrderRepositoryCustom#", "searchByFullText")
    workspace, _ = _resolve(tmp_path, facts)
    routes = _routes(workspace)
    workspace.close()

    assert routes == FULL_ROUTES
