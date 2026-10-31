"""Vert.x WebClient calls (`vertx-webclient.yml`, the `fluent` style; spec 2026-10-30 §3d).

The facts below are shaped as CP-56 row group (h) records javac's output for a WebClient
call (`scripts/probes/cp56_vertx_web.md`, rows 317-322): every call `invokeinterface` on
`WebClient` or `HttpRequest`, the root's result the receiver of the next call, a port an
`int` literal, a statement-style request's later calls made on the stored request with their
results dropped (row 322).
"""

from pathlib import Path

import pytest
from test_call_engines import _MODULE, CATALOGS_DIR, _resolve_fluent, _resolve_fluent_walked

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.domain.facts import (
    CallArgument,
    CallSiteFact,
    CallTarget,
    MethodReturnFact,
    SymbolFact,
)
from sextant.domain.symbols import method_descriptor
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource

CLIENT = "io/vertx/ext/web/client/WebClient#"
REQUEST = "io/vertx/ext/web/client/HttpRequest#"
TEMPLATE = "io/vertx/uritemplate/UriTemplate#"
HTTP_METHOD = "io/vertx/core/http/HttpMethod#"
CALLER = _MODULE + "com/acme/vertx/InventoryClient#call()Lio/vertx/core/Future;."

_RETURNS = "Lio/vertx/ext/web/client/HttpRequest;"
_URI = f"(Ljava/lang/String;){_RETURNS}"
_HOST_URI = f"(Ljava/lang/String;Ljava/lang/String;){_RETURNS}"
_PORT_HOST_URI = f"(ILjava/lang/String;Ljava/lang/String;){_RETURNS}"
_SOCKET_URI = f"(Lio/vertx/core/http/HttpMethod;Lio/vertx/core/net/SocketAddress;Ljava/lang/String;){_RETURNS}"
_OPTIONS = f"(Lio/vertx/core/http/HttpMethod;Lio/vertx/core/http/RequestOptions;){_RETURNS}"
_INVENTORY = "com/acme/vertx/InventoryClient#"
_SOCKET_HOST_URI = (
    "(Lio/vertx/core/http/HttpMethod;Lio/vertx/core/net/SocketAddress;Ljava/lang/String;"
    f"Ljava/lang/String;){_RETURNS}"
)
_STRING_STRING = f"(Ljava/lang/String;Ljava/lang/String;){_RETURNS}"
_SEND = "()Lio/vertx/core/Future;"


def _vertx_webclient() -> Catalog:
    return next(c for c in YamlCatalogSource(CATALOGS_DIR).load() if c.id == "vertx-webclient")


def _string(value: str) -> CallArgument:
    return CallArgument(kind="string", value=value)


def _int(value: int) -> CallArgument:
    return CallArgument(kind="int", value=value)


class _Body:
    """One method body's call sites, numbered as the extractor numbers them: ordinals in
    order, each call's result a fresh value id."""

    def __init__(self, caller: str = CALLER) -> None:
        self.caller = caller
        self.sites: list[CallSiteFact] = []
        self._next_value = 100

    def call(
        self,
        owner: str,
        name: str,
        descriptor: str,
        receiver: int | None,
        arguments: list[CallArgument],
        invoke_kind: str = "interface",
    ) -> int:
        self._next_value += 1
        self.sites.append(
            CallSiteFact(
                document_id="doc_1",
                caller=self.caller,
                target=CallTarget(owner=owner, name=name, descriptor=descriptor),
                invoke_kind=invoke_kind,
                ordinal=len(self.sites),
                receiver=receiver,
                result=self._next_value,
                arguments=arguments,
            )
        )
        return self._next_value

    def chain(self, root: tuple[str, str, list[CallArgument]], *steps: tuple) -> int:
        """`client.<root>(…).<step>(…)…` on one operand stack (row 317)."""
        value = self.call(CLIENT, root[0], root[1], 90, root[2])
        for name, descriptor, arguments in steps:
            value = self.call(REQUEST, name, descriptor, value, arguments)
        return value


def _send() -> tuple[str, str, list[CallArgument]]:
    return ("send", _SEND, [])


def _rows(tmp_path: Path, body: _Body) -> list[dict]:
    workspace = _resolve_fluent(tmp_path, body.sites, _vertx_webclient())
    rows = [dict(row) for row in workspace.query("endpoints")]
    workspace.close()
    return rows


def _calls(rows: list[dict]) -> list[tuple]:
    return sorted(
        ((r["method"], r["peer"], r["path"], r["resolution"]) for r in rows),
        key=str,
    )


@pytest.mark.pins("fluent.host-and-port-compose-one-peer")
def test_parts_and_absolute_forms_give_one_peer(tmp_path: Path):
    """`client.get(8080, "inventory", "/stock")` and `client.getAbs("http://inventory:8080/
    stock")` are one call, so they have one peer: `inventory:8080`, the authority CP-2 splits
    the absolute URL into. `client.get("inventory", "/stock")` names no port, so its peer is
    the host alone (the client's default port is not read here, spec §2a)."""
    body = _Body()
    body.chain(
        ("get", _PORT_HOST_URI, [_int(8080), _string("inventory"), _string("/stock")]), _send()
    )
    body.chain(("getAbs", _URI, [_string("http://inventory:8080/stock")]), _send())
    body.chain(("post", _HOST_URI, [_string("inventory"), _string("/stock")]), _send())

    assert _calls(_rows(tmp_path, body)) == [
        ("GET", "inventory:8080", "/stock", "resolved"),
        ("POST", "inventory", "/stock", "resolved"),
    ]


@pytest.mark.pins("fluent.a-stated-host-or-port-replaces-the-urls-own")
def test_a_host_or_port_step_replaces_that_part_of_an_absolute_urls_authority(tmp_path: Path):
    """Vert.x applies a request's own `host` and `port` at send time over what an absolute URL
    parsed (CP-56 rows 129-130), each part on its own: `getAbs("http://a:1/x").host("b")` goes
    to `b:1`, `getAbs("http://a/y").port(9)` to `a:9`."""
    body = _Body()
    body.chain(("getAbs", _URI, [_string("http://a:1/x")]), ("host", _URI, [_string("b")]), _send())
    body.chain(
        ("postAbs", _URI, [_string("http://a/y")]),
        ("port", f"(I){_RETURNS}", [_int(9)]),
        _send(),
    )

    assert _calls(_rows(tmp_path, body)) == [
        ("GET", "b:1", "/x", "resolved"),
        ("POST", "a:9", "/y", "resolved"),
    ]


def test_a_port_on_a_request_naming_no_host_publishes_no_peer(tmp_path: Path):
    """`client.get("/x").port(9)`: the host is the client's default, which is not read here,
    and a port is not a peer (spec §2a: an unset default is never published)."""
    body = _Body()
    body.chain(("get", _URI, [_string("/x")]), ("port", f"(I){_RETURNS}", [_int(9)]), _send())

    assert _calls(_rows(tmp_path, body)) == [("GET", None, "/x", "resolved")]


@pytest.mark.pins("fluent.an-unread-host-leaves-the-peer-unread")
def test_an_unread_host_leaves_the_peer_unread_and_keeps_the_path(tmp_path: Path):
    """`client.get(8080, host, "/x")` with `host` a value nothing here reads: who is called
    went unread, so the peer is NULL and the row `partial`; the path is its own evidence and
    stays (the user's ruling of 2026-10-17, "peer and path from separate evidence")."""
    body = _Body()
    body.chain(
        ("get", _PORT_HOST_URI, [_int(8080), CallArgument(kind="unresolved"), _string("/x")]),
        _send(),
    )

    assert _calls(_rows(tmp_path, body)) == [("GET", None, "/x", "partial")]


@pytest.mark.pins("vertx-webclient.a-uri-template-is-read-off-its-factory")
def test_a_uri_template_form_reads_its_template_off_the_factory(tmp_path: Path):
    """`client.get(8080, "inventory", UriTemplate.of("/stock/{sku}"))`: the template is read
    off `UriTemplate.of`'s argument, its `{sku}` hole a hole."""
    body = _Body()
    template = body.call(
        TEMPLATE,
        "of",
        "(Ljava/lang/String;)Lio/vertx/uritemplate/UriTemplate;",
        None,
        [_string("/stock/{sku}")],
        invoke_kind="static",
    )
    body.chain(
        (
            "get",
            f"(ILjava/lang/String;Lio/vertx/uritemplate/UriTemplate;){_RETURNS}",
            [_int(8080), _string("inventory"), CallArgument(kind="unresolved", source=template)],
        ),
        _send(),
    )

    assert _calls(_rows(tmp_path, body)) == [("GET", "inventory:8080", "/stock/{sku}", "resolved")]


@pytest.mark.pins("vertx-webclient.a-socket-address-form-reads-its-uri")
def test_a_socket_address_form_reads_its_uri_as_the_path_with_no_peer(tmp_path: Path):
    """`client.request(GET, address, "/x").send()` and `client.request(POST, address,
    "inventory", "/y").send()`: the server address is not read, so neither row has a peer, and
    the uri string is the path, read as any uri is (coordinator ruling 2026-10-31, item 1)."""
    body = _Body()
    socket = CallArgument(kind="unresolved")
    body.chain(
        (
            "request",
            _SOCKET_URI,
            [CallArgument(kind="enum", symbol=f"{HTTP_METHOD}GET."), socket, _string("/x")],
        ),
        _send(),
    )
    body.chain(
        (
            "request",
            _SOCKET_HOST_URI,
            [
                CallArgument(kind="enum", symbol=f"{HTTP_METHOD}POST."),
                socket,
                _string("inventory"),
                _string("/y"),
            ],
        ),
        _send(),
    )

    assert _calls(_rows(tmp_path, body)) == [
        ("GET", None, "/x", "resolved"),
        ("POST", None, "/y", "resolved"),
    ]


@pytest.mark.pins("vertx-webclient.a-uri-step-names-an-address")
def test_a_request_options_form_derives_nothing_until_a_uri_names_an_address(tmp_path: Path):
    """`client.request(GET, options).send()` names an address this catalog does not read (the
    options object is Task 13's), so it is no row; a later `uri("/y")` names one (spec §3d)."""
    body = _Body()
    verb = CallArgument(kind="enum", symbol=f"{HTTP_METHOD}GET.")
    options = CallArgument(kind="unresolved")
    body.chain(("request", _OPTIONS, [verb, options]), _send())
    body.chain(("request", _OPTIONS, [verb, options]), ("uri", _URI, [_string("/y")]), _send())

    assert _calls(_rows(tmp_path, body)) == [("GET", None, "/y", "resolved")]


@pytest.mark.pins("fluent.a-host-or-port-is-traced-as-the-url-is")
def test_a_host_handed_in_as_a_parameter_is_the_literal_its_callers_pass(tmp_path: Path):
    """`stock(host)` does `client.get(8080, host, "/stock").send()`, and its one caller passes
    `"inventory"`: the host is traced to its source as the `url` is, so the peer is
    `inventory:8080` (coordinator ruling 2026-10-31, item 4)."""
    jvm = "(Ljava/lang/String;)Lio/vertx/core/Future;"
    stock = _MODULE + method_descriptor(_INVENTORY, "stock", jvm)
    run = _MODULE + method_descriptor(_INVENTORY, "run", "()V")
    body = _Body(stock)
    body.chain(
        (
            "get",
            _PORT_HOST_URI,
            [_int(8080), CallArgument(kind="parameter", value=0), _string("/stock")],
        ),
        _send(),
    )
    facts = [
        *body.sites,
        SymbolFact(document_id="doc_1", symbol=_MODULE + _INVENTORY, construct_kind="class"),
        *(
            SymbolFact(
                document_id="doc_1",
                symbol=symbol,
                construct_kind="method",
                enclosing=_MODULE + _INVENTORY,
            )
            for symbol in (stock, run)
        ),
        # A body was read for `stock`, so the call from `run` reaches it.
        MethodReturnFact(document_id="doc_1", method=stock, ordinal=2),
        CallSiteFact(
            document_id="doc_1",
            caller=run,
            target=CallTarget(owner=_INVENTORY, name="stock", descriptor=jvm),
            invoke_kind="virtual",
            ordinal=0,
            receiver=None,
            result=None,
            arguments=[_string("inventory")],
        ),
    ]
    workspace = _resolve_fluent_walked(tmp_path, facts, _vertx_webclient())
    rows = [dict(row) for row in workspace.query("endpoints")]
    workspace.close()

    assert _calls(rows) == [("GET", "inventory:8080", "/stock", "resolved")]


@pytest.mark.pins("fluent.a-configured-host-is-its-key")
def test_a_host_that_reaches_a_config_key_publishes_the_key_as_the_peer(tmp_path: Path):
    """A host whose trace ends at a configuration key (`${search.host}`, as the field ladder
    renders one) is that key: the peer is `${search.host}:9200` and the path stays `/q`, never
    `//${search.host}:9200/q` (coordinator ruling 2026-10-31, item 5)."""
    body = _Body()
    body.chain(
        ("get", _PORT_HOST_URI, [_int(9200), _string("${search.host}"), _string("/q")]), _send()
    )

    assert _calls(_rows(tmp_path, body)) == [("GET", "${search.host}:9200", "/q", "resolved")]


@pytest.mark.pins("fluent.an-unread-first-piece-behind-a-stated-host-is-a-hole")
def test_an_unread_first_uri_piece_behind_a_stated_host_is_a_hole_in_the_path(tmp_path: Path):
    """`client.get(8080, "inventory", prefix + "/x")` with `prefix` unread: the reader writes a
    leading unread piece as `<host>`, but the host is stated, so the peer is `inventory:8080`
    and the piece is the hole a known authority's unread path piece is (`/{}/x` behind
    `http://h`), the row `partial` (coordinator ruling 2026-10-31, item 5)."""
    body = _Body()
    joined = body.call(
        "java/lang/invoke/StringConcatFactory#",
        "makeConcatWithConstants",
        "(Ljava/lang/String;)Ljava/lang/String;",
        None,
        [CallArgument(kind="unresolved")],
        invoke_kind="static",
    )
    body.chain(
        (
            "get",
            _PORT_HOST_URI,
            [
                _int(8080),
                _string("inventory"),
                CallArgument(kind="concat", source=joined, value="{}/x"),
            ],
        ),
        _send(),
    )

    assert _calls(_rows(tmp_path, body)) == [("GET", "inventory:8080", "{}/x", "partial")]


def test_headers_and_query_parameters_are_collected(tmp_path: Path):
    """`putHeader` and `addQueryParam`/`setQueryParam` accumulate, one entry per call, as
    `spring-webclient.yml`'s `header` and `queryParam` do."""
    body = _Body()
    body.chain(
        ("getAbs", _URI, [_string("http://search/q")]),
        ("putHeader", _STRING_STRING, [_string("X-Tenant"), _string("acme")]),
        ("addQueryParam", _STRING_STRING, [_string("q"), _string("shoes")]),
        ("setQueryParam", _STRING_STRING, [_string("page"), _string("2")]),
        _send(),
    )
    workspace = _resolve_fluent(tmp_path, body.sites, _vertx_webclient())
    entries = sorted(
        (r["kind"], r["name"], r["value"]) for r in workspace.query("endpoint_metadata")
    )
    workspace.close()

    assert entries == [
        ("header", "X-Tenant", "acme"),
        ("query", "page", "2"),
        ("query", "q", "shoes"),
    ]


def test_a_statement_style_request_through_self_returning_calls_is_one_row(tmp_path: Path):
    """Row 322: `r = client.post(q); r.addQueryParam(…); r.timeout(…); r.basicAuthentication(…);
    r.as(…).send()` — each call made on the stored request, its result dropped. One row."""
    body = _Body()
    request = body.call(CLIENT, "postAbs", _URI, 90, [_string("http://prometheus:9090/q")])
    body.call(REQUEST, "addQueryParam", _STRING_STRING, request, [_string("a"), _string("b")])
    body.call(REQUEST, "timeout", f"(J){_RETURNS}", request, [CallArgument(kind="long", value=5)])
    body.call(REQUEST, "basicAuthentication", _STRING_STRING, request, [_string("u"), _string("p")])
    typed = body.call(
        REQUEST,
        "as",
        f"(Lio/vertx/ext/web/codec/BodyCodec;){_RETURNS}",
        request,
        [CallArgument(kind="unresolved")],
    )
    body.call(REQUEST, "send", _SEND, typed, [])

    assert _calls(_rows(tmp_path, body)) == [("POST", "prometheus:9090", "/q", "resolved")]


@pytest.mark.declines("vertx-webclient")
@pytest.mark.pins("fluent.no-terminal-no-row")
def test_a_request_never_sent_derives_nothing(tmp_path: Path):
    """§10 near-miss for the TERMINAL conjunct: the root, its descriptor, a literal address
    and a self-returning step all hold, and the request is never sent."""
    body = _Body()
    body.chain(
        ("get", _PORT_HOST_URI, [_int(8080), _string("inventory"), _string("/stock")]),
        ("putHeader", _STRING_STRING, [_string("X-Tenant"), _string("acme")]),
    )

    assert _rows(tmp_path, body) == []


@pytest.mark.declines("vertx-webclient")
@pytest.mark.pins("fluent.root-owner-is-the-declared-type")
def test_a_call_on_an_applications_own_client_type_derives_nothing(tmp_path: Path):
    """§10 near-miss for the ROOT OWNER conjunct: the method name, its descriptor, a literal
    address and a real `send()` on `HttpRequest` all hold; only the type the chain roots on is
    the application's own, which this catalog never read."""
    body = _Body()
    value = body.call("com/acme/vertx/OwnClient#", "get", _URI, 90, [_string("http://a/x")])
    body.call(REQUEST, "send", _SEND, value, [])

    assert _rows(tmp_path, body) == []


@pytest.mark.parametrize("field", ["host", "port"])
@pytest.mark.pins("chains.host-and-port-are-call-site-positions")
def test_a_host_or_port_capture_that_is_not_a_position_is_refused(tmp_path: Path, field: str):
    """`host` and `port` read an argument, always: `host: inventory` would capture nothing
    and publish a row with no peer, indistinguishable from a call naming none."""
    catalog = _vertx_webclient()
    steps = [
        {**step, "captures": {field: "inventory"}} if step["method"] == field else step
        for step in catalog.matches["steps"]
    ]
    broken = Catalog(
        id=catalog.id,
        style=catalog.style,
        protocol=catalog.protocol,
        direction=catalog.direction,
        requires=catalog.requires,
        matches={**catalog.matches, "steps": steps},
        source=catalog.source,
        value_model=catalog.value_model,
    )
    with pytest.raises(CatalogError, match=f"`{field}: inventory`.*not a call-site position"):
        _resolve_fluent(tmp_path, [], broken)


def test_the_catalog_flags_every_self_returning_request_method_and_nothing_else():
    """Every `HttpRequest` step is a method CP-56 row 111 lists the INTERFACE declaring to
    return `HttpRequest` and answering with its receiver, at some measured version (28 at
    4.5.10, 27 at 5.0.0, 29 at 5.2.1, counted by overload; by name the union below), each
    flagged `returns_receiver`; `copy()` (answered with a new request) is not one. The other
    steps are the body-carrying terminals, which send rather than return the request."""
    row_111 = {
        "addQueryParam", "as", "authentication", "connectTimeout", "expect", "followRedirects",
        "host", "idleTimeout", "method", "multipartMixed", "port", "proxy", "putHeader",
        "putHeaders", "routingKey", "setQueryParam", "setTemplateParam", "ssl", "timeout",
        "traceOperation", "uri", "virtualHost", "basicAuthentication",
        "bearerTokenAuthentication",
    }  # fmt: skip
    steps = _vertx_webclient().matches["steps"]
    flagged = {s["method"] for s in steps if s.get("returns_receiver") is True}
    unflagged = {s["method"] for s in steps if s.get("returns_receiver") is not True}

    assert flagged == row_111
    assert unflagged == {"sendJson", "sendJsonObject", "sendBuffer"}
    assert {s["owner"] for s in steps} == {"io.vertx.ext.web.client.HttpRequest"}
    # CP-56 rows 304-323 print some owners with a stray `;`; none is copied here.
    assert all(not str(step["owner"]).endswith(";") for step in steps)
