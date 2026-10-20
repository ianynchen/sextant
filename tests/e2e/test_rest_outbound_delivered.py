"""REST outbound is delivered when every way a Spring Boot module calls an HTTP endpoint is
visible. Each test names the shape.

**Not a document check.** Real bytecode, real pipeline, assertion on derived endpoints.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.cli.app import cli
from sextant.domain.redaction import REDACTED
from sextant.storage.duckdb.workspace import DuckDbWorkspace

SPRING7 = FIXTURES / "orders-spring7"
QUARKUS = FIXTURES / "orders-quarkus"
FLUENT_ADDRESS = FIXTURES / "orders-fluentaddress"
DISCOVERY = FIXTURES / "orders-discovery"
PATH_VARS = FIXTURES / "orders-pathvars"


@pytest.fixture(scope="module")
def path_var_rows(tmp_path_factory: pytest.TempPathFactory) -> set[tuple[str, str, str]]:
    """`(peer, path, resolution)` for every outbound row of `fixtures/orders-pathvars`."""
    workspace_dir = tmp_path_factory.mktemp("rest-pathvars")
    compile_fixture(PATH_VARS)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(PATH_VARS), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return {
            (str(row["peer"]), str(row["path"]), str(row["resolution"]))
            for row in workspace.query("endpoints")
            if str(row["direction"]) == "outbound"
        }
    finally:
        workspace.close()


@pytest.mark.pins("values.a-hole-is-NAMED-after-the-value-that-fills-it")
def test_a_path_segment_built_from_a_variable_names_that_variable(path_var_rows):
    """**The most ordinary outbound path there is**, and the hole in it now carries a name.

        restTemplate.getForObject("http://customers-service/owners/" + ownerId + "/pets", …)

    The walk assembles `http://customers-service/owners/{}/pets` and the facts name the
    operand — `signature.parameters[0].name == "ownerId"` — so the published path is
    `/owners/{ownerId}/pets`, which is how the SERVER states the same route
    (`@GetMapping("/owners/{ownerId}/pets")`). An anonymous `{}` said "something here" about
    a value the facts name, and two rows for the same endpoint could not be compared.

    **The third row's hole has no name to take.** `"?petId=" + join(petIds)` fills from a
    call's RESULT; inventing a name from the method would be naming a variable the code does
    not have. Its QUERY STRING is now lifted off the address (`OI-151`), so the row publishes
    `/pets/visits` — which is what `visits-service` serves — and the parameter is an
    `endpoint_metadata` entry beside it.

    **Which is why the first two rows read `resolved` and the third reads `partial`** (ruled
    by the user 2026-10-19). `resolved` means nothing about the destination went unread, and
    a NAMED hole is read — it is the route's own variable, the same text
    `customers-service` publishes for the same route from its own `@PostMapping`. An
    anonymous `{}` is a piece nobody read, and an unread authority is the other cause; the
    third row has the first, `apollo-portal`'s eight have the second.

    **Lifting the query does NOT promote that row, and the distinction is the hole
    convention's own.** `petId`'s value was not read, so the row keeps `partial` and the
    entry keeps `unresolved`. The row this shape mirrors on real code —
    `api-gateway`'s `.uri(hostname + "pets/visits?petId={petId}", …)` — reads `resolved`
    because `{petId}` is URI-template text the programmer WROTE, not a hole the walk left.
    Same published address, two different facts about the value, and the two words say which.

    The HOST is not named this way even when its operand has a name (`OI-152`): in the
    authority position what a reader needs is the peer's identity, which a local name does
    not give, so `<host>` stays `<host>`.
    """
    assert path_var_rows == {
        ("customers-service", "/owners/{ownerId}/pets", "resolved"),
        ("visits-service", "/owners/{ownerId}/pets/{petId}/visits", "resolved"),
        ("visits-service", "/pets/visits", "partial"),
    }


@pytest.fixture(scope="module")
def spring7_outbound(tmp_path_factory: pytest.TempPathFactory) -> set[tuple[str, str, str]]:
    workspace_dir = tmp_path_factory.mktemp("rest-out")
    compile_fixture(SPRING7)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(SPRING7), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return {
            (str(row["catalog_id"]), str(row["method"]), str(row["path"]))
            for row in workspace.query("endpoints")
            if str(row["direction"]) == "outbound"
        }
    finally:
        workspace.close()


def test_an_http_interface_registered_by_import_http_services_derives(spring7_outbound):
    """Spring 7's `@ImportHttpServices` registers `@HttpExchange` interfaces as proxied
    beans in one declaration, replacing the per-interface `HttpServiceProxyFactory`
    wiring of 6.x.

    MEASURED 2026-09-11: this derived before any catalog read the registration
    annotation, because the wire identity lives on the interface's own `@HttpExchange`
    and `spring-http-interface.yml` reads that with `declared_on: interface`. The gap
    COVERAGE stated — "registration unread" — implied missing rows; there were none. This
    test pins that the Spring 7 form keeps deriving, which is the claim that matters.
    """
    assert ("spring-http-interface", "GET", "/inventory/levels/{sku}") in spring7_outbound, (
        f"an @ImportHttpServices-registered interface stopped deriving. "
        f"Derived: {sorted(spring7_outbound)}"
    )


GATEWAY = FIXTURES / "orders-gateway"


@pytest.fixture(scope="module")
def gateway_rows(tmp_path_factory: pytest.TempPathFactory) -> list[dict]:
    """Every endpoint row the Spring Cloud Gateway fixture derives, whole."""
    workspace_dir = tmp_path_factory.mktemp("gateway-out")
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


def test_gateway_targets_derive_outbound(gateway_rows):
    """`spring-cloud-gateway-outbound`, spec §14 test 11: every `uri(…)` a route's lambda
    ends in, read through `lambda_steps` on both static receiver types (`BooleanSpec.uri`
    after a predicate, `UriSpec.uri` after `filters(…)`), kept WHOLE — a routing
    destination, not a request URL: `lb://orders-service` names a load-balanced service,
    and splitting it into a peer and a path would publish an address the gateway never
    dials. `peer` NULL on every row, no verb, caller = `routes`.

    `uri(billing)` reads `http://billing-service` at `resolved`: `billing` is a `final
    String` field with a literal initialiser — a constant variable (JLS §4.12.4) — so
    javac writes the literal itself at the call (`ldc`, measured on the compiled
    fixture), and the lambda still captures `this` for it. A field that is not a constant
    would arrive as a `field` read and the row would be `unresolved`; this pin moves the
    day the fixture's field stops being one.

    Exactly eight rows: one per `route(…)` call, both overloads — the eighth is `guarded`'s
    `uri("http://guarded-service")`, a route added for its inbound header/query
    requirements (spec 2026-09-19 §5c) whose target derives here like any other."""
    rows = [
        r
        for r in gateway_rows
        if r["catalog_id"] == "spring-cloud-gateway-outbound" and r["direction"] == "outbound"
    ]
    targets = {(r["path"], r["resolution"]) for r in rows}
    assert targets == {
        ("http://orders-service", "resolved"),
        ("lb://orders-service", "resolved"),
        ("http://ab-service", "resolved"),
        ("http://public-service", "resolved"),
        ("http://legacy-service", "resolved"),
        ("http://billing-service", "resolved"),
        ("http://host-service", "resolved"),
        ("http://guarded-service", "resolved"),
    }, sorted(targets, key=str)
    assert len(rows) == 8, sorted(targets, key=str)
    assert all(r["peer"] is None and r["method"] is None for r in rows), rows
    assert all("#routes(" in str(r["caller"]) for r in rows), sorted({r["caller"] for r in rows})


@pytest.fixture(scope="module")
def outbound_rows(analyzed_orders_service: Path) -> list[dict]:
    """Every outbound row of the session's one `orders-service` analysis, whole (the
    `tests/conftest.py` fixture — this only reads rows, it runs no analysis of its own)."""
    workspace = DuckDbWorkspace(analyzed_orders_service / "workspace.duckdb")
    try:
        return [dict(row) for row in workspace.query("endpoints") if row["direction"] == "outbound"]
    finally:
        workspace.close()


def test_the_jdk_http_client_derives_every_request_it_builds_and_sends(outbound_rows):
    """`jdk-httpclient`, spec §14 test 14: `JdkOrdersClient`'s four inline chains, each
    with the address read exactly. The POST is rooted on the argument-less `newBuilder()`
    and reads its address through `uri(URI.create(…))` — `url_via`, the same linked-call
    ladder `channel_via` follows; the PATCH is rooted on `newBuilder(URI.create(…))`, its
    verb read off `method("PATCH", …)`, its request handed to `sendAsync` — the second
    name of the terminal's `method` list; `fetchSeventh` is rooted on
    `newBuilder(new URI("…/7"))`, the `<init>` form of the ladder with `arity: 1` (fix
    round 1), `resolved`. The peer is split off the URL as every `fluent` row's is.

    **POST and PATCH are `unresolved`, and that is the pin, not a gap left open.** Each
    captures a `body` — `POST(BodyPublishers.ofString(body))`, `method("PATCH",
    …ofString(body))` — and a `BodyPublisher` is never a payload type the shape pass can
    read, so the capture is reached and unread and demotes the row (ruling I1,
    `_capture_resolved`). It is the exact answer `okhttp.yml` gives
    `post(RequestBody.create(…))` on this same fixture (`LegacyOkHttp.submitExport`,
    `unresolved`). A row saying "this method POSTs to `/v1/orders` with a body we could
    not read" is true; one saying `resolved` over a NULL `request_shape` would claim a
    read that never happened. Reading through `BodyPublishers.ofString(x)` to `x`'s type
    is its own item (`jdk-body-publisher`).

    `fetch`'s GET is `unresolved` with `path` NULL for a different reason: its address is
    `"…/v1/orders/" + id`, a `concat` the extractor records as a template with a hole,
    and `url_of` reads a `string` argument and nothing else — the documented rule
    (`shapes/arguments.py`, `_UNREAD_KINDS`' own note); the ladder reaches the
    constructor and finds that concat, and answers the same way a direct read would.

    `POST /v1/orders` is ALSO the Feign row `OrdersLoopClient#createOrder` derives, on
    purpose: an outbound row is per caller and peer (fix round 1, `insert_endpoints.sql`),
    and `test_an_outbound_path_two_engines_call_keeps_every_caller` pins both.

    `deleteRequest()`'s chain reaches `build()` in the helper and `send` is in
    `viaHelper()` — a request built in one method and sent in another. `fluent`'s stated
    rule (D02 §4, `okhttp.yml`: a built request is not an issued one) is that the chain
    never reaches a terminal and derives NOTHING; spec §13 case 9 records that the JDK
    client follows it. Asserted absent so the day the rule changes, this moves."""
    rows = {
        (r["method"], r["peer"], r["path"], r["resolution"])
        for r in outbound_rows
        if r["catalog_id"] == "jdk-httpclient"
    }
    assert rows == {
        ("POST", "orders.example.com", "/v1/orders", "unresolved"),
        ("GET", "orders.example.com", "/v1/orders/7", "resolved"),
        ("GET", None, None, "unresolved"),
        ("PATCH", "orders.example.com", "/v1/orders/42", "unresolved"),
    }, sorted(rows, key=str)
    assert all(
        r["request_shape"] is None for r in outbound_rows if r["catalog_id"] == "jdk-httpclient"
    )


def test_an_outbound_path_two_engines_call_keeps_every_caller(outbound_rows):
    """Fix round 1 (Major). `POST https://orders.example.com/v1/orders` is called by
    `OrdersLoopClient#createOrder` through Feign (`spring-cloud-openfeign`, annotation
    driven, peer `orders-loop`), by `JdkOrdersClient#create` (`jdk-httpclient`, a
    call-side `fluent` catalog, peer `orders.example.com`) and by
    `ApacheOrdersClient#create` (`apache-httpclient`, the constructor form). An outbound
    row is per caller and peer (F5 §6.1 rule 1), and all three stand. Measured before the fix: the
    annotation-driven turn compared wire identity alone, and the Feign row VANISHED the
    moment the JDK client called the same path — no row, no gap."""
    callers = {
        (r["catalog_id"], r["peer"], r["caller"].rsplit("/", 1)[1].partition("(")[0])
        for r in outbound_rows
        if r["method"] == "POST" and r["path"] == "/v1/orders"
    }
    assert callers == {
        ("spring-cloud-openfeign", "orders-loop", "OrdersLoopClient#createOrder"),
        ("jdk-httpclient", "orders.example.com", "JdkOrdersClient#create"),
        ("apache-httpclient", "orders.example.com", "ApacheOrdersClient#create"),
    }, sorted(callers, key=str)


def test_the_apache_client_derives_the_builder_and_the_constructor_forms(outbound_rows):
    """`apache-httpclient`, spec §12, both spellings of a classic request. The builder
    form — `ClassicRequestBuilder.get("…").build()` handed to `CloseableHttpClient.execute`
    — is `okhttp.yml`'s exact shape, the static root joined to the client through the
    argument `source` id. The constructor form — `new HttpPost("…")` and `new
    HttpGet(URI.create(…))` handed straight to `execute`, no `build()` between — is a
    `<init>` root that is itself the terminal: the join reads the constructed value's id
    (its `receiver`, CP-3; fix round 1 — reading the constructor's void `result` made both
    derive nothing). Every row `resolved`, the verb the factory's or the class's own name,
    the peer split off the URL; no `body` is captured on either form (an `HttpEntity` is a
    transport wrapper, not a wire type), so nothing demotes them."""
    rows = {
        (r["method"], r["peer"], r["path"], r["resolution"])
        for r in outbound_rows
        if r["catalog_id"] == "apache-httpclient"
    }
    assert rows == {
        ("GET", "orders.example.com", "/v1/orders", "resolved"),
        ("POST", "orders.example.com", "/v1/orders", "resolved"),
        ("GET", "orders.example.com", "/v1/orders/7", "resolved"),
    }, sorted(rows, key=str)


@pytest.fixture(scope="module")
def quarkus_endpoints(tmp_path_factory: pytest.TempPathFactory) -> list[dict]:
    """Every HTTP row the Quarkus fixture derives, analysed once. Own copy rather than an
    import from `test_rest_inbound_delivered.py`: that file is not a shared fixture
    module, so this one compiles and analyses the module itself, the `spring7` shape."""
    workspace_dir = tmp_path_factory.mktemp("quarkus-out")
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


def test_a_microprofile_rest_client_interface_derives_its_outbound_operations(quarkus_endpoints):
    """`mp-rest-client` (B/C Task 10b, spec §3f): `OrdersClient`'s two `@Path`-gated
    methods derive two outbound rows whose `peer` is `configKey` ("orders"), and
    `BillingClient`'s single method derives one whose `peer` is `baseUri`
    ("http://billing.internal/api") — CP-22 row 2's `peer_annotation` key, read off
    `@RegisterRestClient` rather than off `@Path`. The client interface mints no
    INBOUND row: `jakarta-jaxrs.yml`/`quarkus-rest.yml` both declare `declared_on:
    class`, so a `@Path`-carrying INTERFACE is invisible to them."""
    out = {
        (r["method"], r["path"], r["peer"])
        for r in quarkus_endpoints
        if r["direction"] == "outbound" and r["protocol"] == "http"
    }
    assert {
        ("GET", "/remote/orders", "orders"),
        ("GET", "/remote/orders/{id}", "orders"),
        ("GET", "/invoices", "http://billing.internal/api"),
    } <= out, sorted(out)
    assert not [
        r
        for r in quarkus_endpoints
        if r["direction"] == "inbound" and r["path"].startswith("/remote/orders")
    ]


@pytest.fixture(scope="module")
def discovery_rows(tmp_path_factory: pytest.TempPathFactory) -> set[tuple[str, str, str]]:
    """`(peer, path, resolution)` for every outbound row of `fixtures/orders-discovery`."""
    workspace_dir = tmp_path_factory.mktemp("rest-discovery")
    compile_fixture(DISCOVERY)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(DISCOVERY), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return {
            (str(row["peer"]), str(row["path"]), str(row["resolution"]))
            for row in workspace.query("endpoints")
            if str(row["direction"]) == "outbound"
        }
    finally:
        workspace.close()


@pytest.mark.pins("arguments.a-PEER-is-asked-of-its-own-evidence")
def test_a_peer_resolved_through_service_discovery_names_the_service(discovery_rows):
    """`OI-138` cause 3, and `OI-142`'s ruling 2 finally landing.

        discoveryClient.getInstances("customers-service").get(0).getUri() + "/owners"

    Nothing in that class file is an address — the host comes from a registry while the
    program runs — and the one thing the code states is the service NAME, three calls back
    from the position the catalog asks about, with javac's `String.valueOf` inserted around
    the `URI` operand.

    **Measured before: `<host>/owners` with no peer.** The path was read and the peer was
    not, so the document knew this module called SOMETHING at `/owners`.

    **The peer is asked as its own question**, of the first operand alone, accepting only an
    answer that yields an AUTHORITY — which is what makes it sound where a join would not be.
    `OI-142` recorded the reason: an identity's TEXT is not an address (for a destination
    identified as `"orders"`, `toString()` is a vendor debug string), while an identity's
    AUTHORITY is a peer. So the path keeps coming from a walk handed no identities at all,
    and the peer comes from the identity table.

    On real code this is the whole point: `spring-petclinic-customers-service` serves
    `/owners` and `/owners/{ownerId}/pets`, so these rows now match the callee's own inbound
    rows and the document carries the arrow.
    """
    assert discovery_rows == {
        ("customers-service", "/owners", "resolved"),
        ("customers-service", "/owners/{ownerId}/pets", "resolved"),
        ("None", "<host>/orders", "partial"),
    }


@pytest.mark.pins(
    "arguments.a-PEER-is-refused-where-ANY-path-did-not-answer-one",
    "values.a-path-a-RENDERING-cannot-carry-is-replaced-never-dropped",
)
def test_a_host_another_caller_supplies_refuses_the_peer(discovery_rows):
    """The third row of the same fixture, and the bound on the one above it.

        private String fetch(URI host) {
            return restTemplate.getForObject(host + "/orders", String.class);
        }
        fetch(discoveryClient.getInstances("customers-service").get(0).getUri());
        fetch(supplied);                                   // a URI this module was HANDED

    The concat is in `fetch`, and `fetch` is two calling contexts — so its first operand
    answers on two paths, one naming `customers-service` and one reading nothing at all. A
    peer column states who is called, not who is called sometimes, so this row keeps
    `<host>/orders` with no peer: exactly what it said before any of this work.

    **Measured as a false fact before the refusal existed:** peer `customers-service`, and
    at `resolved` once a named peer stopped meaning `partial`. Two layers each lost one of
    the two paths — the `preserves` filter DROPPED the pair it could not carry instead of
    replacing it, and the peer question then asked only the answers that survived, so
    "several peers for one call is not a peer" was never reached. A field with two writers
    and a two-branch helper are the same defect by two other routes, both measured.
    """
    assert ("None", "<host>/orders", "partial") in discovery_rows
    assert not [row for row in discovery_rows if row[1].endswith("/orders") and row[0] != "None"]


@pytest.fixture(scope="module")
def fluent_address_rows(tmp_path_factory: pytest.TempPathFactory) -> set[tuple[str, str, str]]:
    """`(peer, path, resolution)` for every outbound row of `fixtures/orders-fluentaddress`."""
    workspace_dir = tmp_path_factory.mktemp("rest-fluentaddress")
    compile_fixture(FLUENT_ADDRESS)
    result = CliRunner().invoke(
        cli, ["module", "analyze", str(FLUENT_ADDRESS), "--workspace", str(workspace_dir)]
    )
    assert result.exit_code == 0, result.output
    workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
    try:
        return {
            (str(row["peer"]), str(row["path"]), str(row["resolution"]))
            for row in workspace.query("endpoints")
            if str(row["direction"]) == "outbound"
        }
    finally:
        workspace.close()


@pytest.fixture(scope="module")
def query_entry_rows(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[str, set[tuple[str, str, str, str, str]]]:
    """`endpoint_metadata` query entries and outbound addresses, per ENGINE.

    Two fixtures because the two engines mint their rows in different files and `OI-151`
    had to be answered in both — `orders-fluentaddress`'s `WebClient` chain is `fluent`,
    `orders-pathvars`' `RestTemplate` call is `single_call`.
    """
    out: dict[str, set[tuple[str, str, str, str, str]]] = {}
    for engine, fixture in (("fluent", FLUENT_ADDRESS), ("single_call", PATH_VARS)):
        workspace_dir = tmp_path_factory.mktemp(f"rest-query-{engine}")
        compile_fixture(fixture)
        result = CliRunner().invoke(
            cli, ["module", "analyze", str(fixture), "--workspace", str(workspace_dir)]
        )
        assert result.exit_code == 0, result.output
        workspace = DuckDbWorkspace(workspace_dir / "workspace.duckdb")
        try:
            out[engine] = {
                (
                    str(row["direction"]),
                    str(row["path"]),
                    str(row["kind"]),
                    str(row["name"]),
                    str(row["resolution"]),
                )
                for row in workspace.query("endpoint_metadata")
            }
            out[f"{engine}:value"] = {
                (str(row["name"]), str(row["value"]), "", "", "")
                for row in workspace.query("endpoint_metadata")
            }
        finally:
            workspace.close()
    return out


@pytest.mark.pins("arguments.a-QUERY-STRING-is-not-part-of-the-address")
def test_a_query_string_leaves_the_address_and_becomes_an_entry(query_entry_rows):
    """`OI-151`, in BOTH engines — the two sides of one call recorded the same contract two
    different ways.

        @GetMapping("pets/visits")                              // visits-service serves
        public Visits read(@RequestParam("petId") List<Integer> petIds)

        .uri(hostname + "pets/visits?petId={petId}", joinIds(petIds))   // api-gateway calls

    Nothing is wrong at runtime: that is the same contract from both ends. What disagreed is
    how it was RECORDED. The server published `path` `/pets/visits` with the parameter as an
    `endpoint_metadata` row; the client published `/pets/visits?petId={petId}` and no entry
    at all, so the two rows could not be compared on the address — the linking tier (`GAP-2`)
    would miss a link that is exact in the code, and a reader diffing the columns saw a
    mismatch that is not one.

    **`kind` is `query`, not `param`, and that is read rather than chosen.** The vaguer word
    has a stated rule — "`param` only for the two APIs that cannot tell the query string from
    a form body" (`@RequestParam`, `params=`, the Servlet's `getParameter`) — and an outbound
    URI template is not one of them. A client's `query` SATISFIES a server's `param`; that is
    a matching rule for `M06`, not a reason to write the looser word.

    **A value is read or it is not.** `page=2` is a literal at `resolved`; `petId`'s value is
    a runtime value at `unresolved`, because *this call sends a `petId` parameter whose value
    we could not read* is a different statement from *it sends none*. `requirement` is NULL
    throughout — an entry a call SENDS enforces nothing.
    """
    for engine in ("fluent", "single_call"):
        assert ("outbound", "/pets/visits", "query", "petId", "unresolved") in query_entry_rows[
            engine
        ], engine
        assert not [row for row in query_entry_rows[engine] if "?" in row[1]], (
            f"{engine} left a query on an address"
        )
    assert ("outbound", "/pets/visits", "query", "page", "resolved") in query_entry_rows["fluent"]


@pytest.mark.pins("arguments.a-QUERY-parameters-value-is-masked-by-its-own-name")
def test_a_credential_in_a_query_string_is_masked_at_the_origin(query_entry_rows):
    """`schema.sql`'s `value` column: a metadata value is masked AT THE ORIGIN, because
    nothing downstream masks one and `endpoint_metadata` is exported whole.

        .uri("http://visits-service/pets/visits?petId=" + petId + "&page=2&token=sk-live-xyz")

    `?access_token=…` is an ordinary way to write an outbound call, and `OI-151` made both
    engines writers of this table — `single_call` for the first time, which is why it grew a
    redactor of its own rather than borrowing a shared row builder that would have masked on
    nobody's behalf.

    The redactor keys on the parameter's OWN name, which is the shape it was built for:
    `token` is a built-in key pattern, `page` is not.
    """
    for engine in ("fluent", "single_call"):
        values = query_entry_rows[f"{engine}:value"]
        assert ("token", REDACTED, "", "", "") in values, engine
    assert ("page", "2", "", "", "") in query_entry_rows["fluent:value"]


@pytest.mark.pins("fluent.an-assembled-address-is-read-with-the-URL-reader")
def test_both_engines_give_one_answer_for_one_assembled_address(fluent_address_rows):
    """`OI-144`. One address, written once each way:

        restTemplate.getForObject(base + "/owners", String.class);          // single_call
        builder.build().get().uri(base + "/owners")…                        // fluent

    **Measured before the fix: `single_call` published `<host>/owners` at `partial` and
    `fluent` published `path` NULL at `unresolved`** — two engines, two answers about one
    piece of evidence, which is the disease the shared walk was built to end.

    The cause was the READER, not the walk. `fluent`'s assembled-address arm asked
    `channel_of_answer`, which refuses a template on purpose — a broker resolves a
    destination it is GIVEN and half of one is not a destination — where an HTTP address has
    `url_of_answer` for exactly this case. So the fluent row is now the same row, and the
    whole-literal chain beside it is untouched.
    """
    assert fluent_address_rows == {
        ("None", "<host>/owners", "partial"),
        ("vets-service", "/vets", "resolved"),
        ("visits-service", "/pets/visits", "resolved"),
    }
