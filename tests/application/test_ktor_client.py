"""The Ktor HTTP client (`ktor-client.yml`, the `fluent` style; spec 2026-10-26 §3c).

Kotlin inlines every client call, so there is no `get(...)` call to match: the call site
holds the builder sequence itself. CP-54 row group (b), rows 3-15
(`scripts/probes/cp54_ktor_client_ws_sse.md`), measured it for each form:

    new HttpRequestBuilder()                         the root
    [builder.setMethod(HttpMethod.<Verb>)]           non-GET forms with an address only
    HttpRequestKt.url(builder, "…")                  a static extension, receiver arg 0
    builder.setMethod(HttpMethod.<Verb>)
    [builder.setBody(x); builder.setBodyType(…)]     twice each where a body is set
    new HttpStatement(builder, client)               the builder is argument 0
    statement.execute()

The facts below are that sequence as the extractor emits it — read off the probe module's
own scan, value ids and argument kinds included: the builder is one value id throughout,
`url`'s receiver is null with the builder an `instance` argument, and the verb is an
`enum`-kind argument (a static field typed as its own owner, D00 §5).
"""

from pathlib import Path

import pytest
import yaml
from test_call_engines import CATALOGS_DIR, FLUENT_CAPABILITIES, _document, _resolve_fluent

from sextant.application.resolve.call_edges import record_call_edges
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.application.resolve.return_flow import record_return_flows
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import CallArgument, CallSiteFact, CallTarget
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.storage.duckdb.workspace import DuckDbWorkspace

BUILDER = "io/ktor/client/request/HttpRequestBuilder#"
REQUEST_KT = "io/ktor/client/request/HttpRequestKt#"
STATEMENT = "io/ktor/client/statement/HttpStatement#"
HTTP_METHOD = "io/ktor/http/HttpMethod#"

_SET_METHOD = "(Lio/ktor/http/HttpMethod;)V"
_URL = "(Lio/ktor/client/request/HttpRequestBuilder;Ljava/lang/String;)V"
# The parts overload, `url(scheme, host, port, path, block)` (CP-54 row 47 (2)), which the
# `url` step must not read: its argument 1 is the SCHEME.
_URL_PARTS = (
    "(Lio/ktor/client/request/HttpRequestBuilder;Ljava/lang/String;Ljava/lang/String;"
    "Ljava/lang/Integer;Ljava/lang/String;Lkotlin/jvm/functions/Function1;)V"
)
_STATEMENT = "(Lio/ktor/client/request/HttpRequestBuilder;Lio/ktor/client/HttpClient;)V"

# The value id the builder holds for the whole call (the probe module's own scan gave 18).
_B = 18


def _ktor_client():
    return next(c for c in YamlCatalogSource(CATALOGS_DIR).load() if c.id == "ktor-client")


def _site(
    caller: str,
    owner: str,
    name: str,
    descriptor: str,
    ordinal: int,
    receiver: int | None,
    arguments: list[CallArgument],
    invoke_kind: str = "virtual",
    result: int | None = None,
) -> CallSiteFact:
    return CallSiteFact(
        document_id="doc_1",
        caller=caller,
        target=CallTarget(owner=owner, name=name, descriptor=descriptor),
        invoke_kind=invoke_kind,
        ordinal=ordinal,
        receiver=receiver,
        result=result,
        arguments=arguments,
    )


def _verb(name: str) -> CallArgument:
    return CallArgument(kind="enum", symbol=HTTP_METHOD + name + ".")


def _inlined_call(
    caller: str,
    address: str,
    verbs: tuple[str | None, str | None],
    body: CallArgument | None = None,
    issued: bool = True,
    url_descriptor: str = _URL,
    client: CallArgument | None = None,
) -> list[CallSiteFact]:
    """One inlined client call, in CP-54 row (b)'s order. `verbs` is the verb set before
    `url` and the one set after it (None where that `setMethod` is not compiled); `body`
    adds the two `setBody`/`setBodyType` pairs; `issued=False` leaves out the
    `HttpStatement` the builder is handed to; `client` is the `HttpStatement`'s argument 1,
    a field nothing writes unless a test says otherwise."""
    sites: list[CallSiteFact] = []

    def add(owner, name, descriptor, receiver, arguments, invoke_kind="virtual", result=None):
        sites.append(
            _site(
                caller,
                owner,
                name,
                descriptor,
                len(sites),
                receiver,
                arguments,
                invoke_kind,
                result,
            )
        )

    add(BUILDER, "<init>", "()V", _B, [], invoke_kind="special")
    before, after = verbs
    if before is not None:
        add(BUILDER, "setMethod", _SET_METHOD, _B, [_verb(before)])
    add(
        REQUEST_KT,
        "url",
        url_descriptor,
        None,
        [
            CallArgument(kind="instance", source=_B, symbol=BUILDER),
            CallArgument(kind="string", value=address),
        ],
        invoke_kind="static",
    )
    if after is not None:
        add(BUILDER, "setMethod", _SET_METHOD, _B, [_verb(after)])
    for _ in range(2 if body is not None else 0):
        add(BUILDER, "setBody", "(Ljava/lang/Object;)V", _B, [body])
        add(
            BUILDER,
            "setBodyType",
            "(Lio/ktor/util/reflect/TypeInfo;)V",
            _B,
            [CallArgument(kind="null")],
        )
    if issued:
        add(
            STATEMENT,
            "<init>",
            _STATEMENT,
            176,
            [
                CallArgument(kind="instance", source=_B, symbol=BUILDER),
                client or CallArgument(kind="field", symbol="com/acme/kt/ClientKt#client."),
            ],
            invoke_kind="special",
        )
        add(
            STATEMENT,
            "execute",
            "(Lkotlin/coroutines/Continuation;)Ljava/lang/Object;",
            176,
            [CallArgument(kind="parameter", value=0)],
            result=182,
        )
    return sites


def _rows(tmp_path: Path, facts: list[CallSiteFact]) -> list[tuple]:
    workspace = _resolve_fluent(tmp_path, facts, _ktor_client())
    rows = workspace.query("endpoints")
    workspace.close()
    return sorted(
        (
            r["caller"],
            r["direction"],
            r["method"],
            r["peer"],
            r["path"],
            r["resolution"],
            r["request_shape"] is not None,
        )
        for r in rows
    )


def _caller(name: str) -> str:
    return f"com/acme/kt/ClientKt#{name}()."


@pytest.mark.pins("ktor.an-INLINED-client-call-is-an-outbound-row")
def test_a_get_with_an_address_is_an_outbound_get_row(tmp_path: Path):
    """`client.get("https://orders.example.com/orders")` (CP-54 row 3): one outbound GET,
    the absolute address split into peer and path as OkHttp's rows are."""
    facts = _inlined_call(
        _caller("fetch"), "https://orders.example.com/orders", verbs=(None, "Get")
    )
    assert _rows(tmp_path, facts) == [
        (_caller("fetch"), "outbound", "GET", "orders.example.com", "/orders", "resolved", False)
    ]


@pytest.mark.pins("ktor.an-INLINED-client-call-is-an-outbound-row")
def test_a_post_with_a_body_sets_its_verb_twice_and_is_one_post_row(tmp_path: Path):
    """`client.post(url) { setBody(x) }` (CP-54 row 4) sets the verb before `url` and again
    at the end, with the same value, and its body twice. That is one POST row, with the
    body read."""
    facts = _inlined_call(
        _caller("create"),
        "https://orders.example.com/orders",
        verbs=("Post", "Post"),
        body=CallArgument(kind="string", value="x"),
    )
    assert _rows(tmp_path, facts) == [
        (_caller("create"), "outbound", "POST", "orders.example.com", "/orders", "resolved", True)
    ]


def test_a_get_with_the_address_set_in_its_block_is_a_get_row(tmp_path: Path):
    """`client.get { url(u) }` (CP-54 row 11) compiles to the same sequence as row 3."""
    facts = _inlined_call(
        _caller("block"), "https://orders.example.com/blockurl", verbs=(None, "Get")
    )
    assert _rows(tmp_path, facts) == [
        (_caller("block"), "outbound", "GET", "orders.example.com", "/blockurl", "resolved", False)
    ]


def test_a_request_whose_block_sets_the_verb_is_a_row_with_that_verb(tmp_path: Path):
    """`client.request(u) { method = HttpMethod.Put }` (CP-54 row 12): the one `setMethod`
    is the block's, after `url`."""
    facts = _inlined_call(_caller("replace"), "https://orders.example.com/put", verbs=(None, "Put"))
    assert _rows(tmp_path, facts) == [
        (_caller("replace"), "outbound", "PUT", "orders.example.com", "/put", "resolved", False)
    ]


def test_a_prepared_get_is_a_get_row(tmp_path: Path):
    """`client.prepareGet(u).execute()` (CP-54 row 13) builds the same `HttpStatement`."""
    facts = _inlined_call(
        _caller("prepared"), "https://orders.example.com/prepared", verbs=(None, "Get")
    )
    assert _rows(tmp_path, facts) == [
        (
            _caller("prepared"),
            "outbound",
            "GET",
            "orders.example.com",
            "/prepared",
            "resolved",
            False,
        )
    ]


def test_two_differing_verbs_take_the_last_as_ktors_builder_does(tmp_path: Path):
    """`setMethod` is a property setter, so the request carries the value it was set to
    last (DR-6). CP-54 measured the two values equal wherever Ktor sets the verb twice;
    where they ever differ, the last one is the verb."""
    facts = _inlined_call(
        _caller("changed"), "https://orders.example.com/orders", verbs=("Post", "Put")
    )
    assert _rows(tmp_path, facts) == [
        (_caller("changed"), "outbound", "PUT", "orders.example.com", "/orders", "resolved", False)
    ]


def test_a_builder_with_no_verb_set_is_get(tmp_path: Path):
    """A fresh `HttpRequestBuilder`'s verb is GET (CP-54 row 50, read off its constructor
    and run): the root's own capture, standing where no `setMethod` follows."""
    facts = _inlined_call(_caller("bare"), "https://orders.example.com/orders", verbs=(None, None))
    assert _rows(tmp_path, facts) == [
        (_caller("bare"), "outbound", "GET", "orders.example.com", "/orders", "resolved", False)
    ]


@pytest.mark.pins("fluent.a-RELATIVE-address-off-a-client-base-is-unresolved")
def test_a_relative_url_with_no_base_stays_relative_and_unresolved(tmp_path: Path):
    """`client.get("relative/path")` (CP-54 row 14). Ktor joins a relative address onto the
    client's `defaultRequest` base, and this client's construction is not reached: the
    field it is read from has no writer. So the row keeps the relative path it states and
    is `unresolved`, with no peer: the code says which path, not which service. (Ktor's own
    `http://localhost` for a client with no base, CP-54 row 57, is never assumed either,
    D02.)"""
    facts = _inlined_call(_caller("relative"), "relative/path", verbs=(None, "Get"))
    assert _rows(tmp_path, facts) == [
        (_caller("relative"), "outbound", "GET", None, "relative/path", "unresolved", False)
    ]


@pytest.mark.declines("ktor-client")
@pytest.mark.pins("fluent.a-built-request-is-not-an-issued-one")
def test_a_request_builder_never_handed_to_a_statement_derives_nothing(tmp_path: Path):
    """The near-miss: the whole builder sequence, and no `HttpStatement` it is handed to. A
    request assembled and never issued is not a call this module makes."""
    facts = _inlined_call(
        _caller("abandoned"),
        "https://orders.example.com/orders",
        verbs=(None, "Get"),
        issued=False,
    )
    assert _rows(tmp_path, facts) == []


@pytest.mark.declines("ktor-client")
@pytest.mark.pins("ktor.the-url-step-reads-only-the-STRING-overload")
def test_the_url_parts_overload_is_not_read_as_an_address(tmp_path: Path):
    """`url(scheme, host, port, path, block)` (CP-54 row 47 (2)) shares the name `url`, and
    its argument 1 is the scheme. Read as the address, the row would call `https`; the step
    is narrowed to the `(HttpRequestBuilder, String)` overload, so this row carries no
    address — `path` NULL at `unresolved` (the parts form is not assembled, spec §3g)."""
    facts = _inlined_call(_caller("parts"), "https", verbs=(None, "Get"), url_descriptor=_URL_PARTS)
    assert _rows(tmp_path, facts) == [
        (_caller("parts"), "outbound", "GET", None, None, "unresolved", False)
    ]


def _verb_field_tables(node: object) -> list[dict]:
    """Every `verb_values.fields` table in a catalog document, wherever it sits."""
    if isinstance(node, list):
        return [table for item in node for table in _verb_field_tables(item)]
    if not isinstance(node, dict):
        return []
    tables = [table for value in node.values() for table in _verb_field_tables(value)]
    verb_values = node.get("verb_values")
    if isinstance(verb_values, dict) and "fields" in verb_values:
        tables.append(verb_values["fields"])
    return tables


def test_the_routing_and_client_catalogs_spell_one_verb_field_table():
    """`HttpMethod`'s nine static fields are spelled twice, once in `ktor-routing.yml` and
    once in `ktor-client.yml`, because each catalog keeps its own `verb_values`. Both say
    which verb the same Ktor field is, so they must agree entry for entry: an edit to one
    alone reads `HttpMethod.Query` as a verb on one side of a call and as nothing on the
    other. Removing the copy is logged for later; until then this pins the two equal."""
    tables = {
        name: _verb_field_tables(yaml.safe_load((CATALOGS_DIR / name).read_text(encoding="utf-8")))
        for name in ("ktor-routing.yml", "ktor-client.yml")
    }
    routing, client = tables["ktor-routing.yml"], tables["ktor-client.yml"]
    assert routing and client, tables
    assert all(table == client[0] for table in [*routing, *client]), tables
    assert len(client[0]) == 9, client[0]


def _branched_address(caller: str) -> list[CallSiteFact]:
    """`client.get("https://orders.example.com/v1" + (if (c) "/a" else "/b"))`: the url is a
    concat (value 90) whose one operand is a branch between two literals."""
    sites = _inlined_call(caller, "unused", verbs=(None, "Get"))
    url = next(site for site in sites if site.target.name == "url")
    url.arguments[1] = CallArgument(
        kind="concat", source=90, value="https://orders.example.com/v1{}"
    )
    branch = CallArgument(
        kind="merge",
        candidates=[
            CallArgument(kind="string", value="/a"),
            CallArgument(kind="string", value="/b"),
        ],
    )
    return [
        *sites,
        _site(
            caller,
            "java/lang/invoke/StringConcatFactory#",
            "makeConcatWithConstants",
            "(Ljava/lang/String;)Ljava/lang/String;",
            len(sites),
            None,
            [branch],
            invoke_kind="static",
            result=90,
        ),
    ]


@pytest.mark.pins("fluent.a-BRANCHED-assembled-address-keeps-its-unfilled-template")
def test_a_branched_assembled_address_keeps_the_template_it_published_before(tmp_path: Path):
    """Ruling 7 lists `/v1/a` and `/v1/b`, each `narrowed`, and this engine carries ONE
    address per chain (`OI-134`). The walk may never take an answer away, so the chain keeps
    what it published before the branch was listed: the template with that hole unfilled,
    at `partial`."""
    caller = _caller("branched")
    workspace = _resolve_walked_fluent(tmp_path, _branched_address(caller))
    rows = sorted(
        (r["method"], r["peer"], r["path"], r["resolution"])
        for r in workspace.query("endpoints")
        if r["caller"] == caller
    )
    workspace.close()
    assert rows == [("GET", "orders.example.com", "/v1{}", "partial")]


def _resolve_walked_fluent(tmp_path: Path, facts: list[CallSiteFact]):
    """`_resolve_fluent` with the derived tables the walk's edges read built first."""
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    record_return_flows(workspace)
    record_call_edges(workspace)
    assert derive_endpoints(workspace, [_ktor_client()], capabilities=FLUENT_CAPABILITIES) == []
    return workspace
