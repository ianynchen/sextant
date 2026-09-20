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


def test_a_kotlin_dsl_route_declared_under_a_media_guard_alone_is_one_unresolved_row(http_rows):
    """The tracked gap, NOT the destination (`dsl-media-route` on the register; A1 Task 5
    review). `KotlinMvcRoutes.kt` writes `accept(MediaType.APPLICATION_JSON) { h }` — the
    DSL's `accept(MediaType, Function1)V`, a route declared under a media guard alone —
    and this grammar has no word for a media rule that also carries a handler. It derived
    SILENCE; it derives one row, `unresolved`, path NULL, no handler, attributed to the
    declaring method, until the word exists."""
    gap = [
        row
        for row in http_rows
        if row["catalog_id"] == "spring-mvc-router"
        and _short_caller(row) == "KotlinMvcRoutes#ktMvcRoutes"
        and row["resolution"] == "unresolved"
    ]
    assert [(row["method"], row["path"], row["handler"]) for row in gap] == [(None, None, None)]


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
def javalin_routes(tmp_path_factory: pytest.TempPathFactory) -> set[tuple[str, str, str]]:
    """`(direction, method, path)` for every inbound HTTP row the Javalin fixture derives."""
    workspace_dir = tmp_path_factory.mktemp("javalin")
    compile_fixture(JAVALIN)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(JAVALIN), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return {
            (str(row["direction"]), str(row["method"]), str(row["path"]))
            for row in workspace.query("endpoints")
            if str(row["protocol"]) == "http"
        }
    finally:
        workspace.close()


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
    }
    assert expected <= javalin_routes, sorted(javalin_routes)
    assert ("inbound", "GET", "/{id}") not in javalin_routes
    assert ("inbound", "POST", "/jv/nested/**") not in javalin_routes
    assert ("inbound", "GET", "/jv/nestedplainx") not in javalin_routes


KTOR = FIXTURES / "orders-ktor"


@pytest.fixture(scope="module")
def ktor_rows(tmp_path_factory: pytest.TempPathFactory) -> list[dict]:
    """Every endpoint row the Ktor fixture derives, whole — the Ktor test reads the
    handler and the caller beside the identity, which the Javalin fixture's triples
    do not carry."""
    workspace_dir = tmp_path_factory.mktemp("ktor")
    compile_fixture(KTOR)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(KTOR), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return [dict(row) for row in workspace.query("endpoints")]
    finally:
        workspace.close()


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
    … } }` on ktor-server-core 3.0.3: every verb is a static extension whose receiver is
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
    # Exactly twenty-seven rows — the twenty-four above, the stray, and the two `mount`
    # rows — so an extra row (a conflict's route, a duplicate) cannot pass silently.
    assert len(ktor_rows) == 27, sorted(rows, key=str)
    stray = [r for r in ktor_rows if "#elsewhere(" in str(r["caller"])]
    assert len(stray) == 1 and stray[0]["resolution"] == "unresolved", stray
    assert not any(str(r["path"]).startswith("/api") for r in stray), stray
    assert all(
        "#orders(" in str(r["caller"]) or "#selectors(" in str(r["caller"])
        for r in ktor_rows
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
    default, classes = _rows_modulo_module(ktor_rows), _rows_modulo_module(ktor_classlambda_rows)
    assert default == classes, {
        "only under the default profile": sorted(default - classes, key=str),
        "only under -Xlambdas=class": sorted(classes - default, key=str),
    }
    assert len(ktor_classlambda_rows) == len(ktor_rows) == 27


GATEWAY = FIXTURES / "orders-gateway"


@pytest.fixture(scope="module")
def gateway_rows(tmp_path_factory: pytest.TempPathFactory) -> list[dict]:
    """Every endpoint row the Spring Cloud Gateway fixture derives, whole — the test reads
    the handler and the caller beside the identity."""
    workspace_dir = tmp_path_factory.mktemp("gateway")
    compile_fixture(GATEWAY)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(GATEWAY), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return [dict(row) for row in workspace.query("endpoints")]
    finally:
        workspace.close()


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

    Both `route` overloads derive — the named six and the unnamed host-only one — because a
    body-linked entry is told apart by `arity` like every other rule (A2 Task 7); matched on
    owner and name alone, the first entry claimed both and the host-only route was one
    unresolved row. Exactly nine rows from this catalog — the seven resolved and the two
    unresolved — so an extra row (a negator's lambda body scanned as a tree of its own, a
    pass-through reached unconsumed, a duplicate) cannot pass silently."""
    rows = [r for r in gateway_rows if r["catalog_id"] == "spring-cloud-gateway"]
    identities = {(r["method"], r["path"], r["resolution"]) for r in rows}
    assert {
        (None, "/orders/**", "resolved"),
        ("POST", "/orders/**", "resolved"),
        ("PUT", "/orders/**", "resolved"),
        (None, "/a/**", "resolved"),
        (None, "/b/**", "resolved"),
        (None, "/billing/**", "resolved"),  # captured `this`: the spec is parameter 0
        (None, "/**", "resolved"),  # host only, the `route(Function)` overload
        (None, None, "unresolved"),  # not-admin, and legacy (captured local, concat path)
    } == identities, sorted(identities, key=str)
    unresolved = [r for r in rows if r["resolution"] == "unresolved"]
    assert len(unresolved) == 2 and all(r["method"] is None for r in unresolved), unresolved
    assert len(rows) == 9, sorted(identities, key=str)
    assert all(r["handler"] is None for r in rows), [r["handler"] for r in rows]
    assert all("#routes(" in str(r["caller"]) for r in rows), sorted({r["caller"] for r in rows})
