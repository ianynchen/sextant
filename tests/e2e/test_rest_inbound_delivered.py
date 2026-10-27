"""REST inbound is delivered when every way a Spring Boot module exposes an HTTP endpoint
is visible. This file grows one shape at a time; each test names the shape and the gap it
closed.

**Not a document check.** Real bytecode, real pipeline, assertion on derived endpoints.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.cli.app import cli
from sextant.domain.symbols import bare_descriptor
from sextant.storage.duckdb.workspace import DuckDbWorkspace

FIXTURE = FIXTURES / "orders-service"


@pytest.fixture(scope="module")
def http_routes(analyzed_orders_service: Path) -> set[tuple[str, str, str]]:
    """`(catalog, method, path)` for every inbound HTTP row the fixture derives."""
    # The session's one `module analyze` of `orders-service` (`tests/conftest.py`), not a
    # run of its own: this fixture only reads rows. MEASURED on PR #20's CI run 34665949923:
    # the e2e files each analysed the same fixture on their own worker at once, and the
    # progress bar sat at 78% for nineteen minutes while all four did.
    workspace = DuckDbWorkspace(analyzed_orders_service / "workspace.duckdb")
    try:
        return {
            (str(row["catalog_id"]), str(row["method"]), str(row["path"]))
            for row in workspace.query("endpoints")
            if str(row["protocol"]) == "http" and str(row["direction"]) == "inbound"
        }
    finally:
        workspace.close()


def test_a_data_rest_resource_over_mongodb_derives_its_route_table(http_routes):
    """`G-45`. Spring Data REST reads the JPA repository contracts only, so a
    `MongoRepository` — which Spring Data REST exposes identically, and which extends the
    very `ListCrudRepository` the roster names — derived nothing. The parent is reached
    through a jar hop the fact stream does not cross, so naming the parent is not enough:
    the roster has to name the store contract itself.
    """
    expected = {
        ("spring-data-rest", "GET", "/shipments"),
        ("spring-data-rest", "POST", "/shipments"),
        ("spring-data-rest", "GET", "/shipments/{id}"),
        ("spring-data-rest", "PUT", "/shipments/{id}"),
        ("spring-data-rest", "PATCH", "/shipments/{id}"),
        ("spring-data-rest", "DELETE", "/shipments/{id}"),
    }
    missing = expected - http_routes
    assert missing == set(), (
        f"a MongoRepository behind @RepositoryRestResource derived {6 - len(missing)} of 6 "
        f"routes. Missing: {sorted(missing)}"
    )


def test_the_jpa_resource_still_derives(http_routes):
    """The control: `CatalogRepository`, exposed at `/orderViews`, derived before this."""
    assert ("spring-data-rest", "GET", "/orderViews") in http_routes, (
        "the JPA-backed Data REST resource stopped deriving"
    )


@pytest.fixture(scope="module")
def http_rows(analyzed_orders_service: Path) -> list[dict]:
    """Every inbound HTTP row of the session's one `orders-service` analysis, whole —
    for the tests that read `resolution` and `handler`, not only the address."""
    workspace = DuckDbWorkspace(analyzed_orders_service / "workspace.duckdb")
    try:
        return [
            dict(row)
            for row in workspace.query("endpoints")
            if str(row["protocol"]) == "http" and str(row["direction"]) == "inbound"
        ]
    finally:
        workspace.close()


def test_the_builder_form_derives_every_route_on_both_stacks(http_routes):
    """`G-37`, spec §8: the builder DSL, every overload, both stacks, with the mid-chain
    filter, the nested body, the static resource and the catch-all."""
    flux, mvc = "spring-webflux-router", "spring-mvc-router"
    expected = {
        (flux, "GET", "/bld/orders"),
        (flux, "GET", "/bld/orders/{id}"),
        (flux, "GET", "/bld/health"),
        (flux, "POST", "/bld/orders"),
        (flux, "PUT", "/bld/orders/{id}"),
        (flux, "GET", "/bld/nested/inner"),
        (flux, "DELETE", "/bld/nested/inner/{id}"),
        (flux, "GET", "/bld/static/**"),
        (mvc, "GET", "/mvcbld/orders"),
        (mvc, "GET", "/mvcbld/orders/{id}"),
        (mvc, "GET", "/mvcbld/health"),
        (mvc, "POST", "/mvcbld/orders"),
        (mvc, "PUT", "/mvcbld/orders/{id}"),
        (mvc, "GET", "/mvcbld/nested/inner"),
        (mvc, "DELETE", "/mvcbld/nested/inner/{id}"),
        (mvc, "GET", "/mvcbld/static/**"),
        (flux, "GET", "/**"),
        (mvc, "GET", "/**"),
        # The Supplier form of `nest` (A1 final review, I-1): the body is a whole chain.
        (flux, "GET", "/bld/sup/inner"),
        (mvc, "GET", "/mvcbld/sup/inner"),
    }
    missing = expected - http_routes
    assert missing == set(), f"builder routes missing: {sorted(missing)}"


@pytest.fixture(scope="module")
def http_requirements(analyzed_orders_service: Path) -> set[tuple]:
    """Every inbound `endpoint_metadata` row of the session's one `orders-service` analysis
    (spec 2026-09-19 §5), as `_requirements` spells them."""
    workspace = DuckDbWorkspace(analyzed_orders_service / "workspace.duckdb")
    try:
        return _requirements(
            [
                dict(row)
                for row in workspace.query("endpoint_metadata")
                if row["direction"] == "inbound"
            ]
        )
    finally:
        workspace.close()


def test_a_query_param_predicate_reaches_endpoint_metadata_on_the_functional_router(
    http_requirements, http_rows
):
    """`inbound-request-requirements` on the Spring functional side (spec 2026-09-19 §5c;
    CP-26 row 1). `OrderRoutes.routes` guards `GET /fn/orders` with `.and(RequestPredicates.
    queryParam("v", "2"))`: the predicate constrains no path and no verb — the row is
    `GET /fn/orders`, `produces` JSON, exactly as before — and it demands `?v=2`, which
    reaches `endpoint_metadata` as query `v`, value `2`, `required` (`QueryParamPredicate.
    test` returns false without it), `caller` the row's handler `RouteHandlers#listOrders`.
    The only `queryParam` on the fixture, so the only query row the router writes;
    `headers(Predicate)` is stated unread on the catalog and no row claims otherwise."""
    handler = next(
        str(r["handler"]) for r in http_rows if r["path"] == "/fn/orders" and r["method"] == "GET"
    )
    assert handler.endswith("com/acme/orders/routes/RouteHandlers#listOrders(sig_a2451eb8).")
    assert {r for r in http_requirements if r[1] == "/fn/orders"} == {
        ("GET", "/fn/orders", handler, "query", "v", "2", "required", "resolved"),
    }
    assert not any(r[3] == "query" and r[1] != "/fn/orders" for r in http_requirements), (
        "a query requirement appeared on a row nothing guards"
    )


def test_a_supplier_body_derives_its_route_once_under_the_prefix_and_never_bare(http_rows):
    """A1 final review, I-1. `nest(path("/bld/sup"), () -> route().GET("/inner", h).build())`
    is Spring's own Javadoc example for the Supplier overload, and its body is a chain of
    its own whose `build()` nothing in the body consumes — so the body rooted beside the
    prefix's fold and published a bare `GET /inner` with the compiler-generated lambda as
    its declarer. The prefixed row, declared by the `@Bean` method, is the only one on
    each stack; no row of either builder catalog carries a lambda as `caller`."""
    sup = [
        (row["catalog_id"], row["path"], row["resolution"], str(row["caller"]).split("#")[-1])
        for row in http_rows
        if str(row["path"]).endswith("/sup/inner")
    ]
    assert sorted((c, p, r, m.split("(")[0]) for c, p, r, m in sup) == [
        ("spring-mvc-router", "/mvcbld/sup/inner", "resolved", "mvcBuilderRoutes"),
        ("spring-webflux-router", "/bld/sup/inner", "resolved", "builderRoutes"),
    ], sup
    bare = [
        (row["path"], row["caller"])
        for row in http_rows
        if row["catalog_id"] in ("spring-webflux-router", "spring-mvc-router")
        and (row["path"] == "/inner" or "lambda$" in str(row["caller"]))
    ]
    assert bare == [], bare


def test_every_builder_route_is_resolved_including_the_one_past_the_filter(http_rows):
    """Spec §8 test 5, live: `POST /bld/orders` and `PUT /bld/orders/{id}` sit PAST the
    chain's `filter(...)`, and a pass-through the catalog did not declare would have
    poisoned every route to its left (spec §4b). Every builder row is `resolved`."""
    builder_rows = [row for row in http_rows if str(row["path"]).startswith(("/bld/", "/mvcbld/"))]
    assert builder_rows and {row["resolution"] for row in builder_rows} == {"resolved"}, [
        (row["path"], row["resolution"]) for row in builder_rows
    ]


def test_the_builder_catch_all_serves_every_path_and_is_resolved(http_rows):
    """Spec §7 case 3 as ruled: `route().GET(h::health).build()` constrains no path, so it
    serves every path and publishes the framework's any-path pattern at `resolved` — one
    row per stack, never a resolved NULL path (which the addresses-nothing gate drops).
    Four rows since A1 Task 5: the Kotlin DSL's `GET { }` on each stack is the same
    catch-all (`KotlinMvcRoutes.kt`, `KotlinWebFluxRoutes.kt`), distinct by `caller`."""
    catch_alls = [
        row
        for row in http_rows
        if row["catalog_id"] in ("spring-webflux-router", "spring-mvc-router")
        and row["method"] == "GET"
        and row["path"] == "/**"
    ]
    assert {row["resolution"] for row in catch_alls} == {"resolved"} and len(catch_alls) == 4, (
        catch_alls
    )
    assert len({row["caller"] for row in catch_alls}) == 4, catch_alls


def test_the_static_resource_route_is_served_with_no_handler(http_rows):
    """Spec §6: `resources("/bld/static/**", location)` is an inbound boundary a client
    can GET and receive bytes from. The row carries the pattern and the verb, and its
    `handler` is NULL — there is no handler method, and none is invented."""
    static = [row for row in http_rows if str(row["path"]).endswith("/static/**")]
    assert sorted((row["path"], row["handler"], row["resolution"]) for row in static) == [
        ("/bld/static/**", None, "resolved"),
        ("/mvcbld/static/**", None, "resolved"),
    ]


def test_every_kotlin_dsl_verb_overload_derives_what_it_declares_on_both_stacks(http_rows):
    """`W44-verb-overloads` and `GAP-1b`, spec §1b's measured table turned into rows: on
    the servlet stack the four declaring `GET` overloads each derive their route, the
    catch-all is RESOLVED at `/**` (the framework's any-path pattern, spec §7 case 3),
    and the three-argument form keeps its handler; on the reactive stack the
    non-coroutine `router { }` derives at all. The caller is part of every tuple so the
    two DSL catch-alls are pinned on their own — the builder catch-alls of Task 4 publish
    the same `GET /**` and would satisfy a caller-less tuple."""
    rows = {
        (
            row["catalog_id"],
            row["method"],
            row["path"],
            row["resolution"],
            row["handler"] is not None,
            _short_caller(row),
        )
        for row in http_rows
        if row["path"] == "/**" or str(row["path"]).startswith(("/ktmvc", "/ktflux"))
    }
    mvc, flux = "KotlinMvcRoutes#ktMvcRoutes", "KotlinWebFluxRoutes#ktFluxRoutes"
    assert {
        ("spring-mvc-router", "GET", "/ktmvc/invoices", "resolved", True, mvc),
        ("spring-mvc-router", "GET", "/ktmvc/invoices/{id}", "resolved", True, mvc),
        ("spring-mvc-router", "GET", "/ktmvc/health", "resolved", True, mvc),
        ("spring-mvc-router", "POST", "/ktmvc/invoices", "resolved", True, mvc),
        ("spring-mvc-router", "GET", "/**", "resolved", True, mvc),
        ("spring-webflux-router", "GET", "/ktflux/orders", "resolved", True, flux),
        ("spring-webflux-router", "GET", "/ktflux/orders/{id}", "resolved", True, flux),
        ("spring-webflux-router", "POST", "/ktflux/orders", "resolved", True, flux),
        ("spring-webflux-router", "GET", "/**", "resolved", True, flux),
    } <= rows, sorted(rows)


def test_a_kotlin_dsl_route_declared_under_a_media_guard_alone_derives_its_any_path_row(
    http_rows,
):
    """`dsl-media-route` (spec 2026-09-21 §7a; CP-29 row 10). `KotlinMvcRoutes.kt` writes
    `accept(MediaType.APPLICATION_JSON) { h }` inside `"/ktmvc".nest { }` and
    `KotlinOrderRoutes.kt` writes it at the top of `coRouter { }` — the DSLs'
    `accept(MediaType, Function1/Function2)V`, a route declared under a media guard alone.
    Each is one RESOLVED row: no verb (`method` NULL — the guard names none, and no
    `all_methods` fan-out, §0b A1), the served any-path pattern under whatever prefix
    encloses it (`/ktmvc/**` on the servlet stack, `/**` on the reactive one), the media
    as `produces`, and the lambda as the handler. *This pinned one `unresolved` row with
    path NULL and no handler on the servlet stack — the tracked gap — until the word
    existed; the reactive fixture had no instance.* No other row on either catalog moves."""
    routers = ("KotlinMvcRoutes#ktMvcRoutes", "KotlinOrderRoutes#ktRoutes")
    own = [row for row in http_rows if row["caller"] and _short_caller(row) in routers]
    rows = {
        (row["catalog_id"], row["method"], row["path"], row["produces"], row["resolution"])
        for row in own
        if row["method"] is None
    }
    assert rows == {
        ("spring-mvc-router", None, "/ktmvc/**", '["application/json"]', "resolved"),
        ("spring-webflux-router", None, "/**", '["application/json"]', "resolved"),
    }, sorted(rows, key=str)
    handlers = {
        row["catalog_id"]: bare_descriptor(str(row["handler"]))
        for row in own
        if row["method"] is None
    }
    assert handlers == {
        # The servlet lambda compiles to an `invokedynamic` body on the declaring class; the
        # coroutine one to a `SuspendLambda` class read through `lambda_body`.
        "spring-mvc-router": (
            "com/acme/orders/mvcroutes/KotlinMvcRoutes#"
            "ktMvcRoutes$lambda$7$lambda$5$lambda$4(sig_8817f35e)."
        ),
        "spring-webflux-router": (
            "com/acme/orders/routes/KotlinOrderRoutes$ktRoutes$1$2#invokeSuspend(sig_262c527a)."
        ),
    }, handlers
    assert [row for row in own if row["resolution"] == "unresolved"] == []


def test_a_dsl_receiver_helper_called_inside_the_kotlin_router_derives_its_route(http_rows):
    """`ktor-route-extensions` on the Spring functional side (spec 2026-09-19 §4a).
    `KotlinOrderRoutes.kt` calls `extra()` inside `coRouter { }`, and `fun
    CoRouterFunctionDsl.extra() { GET("/kt/extra") { } }` is a top-level extension: a
    STATIC `extra(CoRouterFunctionDsl)` whose one argument is the block's own parameter —
    the origin `coRouter`'s entry names — so the walk follows the call, the member `GET`
    inside sits on the callee's parameter 0 and derives resolved, and the row's caller is
    `ktRoutes`, the tree's root, never `extra`. The handler is the helper's own suspend
    lambda class (`KotlinOrderRoutesKt$extra$1`, the file facade's), read through
    `lambda_body` as every Kotlin handler is."""
    rows = [
        (row["catalog_id"], row["resolution"], _short_caller(row), row["handler"])
        for row in http_rows
        if row["path"] == "/kt/extra"
    ]
    assert rows == [
        (
            "spring-webflux-router",
            "resolved",
            "KotlinOrderRoutes#ktRoutes",
            (
                "sextant-jvm maven com.acme/orders-service 1.0.0 "
                "com/acme/orders/routes/KotlinOrderRoutesKt$extra$1#invokeSuspend(sig_262c527a)."
            ),
        )
    ], rows


def _short_caller(row: dict) -> str:
    """`Class#method` out of a module-prefixed caller symbol."""
    return str(row["caller"]).rsplit("/", 1)[1].partition("(")[0]


SPRING7 = FIXTURES / "orders-spring7"
CONTEXT_PATH = FIXTURES / "orders-contextpath"
PATH_PREFIXES = FIXTURES / "orders-pathprefixes"


@pytest.fixture(scope="module")
def spring7(tmp_path_factory: pytest.TempPathFactory) -> tuple[list[dict], list[dict]]:
    """The Spring 7 fixture, analysed once: `(endpoints, open_questions)`. Its own module
    because `@RequestMapping(version = …)` exists only from 7.0 and the main fixture is on
    6.1.6."""
    workspace_dir = tmp_path_factory.mktemp("spring7")
    compile_fixture(SPRING7)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(SPRING7), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return (
            [dict(row) for row in workspace.query("endpoints")],
            [dict(row) for row in workspace.query("open_questions")],
        )
    finally:
        workspace.close()


@pytest.fixture(scope="module")
def spring7_questions(spring7) -> list[dict]:
    return spring7[1]


@pytest.fixture(scope="module")
def context_path_rows(tmp_path_factory: pytest.TempPathFactory) -> list[dict]:
    """`fixtures/orders-contextpath`, analysed once. Its own module because a context path
    moves EVERY inbound path in the module that sets it, so the key cannot live in a fixture
    whose figures anything else pins."""
    workspace_dir = tmp_path_factory.mktemp("contextpath")
    compile_fixture(CONTEXT_PATH)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(CONTEXT_PATH), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return [dict(row) for row in workspace.query("endpoints")]
    finally:
        workspace.close()


@pytest.fixture(scope="module")
def path_prefix_rows(tmp_path_factory: pytest.TempPathFactory) -> set[tuple[str, str, str]]:
    """`fixtures/orders-pathprefixes`, analysed once."""
    workspace_dir = tmp_path_factory.mktemp("pathprefixes")
    compile_fixture(PATH_PREFIXES)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(PATH_PREFIXES), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return {
            (str(row["method"]), str(row["path"]), str(row["resolution"]))
            for row in workspace.query("endpoints")
            if str(row["direction"]) == "inbound"
        }
    finally:
        workspace.close()


@pytest.mark.pins("path_prefix.a-prefix-pairs-with-the-pattern-on-ITS-OWN-path")
@pytest.mark.pins("path_prefix.an-entry-belongs-to-the-map-the-installer-RECEIVES")
@pytest.mark.pins("path_prefix.a-prefix-reaches-only-the-classes-the-predicate-ADMITS")
@pytest.mark.pins("path_prefix.an-UNRESOLVED-prefix-is-refused")
@pytest.mark.pins("path_prefix.a-SUBCLASS-of-the-mapping-installs-prefixes-too")
@pytest.mark.pins("path_prefix.the-ENTRY-is-not-matched-on-the-maps-static-type")
def test_a_prefix_installed_by_package_reaches_the_rows_it_moves(path_prefix_rows):
    """`OI-148` §4, and the intention test for it.

    Two controllers map `/orders/{id}`, in `…controller.admin` and `…controller.app`, and a
    config class installs a prefix per package through Spring's own API:

        prefixes.put("/admin-api", clazz -> matcher.match("**.controller.admin.**",
                                                          clazz.getPackage().getName()));
        mapping.setPathPrefixes(prefixes);

    **Measured before the mechanism: TWO rows, both `/orders/{id}`** — so the document showed
    one path where two endpoints exist, which is exactly `ruoyi-vue-pro`'s own collapse
    (`/system/tenant/get-by-website` appears once there, and its admin and app controllers
    are separated by nothing else).

    This is configuration rather than runtime logic, by the user's distinction of 2026-10-18:
    the map is built once at wiring time from values fixed before any request arrives. What
    unblocked it was the walk's sixth edge, which made `ruoyi`'s own getter chain resolve.

    **`/internal-api` and `/ops-api` are the pairing**, and the reason this fixture has more
    than two controllers. They are declared at ONE `put` site — `putPathPrefix`, called once
    per group, which is `ruoyi`'s own shape — so the walk answers both prefixes and both
    patterns there. A reader that paired them by site would cross them; `resolve_positions`
    pairs them by PATH, and the two crossed combinations are refused because they chose
    different `new Api(…)` sites on the way out. Their installer is also a SUBCLASS of the
    framework's mapping, which is how an ordinary Spring customisation spells it.

    **The last three rows are the ones that must NOT move, and each is a wrong address a
    reader can publish** — all three were measured as real defects on probe modules before
    the conjuncts that refuse them existed:

    * `/audit-logs/{id}` — `auditCategories()` builds a map of exactly this shape and hands
      it to nobody, so there is nothing to join it to an installer. Published `/AUDIT/…`.
    * `/ext/{id}` — its prefix IS declared, as `${api.ext-prefix}`, which Spring resolves
      through its embedded value resolver first. Published the placeholder verbatim.
    * `/fn/items` — a functional route whose class sits in `…controller.admin`, prefixed for
      `@RestController` classes. `RouterFunctionMapping` has no prefixes at all, and the
      predicate's own annotation conjunct is what says so. Published `/admin-api/fn/items`.

    Two more shapes are asserted by the rows above rather than by rows of their own: the
    inline entries are `put` on a `LinkedHashMap`-TYPED variable (so no `java/util/Map#put`
    site exists for them), and `/admin-api` and `/app-api` are installed on the framework
    class while `/internal-api` and `/ops-api` are installed on the subclass.

    **`/text-api` is the walk's SEVENTH edge** (`OI-150`): `putTextPrefix` holds the prefix
    and the pattern as plain `String` parameters, so the lambda CAPTURES the pattern and
    reaching it means crossing from the lambda's synthetic body into the site that captured
    it. The prefix needs no such crossing — it is an argument of `put` — so this row is the
    one place in the suite where the two halves of a declaration need two different
    crossings, and without the capture edge it published `/text/{id}`.
    """
    assert path_prefix_rows == {
        ("GET", "/admin-api/orders/{id}", "resolved"),
        ("GET", "/app-api/orders/{id}", "resolved"),
        ("GET", "/internal-api/orders/{id}", "resolved"),
        ("GET", "/ops-api/orders/{id}", "resolved"),
        ("GET", "/text-api/text/{id}", "resolved"),
        ("GET", "/audit-logs/{id}", "resolved"),
        ("GET", "/ext/{id}", "resolved"),
        ("GET", "/fn/items", "resolved"),
    }


def test_a_configured_context_path_and_servlet_path_reach_the_published_rows(context_path_rows):
    """`OI-148`, and the intention test for spec 2026-10-18 (§4.1 — the fixture and the
    assertion come first, and this one failed before the mechanism existed).

    The fixture's `application.properties` sets

        server.servlet.context-path=/shop/
        spring.mvc.servlet.path=/api

    and its controller says only `@RequestMapping("/orders")` + `@GetMapping("/{id}")`. The
    served address is therefore `/shop/api/orders/{id}` and **nothing in the Java says so** —
    the only evidence for `/shop/api` is configuration, which `annotation_driven` could not
    read (COVERAGE §5.1's boundary, in its own words: *"a module that overrides the base path
    is published under `/actuator` regardless"*).

    Measured before the fix: both rows published at `/orders/{id}` and `/orders`, `resolved`,
    with both keys sitting resolved in `resolved_config` and nothing joining them. The same
    defect had 44 wrong routes recorded in a PINNED corpus — `spring-petclinic-rest` sets
    `server.servlet.context-path=/petclinic/`.

    **The trailing separator is part of the test, not an accident.** The configured value ends
    in `/` exactly as petclinic's does, and the published path must be `/shop/api/orders/{id}`
    rather than `/shop//api/orders/{id}`.
    """
    served = {
        (row["method"], row["path"]) for row in context_path_rows if row["direction"] == "inbound"
    }

    assert served == {
        ("GET", "/shop/api/orders/{id}"),
        ("POST", "/shop/api/orders"),
    }
    # And the rows stay resolved: a prefix every environment agrees on is an answer, not a
    # reason to doubt the address (spec §1's second outcome).
    assert {row["resolution"] for row in context_path_rows if row["direction"] == "inbound"} == {
        "resolved"
    }


def test_class_level_produces_reaches_every_handler_that_declares_none(spring7):
    """`@RequestMapping(value = "/v7/reports", produces = "application/xml")` on the class,
    `@GetMapping("/daily")` on the method. Spring's `ProducesRequestCondition.combine`
    keeps the method's condition when it declares one and the class's otherwise.

    Before this the class-level attribute was never read: the row derived `produces` NULL
    and `format` unresolved — and in a Boot module with Jackson on the classpath the
    same row would have fallen to `json`/`narrowed`, calling an XML route JSON. Found
    2026-09-12 while measuring Quarkus's `@RouteBase(produces = …)`, which is the same
    shape.
    """
    endpoints, _ = spring7
    rows = [row for row in endpoints if row["path"] == "/v7/reports/daily"]
    assert rows, f"/v7/reports/daily was not derived. Paths: {sorted(r['path'] for r in endpoints)}"
    (row,) = rows
    assert row["produces"] == '["application/xml"]', f"produces: {row['produces']!r}"
    assert (row["format"], row["format_resolution"]) == ("xml", "resolved"), (
        f"format: {row['format']!r} {row['format_resolution']!r}"
    )


def _spring7_row(endpoints: list[dict], method: str, path: str) -> dict:
    rows = [
        r
        for r in endpoints
        if r["method"] == method and r["path"] == path and r["direction"] == "inbound"
    ]
    assert len(rows) == 1, (
        f"{method} {path}: {len(rows)} rows; paths: {sorted(r['path'] for r in endpoints)}"
    )
    return rows[0]


def test_the_javax_spelling_derives_the_same_operations(spring7_routes):
    expected = {
        ("http", "GET", "/legacy/orders"),
        ("http", "POST", "/legacy/orders"),
        ("http", "GET", "/legacy/orders/{id}"),
    }
    assert expected <= spring7_routes, sorted(expected - spring7_routes)


def test_a_validated_entity_parameter_is_still_the_body(spring7):
    endpoints, _ = spring7
    row = _spring7_row(endpoints, "POST", "/validated/orders")
    assert row["request_shape"] is not None
    assert json.loads(row["request_shape"])["shape_id"].endswith("ValidatedResource$Order#")


def test_a_class_implementing_a_path_interface_derives_the_interfaces_operations(spring7):
    endpoints, _ = spring7
    assert {(r["method"], r["path"]) for r in endpoints if r["path"].startswith("/api/orders")} == {
        ("GET", "/api/orders"),
        ("GET", "/api/orders/{id}"),
        ("GET", "/api/orders/events"),
    }
    by_id = _spring7_row(endpoints, "GET", "/api/orders/{id}")
    assert by_id["produces"] == '["application/json"]'
    assert by_id["handler"].endswith(
        "OrdersResource#byId(sig_" + by_id["handler"].split("sig_")[1]
    )  # the IMPLEMENTOR handles it
    assert _spring7_row(endpoints, "GET", "/api/orders/events")["protocol"] == "sse"


def test_jaxrs_media_comes_from_the_sibling_and_the_class_default(spring7):
    endpoints, _ = spring7
    assert (
        _spring7_row(endpoints, "GET", "/jaxrs/orders")["produces"] == '["application/json"]'
    )  # class-level @Produces
    assert (
        _spring7_row(endpoints, "POST", "/jaxrs/orders")["consumes"] == '["application/json"]'
    )  # method-level @Consumes


def test_two_versions_of_one_route_are_not_reported_as_a_conflict(spring7_questions):
    """Spring 7 API versioning. `version` is a request condition `RequestMappingInfo.equals`
    compares exactly as it compares `params` and `headers`, so two handlers on `/orders`
    with different versions are DISTINCT mappings and Spring serves both.

    Before this, `spring-web.yml`'s conflict discriminators were `[params, headers]` only:
    the two mappings looked identical and Sextant filed a `routing_conflict` — a false
    question on a legitimately versioned API, which is worse than a missing row because it
    tells the reader their code is broken.
    """
    conflicts = [q for q in spring7_questions if str(q.get("question")) == "routing_conflict"]
    assert conflicts == [], f"two versions of one route were reported as conflicting: {conflicts}"


@pytest.fixture(scope="module")
def spring7_routes(tmp_path_factory: pytest.TempPathFactory) -> set[tuple[str, str, str]]:
    """`(protocol, method, path)` for every inbound row the Spring 7 / JAX-RS fixture derives."""
    workspace_dir = tmp_path_factory.mktemp("jaxrs")
    compile_fixture(SPRING7)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(SPRING7), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return {
            (str(row["protocol"]), str(row["method"]), str(row["path"]))
            for row in workspace.query("endpoints")
            if str(row["direction"]) == "inbound"
        }
    finally:
        workspace.close()


def test_a_jaxrs_resource_derives_every_operation(spring7_routes):
    """JAX-RS — Quarkus, Helidon, Jersey, RESTEasy. The verb is a MARKER annotation
    (`@GET` carries nothing), the path is a separate `@Path` on the class and/or method,
    and the two combine. Before this, no catalog read `jakarta.ws.rs` at all, so a module
    written against it exported no HTTP surface.
    """
    expected = {
        ("http", "GET", "/jaxrs/orders"),  # class @Path, no method @Path
        ("http", "POST", "/jaxrs/orders"),
        ("http", "GET", "/jaxrs/orders/{id}"),  # class @Path + method @Path
        ("http", "DELETE", "/jaxrs/orders/{id}"),
    }
    missing = expected - spring7_routes
    assert missing == set(), (
        f"a JAX-RS resource derived {4 - len(missing)} of 4. Missing: {sorted(missing)}. "
        f"Derived: {sorted(spring7_routes)}"
    )


def test_a_jaxrs_sse_endpoint_is_classified_as_sse(spring7_routes):
    """`@Produces(MediaType.SERVER_SENT_EVENTS)` is how JAX-RS declares an SSE endpoint —
    the only Java gap left in the SSE cell. It must land in the `sse` bucket, not `http`,
    exactly as Spring's `SseEmitter` routes already do."""
    assert ("sse", "GET", "/jaxrs/orders/events") in spring7_routes, (
        f"the JAX-RS SSE endpoint was not classified as sse. Derived: {sorted(spring7_routes)}"
    )


MICRONAUT = FIXTURES / "orders-micronaut"


@pytest.fixture(scope="module")
def micronaut_routes(tmp_path_factory: pytest.TempPathFactory) -> set[tuple[str, str, str, str]]:
    """`(catalog, direction, method, path)` for every HTTP row the Micronaut fixture derives."""
    workspace_dir = tmp_path_factory.mktemp("micronaut")
    compile_fixture(MICRONAUT)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(MICRONAUT), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return {
            (str(row["catalog_id"]), str(row["direction"]), str(row["method"]), str(row["path"]))
            for row in workspace.query("endpoints")
            if str(row["protocol"]) == "http"
        }
    finally:
        workspace.close()


def test_a_micronaut_controller_derives_every_operation(micronaut_routes):
    """Micronaut's server side. `@Controller` carries the prefix, `@Get`/`@Post`/… carry
    the path (`value` or `uri`) and media on the same annotation — the shape Spring's
    `@GetMapping` has, so this is the `annotation_driven` vocabulary as it exists. Before
    this, no catalog read `io.micronaut.http` and a Micronaut module exported nothing."""
    expected = {
        ("micronaut-http", "inbound", "GET", "/mn/orders"),
        ("micronaut-http", "inbound", "GET", "/mn/orders/{id}"),
        ("micronaut-http", "inbound", "POST", "/mn/orders"),
        ("micronaut-http", "inbound", "DELETE", "/mn/orders/{id}"),
    }
    missing = expected - micronaut_routes
    assert missing == set(), (
        f"a Micronaut controller derived {4 - len(missing)} of 4. Missing: {sorted(missing)}. "
        f"Derived: {sorted(micronaut_routes)}"
    )


def test_a_micronaut_declarative_client_derives_outbound(micronaut_routes):
    """Micronaut's declarative client: the same verb annotations on an interface carrying
    `@Client`, which decides the direction — the shape `spring-http-interface.yml` already
    reads for `@HttpExchange` with `declared_on: interface`."""
    assert (
        "micronaut-http-client",
        "outbound",
        "GET",
        "/inventory/levels/{sku}",
    ) in micronaut_routes, (
        f"a @Client interface derived no outbound row. Derived: {sorted(micronaut_routes)}"
    )


QUARKUS = FIXTURES / "orders-quarkus"


@pytest.fixture(scope="module")
def quarkus_endpoints(tmp_path_factory: pytest.TempPathFactory) -> list[dict]:
    """Every HTTP-surfaced row the Quarkus fixture derives, analysed once —
    `http` and `sse`, since `protocol_hint` (D02 §2) RECLASSIFIES an HTTP row
    to `sse` rather than minting a second one. The filter used to read
    `protocol == "http"` alone, which pre-dated `quarkus-rest.yml`'s own SSE
    row (B/C Task 10, spec §3c M1): a route `protocol_hint` correctly
    reclassifies was then invisible to this very fixture's own SSE test,
    which is a fixture bug rather than a feature gap."""
    workspace_dir = tmp_path_factory.mktemp("quarkus")
    compile_fixture(QUARKUS)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(QUARKUS), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return [
            dict(row)
            for row in workspace.query("endpoints")
            if str(row["protocol"]) in ("http", "sse")
        ]
    finally:
        workspace.close()


@pytest.fixture(scope="module")
def quarkus_routes(quarkus_endpoints) -> set[tuple[str, str, str]]:
    """`(direction, method, path)`."""
    return {(str(r["direction"]), str(r["method"]), str(r["path"])) for r in quarkus_endpoints}


@pytest.fixture(scope="module")
def quarkus_media(quarkus_endpoints) -> dict[tuple[str, str], tuple[str | None, str | None]]:
    """`(method, path) -> (consumes, produces)`."""
    return {
        (str(r["method"]), str(r["path"])): (r["consumes"], r["produces"])
        for r in quarkus_endpoints
    }


def test_quarkus_reactive_routes_derive_every_route(quarkus_routes):
    """Quarkus's `@Route`: any class, no CDI marker needed; `@RouteBase(path)` is the class
    prefix and `@Route(path, methods)` the handler — `methods` is an enum ARRAY, so one
    handler serving two verbs is two rows, and `@Route` is `@Repeatable` through
    `Route$Routes`, so two routes on one handler are two rows too. Measured at
    quarkus-reactive-routes 3.17.5 (`javap` on `Route`, `RouteBase`, `Route$HttpMethod`).

    Path composition measured in the deployment processor (`ReactiveRoutesProcessor`,
    3.17.5): base + `/` + route, single slash; a route path missing its leading `/` gets
    one. A bare `@Route` with no `path` is served at `/` + dashify(method name) — that
    form is NOT derived here and the catalog says so; a wrong row is worse than none.
    """
    expected = {
        ("inbound", "GET", "/qk/orders/"),
        ("inbound", "GET", "/qk/orders/:id"),
        ("inbound", "POST", "/qk/orders/"),
        ("inbound", "PUT", "/qk/orders/:id"),
        ("inbound", "DELETE", "/qk/orders/:id"),
        ("inbound", "POST", "/qk/orders/:id/cancel"),
        ("inbound", "POST", "/qk/orders/:id/void"),
    }
    missing = expected - quarkus_routes
    assert missing == set(), (
        f"Quarkus @Route: missing {sorted(missing)}. Derived: {sorted(quarkus_routes)}"
    )


def test_quarkus_route_base_media_reaches_every_route(quarkus_media):
    """`@RouteBase(produces = "application/json")` applies to every `@Route` that declares
    none, and a `@Route(consumes = …)` keeps its own — the same class-then-method rule as
    Spring's, and read by the same engine words."""
    assert quarkus_media[("GET", "/qk/orders/:id")] == (None, '["application/json"]'), (
        f"class-level produces did not reach the route: {quarkus_media}"
    )
    assert quarkus_media[("POST", "/qk/orders/")] == (
        '["application/json"]',
        '["application/json"]',
    ), f"the route's own consumes was lost or the class produces did not reach it: {quarkus_media}"


def test_quarkus_rest_binds_the_body_the_way_quarkus_does(quarkus_endpoints):
    def row(method, path):
        return next(r for r in quarkus_endpoints if r["method"] == method and r["path"] == path)

    assert row("GET", "/q/orders/{id}")["request_shape"] is None  # `id` is the path variable
    assert json.loads(row("PUT", "/q/orders/{id}")["request_shape"])["shape_id"].endswith(
        "OrderResource$Order#"
    )
    assert row("POST", "/q/orders/upload")["request_shape"] is None  # container
    assert row("GET", "/q/orders/whoami")["request_shape"] is None  # RoutingContext


def test_quarkus_element_type_alone_makes_a_stream_sse(quarkus_endpoints):
    """CP-19 row 2a, both branches: the element type ALONE implies SSE (`/events`),
    `@Produces(SERVER_SENT_EVENTS)` alone is SSE by media (`/ticks`), and the element
    type beside a method-level `@Produces("application/x-ndjson")` is NOT — Quarkus reads
    the method's `@Produces` first and falls to the marker only when that read is empty
    (`/ndjson`, the final review's Important 2; `OrderResource#ndjson` took the fixture's
    `endpoints` rows from 16 to 17, all of them HTTP-surfaced)."""
    protocols = {r["path"]: r["protocol"] for r in quarkus_endpoints if r["direction"] == "inbound"}
    assert protocols["/q/orders/events"] == "sse"
    assert protocols["/q/orders/ticks"] == "sse"
    assert protocols["/q/orders/ndjson"] == "http"


JAVALIN = FIXTURES / "orders-javalin"


@pytest.fixture(scope="module")
def javalin_tables(tmp_path_factory: pytest.TempPathFactory) -> dict[str, list[dict]]:
    """One `module analyze` of the Javalin fixture — the routes below and the handler-read
    rows (§5d) both read it, so it runs once per file rather than once per fixture."""
    return _analyzed_tables(JAVALIN, tmp_path_factory.mktemp("javalin"))


@pytest.fixture(scope="module")
def javalin_routes(javalin_tables: dict[str, list[dict]]) -> set[tuple[str, str, str]]:
    """`(direction, method, path)` for every inbound HTTP row the Javalin fixture derives."""
    return {
        (str(row["direction"]), str(row["method"]), str(row["path"]))
        for row in javalin_tables["endpoints"]
        if str(row["protocol"]) == "http"
    }


def test_javalin_flat_registrations_derive_every_route(javalin_routes):
    """`app.get("/path", handler)` on a `Javalin` — the form the Javalin front page
    shows. javalin 6.4.0: the verbs are default methods on `JavalinDefaultRoutingApi`,
    path at argument 0, handler a lambda at 1 (the handler recorded is the calling
    method, as for every `single_call` inbound row). The SECOND flat form,
    `config.router.mount(router -> router.get(...))`, calls the identical descriptors
    on `JavalinDefaultRouting` — the other type `JavalinDefaultRoutingApi` implements —
    with no nesting at all, so it derives exactly like `app.get(...)` does."""
    expected = {
        ("inbound", "GET", "/jv/orders"),
        ("inbound", "GET", "/jv/orders/{id}"),
        ("inbound", "POST", "/jv/orders"),
        ("inbound", "DELETE", "/jv/orders/{id}"),
        ("inbound", "GET", "/jv/mounted"),
        ("inbound", "POST", "/jv/mounted"),
    }
    missing = expected - javalin_routes
    assert missing == set(), f"missing {sorted(missing)}. Derived: {sorted(javalin_routes)}"
    assert ("inbound", "GET", "/{id}") not in javalin_routes, (
        "the ApiBuilder inner path was published WITHOUT its `path(…)` prefix — a wrong row"
    )


def test_javalin_api_builder_derives_the_composed_path(javalin_routes):
    """`javalin-apibuilder`, spec §14 test 12: two nesting levels; a path-less verb serves
    its prefix and nothing more (Javalin's `prefixPath("")`, measured on the 6.4.0 jar —
    `POST /jv/nested`, never `/jv/nested/**`); the role-carrying overload reads the same
    positions; every row's caller is the method holding `apiBuilder`, which is the
    `config -> …` lambda `Javalin.create` was handed. The slashless `path("plain", () ->
    get("x", …))` reads `/jv/nested/plain/x` — the catalog's `path_join: leading_slash`
    is Javalin's own `prefixPath` rule, and the glued `/jv/nestedplainx` is the resolved
    wrong row it prevents (Task 3 fix round 1). A static helper CALLED from a block derives
    under the prefix that reached the call (`ktor-route-extensions` on the Javalin side)."""
    expected = {
        ("inbound", "GET", "/jv/nested/{id}"),
        ("inbound", "POST", "/jv/nested"),
        ("inbound", "GET", "/jv/nested/{id}/items"),
        ("inbound", "DELETE", "/jv/nested/{id}/items/{itemId}"),
        ("inbound", "GET", "/jv/nested/plain/x"),
        # `path("/jv/helped", () -> helped())` with `static void helped() { get("/h", h); }`:
        # the helper is CALLED from the block, not linked as its body, and the catalog's
        # `follow_calls: all` is what follows it — `ApiBuilder.staticInstance()` throws
        # outside a block (6.4.0 jar), so the call can only ever run inside one (spec
        # 2026-09-19 §4a).
        ("inbound", "GET", "/jv/helped/h"),
        ("inbound", "GET", "/jv/nested/reads"),  # the handler-read fixture (§5d), below
    }
    assert expected <= javalin_routes, sorted(javalin_routes)
    assert ("inbound", "GET", "/{id}") not in javalin_routes
    assert ("inbound", "POST", "/jv/nested/**") not in javalin_routes
    assert ("inbound", "GET", "/jv/nestedplainx") not in javalin_routes


KTOR = FIXTURES / "orders-ktor"


def _analyzed_tables(fixture: Path, workspace_dir: Path) -> dict[str, list[dict]]:
    """One `module analyze` of `fixture`, and the two tables the tests below read —
    `endpoints` whole, and the inbound `endpoint_metadata` rows the requirements pass
    wrote against them (spec 2026-09-19 §5)."""
    compile_fixture(fixture)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(fixture), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return {
            "endpoints": [dict(row) for row in workspace.query("endpoints")],
            "endpoint_metadata": [
                dict(row)
                for row in workspace.query("endpoint_metadata")
                if row["direction"] == "inbound"
            ],
        }
    finally:
        workspace.close()


def _requirements(metadata: list[dict]) -> set[tuple]:
    """`(method, path, caller, kind, name, value, requirement, resolution)` per inbound
    metadata row — what a route's tree demands, keyed by the row it demands it of."""
    return {
        (
            r["method"],
            r["path"],
            r["caller"],
            r["kind"],
            r["name"],
            r["value"],
            r["requirement"],
            r["resolution"],
        )
        for r in metadata
    }


@pytest.fixture(scope="module")
def ktor_tables(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """The two tables, and the module document one `render` of the same analysis writes
    (`document`): the Ktor client, WebSocket and SSE pins below read the rows in the
    document as well as in the table, because the document is the result."""
    workspace_dir = tmp_path_factory.mktemp("ktor")
    tables: dict = _analyzed_tables(KTOR, workspace_dir)
    result = CliRunner().invoke(
        cli, ["module", "render", str(KTOR), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    tables["document"] = (workspace_dir / "render" / "architecture.md").read_text(encoding="utf-8")
    return tables


@pytest.fixture(scope="module")
def ktor_rows(ktor_tables: dict[str, list[dict]]) -> list[dict]:
    """Every endpoint row the Ktor fixture derives, whole — the Ktor test reads the
    handler and the caller beside the identity, which the Javalin fixture's triples
    do not carry."""
    return ktor_tables["endpoints"]


def _suspend_body(handler_class: str) -> str:
    """The module-prefixed symbol of a `KtorRoutesKt` suspend handler's `invokeSuspend` —
    the one body shape every suspend lambda class has, so one disambiguator serves all."""
    return (
        "sextant-jvm maven com.acme/orders-ktor 1.0.0 com/acme/kt/KtorRoutesKt$"
        + handler_class
        + "#invokeSuspend(sig_262c527a)."
    )


def test_ktor_routing_derives_every_route_under_its_nested_prefixes(ktor_rows):
    """`ktor-routing`, spec §14 test 13. `routing { route("/api") { get("/orders") { }
    … } }` on ktor-server-core 3.6.0: every verb is a static extension whose receiver is
    argument 0, every block an `invokedynamic` body, and the route is the prefix chain
    the blocks nest in. `get { }` under `route("/api")` is `method(Get) { handle(body) }`
    on the prefix node itself (`javap -c`), so it serves `/api` — the empty literal
    path, never `/api/**`. The slashless `route("legacy") { get("orders") { } }` reads
    `/api/legacy/orders`: `RoutingPath.parse` splits on `/` and drops the empty parts,
    which is the catalog's `path_join: leading_slash`.

    Every row names its handler: a suspend lambda compiles to a class (kotlinc 2.2.0,
    CP-23), the extractor marks that class's type fact with the `invokeSuspend` holding
    its body, and `effective_call_sites` hands every engine the `instance` as that
    `lambda` (spec 2026-09-19 §3b) — so the handler column that spec §13 case 8 had
    pinned NULL is the body's own symbol. `kotlin-null-handler` closes here, on the Ktor
    rows; the class counters (`$orders$1$1$3$2`) are kotlinc's own, by nesting position.

    The helpers (spec 2026-09-19 §4a, `ktor-route-extensions`): `fun Route.api() {
    get("/helper") { } }` called from `routing { api() }` — Ktor's own recommended way
    to split a routing tree — compiles to `invokestatic api(Route)` with the block's own
    parameter as its argument, the origin, so the walk follows the call into `api`'s body
    with ITS parameter 0 as the origin and `GET /helper` derives, resolved, on `orders()`
    (one router, one declarer — never `api` as the caller). `route("/api") { v2() }` with
    `fun Route.v2() { orders2() }` and `fun Route.orders2() { get("/deep") { } }` is two
    helper calls deep and derives `GET /api/deep`: the prefix that reached the first call
    carries all the way down. Both pins were silence until this walk existed.

    Two outcomes are degraded by design, and both are stated rather than hidden. The
    wrong-receiver case: `other.get("/stray") { }` inside `route("/api") { }` registers
    on ANOTHER route, so it is not under `/api`, and `receiver_arg`'s refusal is one
    unresolved row that never carries the prefix. And `defaults()`: its two `mount(…) {
    get(…) { } }` calls name a module-local DSL function the shipped catalog has no rule
    for, so each is a helper call the walk follows — and inside `mount`, `route(path,
    build)` sits on the origin with `path` as `mount`'s own PARAMETER, which this body
    cannot read. One unresolved row per call, path NULL, attributed to `defaults()`: the
    honest statement that a route is declared there at an address the walk did not read.
    (Under a catalog that names `mount` as a prefix rule the same calls derive `/d/x` and
    `/e/y` resolved — `tests/application/test_ktor_defaults_fixture.py`.)

    The SELECTOR blocks of `selectors()` (spec 2026-09-19 §4b, `ktor-selector-blocks`,
    `ktor-route-with-verb`; every signature CP-24 row 1a): `accept(ContentType.Application.
    Json) { get("/j") { } }` derives `GET /j` with `produces` read through the getter
    `ContentType$Application.getJson()` (CP-24 row 4, `media_values.getters`), and
    `contentType(…) { post("/c") { } }` fills `consumes`; `header("X-Api-Version", "2")`,
    `param("debug")`, `param("mode", "fast")` and `optionalParam("page")` are scopes whose
    routes derive beneath them (`GET /orders`, `/dbg`, `/fast`, `/paged`), each carrying
    the requirement its block states (asserted on `endpoint_metadata` below). The verb
    CONFLICT `method(HttpMethod.Post) { get("/never") { } }` is a node Ktor never
    dispatches (`HttpMethodRouteSelector.evaluate` returns the failure constant on a
    mismatch, CP-24 row 7) and publishes NOTHING — `/never` is absent, not unresolved (A2).
    Every one of these blocks derived nothing before the rules, and `route("/legacy2",
    HttpMethod.Put)` was one unresolved row.

    `handle { }` is the VERB-LESS TERMINAL (spec §4c; a member of the `Route` interface,
    CP-24 row 1b): under `method(HttpMethod.Get)` it takes the scope's verb and serves
    the receiver node itself — the routing root, `GET /` (`RoutingPath.parse("")` has no
    parts; the empty literal canonicalises to `/`), never `/**`; under `route("/legacy2",
    HttpMethod.Put)` it is `PUT /legacy2`; under a bare `route("/health2")` no verb is in
    scope and it expands through `all_methods` — `HttpMethod.DefaultMethods`' seven
    members (CP-24 row 2) — one row each, all on the one handler."""
    rows = {
        (r["method"], r["path"], r["resolution"], r["handler"])
        for r in ktor_rows
        if r["catalog_id"] == "ktor-routing"
    }
    assert {
        ("GET", "/api/orders", "resolved", _suspend_body("orders$1$1$1")),
        ("POST", "/api/orders", "resolved", _suspend_body("orders$1$1$2")),
        ("GET", "/api/v2/orders", "resolved", _suspend_body("orders$1$1$3$1")),
        ("DELETE", "/api/v2/orders/{id}", "resolved", _suspend_body("orders$1$1$3$2")),
        ("GET", "/api/legacy/orders", "resolved", _suspend_body("orders$1$1$4$1")),
        # get { } on the prefix: Ktor serves the prefix itself
        ("GET", "/api", "resolved", _suspend_body("orders$1$1$5")),
        ("GET", "/health", "resolved", _suspend_body("orders$1$2")),
        # the helpers: the handler class is the HELPER's own (`api$1`, `orders2$1`), the
        # caller `orders()` — asserted below
        ("GET", "/helper", "resolved", _suspend_body("api$1")),
        ("GET", "/api/deep", "resolved", _suspend_body("orders2$1")),
        # the selector blocks, on `selectors()`
        ("GET", "/j", "resolved", _suspend_body("selectors$1$3$1")),
        ("POST", "/c", "resolved", _suspend_body("selectors$1$4$1")),
        ("GET", "/orders", "resolved", _suspend_body("selectors$1$5$1")),
        ("GET", "/dbg", "resolved", _suspend_body("selectors$1$6$1")),
        ("GET", "/fast", "resolved", _suspend_body("selectors$1$7$1")),
        ("GET", "/paged", "resolved", _suspend_body("selectors$1$8$1")),
        # the verb-less terminal
        ("GET", "/", "resolved", _suspend_body("selectors$1$1$1")),
        ("PUT", "/legacy2", "resolved", _suspend_body("selectors$1$9$1")),
        *(
            (verb, "/health2", "resolved", _suspend_body("selectors$1$2$1"))
            for verb in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")
        ),
    } <= rows, sorted(rows, key=str)
    assert not any(str(r["path"]) in ("/**", "/health2/**") for r in ktor_rows)
    assert not any(str(r["path"]) in ("/api/**", "/apilegacyorders") for r in ktor_rows)
    assert not any(str(r["path"]) == "/never" for r in ktor_rows), "a verb conflict published"
    media = {
        (r["path"], r["consumes"], r["produces"]) for r in ktor_rows if r["path"] in ("/j", "/c")
    }
    assert media == {("/j", None, '["application/json"]'), ("/c", '["application/json"]', None)}
    # Exactly twenty-eight rows declared in `KtorRoutes.kt` — the twenty-four above, the
    # stray, the two `mount` rows and `reads()`'s `GET /reads/orders/{id}` (the handler-read
    # fixture, §5d, asserted on `endpoint_metadata` below) — so an extra row (a conflict's
    # route, a duplicate) cannot pass silently. Re-pinned 2026-10-26 when the fixture moved
    # to Ktor 3.6.0 (spec 2026-10-26 §3f): the count was of the whole fixture, and
    # `KtorStreams.kt` and `KtorClient.kt` add thirteen rows of their own (three inbound,
    # ten outbound, pinned by the tests below), so the twenty-eight are counted on the file
    # they come from and the fixture's whole count is forty-one. No `KtorRoutes.kt` row moved.
    routes = [r for r in ktor_rows if "/KtorRoutesKt#" in str(r["caller"])]
    assert len(routes) == 28, sorted(rows, key=str)
    assert len(ktor_rows) == 41, sorted(map(str, ktor_rows))
    stray = [r for r in ktor_rows if "#elsewhere(" in str(r["caller"])]
    assert len(stray) == 1 and stray[0]["resolution"] == "unresolved", stray
    assert not any(str(r["path"]).startswith("/api") for r in stray), stray
    assert all(
        "#orders(" in str(r["caller"])
        or "#selectors(" in str(r["caller"])
        or "#reads(" in str(r["caller"])
        for r in routes
        if r["resolution"] == "resolved"
    )
    assert not any(
        "#api(" in str(r["caller"]) or "#v2(" in str(r["caller"]) or "#orders2(" in str(r["caller"])
        for r in ktor_rows
    ), "a helper's route was attributed to the helper — the caller is the tree's root"
    mounted = [r for r in ktor_rows if "#defaults(" in str(r["caller"])]
    assert [(r["method"], r["path"], r["resolution"], r["handler"]) for r in mounted] == [
        (None, None, "unresolved", None),
        (None, None, "unresolved", None),
    ], mounted


def test_ktor_handler_reads_reach_endpoint_metadata(ktor_tables):
    """`inbound-request-requirements`, mechanism 3 on Ktor (spec 2026-09-19 §5d; CP-24
    rows 5–6), on real bytecode. `reads()`'s one handler reads five values and the table
    carries four: `call.request.headers["X-Trace"]` → header, `call.request.
    queryParameters["q"]` → query, `call.parameters["page"]` → query — each `requirement`
    NULL, a bare read stating that the handler reads the value and nothing about what
    Ktor does without it (A3) — and `call.parameters["id"]` NOTHING, because `id` is the
    route's own `{id}` and `call.parameters` merges path and query (`skip_path_variables`,
    A6). The three `get`s are one method on one `StringValues` supertype, told apart by
    the getter that produced the receiver (`via`): `RoutingRequest.getHeaders`,
    `RoutingRequest.getQueryParameters`, `RoutingCall.getParameters` — the CLASS overrides
    a 3.0.3 handler body's `call` (a `RoutingCall`) compiles to, measured on this very
    class and declared as such on the catalog.

    `call.parameters.getOrFail("cursor")` → query `cursor`, `required`, and NOT through a
    call site named `getOrFail`: the function is `inline`, so this body carries its BODY
    — `Parameters.get("cursor") ; ifnonnull ; new MissingRequestParameterException("cursor")
    ; athrow` — and the read reaches the pass as a plain `get` on `getParameters`. The
    catalog's `required_when_thrown` reads what the inlining left behind: the body
    constructs the framework's own exception with THIS read's name as its first argument
    (the extractor hands the `<init>` site the literal, measured), and Ktor does refuse
    the request (CP-24 row 5). `page` beside it, read the same way, stays NULL — the body
    throws for `cursor`, not for `page` (fix round 1; this pin moved from NULL)."""
    requirements = _requirements(ktor_tables["endpoint_metadata"])
    reads = {r for r in requirements if "reads$" in r[2]}
    handler = _suspend_body("reads$1$1")
    assert reads == {
        ("GET", "/reads/orders/{id}", handler, "header", "X-Trace", None, None, "resolved"),
        ("GET", "/reads/orders/{id}", handler, "query", "q", None, None, "resolved"),
        ("GET", "/reads/orders/{id}", handler, "query", "page", None, None, "resolved"),
        ("GET", "/reads/orders/{id}", handler, "query", "cursor", None, "required", "resolved"),
    }
    assert not any(r[4] == "id" for r in requirements), "the path variable was written as a query"
    # The selector rows and the read rows are the whole table: eight rows, nothing else.
    assert len(requirements) == 8, sorted(requirements, key=str)


def test_javalin_handler_reads_reach_endpoint_metadata(javalin_tables):
    """`inbound-request-requirements`, mechanism 3 on Javalin (spec 2026-09-19 §5d; CP-25
    rows 14–15), on real bytecode. The `ApiBuilder` handler under `/jv/nested/reads`:
    `ctx.queryParam("q")` → query and `ctx.header("X-Api")` → header, `requirement` NULL
    (A3: Javalin hands a null through); `ctx.queryParamAsClass("n", Integer.class).get()`
    → query `n`, `required` — `Validator.get()` throws `ValidationException` on an absent
    value, the framework's own refusal, reached through the catalog's `then: { method:
    get }` one result-to-receiver step; the same chain on `headerAsClass("X-Page", …)`
    ending in `getOrDefault(1)` stays NULL. `ctx.header("X-Set", "1")` — the two-argument
    SET on the response (F7) — writes nothing: the entries carry the read's arity and no
    other. The list is declared on `javalin.yml` and reaches this `javalin-apibuilder` row
    because reads are applied by HANDLER, not by catalog (§5d).

    The rows of `flat()` and `mounted()` carry NO reads, and could not: a `single_call`
    row's `handler` is the registering method, not the `Handler` lambda, so the lambda's
    body is outside what this pass scans — a stated boundary, not a claim (COVERAGE)."""
    rows = javalin_tables["endpoints"]
    handler = _handler_of(rows, "GET", "/jv/nested/reads")
    assert "OrderApp#lambda$nested$" in handler
    requirements = _requirements(javalin_tables["endpoint_metadata"])
    assert requirements == {
        ("GET", "/jv/nested/reads", handler, "query", "q", None, None, "resolved"),
        ("GET", "/jv/nested/reads", handler, "query", "n", None, "required", "resolved"),
        ("GET", "/jv/nested/reads", handler, "header", "X-Api", None, None, "resolved"),
        ("GET", "/jv/nested/reads", handler, "header", "X-Page", None, None, "resolved"),
    }


SERVLET = FIXTURES / "orders-servlet"


@pytest.fixture(scope="module")
def servlet_tables(tmp_path_factory: pytest.TempPathFactory) -> dict[str, list[dict]]:
    return _analyzed_tables(SERVLET, tmp_path_factory.mktemp("servlet"))


def test_servlet_handler_reads_reach_endpoint_metadata(servlet_tables):
    """`inbound-request-requirements`, mechanism 3 on the Servlet API (spec 2026-09-19
    §5d; CP-25 row 16), on real bytecode — the first servlet fixture, a `@WebServlet` on
    an `HttpServlet` subclass compiled against the API `tomcat-embed-core` bundles.
    `jakarta-servlet.yml` derives `GET /sv/orders` with `doGet` as its handler
    (`supertype_dispatch`), and `doGet`'s body reads two values: `req.getParameter("q")`
    → `param` (one method for the query string and a form body, §5a) and
    `req.getHeader("X-Api")` → header, both `requirement` NULL — abstract on the API,
    null-on-absent in the container, nothing refuses (A3). Both call sites name
    `HttpServletRequest`, the parameter's declared type, even for the
    `ServletRequest`-declared `getParameter` — which is the owner the entry names.
    `resp.setHeader(...)` is on the response type and writes nothing."""
    rows = servlet_tables["endpoints"]
    assert [(r["catalog_id"], r["method"], r["path"], r["resolution"]) for r in rows] == [
        ("jakarta-servlet", "GET", "/sv/orders", "resolved")
    ]
    handler = _handler_of(rows, "GET", "/sv/orders")
    assert handler.endswith("com/acme/sv/OrderServlet#doGet(sig_55584cc2).")
    assert _requirements(servlet_tables["endpoint_metadata"]) == {
        ("GET", "/sv/orders", handler, "param", "q", None, None, "resolved"),
        ("GET", "/sv/orders", handler, "header", "X-Api", None, None, "resolved"),
    }


KTOR_CLASSLAMBDAS = FIXTURES / "orders-ktor-classlambdas"


def test_the_class_lambda_twin_is_built_from_the_very_same_source():
    """`orders-ktor-classlambdas` compiles a COPY of `KtorRoutes.kt` — a symlink is not
    allowed in the fixture tree — so the two files can drift apart silently, and then the
    "identical rows" test below would compare two different programs. Byte-identical, or
    this says which one moved."""
    original = KTOR / "src" / "main" / "kotlin" / "com" / "acme" / "kt" / "KtorRoutes.kt"
    twin = KTOR_CLASSLAMBDAS / "src" / "main" / "kotlin" / "com" / "acme" / "kt" / "KtorRoutes.kt"
    assert original.read_bytes() == twin.read_bytes(), (
        f"{twin} drifted from {original}: copy the original over it"
    )


@pytest.fixture(scope="module")
def ktor_classlambda_rows(tmp_path_factory: pytest.TempPathFactory) -> list[dict]:
    """Every endpoint row the `-Xlambdas=class` twin derives, whole, from its own analysis."""
    workspace_dir = tmp_path_factory.mktemp("ktor-classlambdas")
    compile_fixture(KTOR_CLASSLAMBDAS)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(KTOR_CLASSLAMBDAS), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return [dict(row) for row in workspace.query("endpoints")]
    finally:
        workspace.close()


def _rows_modulo_module(rows: list[dict]) -> set[tuple]:
    """`(method, path, resolution, handler)` with the handler's module-coordinates prefix
    dropped — the one thing that differs by construction between the two builds, whose
    `artifactId`s differ. Class names do not: the same source compiles to the same
    `KtorRoutesKt$orders$1$1$1` counters under both profiles."""
    return {
        (
            r["method"],
            r["path"],
            r["resolution"],
            None if r["handler"] is None else bare_descriptor(str(r["handler"])),
        )
        for r in rows
    }


def test_the_class_lambda_twin_derives_identical_rows(ktor_rows, ktor_classlambda_rows):
    """`kotlin-class-lambdas`, spec 2026-09-19 §3b and §9, on real bytecode: the same
    `KtorRoutes.kt` compiled with `-Xlambdas=class` — every `Function1` block a `Lambda`
    CLASS `new`ed (or a shared `INSTANCE` read) at the call site where the default profile
    emits an `invokedynamic` — derives the SAME endpoint rows, handler included. The
    extractor marks each lambda class's type fact with the method holding its body
    (`lambda_body`, commit e6497f0's family), and `effective_call_sites` hands every
    engine the `instance` argument as that `lambda`, so the routing walk enters the block
    exactly as it enters an `invokedynamic` one. The handlers are `invokeSuspend` bodies
    under BOTH profiles — a suspend lambda is a class either way — so even the handler
    column agrees once the module prefix is dropped. A difference here is a shape one
    profile reads and the other does not, and it is reported, not tolerated."""
    # Re-pinned 2026-10-26: `orders-ktor` moved to Ktor 3.6.0 (Kotlin stays 2.2.0 until
    # OI-219: the extractor cannot read Kotlin 2.4 metadata) and gained
    # `KtorStreams.kt` and `KtorClient.kt` (spec 2026-10-26 §3f), which the twin does not
    # compile — it stays on Ktor 3.0.3 and Kotlin 2.2.0. The comparison is of the one source
    # both build, `KtorRoutes.kt`, so it now also says that source derives the same rows on
    # Ktor 3.0.3 and on 3.6.0.
    shared = [r for r in ktor_rows if "/KtorRoutesKt#" in str(r["caller"])]
    default, classes = _rows_modulo_module(shared), _rows_modulo_module(ktor_classlambda_rows)
    assert default == classes, {
        "only under the default profile": sorted(default - classes, key=str),
        "only under -Xlambdas=class": sorted(classes - default, key=str),
    }
    assert len(ktor_classlambda_rows) == len(shared) == 28


def test_ktor_selector_requirements_reach_endpoint_metadata(ktor_tables):
    """`inbound-request-requirements` on the Ktor side (spec 2026-09-19 §4b, §4d, §5c).
    What `selectors()`'s tree DEMANDS of a request reaches `endpoint_metadata` against
    the row it demands it of, `caller` = that row's handler (§4d): `header("X-Api-Version",
    "2")` → header, value `2`, `required` — the selector refuses a request without it;
    `param("debug")` → query, no value, `required`; `param("mode", "fast")` → query,
    value `fast`, `required`; `optionalParam("page")` → query, `optional` — the route is
    registered whether or not the parameter is present. These four rows are everything
    `selectors()`'s tree states; the rest of the table is `reads()`'s handler-body reads,
    asserted below, and the two together are the whole table."""
    selectors = {r for r in _requirements(ktor_tables["endpoint_metadata"]) if "selectors$" in r[2]}
    assert selectors == {
        (
            "GET",
            "/orders",
            _suspend_body("selectors$1$5$1"),
            "header",
            "X-Api-Version",
            "2",
            "required",
            "resolved",
        ),
        (
            "GET",
            "/dbg",
            _suspend_body("selectors$1$6$1"),
            "query",
            "debug",
            None,
            "required",
            "resolved",
        ),
        (
            "GET",
            "/fast",
            _suspend_body("selectors$1$7$1"),
            "query",
            "mode",
            "fast",
            "required",
            "resolved",
        ),
        (
            "GET",
            "/paged",
            _suspend_body("selectors$1$8$1"),
            "query",
            "page",
            None,
            "optional",
            "resolved",
        ),
    }


# Ktor's WebSocket and SSE routes, its HTTP client and its WebSocket and SSE clients (spec
# 2026-10-26 §3f, §6), on `orders-ktor` at Ktor 3.6.0. They are here, beside the routing
# pins, because they read the same one analysis of the fixture (`ktor_tables`): a second
# `module analyze` of it in an outbound file would cost a run for rows already in hand.
# The new code is in `KtorStreams.kt` and `KtorClient.kt`, never `KtorRoutes.kt`, so the
# class-lambda twin's copy of that file stays the very same source.


def _streams_body(handler_class: str) -> str:
    """`_suspend_body` for a `KtorStreamsKt` handler."""
    return (
        "sextant-jvm maven com.acme/orders-ktor 1.0.0 com/acme/kt/KtorStreamsKt$"
        + handler_class
        + "#invokeSuspend(sig_262c527a)."
    )


def test_ktor_websocket_and_sse_routes_derive_at_their_nested_paths(ktor_rows):
    """`streams()`: `route("/api") { webSocket("/chat") { }; sse("/events") { } }`. A
    WebSocket route is verbless, as every WebSocket catalog's row is, and nests under the
    prefix as an HTTP route does: `websocket /api/chat`. `sse(path)` is GET (CP-54 rows
    64-78, Ktor registers it under a GET selector): `sse GET /api/events`. Both rows are
    `ktor-routing`'s, read through the one prefix list the three protocols share.

    `method(HttpMethod.Get) { get("/legacy") { } }` is the verb read off Ktor 3.6.0's
    STATIC FIELD on REAL bytecode: kotlinc writes `getstatic HttpMethod.Get`, and the
    extractor describes it as an `enum`-kind argument (the field is typed as its own
    owner, D00 §5). Task 2's hand-made facts gave it the `field` kind and passed while the
    real shape published nothing (Task 4 found and fixed it); this is the pin those facts
    could not be. Agreeing with the route's own GET, it is `GET /legacy`.

    `method(HttpMethod.Post) { webSocket("/never-ws") { } }` is no row: a WebSocket route
    with a path is registered under GET (CP-54 rows 64-78), and Ktor never dispatches a
    GET node under a POST scope, exactly as `/never` above."""
    rows = {
        (r["protocol"], r["method"], r["path"], r["resolution"], r["handler"])
        for r in ktor_rows
        if r["catalog_id"] == "ktor-routing" and "KtorStreamsKt#" in str(r["caller"])
    }
    assert rows == {
        ("websocket", None, "/api/chat", "resolved", _streams_body("streams$1$1$1")),
        ("sse", "GET", "/api/events", "resolved", _streams_body("streams$1$1$2")),
        ("http", "GET", "/legacy", "resolved", _streams_body("streams$1$2$1")),
    }, sorted(rows, key=str)
    assert not any("never-ws" in str(r["path"]) for r in ktor_rows), "a verb conflict published"


def test_ktor_client_calls_derive_outbound_rows_joined_to_the_client_base(ktor_rows):
    """`KtorClient.kt`: a top-level `val client = HttpClient(CIO) { install(WebSockets);
    install(SSE); defaultRequest { url("https://pricing.example.com/") } }` and one call in
    each of the five forms CP-54 row group (b) measured. Every form compiles to the same
    inlined builder sequence, so each is one `ktor-client` row, the peer split off the URL.

    `client.get("quotes")` is RELATIVE: the walk reaches the client through its
    `<clinit>` `putstatic` (a field written from a call, D00 §5), the producer reader finds
    the `HttpClient(CIO) { … }` that built it, the ladder reads `defaultRequest`'s
    `url("…")`, and the address joins by Ktor's own rule (`replace_last_segment`, CP-54
    rows 51-56): `pricing.example.com` `/quotes`, resolved. `install(WebSockets)` and
    `install(SSE)` are plugins that set no base, so the base is trusted (`may_set_base`
    names only `DefaultRequest`'s plugin).

    `client.request(…) { method = HttpMethod.Put }` reads its verb off the static field, as
    the routing selector above does. The WebSocket call is the whole URL in `path`, peer
    NULL, verbless (`jakarta-websocket-client.yml`'s shape); the SSE call is GET, split into
    peer and path.

    The RELATIVE WebSocket and SSE calls join the same base, on real bytecode: `client.ws(
    "/feed")` sends with its own scheme and keeps the base's port, which Ktor writes because
    443 is not `ws`'s default — `ws://pricing.example.com:443/feed`, as CP-54's rows 94-113
    measured (`request_url: {scheme: ws}`); `client.sse("ticks")` joins as `get` does, `GET
    pricing.example.com /ticks` (rows 114-123)."""
    http = {
        (r["method"], r["peer"], r["path"], r["resolution"])
        for r in ktor_rows
        if r["catalog_id"] == "ktor-client" and "#bareOrders(" not in str(r["caller"])
    }
    assert http == {
        ("GET", "pricing.example.com", "/quotes", "resolved"),
        ("POST", "orders.example.com", "/orders", "resolved"),
        ("GET", "stock.example.com", "/levels", "resolved"),
        ("PUT", "orders.example.com", "/orders/7", "resolved"),
        ("GET", "orders.example.com", "/prepared", "resolved"),
    }, sorted(http, key=str)
    streams = {
        (r["catalog_id"], r["protocol"], r["method"], r["peer"], r["path"], r["resolution"])
        for r in ktor_rows
        if r["catalog_id"] in ("ktor-websocket-client", "ktor-sse-client")
    }
    assert streams == {
        (
            "ktor-websocket-client",
            "websocket",
            None,
            None,
            "ws://chat.example.com/chat",
            "resolved",
        ),
        ("ktor-sse-client", "sse", "GET", "events.example.com", "/stream", "resolved"),
        (
            "ktor-websocket-client",
            "websocket",
            None,
            None,
            "ws://pricing.example.com:443/feed",
            "resolved",
        ),
        ("ktor-sse-client", "sse", "GET", "pricing.example.com", "/ticks", "resolved"),
    }, sorted(streams, key=str)
    assert all(
        r["direction"] == "outbound"
        for r in ktor_rows
        if r["catalog_id"] in ("ktor-client", "ktor-websocket-client", "ktor-sse-client")
    )


def test_a_ktor_client_with_no_declared_base_is_not_sent_to_localhost(ktor_rows):
    """`val bare = HttpClient(CIO) { expectSuccess = true }` and `bare.get("orders")`. The
    walk reaches the construction and its block, a rung of the ladder, and the block calls
    no base setter. Ktor would send the request to `http://localhost/orders` (CP-54 rows 50,
    57), but that nothing set a base cannot be proven from bytecode, so the row keeps the
    path it states, peer NULL, at `unresolved` — never a resolved `localhost` (D02, the
    branch's reversal of its first ruling)."""
    bare = [
        (r["catalog_id"], r["method"], r["peer"], r["path"], r["resolution"])
        for r in ktor_rows
        if "#bareOrders(" in str(r["caller"])
    ]
    assert bare == [("ktor-client", "GET", None, "orders", "unresolved")], bare
    assert not any("localhost" in str(r["peer"]) + str(r["path"]) for r in ktor_rows)


def test_ktor_client_and_stream_rows_reach_the_module_document(ktor_tables):
    """The document is the result: the outbound HTTP, WebSocket and SSE rows, and an inbound
    WebSocket route, as `module render` writes them into `architecture.md` — each with its
    destination. HTTP and SSE rows name their peer in the Peer column; a WebSocket row
    carries the whole URL in its identity and records no peer; the base-less call is
    `unresolved` and names no peer."""
    document = ktor_tables["document"]
    outbound = document.split("## Outbound endpoints", 1)[1].split("\n## ", 1)[0]
    for line in (
        "| `GET /quotes` | pricing.example.com | `com/acme/kt/KtorClientKt#quotes(",
        "| `PUT /orders/7` | orders.example.com | `com/acme/kt/KtorClientKt#replaceOrder(",
        "| `GET orders` | none recorded | `com/acme/kt/KtorClientKt#bareOrders(",
        "| `sse GET /stream` | events.example.com | `com/acme/kt/KtorClientKt#events(",
        "| `sse GET /ticks` | pricing.example.com | `com/acme/kt/KtorClientKt#ticks(",
        "| `websocket ws://chat.example.com/chat` | none recorded | `com/acme/kt/KtorClientKt#chat(",
        (
            "| `websocket ws://pricing.example.com:443/feed` | none recorded "
            "| `com/acme/kt/KtorClientKt#feed("
        ),
    ):
        assert line in outbound, (line, outbound)
    assert "| `GET orders` | none recorded" in outbound and "localhost" not in outbound
    assert "| `websocket /api/chat` | `KtorStreamsKt$streams$1$1$1#invokeSuspend` |" in document
    assert "| `sse GET /api/events` | `KtorStreamsKt$streams$1$1$2#invokeSuspend` |" in document


GATEWAY = FIXTURES / "orders-gateway"


@pytest.fixture(scope="module")
def gateway_tables(tmp_path_factory: pytest.TempPathFactory) -> dict[str, list[dict]]:
    return _analyzed_tables(GATEWAY, tmp_path_factory.mktemp("gateway"))


@pytest.fixture(scope="module")
def gateway_rows(gateway_tables: dict[str, list[dict]]) -> list[dict]:
    """Every endpoint row the Spring Cloud Gateway fixture derives, whole — the test reads
    the handler and the caller beside the identity."""
    return gateway_tables["endpoints"]


def test_gateway_routes_derive_their_inbound_surface(gateway_rows):
    """`spring-cloud-gateway`, spec §14 test 10, on spring-cloud-gateway-server-webflux
    5.0.0: every route is a lambda handed to `route(…)`, its predicates a receiver chain on
    the lambda's own parameter, its address the path those predicates read. `path` alone
    serves its path with no verb (a catch-all one column over, spec §13 case 7);
    `path().and().method(POST, PUT)` is one row per verb; `path("/a").or().path("/b")` is
    two rows; the host-only `route(Function)` serves every path, `/**`. No row carries a
    handler — a gateway route forwards, it dispatches to no method — and every row's
    caller is `routes`, the method holding `build()`.

    The two capture shapes a fixed parameter index gets wrong, read off `javap -p` of the
    compiled fixture: `legacy` captures the local `prefix`, so its body is
    `lambda$routes$6(String, PredicateSpec)` and the route's `PredicateSpec` is parameter
    1, not 0; `billing` captures `this`, so its body is the instance method
    `lambda$routes$7(PredicateSpec)` with the spec at parameter 0. Both chains are found
    on the origin parameter — `origin_param: 0` resolved through each lambda's own
    `captures` — and neither is attributed to the wrong value. `billing` then reads its
    literal path, `/billing/**`, resolved. `legacy` reads `prefix + "/**"`, which javac
    compiles to a concatenation (`{}/**`, a hole for the captured value): the path is not
    readable from the body, so that row is `unresolved` with its path NULL — the honest
    answer for an assembled path, and the row is still there, under `routes`, rather
    than silence. `not(p -> p.path("/admin/**"))` is the other unresolved row: a negated
    predicate serves something the negation does not say.

    Both `route` overloads derive — the named seven and the unnamed host-only one — because
    a body-linked entry is told apart by `arity` like every other rule (A2 Task 7); matched
    on owner and name alone, the first entry claimed both and the host-only route was one
    unresolved row. `guarded` — `path("/guarded/**").and().header("X-Api", "v2").and().
    query("debug")` — serves its path exactly as `orders` does: the two predicates narrow
    WHO is served and are the row's requirements (asserted on `endpoint_metadata` below),
    never its address. Exactly ten rows from this catalog — the eight resolved and the two
    unresolved — so an extra row (a negator's lambda body scanned as a tree of its own, a
    pass-through reached unconsumed, a duplicate) cannot pass silently."""
    rows = [r for r in gateway_rows if r["catalog_id"] == "spring-cloud-gateway"]
    identities = {(r["method"], r["path"], r["resolution"]) for r in rows}
    # **Every resolved route is one row per method since 2026-10-17** (user ruling: fan out,
    # but only to methods that are SUPPORTED). What makes all eight honest for a gateway is
    # measured at `scripts/probes/cp29_gateway_properties.md` Q11 — `HttpMethod` appears
    # ZERO times in `RouteDefinitionRouteLocator`, so route construction constrains no
    # method. `RouterFunctions.resources(...)` serves three and not eight, which is why its
    # own catalog still declines `all_methods`.
    #
    # Three things this pins that the fan-out could have broken, and did not:
    #   * `/orders/**` carries an explicit POST and PUT route BESIDE a verbless one, and the
    #     result is eight rows rather than ten — the fanned rows dedupe against the declared
    #     ones through `call_endpoints`' insert-if-absent, so a route declared twice is not
    #     counted twice;
    #   * the two UNRESOLVED rows are not fanned. A route whose address could not be read is
    #     one doubt, and eight rows would present it as eight facts (`_fanned` refuses a
    #     poisoned route for the same reason);
    #   * `/guarded/**`'s header and query requirements ride every fanned row, asserted in
    #     `test_gateway_header_and_query_predicates_reach_endpoint_metadata` below.
    verbs = ("DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT", "TRACE")
    served = ("/orders/**", "/a/**", "/b/**", "/billing/**", "/**", "/guarded/**")
    assert {
        *((verb, path, "resolved") for path in served for verb in verbs),
        (None, None, "unresolved"),  # not-admin, and legacy (captured local, concat path)
    } == identities, sorted(identities, key=str)
    unresolved = [r for r in rows if r["resolution"] == "unresolved"]
    assert len(unresolved) == 2 and all(r["method"] is None for r in unresolved), unresolved
    assert len(rows) == len(served) * len(verbs) + 2, sorted(identities, key=str)
    assert all(r["handler"] is None for r in rows), [r["handler"] for r in rows]
    assert all("#routes(" in str(r["caller"]) for r in rows), sorted({r["caller"] for r in rows})


def test_gateway_header_and_query_predicates_reach_endpoint_metadata(gateway_tables):
    """`inbound-request-requirements` on the Gateway side (spec 2026-09-19 §5c; CP-26 rows
    3–4). `guarded`'s `header("X-Api", "v2")` and `query("debug")` were pass-throughs that
    read nothing; they still carry the chain on, and now also state what the route
    demands: header `X-Api` matching `v2` (the regex as written, the value column),
    query `debug` present (the one-argument overload, no value), both `required` — the
    `HeaderRoutePredicateFactory`/`QueryRoutePredicateFactory` each builds does not
    match the route without them. Against the row they guard, `/guarded/**`, whose
    `caller` is NULL: a gateway route has no handler, and an inbound metadata row's
    `caller` is the handler (§4d). The fixture's other DSL routes state nothing.

    *This pinned the table as exactly those two rows until `gateway-properties-routes`
    (spec 2026-09-21 §7b): the PROPERTY route `cfg-orders` declares `Header=X-Api,v2`
    beside `Method=GET,POST`, so the same requirement stands against each of its two
    rows — through the same stash, joined by `None == None` on `caller` and `handler`
    (`test_gateway_property_routes_derive_their_inbound_and_outbound_rows` below).*"""
    # **`/guarded/**`'s two requirements ride EVERY fanned row** since 2026-10-17, which is
    # `_fanned`'s own rule — "each carrying the route's requirements" — now that the catalog
    # declares `all_methods`. `/cfg/orders/**` declares `Method=GET,POST` and is NOT widened,
    # so its two rows stay two: the contrast is the user's ruling (fan out only to methods
    # that are supported) visible in one assertion.
    assert _requirements(gateway_tables["endpoint_metadata"]) == {
        *(
            (verb, "/guarded/**", None, kind, name, value, "required", "resolved")
            for verb in ("DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT", "TRACE")
            for kind, name, value in (("header", "X-Api", "v2"), ("query", "debug", None))
        ),
        ("GET", "/cfg/orders/**", None, "header", "X-Api", "v2", "required", "resolved"),
        ("POST", "/cfg/orders/**", None, "header", "X-Api", "v2", "required", "resolved"),
    }


def test_gateway_property_routes_derive_their_inbound_and_outbound_rows(gateway_rows):
    """`gateway-properties-routes` (spec 2026-09-21 §7b; CP-29), on
    spring-cloud-gateway-server-webflux 5.0.0: the two routes `application.yml` declares
    under `spring.cloud.gateway.server.webflux.routes` — `cfg-orders` in the shortcut
    spelling (`Path=/cfg/orders/**`, `Method=GET,POST`, `Header=X-Api,v2`, `uri:
    lb://orders`) and `cfg-items` in the map spelling (`name: Path`, `args.patterns:
    /cfg/items/**`, `uri: http://items.internal:8080`) — read by
    `spring-cloud-gateway-properties.yml` through `config_join`'s `indexed:` form.

    Inbound: one row per verb for `cfg-orders`, one verb-less row for `cfg-items` (no
    `Method=` → `method` NULL, resolved — §0b A7, the DSL's own rendering), the pattern
    as the served path, no handler and no caller (a configured route dispatches to no
    method), every row resolved. Outbound: one row per `uri`, the target VERBATIM as the
    `path` with `peer` NULL — exactly the shape `spring-cloud-gateway-outbound.yml`
    publishes for the DSL's `uri(…)` (`test_rest_outbound_delivered.py`): a routing
    destination kept whole, never split into a peer and an empty path. The DSL pair's
    own rows are untouched (their catalog ids are not this one's), and the `Header=`
    requirement is asserted above."""
    rows = [r for r in gateway_rows if r["catalog_id"] == "spring-cloud-gateway-properties"]
    identities = {(r["direction"], r["method"], r["path"], r["resolution"]) for r in rows}
    # **The config form fans out exactly as the DSL form does** since 2026-10-17 (user
    # ruling), and the two routes in one fixture pin both halves of it: `/cfg/items/**`
    # declares no `Method=` and becomes one row per method; `/cfg/orders/**` declares
    # `Method=GET,POST` and stays two. A fan-out keyed on "the verb is NULL" rather than on
    # the catalog's `all_methods` would have widened the declared pair too.
    #
    # **The outbound forward targets are NOT fanned**, deliberately: one destination, and
    # eight rows naming `lb://orders` would say one thing eight times. The inbound rows are
    # the endpoints this module SERVES, which is what a reader asks about by method.
    assert identities == {
        ("inbound", "GET", "/cfg/orders/**", "resolved"),
        ("inbound", "POST", "/cfg/orders/**", "resolved"),
        *(
            ("inbound", verb, "/cfg/items/**", "resolved")
            for verb in ("DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT", "TRACE")
        ),
        ("outbound", None, "lb://orders", "resolved"),
        ("outbound", None, "http://items.internal:8080", "resolved"),
    }, sorted(identities, key=str)
    assert len(rows) == 12, sorted(identities, key=str)
    assert all(r["handler"] is None and r["caller"] is None and r["peer"] is None for r in rows)
    assert all(r["protocol"] == "http" and r["evidence"] == "compiler" for r in rows)
    dsl = {r["catalog_id"] for r in gateway_rows} - {"spring-cloud-gateway-properties"}
    assert dsl == {"spring-cloud-gateway", "spring-cloud-gateway-outbound"}, dsl


# --- §5b `request_params`: what each framework's binder enforces (CP-25 rows 2–12) ------


def _handler_of(rows: list[dict], method: str | None, path: str) -> str:
    # `method` is NULLABLE because a verbless row really has none: a Kafka listener's
    # endpoint carries `method: None`, and asking for it by `None` is asking the question
    # the column answers rather than working around a type.
    return next(str(r["handler"]) for r in rows if r["path"] == path and r["method"] == method)


def _at(requirements: set[tuple], path: str) -> set[tuple]:
    """The rows against one path, the caller shortened to its bare descriptor."""
    return {(r[0], bare_descriptor(str(r[2])), *r[3:]) for r in requirements if r[1] == path}


def test_spring_request_params_record_what_the_binder_enforces(http_requirements, http_rows):
    """`inbound-request-requirements`, mechanism 1 on Spring MVC (spec 2026-09-19 §5b;
    CP-25 rows 2, 3 and 5). `RequestParamsController#search` carries every form the rule
    reads: `q` — a plain `String`, no attribute — is `required`, and it is the row that
    proves the binder predicate reads the DECLARATION and not the type reference, which
    is `nullable: true` for every Java reference type (D00 §5); `tag` is `optional` by
    `required = false`; `page` by a WRITTEN `defaultValue` (row 5: an unwritten one never
    reaches the class file); `sort` by its `Optional` type, and named `sort` by the
    `name` attribute; the `Map` binding `all` is SKIPPED (a row would name the map
    variable as a request parameter); `X-Tenant` a `required` header; `session` an
    `optional` cookie. `kind: param` on `@RequestParam` because Spring cannot tell query
    from form through it (§5a); `value` NULL — an annotation names, it never demands a
    value; `caller` the handler. One row each although two catalogs (`spring-web`,
    `spring-mvc`) can own the class: identical rows meet insert-if-absent (A8)."""
    handler = bare_descriptor(_handler_of(http_rows, "GET", "/v1/params/search"))
    assert handler.endswith("RequestParamsController#search(sig_089e06fc).")
    assert _at(http_requirements, "/v1/params/search") == {
        ("GET", handler, "param", "q", None, "required", "resolved"),
        ("GET", handler, "param", "tag", None, "optional", "resolved"),
        ("GET", handler, "param", "page", None, "optional", "resolved"),
        ("GET", handler, "param", "sort", None, "optional", "resolved"),
        ("GET", handler, "header", "X-Tenant", None, "required", "resolved"),
        ("GET", handler, "cookie", "session", None, "optional", "resolved"),
    }


def test_a_kotlin_defaulted_or_nullable_parameter_is_optional_to_the_binder(
    http_requirements, http_rows
):
    """R1, the false positive the spec's self-review found and ruled on: `@RequestParam
    page: Int = 0` is optional to Spring — `MethodParameter.isOptional()` reaches
    `KotlinDelegate.isOptional`, `KParameter.isOptional()` (CP-25 row 3) — but compiles
    to an `int` slot that no attribute and no nullability marks; the extractor's
    `declares_default: true` (D00 §5a) is what the rule reads. `tag: String?` is optional
    through the `@org.jetbrains.annotations.Nullable` kotlinc emits on the parameter, one
    of the shape model's `nullability.nullable` spellings — the same read as a Java
    `@Nullable`, no language named. The handler is `search` itself, not its `$default`
    bridge."""
    handler = bare_descriptor(_handler_of(http_rows, "GET", "/ktparams/search"))
    assert handler.endswith("KotlinParamController#search(sig_8a91df81).")
    assert _at(http_requirements, "/ktparams/search") == {
        ("GET", handler, "param", "page", None, "optional", "resolved"),
        ("GET", handler, "param", "tag", None, "optional", "resolved"),
    }


# --- §5c `mapping.request_requirement_attrs`: what the mapping's own expressions demand ---


def test_spring_mapping_params_and_headers_expressions_are_requirements(
    http_requirements, http_rows
):
    """`inbound-request-requirements`, mechanism 2 on Spring MVC (spec 2026-09-19 §5c;
    CP-25 rows 4 and 13). `MappingConditionsController` carries every expression form
    on real bytecode: the class's `params = "tenant"` reaches BOTH handlers, `required`
    — `ParamsRequestCondition.combine` unions the class's set with the method's; on
    `versioned`, `v=1` is `required` with the value `1` and `!X-Legacy` is `absent`,
    the request must not carry the header; on `legacy`, `v!=1` is `optional` (served
    whenever `v` is not `1`, an absent `v` included — the excluded value has no column),
    `X-Api` is `required`, and `Accept=application/json` writes NOTHING:
    `HeadersRequestCondition.parseExpressions` drops `Accept`/`Content-Type` and Spring
    reads them as produces/consumes (A4). `kind: param` for `params=`, the same word
    `@RequestParam` carries and for the same reason; `caller` the handler; one row each
    although `spring-web` and `spring-mvc` both read the class (A8)."""
    versioned = bare_descriptor(_handler_of(http_rows, "GET", "/v1/conditions/orders"))
    legacy = bare_descriptor(_handler_of(http_rows, "GET", "/v1/conditions/legacy"))
    assert versioned.endswith("MappingConditionsController#versioned(sig_26be7569).")
    assert _at(http_requirements, "/v1/conditions/orders") == {
        ("GET", versioned, "param", "tenant", None, "required", "resolved"),
        ("GET", versioned, "param", "v", "1", "required", "resolved"),
        ("GET", versioned, "header", "X-Legacy", None, "absent", "resolved"),
    }
    assert _at(http_requirements, "/v1/conditions/legacy") == {
        ("GET", legacy, "param", "tenant", None, "required", "resolved"),
        ("GET", legacy, "param", "v", None, "optional", "resolved"),
        ("GET", legacy, "header", "X-Api", None, "required", "resolved"),
    }
    assert not any(str(r[4]).lower() == "accept" for r in http_requirements), (
        "an Accept header expression was written as a requirement"
    )


def test_the_conflict_detectors_discriminators_are_the_same_requirements(
    http_requirements, http_rows
):
    """W28's `RoutingConditionsController` — three handlers on `GET /v1/routing/orders`
    that Spring registers because `params`/`headers` separate them — now states WHAT
    separates them on each row: `view=summary`, `view=full`, `X-Orders-Api=2`, each
    `required` with its value against its own handler. The same attributes, read the
    same way (the effective annotation set), serving the conflict check and this table
    alike."""
    rows = {
        (bare_descriptor(str(r[2])).rsplit("#", 1)[1].split("(")[0], r[3], r[4], r[5], r[6])
        for r in http_requirements
        if r[1] == "/v1/routing/orders"
    }
    assert rows == {
        ("summary", "param", "view", "summary", "required"),
        ("full", "param", "view", "full", "required"),
        ("versioned", "header", "X-Orders-Api", "2", "required"),
    }


@pytest.fixture(scope="module")
def spring7_tables(tmp_path_factory: pytest.TempPathFactory) -> dict[str, list[dict]]:
    return _analyzed_tables(SPRING7, tmp_path_factory.mktemp("spring7-requirements"))


def test_jaxrs_named_parameters_are_optional_in_both_spellings(spring7_tables):
    """§5b on JAX-RS (CP-25 rows 9–10): `@QueryParam`/`@HeaderParam` declare `value` only,
    and an absent value is null — or the SEPARATE `@DefaultValue`, informational — never a
    400, so every row is `optional` whatever the parameter's type: `q` carries a default
    and `X-Tenant` none, and they read the same. The `javax` spelling derives the same
    row through `javax-jaxrs.yml`. Nothing else on the fixture carries an entry's
    annotation, so these three rows are the whole inbound table."""
    rows = spring7_tables["endpoints"]
    jakarta = bare_descriptor(_handler_of(rows, "GET", "/jaxrs/orders/search"))
    javax = bare_descriptor(_handler_of(rows, "GET", "/legacy/orders/search"))
    requirements = _requirements(spring7_tables["endpoint_metadata"])
    assert _at(requirements, "/jaxrs/orders/search") == {
        ("GET", jakarta, "query", "q", None, "optional", "resolved"),
        ("GET", jakarta, "header", "X-Tenant", None, "optional", "resolved"),
    }
    assert _at(requirements, "/legacy/orders/search") == {
        ("GET", javax, "query", "q", None, "optional", "resolved"),
    }
    assert len(requirements) == 3, sorted(requirements, key=str)


@pytest.fixture(scope="module")
def micronaut_tables(tmp_path_factory: pytest.TempPathFactory) -> dict[str, list[dict]]:
    return _analyzed_tables(MICRONAUT, tmp_path_factory.mktemp("micronaut-requirements"))


def test_micronaut_binds_required_unless_the_argument_is_nullable(micronaut_tables):
    """§5b on Micronaut (CP-25 rows 6–8): no `required` attribute exists, so a
    `@QueryValue String tenant` and a `@Header("X-Tenant")` are `required` — an
    unsatisfied binding throws `UnsatisfiedRouteException` — and `@QueryValue @Nullable
    String q` is `optional`, through Micronaut's OWN `io.micronaut.core.annotation.Nullable`,
    which its processor maps onto the stereotype `Argument.isNullable()` asks for and
    which the shape model lists for that reason. `byId(String id)`, the unannotated
    by-name binding, writes nothing: skipped and stated on the catalog.

    `@QueryValue String pageSize` is `required` too, and names NOTHING (CP-25 row 18):
    the binder reads `pageSize` and, finding no such parameter, retries `page-size` —
    `NameUtils.hyphenate` of the parameter's own name — so a request carrying either
    spelling is served, and `query pageSize required` would state a name the framework
    does not require by itself. `tenant` hyphenates to itself and keeps its name; the
    WRITTEN `X-Tenant` is never respelled.

    **The fifth row is not a requirement at all, and it is here because this assertion
    pins the fixture's WHOLE `endpoint_metadata` table rather than the route's share of
    it.** `micronaut-kafka.yml`'s `metadata_from` (spec 2026-09-22 §2e, CP-32 Q4a/Q9)
    reads `@KafkaListener(groupId = "orders")` off `OrderMessaging$KafkaConsumer` — the
    CLASS, while the row's handler is `onPlaced`, so it arrives through the
    enclosing-type half of the nearest-wins read — and writes it against the listener's
    own `kafka` endpoint. `requirement` is NULL because a qualifying attribute states
    nothing about what the framework demands of a request, `name` is NULL because the
    `kind` is the name of the thing, and `method` is NULL because a listener is verbless.
    It is the only row §2e moves anywhere in this repository (CP-32 Q11a/Q11b: no other
    shipped declaration writes a qualifying attribute at all)."""
    rows = micronaut_tables["endpoints"]
    handler = bare_descriptor(_handler_of(rows, "GET", "/mn/orders/search"))
    listener = bare_descriptor(_handler_of(rows, None, "mn.orders.placed"))
    requirements = _requirements(micronaut_tables["endpoint_metadata"])
    assert _at(requirements, "/mn/orders/search") == {
        ("GET", handler, "query", "q", None, "optional", "resolved"),
        ("GET", handler, "query", "tenant", None, "required", "resolved"),
        ("GET", handler, "query", None, None, "required", "unresolved"),
        ("GET", handler, "header", "X-Tenant", None, "required", "resolved"),
    }
    assert _at(requirements, "mn.orders.placed") == {
        (None, listener, "consumer_group", None, "orders", None, "resolved"),
    }
    assert len(requirements) == 5, sorted(requirements, key=str)


@pytest.fixture(scope="module")
def quarkus_tables(tmp_path_factory: pytest.TempPathFactory) -> dict[str, list[dict]]:
    return _analyzed_tables(QUARKUS, tmp_path_factory.mktemp("quarkus-requirements"))


def test_quarkus_rest_and_reactive_routes_parameters_are_optional(quarkus_tables):
    """§5b on Quarkus, both stacks. Quarkus REST binds its own `@RestQuery` — `value`
    only, the name defaulting to the parameter's (A9, CP-25 row 9) — beside `@QueryParam`
    through the same extractors that hand an absent value through as null (row 10): both
    `optional`. Reactive routes' `@Param`/`@Header` compile to a plain
    `HttpServerRequest.getParam`/`getHeader` read whose return Vert.x declares
    `@Nullable` (rows 11–12): `optional`, as §5b's table asked CP-25 to confirm.

    The fixture's older handlers carry `@Param String id` under `/:id` — the guide's
    idiom for a PATH segment, which Vert.x serves through the same `getParam` — and the
    entry's `skip_path_variables` (ruled 2026-09-20, fix round 1) gives them NO row: `id`
    is the path parameter, and `query id` would be a false statement about what the
    handler binds. `find(@Param id, @Param verbose)` on `/:id` is the pair: one row,
    `verbose`, and none for `id`."""
    rows = quarkus_tables["endpoints"]
    rest = bare_descriptor(_handler_of(rows, "GET", "/q/orders/search"))
    routes = bare_descriptor(_handler_of(rows, "GET", "/qk/orders/search"))
    requirements = _requirements(quarkus_tables["endpoint_metadata"])
    assert _at(requirements, "/q/orders/search") == {
        ("GET", rest, "query", "q", None, "optional", "resolved"),
        ("GET", rest, "query", "tenant", None, "optional", "resolved"),
    }
    assert _at(requirements, "/qk/orders/search") == {
        ("GET", routes, "query", "q", None, "optional", "resolved"),
        ("GET", routes, "header", "X-Tenant", None, "optional", "resolved"),
    }
    find = bare_descriptor(_handler_of(rows, "GET", "/qk/orders/:id"))
    assert _at(requirements, "/qk/orders/:id") == {
        ("GET", find, "query", "verbose", None, "optional", "resolved"),
    }
    assert not any(r[4] == "id" for r in requirements), sorted(requirements, key=str)
    assert len(requirements) == 5, sorted(requirements, key=str)
