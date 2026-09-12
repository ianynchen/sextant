"""REST inbound is delivered when every way a Spring Boot module exposes an HTTP endpoint
is visible. This file grows one shape at a time; each test names the shape and the gap it
closed.

**Not a document check.** Real bytecode, real pipeline, assertion on derived endpoints.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.cli.app import cli
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


@pytest.mark.xfail(
    strict=True,
    reason="JAX-RS puts verb, path and media on THREE separate annotations of one method; "
    "reading one annotation's attribute off a sibling is a vocabulary form the engine "
    "lacks. Measured 2026-09-11: a catalog of the existing forms collapses every GET onto "
    "the class @Path. Engine work — on the delivery list as needing a plan, not a catalog.",
)
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


@pytest.mark.xfail(
    strict=True,
    reason="JAX-RS puts verb, path and media on THREE separate annotations of one method; "
    "reading one annotation's attribute off a sibling is a vocabulary form the engine "
    "lacks. Measured 2026-09-11: a catalog of the existing forms collapses every GET onto "
    "the class @Path. Engine work — on the delivery list as needing a plan, not a catalog.",
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
    """Every HTTP row the Quarkus fixture derives, analysed once."""
    workspace_dir = tmp_path_factory.mktemp("quarkus")
    compile_fixture(QUARKUS)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(QUARKUS), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return [dict(row) for row in workspace.query("endpoints") if str(row["protocol"]) == "http"]
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
    method, as for every `single_call` inbound row)."""
    expected = {
        ("inbound", "GET", "/jv/orders"),
        ("inbound", "GET", "/jv/orders/{id}"),
        ("inbound", "POST", "/jv/orders"),
        ("inbound", "DELETE", "/jv/orders/{id}"),
    }
    missing = expected - javalin_routes
    assert missing == set(), f"missing {sorted(missing)}. Derived: {sorted(javalin_routes)}"
    assert ("inbound", "GET", "/{id}") not in javalin_routes, (
        "the ApiBuilder inner path was published WITHOUT its `path(…)` prefix — a wrong row"
    )


@pytest.mark.xfail(
    strict=True,
    reason="javalin-apibuilder: nested ApiBuilder needs the receiver-chain walk (Category B)",
)
def test_javalin_api_builder_derives_the_composed_path(javalin_routes):
    assert ("inbound", "GET", "/jv/nested/{id}") in javalin_routes
