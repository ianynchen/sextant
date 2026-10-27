"""Ktor's WebSocket and SSE client calls (`ktor-websocket-client.yml`, `ktor-sse-client.yml`,
the `single_call` style; spec 2026-10-26 §3d, §3g items 2 and 4).

Unlike the HTTP client's, these calls are NOT inlined: `client.webSocket("ws://…") { }`
compiles to one static call, `BuildersKt.webSocket$default(client, "ws://…", …)`, with the
client at argument 0 (CP-54 row group (d), rows 28-45). So each is a `single_call` row, and a
relative address joins the client's `defaultRequest` base through the same reader and the same
join the HTTP client uses — declared once, in `client-models/ktor.yml`.

What each call sends to, run through Ktor itself (CP-54 row groups (m) and (n),
`scripts/probes/cp54_ktor_client_ws_sse.md`):

- **WebSocket** (rows 61-63, 94-113): the `DefaultRequest` join, then the call's own scheme,
  and its port where the call sets one. The row keeps the whole URL in `path`, `peer` NULL,
  verbless, as `jakarta-websocket-client.yml`'s do.
- **SSE** (rows 114-123): the `DefaultRequest` join, unchanged. A GET row split into peer and
  path, as the HTTP client's rows are.

The facts are spelled as the CP-54 probe module's own scan spells them: the client a `field`
argument at 0, the address a `string` at 1 (or 4 in the parts form), defaulted arguments
`null`, the `$default` mask an `int`.
"""

from pathlib import Path

import pytest
from test_call_engines import CAPABILITIES, CATALOGS_DIR, _document
from test_client_base import _FILE, _base, _call, _fn, _top_level

from sextant.application.ports.catalogs import CatalogError
from sextant.application.resolve.call_edges import record_call_edges
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.application.resolve.return_flow import record_return_flows
from sextant.application.resolve.shapes.client_base import REPLACE_LAST_SEGMENT, join_url
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import CallArgument, CallSiteFact
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.storage.duckdb.workspace import DuckDbWorkspace

WS_KT = "io/ktor/client/plugins/websocket/BuildersKt#"
SSE_KT = "io/ktor/client/plugins/sse/BuildersKt#"

_CLIENT = "Lio/ktor/client/HttpClient;"
_F1 = "Lkotlin/jvm/functions/Function1;"
_F2 = "Lkotlin/jvm/functions/Function2;"
_CONT = "Lkotlin/coroutines/Continuation;"
_STRING = "Ljava/lang/String;"
_DEFAULTS = "ILjava/lang/Object;"
_SSE_OPTIONS = "Lkotlin/time/Duration;Ljava/lang/Boolean;Ljava/lang/Boolean;"

# `webSocket(urlString, request, block)` and its `$default` bridge (CP-54 rows 28, 36).
_WS_ADDRESS = f"({_CLIENT}{_STRING}{_F1}{_F2}{_CONT}{_DEFAULTS})Ljava/lang/Object;"
# `webSocket(method, host, port, path, request, block)`'s bridge (rows 28, 37).
_WS_PARTS = (
    f"({_CLIENT}Lio/ktor/http/HttpMethod;{_STRING}Ljava/lang/Integer;{_STRING}{_F1}{_F2}"
    f"{_CONT}{_DEFAULTS})Ljava/lang/Object;"
)
# `sse(urlString, request, reconnectionTime, showCommentEvents, showRetryEvents, block)`'s
# bridge, `sse-Mswn-_c$default` (rows 32, 42) — and the OTHER `sse-Mswn-_c`, the
# request-lambda form with a deserializer, whose argument 1 is a `Function1` (row 32 (4)).
_SSE_ADDRESS = f"({_CLIENT}{_STRING}{_F1}{_SSE_OPTIONS}{_F2}{_CONT}{_DEFAULTS})Ljava/lang/Object;"
_SSE_DESERIALIZING = f"({_CLIENT}{_F1}{_F2}{_SSE_OPTIONS}{_F2}{_CONT}{_DEFAULTS})Ljava/lang/Object;"

_CLIENT_FIELD = CallArgument(kind="field", symbol=_FILE + "client.")
_NULL = CallArgument(kind="null")


def _catalog(catalog_id: str):
    return next(c for c in YamlCatalogSource(CATALOGS_DIR).load() if c.id == catalog_id)


def _ws_address_call(caller: str, name: str, address: str) -> CallSiteFact:
    """`client.<name>("<address>") { }`, as the probe compiles it (rows 36, 39-41)."""
    return _call(
        caller,
        0,
        (WS_KT, name + "$default", _WS_ADDRESS),
        [
            _CLIENT_FIELD,
            CallArgument(kind="string", value=address),
            _NULL,
            CallArgument(kind="instance", source=5, symbol="com/acme/kt/ClientsKt$chat$2#"),
            CallArgument(kind="parameter", value=0),
            CallArgument(kind="int", value=2),
            _NULL,
        ],
    )


def _ws_parts_call(caller: str, host: CallArgument, path: str) -> CallSiteFact:
    """`client.webSocket(host = …, port = 8080, path = "…") { }` (row 37), or with `host`
    left to its default: the bridge with the method and request defaulted."""
    port = CallArgument(kind="unresolved", source=6) if host.kind != "null" else _NULL
    return _call(
        caller,
        0,
        (WS_KT, "webSocket$default", _WS_PARTS),
        [
            _CLIENT_FIELD,
            _NULL,
            host,
            port,
            CallArgument(kind="string", value=path),
            _NULL,
            CallArgument(kind="instance", source=9, symbol="com/acme/kt/ClientsKt$parts$2#"),
            CallArgument(kind="parameter", value=0),
            CallArgument(kind="int", value=17 if host.kind != "null" else 23),
            _NULL,
        ],
    )


def _sse_call(caller: str, address: str) -> CallSiteFact:
    """`client.sse("<address>") { }`, the `sse-Mswn-_c$default` bridge (row 42)."""
    return _call(
        caller,
        0,
        (SSE_KT, "sse-Mswn-_c$default", _SSE_ADDRESS),
        [
            _CLIENT_FIELD,
            CallArgument(kind="string", value=address),
            _NULL,
            _NULL,
            _NULL,
            _NULL,
            CallArgument(kind="instance", source=8, symbol="com/acme/kt/ClientsKt$events$2#"),
            CallArgument(kind="parameter", value=0),
            CallArgument(kind="int", value=30),
            _NULL,
        ],
    )


def _rows(tmp_path: Path, facts: list, *catalog_ids: str) -> list[tuple]:
    """The facts with the two tables the value walk reads built first, then the catalogs."""
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    record_return_flows(workspace)
    record_call_edges(workspace)
    catalogs = [_catalog(catalog_id) for catalog_id in catalog_ids]
    assert derive_endpoints(workspace, catalogs, capabilities=CAPABILITIES) == []
    rows = sorted(
        (
            r["caller"],
            r["protocol"],
            r["direction"],
            r["method"],
            r["peer"],
            r["path"],
            r["resolution"],
        )
        for r in workspace.query("endpoints")
    )
    workspace.close()
    return rows


_WS = "ktor-websocket-client"
_SSE = "ktor-sse-client"
_API = "https://api.example.com/"


@pytest.mark.pins("ktor.a-WEBSOCKET-client-call-is-an-outbound-row")
def test_a_ktor_websocket_client_url_is_an_outbound_row(tmp_path: Path):
    """`client.webSocket("ws://chat.example.com/chat") { }` (CP-54 row 36): one outbound
    WebSocket row, the whole URL in `path` and `peer` NULL, verbless, as every outbound
    WebSocket catalog's rows are. An absolute address is the whole address whatever the
    client's base (row 63)."""
    facts = [
        *_top_level("client", 1, [_base(_API)]),
        _ws_address_call(_fn("chat"), "webSocket", "ws://chat.example.com/chat"),
    ]
    assert _rows(tmp_path, facts, _WS) == [
        (_fn("chat"), "websocket", "outbound", None, None, "ws://chat.example.com/chat", "resolved")
    ]


@pytest.mark.pins("ktor.a-relative-WS-call-joins-the-base")
def test_a_relative_ws_call_joins_the_base(tmp_path: Path):
    """`client.ws("/opentelemetry/websocket") { }` on a client built with `defaultRequest {
    url("https://api.example.com/") }`: Ktor joins the address onto the base and sends it with
    `ws`'s scheme and the base's port, `ws://api.example.com:443/…` (CP-54 rows 61, 95)."""
    facts = [
        *_top_level("client", 1, [_base(_API)]),
        _ws_address_call(_fn("chat"), "ws", "/opentelemetry/websocket"),
    ]
    assert _rows(tmp_path, facts, _WS) == [
        (
            _fn("chat"),
            "websocket",
            "outbound",
            None,
            None,
            "ws://api.example.com:443/opentelemetry/websocket",
            "resolved",
        )
    ]


@pytest.mark.pins("ktor.a-WEBSOCKET-call-sends-with-its-OWN-scheme-and-port")
def test_wss_and_a_session_set_their_own_port(tmp_path: Path):
    """`wss("…")` sets `wss`'s default port and `webSocketSession("…")` sets `ws`'s, so
    neither writes the base's `:443` (CP-54 rows 96, 98): one rule, the port the call sets,
    read off each row's `request_url`."""
    facts = [
        *_top_level("client", 1, [_base(_API)]),
        _ws_address_call(_fn("secure"), "wss", "/secure/websocket"),
        _call(
            _fn("session"),
            0,
            (
                WS_KT,
                "webSocketSession$default",
                f"({_CLIENT}{_STRING}{_F1}{_CONT}{_DEFAULTS})Ljava/lang/Object;",
            ),
            [
                _CLIENT_FIELD,
                CallArgument(kind="string", value="/session"),
                _NULL,
                CallArgument(kind="parameter", value=0),
                CallArgument(kind="int", value=2),
                _NULL,
            ],
        ),
    ]
    assert [(row[0], row[5]) for row in _rows(tmp_path, facts, _WS)] == [
        (_fn("secure"), "wss://api.example.com/secure/websocket"),
        (_fn("session"), "ws://api.example.com/session"),
    ]


def test_a_relative_ws_call_on_a_client_with_no_readable_base_stays_relative(tmp_path: Path):
    """A client whose construction is not reached has no base the reader can state, so the
    address the code wrote is a path, not the URL called: `unresolved`, as the HTTP client's
    relative rows are."""
    facts = [_ws_address_call(_fn("chat"), "ws", "/chat")]
    assert _rows(tmp_path, facts, _WS) == [
        (_fn("chat"), "websocket", "outbound", None, None, "/chat", "unresolved")
    ]


@pytest.mark.pins("ktor.an-SSE-client-call-is-an-outbound-row")
def test_a_ktor_sse_client_is_an_outbound_sse_row(tmp_path: Path):
    """`client.sse("https://events.example.com/stream") { }` (CP-54 row 42) compiles to
    `sse-Mswn-_c$default`: one outbound SSE row, GET, the address split into peer and path."""
    facts = [
        *_top_level("client", 1, [_base(_API)]),
        _sse_call(_fn("events"), "https://events.example.com/stream"),
    ]
    assert _rows(tmp_path, facts, _SSE) == [
        (_fn("events"), "sse", "outbound", "GET", "events.example.com", "/stream", "resolved")
    ]


def test_a_relative_sse_call_joins_the_base_by_the_http_join(tmp_path: Path):
    """`client.sse("stream")` over `https://api.example.com/v1/`: Ktor sends
    `https://api.example.com/v1/stream`, the HTTP join with no change of scheme (CP-54 row
    115)."""
    facts = [
        *_top_level("client", 1, [_base("https://api.example.com/v1/")]),
        _sse_call(_fn("events"), "stream"),
    ]
    assert _rows(tmp_path, facts, _SSE) == [
        (_fn("events"), "sse", "outbound", "GET", "api.example.com", "/v1/stream", "resolved")
    ]


@pytest.mark.declines("ktor-sse-client")
@pytest.mark.pins("single_call.claimed-arity")
def test_the_other_sse_overload_sharing_the_name_is_not_read(tmp_path: Path):
    """`sse-Mswn-_c` also names the request-lambda form with a deserializer, whose argument 1
    is a `Function1` (CP-54 row 32 (4)). Matched on its name alone, the lambda would be read as
    the address; only the descriptor separates the two, so that call derives no row."""
    facts = [
        *_top_level("client", 1, [_base(_API)]),
        _call(
            _fn("lambda"),
            0,
            (SSE_KT, "sse-Mswn-_c$default", _SSE_DESERIALIZING),
            [
                _CLIENT_FIELD,
                CallArgument(kind="lambda", source=3, symbol=_FILE + "lambda$0()."),
                CallArgument(kind="lambda", source=4, symbol=_FILE + "lambda$1()."),
                _NULL,
                _NULL,
                _NULL,
                CallArgument(kind="instance", source=8, symbol="com/acme/kt/ClientsKt$l$2#"),
                CallArgument(kind="parameter", value=0),
                CallArgument(kind="int", value=56),
                _NULL,
            ],
        ),
    ]
    assert _rows(tmp_path, facts, _SSE) == []


@pytest.mark.declines("ktor-websocket-client")
@pytest.mark.pins("single_call.call-site-owner")
def test_a_module_helper_shaped_like_ktors_ws_derives_no_row(tmp_path: Path):
    """A module's own `suspend fun HttpClient.ws(path: String, …)` compiles to a static
    `ws$default` with Ktor's exact name, arity and descriptor, on the module's own file
    class. It is not Ktor's call — what it sends to is whatever its body does — so it
    derives no row: only `websocket.BuildersKt`'s own functions are matched."""
    helper = _call(
        _fn("chat"),
        0,
        ("com/acme/kt/ChatKt#", "ws$default", _WS_ADDRESS),
        _ws_address_call(_fn("chat"), "ws", "/chat").arguments,
    )
    facts = [*_top_level("client", 1, [_base(_API)]), helper]
    assert _rows(tmp_path, facts, _WS) == []


def test_the_request_lambda_form_derives_no_websocket_row(tmp_path: Path):
    """`client.webSocket({ url("ws://…") }) { }` (CP-54 row 38) shares the name `webSocket`
    with the address forms and carries its address inside a lambda, at argument 1. No row
    declares that descriptor, so it derives nothing — never a row reading the lambda as an
    address."""
    facts = [
        *_top_level("client", 1, [_base(_API)]),
        _call(
            _fn("lambda"),
            0,
            (WS_KT, "webSocket", f"({_CLIENT}{_F1}{_F2}{_CONT})Ljava/lang/Object;"),
            [
                _CLIENT_FIELD,
                CallArgument(kind="lambda", source=3, symbol=_FILE + "lambda$0()."),
                CallArgument(kind="instance", source=4, symbol="com/acme/kt/ClientsKt$l$3#"),
                CallArgument(kind="parameter", value=0),
            ],
        ),
    ]
    assert _rows(tmp_path, facts, _WS) == []


@pytest.mark.pins("ktor.a-HOST-in-the-parts-form-is-not-assembled")
def test_the_host_port_path_form_is_not_assembled(tmp_path: Path):
    """`client.webSocket(host = "chat.example.com", port = 8080, path = "/parts") { }` (CP-54
    row 37): Ktor sends to the host it is given (row 109), and no shipped rule assembles a
    scheme, host, port and path. The row keeps the path it read, `unresolved`; it is never
    joined to the base, which the host replaces. With the host and port left to their
    defaults, the path joins the base exactly as `ws("/parts")` would (row 107)."""
    facts = [
        *_top_level("client", 1, [_base(_API)]),
        _ws_parts_call(
            _fn("parts"), CallArgument(kind="string", value="chat.example.com"), "/parts"
        ),
        _ws_parts_call(_fn("pathOnly"), _NULL, "/parts"),
    ]
    assert _rows(tmp_path, facts, _WS) == [
        (_fn("parts"), "websocket", "outbound", None, None, "/parts", "unresolved"),
        (
            _fn("pathOnly"),
            "websocket",
            "outbound",
            None,
            None,
            "ws://api.example.com:443/parts",
            "resolved",
        ),
    ]


_SSE_PARTS = (
    f"({_CLIENT}{_STRING}{_STRING}Ljava/lang/Integer;{_STRING}{_F1}{_SSE_OPTIONS}{_F2}{_CONT}"
    f"{_DEFAULTS})Ljava/lang/Object;"
)


def _sse_parts_call(caller: str, path: str) -> CallSiteFact:
    """`client.sse(path = "<path>") { }`: the `sse-tL6_L-A$default` bridge, every part but
    the path left to its default (`null`, CP-54 rows 43, 122)."""
    return _call(
        caller,
        0,
        (SSE_KT, "sse-tL6_L-A$default", _SSE_PARTS),
        [
            _CLIENT_FIELD,
            _NULL,
            _NULL,
            _NULL,
            CallArgument(kind="string", value=path),
            _NULL,
            _NULL,
            _NULL,
            _NULL,
            CallArgument(kind="instance", source=12, symbol="com/acme/kt/ClientsKt$p$2#"),
            CallArgument(kind="parameter", value=0),
            CallArgument(kind="int", value=495),
            _NULL,
        ],
    )


@pytest.mark.pins("ktor.a-PARTS-path-is-a-path-never-an-address")
def test_a_parts_path_is_read_as_a_path_never_as_an_address(tmp_path: Path):
    """`sse(path = "https://e.example.com/s")` and `sse(path = "//x/y")` over
    `https://api.example.com/v1/`: Ktor never parses the parts form's path (CP-54 rows
    129-130), so neither names `e.example.com` or `x`. Both are paths on the base's host. A
    path carrying a query is kept, `unresolved` (row 131 not modelled)."""
    facts = [
        *_top_level("client", 1, [_base("https://api.example.com/v1/")]),
        _sse_parts_call(_fn("whole"), "https://e.example.com/s"),
        _sse_parts_call(_fn("slashes"), "//x/y"),
        _sse_parts_call(_fn("query"), "/stream?x=1"),
    ]
    assert _rows(tmp_path, facts, _SSE) == [
        (_fn("query"), "sse", "outbound", "GET", None, "/stream", "unresolved"),
        (_fn("slashes"), "sse", "outbound", "GET", "api.example.com", "//x/y", "resolved"),
        (
            _fn("whole"),
            "sse",
            "outbound",
            "GET",
            "api.example.com",
            "/v1/https://e.example.com/s",
            "resolved",
        ),
    ]


def test_a_configuration_key_base_under_a_websocket_call_is_carried_without_the_rewrite(
    tmp_path: Path,
):
    """`defaultRequest { url("${chat.url}") }` and `client.ws("/chat")`: the base is carried
    as the HTTP client's configuration base is, `${chat.url}/chat` at `partial`, and the
    `ws` scheme is NOT written into it — the deployed value's scheme and port are unknown, so
    the rewrite has nothing it could rewrite."""
    facts = [
        *_top_level("client", 1, [_base("${chat.url}")]),
        _ws_address_call(_fn("chat"), "ws", "/chat"),
    ]
    assert _rows(tmp_path, facts, _WS) == [
        (_fn("chat"), "websocket", "outbound", None, None, "${chat.url}/chat", "partial")
    ]


# --- The WebSocket join, one assertion per CP-54 row (m) -----------------------------------
_PORTS = {"http": 80, "https": 443, "ws": 80, "wss": 443}
_WS_REQUEST = {"scheme": "ws"}
_WSS_ADDRESS_REQUEST = {"scheme": "wss", "port": 443}
_SESSION_REQUEST = {"scheme": "ws", "port": 80}
_WSS_PARTS_REQUEST = {"scheme": "wss"}


@pytest.mark.pins("ktor.a-WEBSOCKET-call-sends-with-its-OWN-scheme-and-port")
@pytest.mark.parametrize(
    ("row", "base", "address", "request_url", "sent"),
    [
        (61, "https://api.example.com/v1/", "/chat", _WS_REQUEST, "ws://api.example.com:443/chat"),
        (
            62,
            "http://api.example.com/v1/",
            "/chat",
            _WSS_ADDRESS_REQUEST,
            "wss://api.example.com/chat",
        ),
        (95, "https://api.example.com/v1/", "/chat", _WS_REQUEST, "ws://api.example.com:443/chat"),
        (96, "https://api.example.com/v1/", "/chat", _SESSION_REQUEST, "ws://api.example.com/chat"),
        (97, "http://api.example.com/v1/", "/chat", _WS_REQUEST, "ws://api.example.com/chat"),
        (
            98,
            "https://api.example.com/v1/",
            "/chat",
            _WSS_ADDRESS_REQUEST,
            "wss://api.example.com/chat",
        ),
        (
            99,
            "https://api.example.com/v1/",
            "chat",
            _WS_REQUEST,
            "ws://api.example.com:443/v1/chat",
        ),
        (
            100,
            "https://api.example.com:8443/v1/",
            "/chat",
            _WS_REQUEST,
            "ws://api.example.com:8443/chat",
        ),
        (
            101,
            "https://api.example.com:8443/v1/",
            "/chat",
            _WSS_ADDRESS_REQUEST,
            "wss://api.example.com/chat",
        ),
        (
            102,
            "http://api.example.com:8080/v1/",
            "/chat",
            _WS_REQUEST,
            "ws://api.example.com:8080/chat",
        ),
        (
            103,
            "http://api.example.com:8080/v1/",
            "/chat",
            _WSS_ADDRESS_REQUEST,
            "wss://api.example.com/chat",
        ),
        (
            104,
            "https://api.example.com/v1/?key=1",
            "/chat?room=1",
            _WS_REQUEST,
            "ws://api.example.com:443/chat?room=1&key=1",
        ),
        (
            105,
            "https://api.example.com/v1/",
            "/parts",
            _WS_REQUEST,
            "ws://api.example.com:443/parts",
        ),
        (
            106,
            "http://api.example.com/v1/",
            "/parts",
            _WSS_PARTS_REQUEST,
            "wss://api.example.com:80/parts",
        ),
        (
            108,
            "https://api.example.com/v1/",
            "/parts",
            _SESSION_REQUEST,
            "ws://api.example.com/parts",
        ),
        (
            110,
            "https://api.example.com/v1/",
            "https://other.example.com/x",
            _WS_REQUEST,
            "https://other.example.com/x",
        ),
        (
            111,
            "https://api.example.com/v1/",
            "ws://other.example.com/x",
            _WSS_ADDRESS_REQUEST,
            "ws://other.example.com/x",
        ),
    ],
)
def test_the_websocket_join_is_ktors(row, base, address, request_url, sent):
    """Each case is what Ktor's engine received (CP-54 rows 61-62, 95-111): the `DefaultRequest`
    join for the path and query, the call's scheme, its port where it sets one and the base's
    otherwise, written only where it differs from the scheme's default (row 94)."""
    assert join_url(base, address, REPLACE_LAST_SEGMENT, request_url, _PORTS) == sent, row


@pytest.mark.parametrize(
    ("base", "address", "ports"),
    [
        # A base whose scheme has no default port in the table: its port is not known.
        ("ftp://api.example.com/v1/", "/chat", _PORTS),
        # A scheme and no host, as for `get` (rows 81-82).
        ("https://api.example.com/v1/", "gemini-pro:generate", _PORTS),
    ],
)
def test_the_websocket_join_declines_what_it_does_not_model(base, address, ports):
    assert join_url(base, address, REPLACE_LAST_SEGMENT, _WS_REQUEST, ports) is None


@pytest.mark.pins("ktor.a-PROTOCOL-RELATIVE-address-under-a-call-scheme-declines")
def test_a_protocol_relative_address_under_a_call_scheme_declines():
    """`ws("//other.example.com/x")` takes the CALL's scheme (CP-54 row 113), where `get`'s
    takes the base's (row 83), and the port a call setting one would write is not measured:
    declined rather than predicted."""
    assert (
        join_url(
            "https://api.example.com/v1/",
            "//other.example.com/x",
            REPLACE_LAST_SEGMENT,
            _WS_REQUEST,
            _PORTS,
        )
        is None
    )


@pytest.mark.pins("ktor.a-base-carrying-USER-INFO-under-a-call-scheme-declines")
def test_a_base_carrying_user_info_under_a_call_scheme_declines():
    """The scheme rewrite rebuilds the authority from the base's host and port; a base with
    user info in it is not measured, so the join declines rather than write it back."""
    assert (
        join_url(
            "https://user@api.example.com/v1/", "/chat", REPLACE_LAST_SEGMENT, _WS_REQUEST, _PORTS
        )
        is None
    )


# --- The parts form's path, one assertion per CP-54 row (o) -------------------------------


@pytest.mark.parametrize(
    ("row", "base", "path", "request_url", "sent"),
    [
        (124, "https://api.example.com/v1/", "//x/y", _WS_REQUEST, "ws://api.example.com:443//x/y"),
        (
            125,
            "https://api.example.com/v1/",
            "https://e.example.com/s",
            _WS_REQUEST,
            "ws://api.example.com:443/v1/https://e.example.com/s",
        ),
        (
            128,
            "https://api.example.com/v1/",
            "parts",
            _WS_REQUEST,
            "ws://api.example.com:443/v1/parts",
        ),
        (129, "https://api.example.com/v1/", "//x/y", None, "https://api.example.com//x/y"),
        (
            130,
            "https://api.example.com/v1/",
            "https://e.example.com/s",
            None,
            "https://api.example.com/v1/https://e.example.com/s",
        ),
        (132, "https://api.example.com/v1/", "stream", None, "https://api.example.com/v1/stream"),
        (
            133,
            "https://api.example.com/v1/?key=1",
            "/parts",
            _WS_REQUEST,
            "ws://api.example.com:443/parts?key=1",
        ),
        (
            134,
            "https://api.example.com/v1/?key=1",
            "/parts",
            None,
            "https://api.example.com/parts?key=1",
        ),
    ],
)
def test_a_parts_path_joins_as_segments_never_as_an_address(row, base, path, request_url, sent):
    """The parts form hands `path` to `setEncodedPath`, never to `takeFrom` (CP-54 rows
    124-134): the text is split on `/` as it stands, so `//x/y` is no authority and a whole
    URL no absolute address."""
    assert (
        join_url(base, path, REPLACE_LAST_SEGMENT, request_url, _PORTS, path_only=True) == sent
    ), row


@pytest.mark.parametrize("path", ["/chat?room=1", "/chat#top"])
def test_a_parts_path_carrying_a_query_or_fragment_declines(path):
    """Ktor writes `?` and `#` in a parts path as they stand (CP-54 rows 126-127, 131); how a
    base's own query follows them is not measured."""
    assert join_url(_API, path, REPLACE_LAST_SEGMENT, _WS_REQUEST, _PORTS, path_only=True) is None


# --- One ladder, three catalogs -------------------------------------------------------------


@pytest.mark.pins("ktor.the-client-BASE-is-declared-once-for-every-catalog")
def test_the_three_ktor_client_catalogs_read_one_declared_ladder():
    """The HTTP, WebSocket and SSE catalogs name `client_model: ktor` and state only where the
    client sits at their own call — argument 1 of `HttpStatement`'s constructor for HTTP,
    argument 0 of every `BuildersKt` call for the other two — so the base each reads is set
    through ONE ladder, never three copies that can drift."""
    loaded = {c.id: c for c in YamlCatalogSource(CATALOGS_DIR).load()}
    declared = {
        catalog_id: loaded[catalog_id].matches["client_base"]
        for catalog_id in ("ktor-client", _WS, _SSE)
    }
    assert {catalog_id: base["client_arg"] for catalog_id, base in declared.items()} == {
        "ktor-client": 1,
        _WS: 0,
        _SSE: 0,
    }
    shared = [{k: v for k, v in base.items() if k != "client_arg"} for base in declared.values()]
    assert shared[0] == shared[1] == shared[2]
    assert [rung["method"] for rung in shared[0]["ladder"]] == [
        "HttpClient",
        "HttpClient",
        "config",
        "defaultRequest",
    ]


def _write_catalog(directory: Path, client_base: str) -> None:
    (directory / "client-models").mkdir()
    (directory / "client-models" / "acme.yml").write_text(
        "id: acme\n"
        "client_base:\n"
        "  ladder: [{ owner: com.acme.ClientKt, method: Client, block_arg: 1 }]\n"
        "  setter: { owner: com.acme.Defaults, method: url, value_arg: 0 }\n"
        "  join: replace_last_segment\n"
        "  may_set_base: []\n",
        encoding="utf-8",
    )
    (directory / "acme.yml").write_text(
        "id: acme-ws\nstyle: single_call\nprotocol: websocket\ndirection: outbound\n"
        "client_model: acme\n"
        "matches:\n"
        "  owner: com.acme.BuildersKt\n"
        f"  {client_base}\n"
        "  methods: []\n",
        encoding="utf-8",
    )


def test_a_catalog_naming_a_client_model_takes_its_ladder(tmp_path: Path):
    _write_catalog(tmp_path, "client_base: { client_arg: 0 }")
    (catalog,) = YamlCatalogSource(tmp_path).load()
    assert catalog.matches["client_base"]["client_arg"] == 0
    assert catalog.matches["client_base"]["join"] == REPLACE_LAST_SEGMENT


@pytest.mark.pins("ktor.a-client-model-key-cannot-be-COPIED-into-a-catalog")
def test_a_catalog_cannot_copy_a_key_of_its_client_model(tmp_path: Path):
    """The model's `join` declared again in the catalog: two copies of one key, which the
    merge would let the catalog's win silently."""
    _write_catalog(tmp_path, "client_base: { client_arg: 0, join: replace_last_segment }")
    with pytest.raises(CatalogError, match="join"):
        YamlCatalogSource(tmp_path).load()


def test_a_catalog_cannot_omit_its_half_of_the_client_model(tmp_path: Path):
    """No statement of where this catalog's client sits."""
    _write_catalog(tmp_path, "other: 1")
    with pytest.raises(CatalogError, match="client_arg"):
        YamlCatalogSource(tmp_path).load()


def test_an_unknown_client_model_is_refused(tmp_path: Path):
    _write_catalog(tmp_path, "client_base: { client_arg: 0 }")
    text = (tmp_path / "acme.yml").read_text(encoding="utf-8")
    (tmp_path / "acme.yml").write_text(text.replace("client_model: acme", "client_model: x"))
    with pytest.raises(CatalogError, match="client-models"):
        YamlCatalogSource(tmp_path).load()


_ROW = '{ name: ws, arity: 2, descriptor: "(Lcom/acme/Client;Ljava/lang/String;)V", channel_arg: 1'


@pytest.mark.parametrize(
    ("model_extra", "client_base", "row", "named"),
    [
        # A call's `request_url` with no base to join it to.
        ("", "", _ROW + ", request_url: { scheme: ws } }", "client_base"),
        # A scheme the base's `default_ports` does not name: the port cannot be decided.
        (
            "  default_ports: { http: 80 }\n",
            "client_base: { client_arg: 0 }",
            _ROW + ", request_url: { scheme: ws } }",
            "default port",
        ),
        # A `request_url` key the reader does not know.
        (
            "  default_ports: { ws: 80 }\n",
            "client_base: { client_arg: 0 }",
            _ROW + ", request_url: { scheme: ws, host: x } }",
            "request_url",
        ),
        # A port that is no port.
        (
            "  default_ports: { ws: 80 }\n",
            "client_base: { client_arg: 0 }",
            _ROW + ", request_url: { scheme: ws, port: true } }",
            "request_url",
        ),
        # `address_parts` that is not a list of positions.
        ("", "client_base: { client_arg: 0 }", _ROW + ", address_parts: 2 }", "address_parts"),
        ("", "", _ROW + ", address_parts: [] }", "address_parts"),
    ],
)
@pytest.mark.pins("single_call.a-malformed-request-url-or-address-parts-is-refused")
def test_a_malformed_call_row_is_refused_at_load(
    tmp_path: Path, model_extra: str, client_base: str, row: str, named: str
):
    """Every new row word is checked before any call is matched: a `request_url` nothing can
    render, or `address_parts` naming no positions, would otherwise load and silently publish
    an address the call never reaches."""
    _refused(tmp_path, model_extra, client_base, row, named)


def test_a_malformed_port_table_is_refused_at_load(tmp_path: Path):
    """`default_ports` that is not a mapping of schemes to ports, refused by the client base's
    own reader."""
    _refused(
        tmp_path,
        "  default_ports: { ws: eighty }\n",
        "client_base: { client_arg: 0 }",
        _ROW + " }",
        "default_ports",
    )


def _refused(tmp_path: Path, model_extra: str, client_base: str, row: str, named: str) -> None:
    (tmp_path / "client-models").mkdir()
    (tmp_path / "client-models" / "acme.yml").write_text(
        "id: acme\n"
        "client_base:\n"
        "  ladder: [{ owner: com.acme.ClientKt, method: Client, block_arg: 1 }]\n"
        "  setter: { owner: com.acme.Defaults, method: url, value_arg: 0 }\n"
        "  join: replace_last_segment\n"
        "  may_set_base: []\n" + model_extra,
        encoding="utf-8",
    )
    (tmp_path / "acme.yml").write_text(
        "id: acme-ws\nstyle: single_call\nprotocol: websocket\ndirection: outbound\n"
        + ("client_model: acme\n" if client_base else "")
        + "matches:\n"
        "  owner: com.acme.BuildersKt\n"
        + (f"  {client_base}\n" if client_base else "")
        + f"  methods:\n    - {row}\n",
        encoding="utf-8",
    )
    (catalog,) = YamlCatalogSource(tmp_path).load()
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), [])
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    try:
        with pytest.raises(CatalogError, match=named):
            derive_endpoints(workspace, [catalog], capabilities=CAPABILITIES)
    finally:
        workspace.close()
