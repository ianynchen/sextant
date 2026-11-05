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

from flow_facts import straight_line
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
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), straight_line(facts))
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    record_return_flows(workspace)
    record_call_edges(workspace)
    assert derive_endpoints(workspace, [_ktor_client()], capabilities=FLUENT_CAPABILITIES) == []
    return workspace


# A Kotlin `suspend` function with a suspension that is not its last call compiles to a
# coroutine state machine: its resume branch (`label == 1`) goes straight to the code after the
# suspension, so no call made before it runs on every path to the method's exit. Every Ktor call
# that a later line uses (`val r = client.post(u) { … }; return r.bodyAsText()`) has this shape
# (measured on kotlinconf-app and ktor-samples' client-mpp, 2026-11-05). The tests below state
# it: the straight line's positions with `on_every_exit` False, and the calls in `branched` on
# branches that rejoin after them (the `when (body)` that Ktor's inline `setBody` compiles to).


def _in_a_coroutine(facts: list[CallSiteFact], branched: frozenset[int] = frozenset()) -> list:
    """`facts` with the positions a coroutine body gives them (see above). A call in
    `branched` is dominated by the call before it; any other call by the nearest earlier call
    not in `branched`."""
    placed = []
    for fact in straight_line(facts):
        earlier = [ordinal for ordinal in range(fact.ordinal) if ordinal not in branched]
        dominator = fact.ordinal - 1 if fact.ordinal in branched else max(earlier, default=None)
        placed.append(
            fact.model_copy(
                update={"dominator": dominator if fact.ordinal else None, "on_every_exit": False}
            )
        )
    return placed


def _raw_rows(tmp_path: Path, facts: list) -> list[tuple]:
    """`_rows`, for facts that already carry their positions: every row, duplicates kept."""
    write_fact_file(tmp_path / "facts" / "Client.jsonl", _document(), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    assert derive_endpoints(workspace, [_ktor_client()], capabilities=FLUENT_CAPABILITIES) == []
    rows = workspace.query("endpoints")
    workspace.close()
    return sorted(
        (r["method"], r["peer"], r["path"], r["resolution"], r["request_shape"] is not None)
        for r in rows
    )


@pytest.mark.pins("chains.a-chain-is-decided-at-the-call-that-SENDS-it")
def test_a_post_in_a_coroutine_body_is_one_post_row(tmp_path: Path):
    """`val r = client.post(u) { setBody(x) }; return r.bodyAsText()`. No call runs on every
    path to the method's exit, but every one runs on every path to `new HttpStatement(builder,
    client)`, the call that sends the request (ruled by the user 2026-11-05). So nothing
    splits: one POST row, `resolved`, with its body. Measured against the exit, every step
    "may not have run", and the paths that skip `setMethod(Post)` keep the builder's default
    GET, a request this code never sends."""
    facts = _inlined_call(
        _caller("create"),
        "https://orders.example.com/orders",
        verbs=("Post", "Post"),
        body=CallArgument(kind="string", value="x"),
    )
    assert _raw_rows(tmp_path, _in_a_coroutine(facts)) == [
        ("POST", "orders.example.com", "/orders", "resolved", True)
    ]


@pytest.mark.pins("fluent.the-PATHS-of-one-call-are-one-row")
def test_the_paths_of_one_call_with_no_path_are_one_row(tmp_path: Path):
    """The same POST with its address not read (`path` NULL) and its two `setBody` calls on
    branches: two counted splits, so four paths (neither, one, the other, both), which differ
    only in the body. One call is one row (ruled by the user 2026-11-05), and paths that differ
    only in a published part are ONE row, no surer than `partial` (round 4, ruled by the user
    2026-11-03). The address is not read, so the row is `unresolved`, which is weaker."""
    facts = _inlined_call(
        _caller("create"),
        "https",
        verbs=("Post", "Post"),
        body=CallArgument(kind="string", value="x"),
        url_descriptor=_URL_PARTS,
    )
    rows = _raw_rows(tmp_path, _in_a_coroutine(facts, frozenset({4, 5, 6, 7})))
    assert [row[:4] for row in rows] == [("POST", None, None, "unresolved")], rows


@pytest.mark.pins("fluent.a-VERB-on-a-branch-of-one-call-stays-a-row-per-verb")
def test_a_verb_set_on_a_branch_of_one_call_with_no_path_is_a_row_per_verb(tmp_path: Path):
    """`client.request("…") { if (x) method = HttpMethod.Put }` with its address not read: the
    one `setMethod(Put)` is on a branch, so one path sends PUT and the other the builder's
    GET. The verb identifies a row, so the merge of one call's paths keeps a row per verb
    (controller ruling I-2 of the 2026-11-05 fix review)."""
    facts = _inlined_call(_caller("maybe"), "https", verbs=(None, "Put"), url_descriptor=_URL_PARTS)
    rows = _raw_rows(tmp_path, _in_a_coroutine(facts, frozenset({2})))
    assert [row[:4] for row in rows] == [
        ("GET", None, None, "unresolved"),
        ("PUT", None, None, "unresolved"),
    ], rows


def _second_call(facts: list[CallSiteFact]) -> list[CallSiteFact]:
    """`facts` and a second copy of the call after it in the same method: its own builder
    (value 19) and statement (value 177), its ordinals after the first call's."""
    moved = len(facts)
    renumbered = {_B: 19, 176: 177, 182: 183}
    copies = []
    for fact in facts:
        arguments = [
            argument.model_copy(update={"source": renumbered.get(argument.source)})
            if argument.source is not None
            else argument
            for argument in fact.arguments
        ]
        copies.append(
            fact.model_copy(
                update={
                    "ordinal": fact.ordinal + moved,
                    "receiver": renumbered.get(fact.receiver, fact.receiver),
                    "result": renumbered.get(fact.result, fact.result),
                    "arguments": arguments,
                }
            )
        )
    return [*facts, *copies]


@pytest.mark.declines("ktor-client")
@pytest.mark.pins("fluent.the-exact-merge-is-keyed-on-the-CALL")
def test_two_calls_with_no_path_in_one_method_stay_two_rows(tmp_path: Path):
    """The near-miss of the merge: two calls in one method, neither address read. Their rows
    read the same, but they are two requests (two builders, two sends), so they stay two
    rows."""
    facts = _inlined_call(_caller("twice"), "https", verbs=(None, "Get"), url_descriptor=_URL_PARTS)
    assert _raw_rows(tmp_path, _in_a_coroutine(_second_call(facts))) == [
        ("GET", None, None, "unresolved", False),
        ("GET", None, None, "unresolved", False),
    ]


@pytest.mark.pins("chains.each-SEND-of-one-request-is-measured-on-its-own")
def test_one_request_sent_from_two_places_is_measured_at_each_send(tmp_path: Path):
    """`b = HttpRequestBuilder(); b.method = Post; b.url(primary); HttpStatement(b,
    client).execute(); if (ok) return; b.url(mirror); HttpStatement(b, client).execute()`: one
    builder, sent from two places. Each send is measured on its own (M9, ruled by the user
    2026-11-05, option A): the first sends to the primary address (the mirror `url` runs after
    it), the second to the mirror (both `url` calls run before it, and the last wins). One row
    per send, each `resolved`."""
    caller = _caller("failover")
    builder = CallArgument(kind="instance", source=_B, symbol=BUILDER)
    client = CallArgument(kind="field", symbol="com/acme/kt/ClientKt#client.")

    def url(ordinal: int, address: str) -> CallSiteFact:
        return _site(
            caller,
            REQUEST_KT,
            "url",
            _URL,
            ordinal,
            None,
            [builder, CallArgument(kind="string", value=address)],
            invoke_kind="static",
        )

    def send(ordinal: int, statement: int) -> list[CallSiteFact]:
        return [
            _site(
                caller,
                STATEMENT,
                "<init>",
                _STATEMENT,
                ordinal,
                statement,
                [builder, client],
                invoke_kind="special",
            ),
            _site(
                caller,
                STATEMENT,
                "execute",
                "(Lkotlin/coroutines/Continuation;)Ljava/lang/Object;",
                ordinal + 1,
                statement,
                [CallArgument(kind="parameter", value=0)],
                result=statement + 6,
            ),
        ]

    facts = [
        _site(caller, BUILDER, "<init>", "()V", 0, _B, [], invoke_kind="special"),
        _site(caller, BUILDER, "setMethod", _SET_METHOD, 1, _B, [_verb("Post")]),
        url(2, "https://orders.example.com/orders"),
        *send(3, 176),
        url(5, "https://mirror.example.com/orders"),
        *send(6, 177),
    ]
    assert _raw_rows(tmp_path, _in_a_coroutine(facts)) == [
        ("POST", "mirror.example.com", "/orders", "resolved", False),
        ("POST", "orders.example.com", "/orders", "resolved", False),
    ]
