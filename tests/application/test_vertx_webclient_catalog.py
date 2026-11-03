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

from flow_facts import straight_line
from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.resolve.shapes.chains import chain_ends
from sextant.domain.facts import (
    CallArgument,
    CallSiteFact,
    CallTarget,
    FieldWriteFact,
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


def _replaced(catalog: Catalog, **matches: object) -> Catalog:
    """`catalog` with some of its `matches` replaced."""
    return Catalog(
        id=catalog.id,
        style=catalog.style,
        protocol=catalog.protocol,
        direction=catalog.direction,
        requires=catalog.requires,
        matches={**catalog.matches, **matches},
        source=catalog.source,
        value_model=catalog.value_model,
    )


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
    workspace = _resolve_fluent(tmp_path, straight_line(body.sites), _vertx_webclient())
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


@pytest.mark.pins("fluent.an-unread-destination-names-no-peer")
@pytest.mark.pins("vertx-webclient.a-socket-address-form-names-no-peer")
def test_a_socket_address_request_names_no_peer_whatever_its_url_or_host_steps_say(
    tmp_path: Path,
):
    """The request goes to the `SocketAddress` (CP-56 rows 325-326), which is not read:
    `requestAbs(POST, address, "http://billing/charges")` has no peer and the path `/charges`;
    `request(GET, address, "/x").host("b")` has no peer either — the URL's authority and the
    host step name the request's `Host`, not where it is sent."""
    body = _Body()
    socket = CallArgument(kind="unresolved")
    body.chain(
        (
            "requestAbs",
            _SOCKET_URI,
            [
                CallArgument(kind="enum", symbol=f"{HTTP_METHOD}POST."),
                socket,
                _string("http://billing/charges"),
            ],
        ),
        _send(),
    )
    body.chain(
        (
            "request",
            _SOCKET_URI,
            [CallArgument(kind="enum", symbol=f"{HTTP_METHOD}GET."), socket, _string("/x")],
        ),
        ("host", _URI, [_string("b")]),
        _send(),
    )

    assert _calls(_rows(tmp_path, body)) == [
        ("GET", None, "/x", "resolved"),
        ("POST", None, "/charges", "resolved"),
    ]


@pytest.mark.pins("fluent.an-unread-destination-is-the-one-word")
def test_a_destination_word_other_than_unread_is_refused(tmp_path: Path):
    """`destination` takes the one literal `unread`; anything else would load and read as a
    chain whose destination is read, silently."""
    catalog = _vertx_webclient()
    roots = [
        {**root, "captures": {**root["captures"], "destination": "server"}}
        if root.get("captures", {}).get("destination") == "unread"
        else root
        for root in catalog.matches["roots"]
    ]
    with pytest.raises(CatalogError, match="`destination: 'server'`, which is only `unread`"):
        _resolve_fluent(tmp_path, [], _replaced(catalog, roots=roots))


@pytest.mark.pins("vertx-webclient.a-uri-step-names-an-address")
def test_a_request_options_form_derives_nothing_until_a_uri_names_an_address(tmp_path: Path):
    """`client.request(GET, options).send()` with an options object nothing here reads names no
    address, so it is no row; a later `uri("/y")` names one (spec §3d)."""
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


@pytest.mark.pins("fluent.the-parts-form-reads-as-the-absolute-form")
@pytest.mark.parametrize(
    ("host", "port", "path"),
    [("inventory", 8080, "/stock"), ("${search.host}", 9200, "/q")],
    ids=["literal-host", "configured-host"],
)
def test_the_parts_form_and_the_absolute_form_publish_one_row(
    tmp_path: Path, host: str, port: int, path: str
):
    """One peer per call, whichever form (coordinator ruling 2026-10-31): `client.get(port,
    host, path)` publishes exactly what `client.getAbs("http://host:port" + path)` does, a host
    that is a configuration key included — the parts are composed into the address the
    absolute form carries and read by the same reader."""
    parts, absolute = _Body(), _Body()
    parts.chain(("get", _PORT_HOST_URI, [_int(port), _string(host), _string(path)]), _send())
    absolute.chain(("getAbs", _URI, [_string(f"http://{host}:{port}{path}")]), _send())

    from_parts = _calls(_rows(tmp_path / "parts", parts))
    from_absolute = _calls(_rows(tmp_path / "absolute", absolute))
    assert from_parts == from_absolute
    assert len(from_parts) == 1


@pytest.mark.pins("fluent.a-host-or-port-is-traced-as-the-url-is")
@pytest.mark.pins("fluent.a-walked-configuration-expression-is-a-read-host")
def test_a_host_the_walk_answers_as_a_configuration_expression_is_read(tmp_path: Path):
    """The walk's EXPRESSION answer for a host (`_part_answer`'s expression arm): a host built
    by a concatenation whose template is the configuration key `${search.host}` and which has
    no operand to fill is an expression, not a literal (§8.2: a deployment's to set), with no
    unread hole, so it is read as the key it names. The row agrees with
    `getAbs("http://${search.host}:9200/q")`."""
    body = _Body()
    joined = body.call(
        "java/lang/invoke/StringConcatFactory#",
        "makeConcatWithConstants",
        "()Ljava/lang/String;",
        None,
        [],
        invoke_kind="static",
    )
    body.chain(
        (
            "get",
            _PORT_HOST_URI,
            [
                _int(9200),
                CallArgument(kind="concat", source=joined, value="${search.host}"),
                _string("/q"),
            ],
        ),
        _send(),
    )
    absolute = _Body()
    absolute.chain(("getAbs", _URI, [_string("http://${search.host}:9200/q")]), _send())

    assert _calls(_rows(tmp_path / "parts", body)) == [
        ("GET", "${search.host}:9200", "/q", "resolved")
    ]
    assert _calls(_rows(tmp_path / "absolute", absolute)) == [
        ("GET", "${search.host}:9200", "/q", "resolved")
    ]


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


@pytest.mark.pins("vertx-webclient.a-statement-style-put-header-returns-its-receiver")
def test_a_statement_style_request_keeps_what_each_statement_set(tmp_path: Path):
    """Row 322: `r = client.post(q); r.putHeader(…); r.addQueryParam(…); r.timeout(…);
    r.as(…).send()` — each call made on the stored request, its result dropped. One row, and
    it carries the header and the query parameter set as statements: a call not flagged
    `returns_receiver` would fork its own branch, and the sent request would carry neither."""
    body = _Body()
    request = body.call(CLIENT, "postAbs", _URI, 90, [_string("http://prometheus:9090/q")])
    body.call(REQUEST, "putHeader", _STRING_STRING, request, [_string("X-Tenant"), _string("acme")])
    body.call(REQUEST, "addQueryParam", _STRING_STRING, request, [_string("a"), _string("b")])
    body.call(REQUEST, "timeout", f"(J){_RETURNS}", request, [CallArgument(kind="long", value=5)])
    typed = body.call(
        REQUEST,
        "as",
        f"(Lio/vertx/ext/web/codec/BodyCodec;){_RETURNS}",
        request,
        [CallArgument(kind="unresolved")],
    )
    body.call(REQUEST, "send", _SEND, typed, [])
    workspace = _resolve_fluent(tmp_path, straight_line(body.sites), _vertx_webclient())
    rows = [dict(row) for row in workspace.query("endpoints")]
    entries = sorted(
        (r["kind"], r["name"], r["value"]) for r in workspace.query("endpoint_metadata")
    )
    workspace.close()

    assert _calls(rows) == [("POST", "prometheus:9090", "/q", "resolved")]
    assert entries == [("header", "X-Tenant", "acme"), ("query", "a", "b")]


def test_a_header_put_on_one_branch_is_a_row_with_it_and_one_without(tmp_path: Path):
    """Rule 9 in the forward chain walk: `r = client.post(q); if (x) r.putHeader("X-Tenant",
    "acme"); r.send()`. The header is not on `send()`'s dominator chain, so the request is sent
    with it on one run and without it on another: two chain ends, the header on one. They are
    one wire (`POST /q`), so one row, `resolved`, carrying the header that run sets."""
    body = _Body()
    request = body.call(CLIENT, "postAbs", _URI, 90, [_string("http://prometheus:9090/q")])
    body.call(REQUEST, "putHeader", _STRING_STRING, request, [_string("X-Tenant"), _string("acme")])
    body.call(REQUEST, "send", _SEND, request, [])
    places = {0: (None, True, 2), 1: (0, False, 2), 2: (0, True, None)}
    sites = [
        site.model_copy(
            update={
                "dominator": places[site.ordinal][0],
                "on_every_exit": places[site.ordinal][1],
                "post_dominator": places[site.ordinal][2],
                "reaches_return": True,
            }
        )
        for site in body.sites
    ]
    workspace = _resolve_fluent(tmp_path, sites, _vertx_webclient())
    rows = [dict(row) for row in workspace.query("endpoints")]
    entries = sorted(
        (r["kind"], r["name"], r["value"]) for r in workspace.query("endpoint_metadata")
    )
    ends = [
        bool(end.captures.get("\x00collected")) for end in chain_ends(workspace, _vertx_webclient())
    ]
    workspace.close()

    assert sorted((r["method"], r["path"], r["resolution"]) for r in rows) == [
        ("POST", "/q", "resolved")
    ]
    assert entries == [("header", "X-Tenant", "acme")]
    assert sorted(ends) == [False, True]


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
    core = [s for s in steps if "io.vertx.ext.web.client.HttpRequest" in _owners(s)]
    flagged = {s["method"] for s in core if s.get("returns_receiver") is True}
    unflagged = {s["method"] for s in core if s.get("returns_receiver") is not True}

    assert flagged == row_111
    assert unflagged == {"sendJson", "sendJsonObject", "sendBuffer"}
    # The wrappers' steps (Task 15, spec §3e): the same methods under their own owners, and
    # the sends of their own that carry a body.
    assert {o for s in steps for o in _owners(s)} == {
        "io.vertx.ext.web.client.HttpRequest",
        "io.vertx.rxjava3.ext.web.client.HttpRequest",
        "io.vertx.mutiny.ext.web.client.HttpRequest",
    }
    for owner in (
        "io.vertx.rxjava3.ext.web.client.HttpRequest",
        "io.vertx.mutiny.ext.web.client.HttpRequest",
    ):
        wrapper = [s for s in steps if owner in _owners(s)]
        assert {s["method"] for s in wrapper if s.get("returns_receiver") is True} == row_111 - {
            "as"
        }  # `as` needs no wrapper entry
        assert {s["method"] for s in wrapper if s.get("returns_receiver") is not True} >= {
            "sendJson", "sendJsonObject", "sendBuffer",
        }  # fmt: skip
    # CP-56 rows 304-323 print some owners with a stray `;`; none is copied here.
    assert all(not o.endswith(";") for step in steps for o in _owners(step))


def _owners(entry: dict) -> list[str]:
    owner = entry["owner"]
    return owner if isinstance(owner, list) else [owner]


# The client's defaults: an options object handed to the factory (Task 13, spec §3d) -------

OPTIONS = "io/vertx/ext/web/client/WebClientOptions#"
REQUEST_OPTIONS = "io/vertx/core/http/RequestOptions#"
_CREATE = (
    "(Lio/vertx/core/Vertx;Lio/vertx/ext/web/client/WebClientOptions;)"
    "Lio/vertx/ext/web/client/WebClient;"
)
_SET_HOST = "(Ljava/lang/String;)Lio/vertx/ext/web/client/WebClientOptions;"
_SET_PORT = "(I)Lio/vertx/ext/web/client/WebClientOptions;"
_SET_TIMEOUT = "(I)Lio/vertx/ext/web/client/WebClientOptions;"


class _Client(_Body):
    """A body that builds its client from an options object before sending: `<init>` on a
    fresh object (no result, row 323), each setter on the value the last one returned, and
    the factory handed the last result."""

    def new(self, owner: str) -> int:
        """`new T()`: the object is the constructor's receiver, the call has no result."""
        self._next_value += 1
        made = self._next_value
        self.sites.append(
            CallSiteFact(
                document_id="doc_1",
                caller=self.caller,
                target=CallTarget(owner=owner, name="<init>", descriptor="()V"),
                invoke_kind="special",
                ordinal=len(self.sites),
                receiver=made,
                result=None,
                arguments=[],
            )
        )
        return made

    def options(self, *setters: tuple[str, str, CallArgument], owner: str = OPTIONS) -> int:
        """`new WebClientOptions().setX(…).setY(…)`, chained (CP-56 row 323)."""
        value = self.new(owner)
        for name, descriptor, argument in setters:
            value = self.call(owner, name, descriptor, value, [argument], invoke_kind="virtual")
        return value

    def create(self, options: CallArgument) -> int:
        return self.call(
            CLIENT,
            "create",
            _CREATE,
            None,
            [CallArgument(kind="parameter", value=0), options],
            invoke_kind="static",
        )

    def on(self, client: int, root: tuple[str, str, list[CallArgument]], *steps: tuple) -> int:
        """`client.<root>(…).<step>(…)…` on the client this body built."""
        value = self.call(CLIENT, root[0], root[1], client, root[2])
        for name, descriptor, arguments in steps:
            value = self.call(REQUEST, name, descriptor, value, arguments)
        return value


def _search_client(body: _Client) -> int:
    """`WebClient.create(vertx, new WebClientOptions().setDefaultHost("search")
    .setDefaultPort(9200))`, the fixture's `SearchClient`."""
    made = body.options(
        ("setDefaultHost", _SET_HOST, _string("search")),
        ("setDefaultPort", _SET_PORT, _int(9200)),
    )
    return body.create(CallArgument(kind="unresolved", source=made))


@pytest.mark.pins(
    "client_base.the-options-rung-reads-the-factorys-options",
    "fluent.a-client-at-the-roots-receiver-is-read-there",
)
def test_the_options_handed_to_the_factory_fill_a_request_naming_no_address(tmp_path: Path):
    """`client.get("/q")` on a client built from options setting the default host and port:
    Vert.x fills both into a request that names neither (CP-56 row 124), so the peer is
    `search:9200`, one peer as for the parts form."""
    body = _Client()
    client = _search_client(body)
    body.on(client, ("get", _URI, [_string("/q")]), _send())

    assert _calls(_rows(tmp_path, body)) == [("GET", "search:9200", "/q", "resolved")]


@pytest.mark.pins(
    "fluent.a-default-fills-only-what-the-request-does-not-name",
    "fluent.an-absolute-request-takes-no-default",
)
def test_a_request_naming_its_own_host_keeps_it(tmp_path: Path):
    """The join is Vert.x's (CP-56 (e)): `get(host, uri)` takes the default port only;
    `get(port, host, uri)` takes neither; `getAbs(url)` reads neither; a `host(…)` step on
    `get(uri)` wins over the default host at send time and keeps the default port."""
    body = _Client()
    client = _search_client(body)
    body.on(client, ("get", _HOST_URI, [_string("other"), _string("/a")]), _send())
    body.on(
        client,
        ("post", _PORT_HOST_URI, [_int(8080), _string("inventory"), _string("/b")]),
        _send(),
    )
    body.on(client, ("putAbs", _URI, [_string("http://billing/c")]), _send())
    body.on(client, ("delete", _URI, [_string("/d")]), ("host", _URI, [_string("h")]), _send())

    assert _calls(_rows(tmp_path, body)) == [
        ("DELETE", "h:9200", "/d", "resolved"),
        ("GET", "other:9200", "/a", "resolved"),
        ("POST", "inventory:8080", "/b", "resolved"),
        ("PUT", "billing", "/c", "resolved"),
    ]


@pytest.mark.pins("values.a-STATIC-FIELD-receiver-is-followed-to-its-writer")
def test_an_options_object_held_in_a_constructor_written_field_is_read(tmp_path: Path):
    """D00 §5: the constructor stores the options in `this.options`, `start()` builds the
    client from that field into `this.client`, and `query()` calls `this.client.get("/q")` —
    the receiver read off `this`'s field (`receiver_field`). The client is followed through
    its field to the factory, and the options through theirs to the setters."""
    owner = "com/acme/vertx/Search#"
    init = _MODULE + method_descriptor(owner, "<init>", "()V")
    start = _MODULE + method_descriptor(owner, "start", "()V")
    query = _MODULE + method_descriptor(owner, "query", "()V")
    building = _Client(init)
    made = building.options(
        ("setDefaultHost", _SET_HOST, _string("search")),
        ("setDefaultPort", _SET_PORT, _int(9200)),
    )
    starting = _Client(start)
    client = starting.create(CallArgument(kind="field", symbol=owner + "options."))
    sending = _Client(query)
    get = sending.call(CLIENT, "get", _URI, None, [_string("/q")])
    sending.call(REQUEST, "send", _SEND, get, [])
    sending.sites[0] = sending.sites[0].model_copy(
        update={"receiver_field": owner + "client.", "receiver": 3}
    )
    facts = [
        *building.sites,
        *starting.sites,
        *sending.sites,
        FieldWriteFact(
            document_id="doc_1",
            field=owner + "options.",
            value=CallArgument(kind="unresolved", source=made),
            written_by=init,
        ),
        FieldWriteFact(
            document_id="doc_1",
            field=owner + "client.",
            value=CallArgument(kind="unresolved", source=client),
            written_by=start,
        ),
    ]
    workspace = _resolve_fluent_walked(tmp_path, facts, _vertx_webclient())
    rows = [dict(row) for row in workspace.query("endpoints")]
    workspace.close()

    assert _calls(rows) == [("GET", "search:9200", "/q", "resolved")]


@pytest.mark.pins("client_base.every-call-returning-the-options-configures-them")
def test_options_configured_statement_by_statement_beside_other_settings_are_read(
    tmp_path: Path,
):
    """Hono's shape: `o = new WebClientOptions(); o.setConnectTimeout(5);
    o.setDefaultHost("search"); WebClient.create(vertx, o)`, each result dropped. A call on
    the options that returns them configures them (CP-56 rows 103, 112), so the timeout is
    not read as the object escaping, and the host is read."""
    body = _Client()
    made = body.new(OPTIONS)
    body.call(OPTIONS, "setConnectTimeout", _SET_TIMEOUT, made, [_int(5)], invoke_kind="virtual")
    body.call(OPTIONS, "setDefaultHost", _SET_HOST, made, [_string("search")], "virtual")
    client = body.create(CallArgument(kind="unresolved", source=made))
    body.on(client, ("get", _URI, [_string("/q")]), _send())

    assert _calls(_rows(tmp_path, body)) == [("GET", "search", "/q", "resolved")]


@pytest.mark.pins("fluent.an-unread-default-leaves-the-resolution-alone")
def test_an_unset_or_unread_default_keeps_the_path_with_no_peer(tmp_path: Path):
    """Options setting no default host (only a port), or a host nothing here reads: Vert.x
    would send to `localhost`, which cannot be proven, and the host it reads is unknown, so the
    peer is NULL. The path is Vert.x's as written, so the row keeps it at its own resolution."""
    body = _Client()
    port_only = body.create(
        CallArgument(
            kind="unresolved", source=body.options(("setDefaultPort", _SET_PORT, _int(9200)))
        )
    )
    unread = body.create(
        CallArgument(
            kind="unresolved",
            source=body.options(("setDefaultHost", _SET_HOST, CallArgument(kind="unresolved"))),
        )
    )
    body.on(port_only, ("get", _URI, [_string("/a")]), _send())
    body.on(unread, ("post", _URI, [_string("/b")]), _send())

    assert _calls(_rows(tmp_path, body)) == [
        ("GET", None, "/a", "resolved"),
        ("POST", None, "/b", "resolved"),
    ]


@pytest.mark.pins("fluent.a-default-set-and-unread-leaves-no-peer")
def test_a_default_port_set_and_unread_leaves_no_peer(tmp_path: Path):
    """Final review I3, D02's options-object rung: `setDefaultHost("search")
    .setDefaultPort(config.port())`. Vert.x sends `get("/q")` to `search:<unread>` and
    `get("h", "/b")` to `h:<unread>`, so neither peer is known: each row keeps its path and
    resolution with `peer` NULL, never the host alone at `resolved`."""
    body = _Client()
    made = body.options(
        ("setDefaultHost", _SET_HOST, _string("search")),
        ("setDefaultPort", _SET_PORT, CallArgument(kind="unresolved")),
    )
    client = body.create(CallArgument(kind="unresolved", source=made))
    body.on(client, ("get", _URI, [_string("/q")]), _send())
    body.on(client, ("post", _HOST_URI, [_string("h"), _string("/b")]), _send())

    assert _calls(_rows(tmp_path, body)) == [
        ("GET", None, "/q", "resolved"),
        ("POST", None, "/b", "resolved"),
    ]


@pytest.mark.pins("client_base.a-default-the-paths-dispute-is-set-and-unread")
def test_two_factories_disputing_the_default_port_leave_no_peer(tmp_path: Path):
    """`this.client` written by two methods whose options name one default host and two
    default ports: which port a request goes to is not known, so `get("/a")` has no peer —
    not `same`, the host alone, at `resolved`, as though no port had been set."""
    owner = "com/acme/vertx/Search#"
    first = _MODULE + method_descriptor(owner, "first", "()V")
    second = _MODULE + method_descriptor(owner, "second", "()V")
    query = _MODULE + method_descriptor(owner, "query", "()V")
    facts: list = []
    for method, port in ((first, 9200), (second, 9300)):
        building = _Client(method)
        made = building.options(
            ("setDefaultHost", _SET_HOST, _string("same")),
            ("setDefaultPort", _SET_PORT, _int(port)),
        )
        client = building.create(CallArgument(kind="unresolved", source=made))
        facts += [
            *building.sites,
            FieldWriteFact(
                document_id="doc_1",
                field=owner + "client.",
                value=CallArgument(kind="unresolved", source=client),
                written_by=method,
            ),
        ]
    sending = _Client(query)
    request = sending.call(CLIENT, "get", _URI, 3, [_string("/a")])
    sending.sites[-1] = sending.sites[-1].model_copy(
        update={"receiver_field": owner + "client.", "receiver_field_kind": "instance"}
    )
    sending.call(REQUEST, "send", _SEND, request, [])
    workspace = _resolve_fluent_walked(tmp_path, [*facts, *sending.sites], _vertx_webclient())
    rows = [dict(row) for row in workspace.query("endpoints")]
    workspace.close()

    assert _calls(rows) == [("GET", None, "/a", "resolved")]


@pytest.mark.pins(
    "fluent.a-request-options-object-is-read-by-the-options-reader",
    "vertx-webclient.a-request-options-form-reads-its-options",
)
def test_a_request_options_object_names_its_address(tmp_path: Path):
    """`client.request(GET, new RequestOptions().setHost("h").setPort(81).setURI("/x"))`:
    the options object is read as the client's is, `setURI` the path and `setHost`/`setPort`
    the request's own parts. One naming only its uri takes the client's default host and port
    (CP-56 row 126: each null part filled separately). One naming no uri is still no row."""
    body = _Client()
    client = _search_client(body)
    verb = CallArgument(kind="enum", symbol=f"{HTTP_METHOD}GET.")
    full = body.options(
        ("setHost", "(Ljava/lang/String;)Lio/vertx/core/http/RequestOptions;", _string("h")),
        ("setPort", "(Ljava/lang/Integer;)Lio/vertx/core/http/RequestOptions;", _int(81)),
        ("setURI", "(Ljava/lang/String;)Lio/vertx/core/http/RequestOptions;", _string("/x")),
        owner=REQUEST_OPTIONS,
    )
    uri_only = body.options(
        ("setURI", "(Ljava/lang/String;)Lio/vertx/core/http/RequestOptions;", _string("/y")),
        owner=REQUEST_OPTIONS,
    )
    no_uri = body.options(
        ("setHost", "(Ljava/lang/String;)Lio/vertx/core/http/RequestOptions;", _string("z")),
        owner=REQUEST_OPTIONS,
    )
    for made in (full, uri_only, no_uri):
        body.on(
            client,
            ("request", _OPTIONS, [verb, CallArgument(kind="unresolved", source=made)]),
            _send(),
        )

    assert _calls(_rows(tmp_path, body)) == [
        ("GET", "h:81", "/x", "resolved"),
        ("GET", "search:9200", "/y", "resolved"),
    ]


def test_a_socket_address_request_joins_no_default(tmp_path: Path):
    """`client.request(GET, address, "/x")` on a client with defaults: the request goes to
    the `SocketAddress` (Task 12's `destination: unread`), so no default is joined."""
    body = _Client()
    client = _search_client(body)
    verb = CallArgument(kind="enum", symbol=f"{HTTP_METHOD}GET.")
    body.on(
        client,
        ("request", _SOCKET_URI, [verb, CallArgument(kind="unresolved"), _string("/x")]),
        _send(),
    )

    assert _calls(_rows(tmp_path, body)) == [("GET", None, "/x", "resolved")]


@pytest.mark.pins("fluent.a-request-options-uri-set-and-unread-is-still-a-row")
def test_a_request_options_uri_set_and_not_read_is_still_a_row(tmp_path: Path):
    """`request(GET, new RequestOptions().setURI(path))` with `path` nothing here reads: the
    request and the fact that it names an address are both seen, so it is a row with the
    address reader's word for the unread uri — never dropped (Task 13 review, item 1)."""
    body = _Client()
    client = _search_client(body)
    verb = CallArgument(kind="enum", symbol=f"{HTTP_METHOD}GET.")
    made = body.options(
        (
            "setURI",
            "(Ljava/lang/String;)Lio/vertx/core/http/RequestOptions;",
            CallArgument(kind="unresolved"),
        ),
        owner=REQUEST_OPTIONS,
    )
    body.on(
        client,
        ("request", _OPTIONS, [verb, CallArgument(kind="unresolved", source=made)]),
        _send(),
    )

    assert _calls(_rows(tmp_path, body)) == [("GET", None, None, "unresolved")]


@pytest.mark.pins("client_base.paths-must-agree-on-a-default")
def test_two_factories_reaching_one_client_fill_only_the_defaults_they_agree_on(
    tmp_path: Path,
):
    """`this.client` written by two methods, each building it from options naming another
    default host and the same default port: which client a request goes out on is not known,
    so the host is not filled — `get("/a")` has no peer — while the port both agree on is:
    `get("h", "/b")` goes to `h:9200`."""
    owner = "com/acme/vertx/Search#"
    first = _MODULE + method_descriptor(owner, "first", "()V")
    second = _MODULE + method_descriptor(owner, "second", "()V")
    query = _MODULE + method_descriptor(owner, "query", "()V")
    facts: list = []
    for method, host in ((first, "one"), (second, "two")):
        building = _Client(method)
        made = building.options(
            ("setDefaultHost", _SET_HOST, _string(host)),
            ("setDefaultPort", _SET_PORT, _int(9200)),
        )
        client = building.create(CallArgument(kind="unresolved", source=made))
        facts += [
            *building.sites,
            FieldWriteFact(
                document_id="doc_1",
                field=owner + "client.",
                value=CallArgument(kind="unresolved", source=client),
                written_by=method,
            ),
        ]
    sending = _Client(query)
    for root in (("get", _URI, [_string("/a")]), ("get", _HOST_URI, [_string("h"), _string("/b")])):
        request = sending.call(CLIENT, root[0], root[1], 3, root[2])
        sending.sites[-1] = sending.sites[-1].model_copy(
            update={"receiver_field": owner + "client.", "receiver_field_kind": "instance"}
        )
        sending.call(REQUEST, "send", _SEND, request, [])
    workspace = _resolve_fluent_walked(tmp_path, [*facts, *sending.sites], _vertx_webclient())
    rows = [dict(row) for row in workspace.query("endpoints")]
    workspace.close()

    assert _calls(rows) == [
        ("GET", "h:9200", "/b", "resolved"),
        ("GET", None, "/a", "resolved"),
    ]


@pytest.mark.pins("fluent.a-request-naming-its-host-takes-the-default-port-unread-path-or-not")
def test_a_request_naming_its_host_takes_the_default_port_though_its_uri_is_unread(
    tmp_path: Path,
):
    """`client.get("h", path)` with `path` unread: a request naming its own host is never
    absolute, so the default port is filled — `h:9200` — and the path stays unread."""
    body = _Client()
    client = _search_client(body)
    body.on(client, ("get", _HOST_URI, [_string("h"), CallArgument(kind="unresolved")]), _send())

    assert _calls(_rows(tmp_path, body)) == [("GET", "h:9200", None, "unresolved")]
