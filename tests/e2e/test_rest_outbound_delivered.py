"""REST outbound is delivered when every way a Spring Boot module calls an HTTP endpoint is
visible. Each test names the shape.

**Not a document check.** Real bytecode, real pipeline, assertion on derived endpoints.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

from fixture_build import FIXTURES, compile_fixture
from sextant.cli.app import cli
from sextant.storage.duckdb.workspace import DuckDbWorkspace

SPRING7 = FIXTURES / "orders-spring7"


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

    Exactly seven rows: one per `route(…)` call, both overloads."""
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
    }, sorted(targets, key=str)
    assert len(rows) == 7, sorted(targets, key=str)
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
    """`jdk-httpclient`, spec §14 test 14: `JdkOrdersClient`'s three inline chains, each
    with the address read exactly. The POST is rooted on the argument-less `newBuilder()`
    and reads its address through `uri(URI.create(…))` — `url_via`, the same linked-call
    ladder `channel_via` follows; the PATCH is rooted on `newBuilder(URI.create(…))`, its
    verb read off `method("PATCH", …)`, its request handed to `sendAsync` — the second
    name of the terminal's `method` list. The peer is split off the URL as every `fluent`
    row's is.

    **Both are `unresolved`, and that is the pin, not a gap left open.** Each captures a
    `body` — `POST(BodyPublishers.ofString(body))`, `method("PATCH", …ofString(body))` —
    and a `BodyPublisher` is never a payload type the shape pass can read, so the capture
    is reached and unread and demotes the row (ruling I1, `_capture_resolved`). It is the
    exact answer `okhttp.yml` gives `post(RequestBody.create(…))` on this same fixture
    (`LegacyOkHttp.submitExport`, `unresolved`). A row saying "this method POSTs to
    `/v1/dispatches` with a body we could not read" is true; one saying `resolved` over a
    NULL `request_shape` would claim a read that never happened. Reading through
    `BodyPublishers.ofString(x)` to `x`'s type is its own item.

    The GET is `unresolved` with `path` NULL for a different reason: its address is
    `"…/v1/dispatches/" + id`, a `concat` the extractor records as a template with a hole,
    and `url_of` reads a `string` argument and nothing else — the documented rule
    (`shapes/arguments.py`, `_UNREAD_KINDS`' own note). `new URI(…)` is not a `url_via`
    form (the catalog states why: the multi-argument constructors), so the argument is
    read directly, and a direct read of a constructed instance is the same NULL.

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
        ("POST", "dispatch.example.com", "/v1/dispatches", "unresolved"),
        ("GET", None, None, "unresolved"),
        ("PATCH", "dispatch.example.com", "/v1/dispatches/42", "unresolved"),
    }, sorted(rows, key=str)
    assert all(
        r["request_shape"] is None for r in outbound_rows if r["catalog_id"] == "jdk-httpclient"
    )


def test_the_apache_client_derives_the_builder_form_handed_to_execute(outbound_rows):
    """`apache-httpclient`, spec §12: `ClassicRequestBuilder.get("…").build()` handed to
    `CloseableHttpClient.execute` — `okhttp.yml`'s exact shape, the static root joined to
    the client through the argument `source` id — `resolved`, the verb the factory's own
    name, the peer split off the URL. No `body` is captured on this form (an `HttpEntity`
    is a transport wrapper, not a wire type), so nothing demotes it."""
    rows = {
        (r["method"], r["peer"], r["path"], r["resolution"])
        for r in outbound_rows
        if r["catalog_id"] == "apache-httpclient"
    }
    assert ("GET", "dispatch.example.com", "/v1/dispatches", "resolved") in rows, sorted(
        rows, key=str
    )


def test_the_apache_constructor_form_derives_nothing_until_the_join_reads_a_constructor(
    outbound_rows,
):
    """`apache-httpclient-constructors`, the stated boundary (spec §12 named the form; A2
    Task 8 measured it). `new HttpPost("…/v1/dispatches")` and `new HttpGet(URI.create(…))`
    handed straight to `execute`, no `build()` between: a `<init>` root that is itself
    the value `execute` consumes. `_walk` checks the root site against `terminal`, but
    the execute-join reads the root's `result`, and a constructor's result is void
    (CP-3) — the constructed value's id is its `receiver` — so the join never sees it and
    the chain derives NOTHING. Measured on the compiled fixture: `execute`'s argument is
    `{kind: instance, source: 2}` and `HttpPost.<init>` has `receiver: 2, result: null`.

    Pinned as ABSENT rather than approximated, so the two rows appear here the day the
    join reads a constructor's chain key, and the catalog's `terminal` gains the form."""
    rows = {
        (r["method"], r["path"]) for r in outbound_rows if r["catalog_id"] == "apache-httpclient"
    }
    assert ("POST", "/v1/dispatches") not in rows, sorted(rows, key=str)
    assert ("GET", "/v1/dispatches/7") not in rows, sorted(rows, key=str)
