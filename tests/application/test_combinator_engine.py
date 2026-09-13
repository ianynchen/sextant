"""Tests for the `combinator` engine (D02 §2's `combinator` style) — the fold
over a router TREE, where predicate arguments link to their producing calls
through `source`, chains link through `result` → `receiver`, and a nested body
arrives as a `lambda`-kind argument naming the method that holds it.

Facts are hand-built to mirror the *real* emitted grammar exactly — every
`owner`/`name`/`invoke_kind`/`ordinal`/`receiver`/`result`/`arguments` shape
here is the one this phase's checkpoint froze against a live scan (items (1a)
and (1b)), down to the compiler noise the walk has to step over: the
`requireNonNull` javac emits beside every bound method reference, the indy site
whose own arguments are opaque, the DSL body's null-check preamble. The
framework the checkpoint scanned is deliberately NOT the one named here — the
catalog below is invented, because an engine that only works for one library's
fqns is the thing spec §1d forbids.

CHECKPOINT FACT, pinned by (1a): a predicate argument arrives
`{"kind":"unresolved","source":<producing call's result>}` — never carrying
the predicate itself — so every constraint in a tree is reached by following
`source`, and a bound method reference arrives as a `lambda`-kind argument
whose `symbol` is the real target method, BARE.
CHECKPOINT FACT, pinned by (1b): a DSL body lands in a synthetic method of its
own, its calls carry `receiver: null` and (mostly) `result: null`, and the
entry-to-body and nest-to-body edges are both `lambda`-kind arguments naming
that method's symbol exactly.
CHECKPOINT FACT, pinned by (3)/F1 and CORRECTED by extractor capability 9.15: a
vararg media constant reaches the facts as ONE `{"kind":"array"}` slot carrying
its own `elements`, each the `enum` it would have been as a single argument.
*That sentence read "as a bare `{"kind":"unresolved"}` with no symbol at all",
which was the pre-9.15 fact and the reason every predicate-derived media column
came back NULL.* A bare `unresolved` is now what an array the extractor could
not read END TO END degrades to (9.15's five rejection rules), and that case is
pinned beside the readable one.
"""

from pathlib import Path

import pytest

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import CallArgument, CallSiteFact, CallTarget, Document, SymbolFact
from sextant.storage.duckdb.workspace import DuckDbWorkspace

# `array_arguments` (capability 9.15) is granted because the real scanner declares it and
# these sets are a real SUBSET of that. *It was added when four catalogs briefly declared
# it in `requires:`; that declaration is reverted (W46's review — it turned a graceful
# degradation into a total skip), so nothing here depends on it now. Kept because the
# varargs reads it feeds are real and a harness that withheld it would be measuring a
# scanner nobody ships.*
CAPABILITIES = {"call_site", "string_constants", "chain_reconstruction", "array_arguments"}
# The module-coordinates prefix a real symbol fact's own `symbol` carries (D00
# §5a); every call-argument symbol stays bare, exactly as the real facts emit
# it (`test_call_engines.py`'s own `_MODULE` precedent).
_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "

# The invented library. `ROUTERS` (static entry calls) and `PREDICATE_TYPE`
# (the composers) and `ROUTER_TYPE` (the chain continuations) are three
# different owners for the same tree, which is exactly the shape the checkpoint
# froze; `DSL_FACADE` and `DSL` are the body-linked entry's own pair, and the
# checkpoint's whole point about them is that they are NOT the same fqn.
ROUTERS = "com/example/web/Routers#"
PREDICATES = "com/example/web/Predicates#"
PREDICATE_TYPE = "com/example/web/Predicate#"
ROUTER_TYPE = "com/example/web/Router#"
DSL_FACADE = "com/example/web/RouterDslFacade#"
DSL = "com/example/web/RouterDsl#"
MEDIA_TYPE = "com/example/web/MediaType#"

HANDLERS = "com/example/routes/Handlers#"
LIST_ORDERS = HANDLERS + "listOrders(sig_a1)."
CREATE_ORDER = HANDLERS + "createOrder(sig_a1)."
HEALTH = HANDLERS + "health(sig_a1)."
DECLARER = "com/example/routes/Routes#"
INLINE_BODY = DECLARER + "lambda$routes$0(sig_a1)."
HANDLER_CLASS = "com/example/routes/Routes$1#"

ROUTES = DECLARER + "routes(sig_r0)."
DSL_ROUTES = DECLARER + "dslRoutes(sig_r0)."
DSL_BODY = DECLARER + "dslRoutes$body(sig_b1)."
DSL_CHILD = DECLARER + "dslRoutes$body$child(sig_b1)."
DSL_GRANDCHILD = DECLARER + "dslRoutes$body$child$leaf(sig_b1)."

JSON = "application/json"
XML = "application/xml"


def _document(document_id: str = "doc_1") -> Document:
    return Document(
        document_id=document_id,
        relative_path="com/example/routes/Routes.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )


def _site(
    caller: str,
    ordinal: int,
    owner: str,
    name: str,
    *,
    arguments: list[CallArgument] | None = None,
    receiver: int | None = None,
    result: int | None = None,
    invoke_kind: str = "static",
    descriptor: str = "(...)V",
) -> CallSiteFact:
    return CallSiteFact(
        document_id="doc_1",
        caller=caller,
        target=CallTarget(owner=owner, name=name, descriptor=descriptor),
        invoke_kind=invoke_kind,
        ordinal=ordinal,
        receiver=receiver,
        result=result,
        arguments=list(arguments or []),
    )


def _method_symbol(bare: str) -> SymbolFact:
    """The method symbol fact a `handler` joins back to — module-prefixed
    exactly as a real one is (D00 §5a). Without it in the workspace no scanned
    document declares that method, and the handler reads NULL rather than
    being concatenated into existence."""
    return SymbolFact(
        document_id="doc_1", symbol=_MODULE + bare, construct_kind=ConstructKind.METHOD
    )


def _handler_symbols() -> list[SymbolFact]:
    return [
        _method_symbol(LIST_ORDERS),
        _method_symbol(CREATE_ORDER),
        _method_symbol(HEALTH),
        _method_symbol(INLINE_BODY),
    ]


def _matches() -> dict[str, object]:
    return {
        "entries": [
            {"owner": "com.example.web.Routers", "methods": ["route", "nest"], "handler_arg": 1},
            {"owner": "com.example.web.RouterDslFacade", "method": "router", "body_arg": 0},
        ],
        "vocabulary": {
            "verbs": [
                {
                    "owner": "com.example.web.Predicates",
                    "method": "GET",
                    "verb": "GET",
                    "path_arg": 0,
                },
                {
                    "owner": "com.example.web.Predicates",
                    "method": "HEAD",
                    "verb": "HEAD",
                    "path_arg": 0,
                },
                {
                    "owner": "com.example.web.Predicates",
                    "method": "POST",
                    "verb": "POST",
                    "path_arg": 0,
                },
                {
                    "owner": "com.example.web.RouterDsl",
                    "method": "GET",
                    "verb": "GET",
                    "path_arg": 0,
                    "handler_arg": 1,
                },
            ],
            "prefixes": [
                {"owner": "com.example.web.Predicates", "method": "path", "path_arg": 0},
                {
                    "owner": "com.example.web.Routers",
                    "method": "nest",
                    "path_arg": 0,
                    "subtree_arg": 1,
                },
                {
                    "owner": "com.example.web.RouterDsl",
                    "method": "nest",
                    "path_arg": 0,
                    "body_arg": 1,
                },
            ],
            "media": [
                {"owner": "com.example.web.Predicates", "method": "accept", "fills": "produces"},
                {
                    "owner": "com.example.web.Predicates",
                    "method": "contentType",
                    "fills": "consumes",
                },
                {"owner": "com.example.web.RouterDsl", "method": "accept", "fills": "produces"},
            ],
            "media_values": {
                "owner": "com.example.web.MediaType",
                "values": {"APPLICATION_JSON": JSON, "APPLICATION_XML": XML},
            },
            "composers": {
                "and": [{"owner": "com.example.web.Predicate", "method": "and"}],
                "or": [{"owner": "com.example.web.Predicate", "method": "or"}],
            },
        },
        # All three forms the grammar allows, and each is load-bearing here.
        # `andRoute`/`and` are owner-qualified because they END chains, and only
        # an owner-declaring continuation may root one; `andNest` is the
        # nest-shaped form, whose second argument is a whole router rather than
        # a handler; `withRoute` is the owner-free form, which extends a walk
        # from a real root and never roots one itself. `and` is deliberately
        # ALSO a composer method — on a different owner — which is the frozen
        # reality of a real predicate/router pair (checkpoint (1a)).
        "continuations": [
            {"name": "andRoute", "owner": "com.example.web.Router"},
            {"name": "andNest", "owner": "com.example.web.Router", "path_arg": 0, "subtree_arg": 1},
            {"name": "and", "owner": "com.example.web.Router"},
            "withRoute",
        ],
    }


def _catalog(matches: dict[str, object] | None = None) -> Catalog:
    return Catalog(
        id="test-functional-routing",
        style="combinator",
        protocol="http",
        direction="inbound",
        requires=("call_site", "string_constants", "chain_reconstruction"),
        matches=_matches() if matches is None else matches,
        source=Path("test-functional-routing.yml"),
    )


def _resolve(tmp_path: Path, facts: list, catalog: Catalog | None = None) -> DuckDbWorkspace:
    write_fact_file(tmp_path / "facts" / "Routes.jsonl", _document(), facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    skipped = derive_endpoints(workspace, [catalog or _catalog()], capabilities=CAPABILITIES)
    assert skipped == []
    return workspace


def _rows(workspace: DuckDbWorkspace) -> list[dict]:
    return [dict(row) for row in workspace.query("endpoints")]


def _identities(rows: list[dict]) -> list[tuple]:
    """Every row's own identity, in the `endpoints` query's own total order
    (`protocol, method, path, handler, caller` — NFR-1), so an assertion below
    reads as the SET of rows the fold derived rather than as the order the
    engine happened to append them in."""
    return [(row["method"], row["path"], row["handler"], row["resolution"]) for row in rows]


# --- (1) one static route call is one resolved endpoint -------------------


def test_a_static_route_call_derives_one_resolved_endpoint_with_its_handler(tmp_path: Path):
    """The whole style in one tree: the predicate argument is followed through
    `source` to the call that produced it, the verb and path come off that
    call, and the handler is the method the `lambda`-kind argument names —
    joined to a real symbol fact, never concatenated. The two compiler-emitted
    noise calls beside it (checkpoint (1a) ruling 5) must change nothing: no
    catalog rule claims their owners, so they are neither rooted nor
    consumed."""
    facts = [
        _site(
            ROUTES,
            0,
            PREDICATES,
            "GET",
            result=3,
            arguments=[CallArgument(kind="string", value="/x")],
        ),
        _site(
            ROUTES,
            1,
            "java/util/Objects#",
            "requireNonNull",
            result=20,
            arguments=[CallArgument(kind="unresolved")],
        ),
        _site(
            ROUTES,
            2,
            "java/lang/invoke/LambdaMetafactory#",
            "handle",
            result=22,
            invoke_kind="dynamic",
        ),
        _site(
            ROUTES,
            3,
            ROUTERS,
            "route",
            result=25,
            arguments=[
                CallArgument(kind="unresolved", source=3),
                CallArgument(kind="lambda", source=22, symbol=LIST_ORDERS),
            ],
        ),
        *_handler_symbols(),
    ]
    workspace = _resolve(tmp_path, facts)
    rows = _rows(workspace)
    workspace.close()

    assert len(rows) == 1
    [row] = rows
    assert (row["protocol"], row["direction"]) == ("http", "inbound")
    assert (row["method"], row["path"]) == ("GET", "/x")
    assert row["handler"] == _MODULE + LIST_ORDERS
    assert row["resolution"] == "resolved"
    assert row["evidence"] == "compiler"
    assert row["catalog_id"] == "test-functional-routing"
    assert row["caller"] == ROUTES
    assert row["peer"] is None
    # spec §1c: a functional handler's payloads live inside its body, so both
    # shape columns stay honestly NULL rather than being guessed from the
    # `ServerRequest`-shaped signature every handler shares.
    assert (row["request_shape"], row["response_shape"]) == (None, None)


# --- (2) a nest prefix folds onto every route of its subtree ---------------


def test_a_nest_prefix_folds_onto_every_route_of_its_subtree_exactly_once(tmp_path: Path):
    """The prefix is pushed onto the whole subtree, and — the half that is easy
    to get wrong — the subtree is NOT also derived bare. The inner `route` is
    consumed as the chain's receiver and the chain's own result is consumed as
    the nest's subtree argument, so the only tree root in the method is the
    nest itself."""
    facts = [
        _site(
            ROUTES,
            0,
            PREDICATES,
            "path",
            result=3,
            arguments=[CallArgument(kind="string", value="/fn")],
        ),
        _site(
            ROUTES,
            1,
            PREDICATES,
            "GET",
            result=7,
            arguments=[CallArgument(kind="string", value="/a")],
        ),
        _site(
            ROUTES,
            2,
            ROUTERS,
            "route",
            result=25,
            arguments=[
                CallArgument(kind="unresolved", source=7),
                CallArgument(kind="lambda", symbol=LIST_ORDERS),
            ],
        ),
        _site(
            ROUTES,
            3,
            PREDICATES,
            "GET",
            result=30,
            arguments=[CallArgument(kind="string", value="/b")],
        ),
        _site(
            ROUTES,
            4,
            ROUTER_TYPE,
            "andRoute",
            receiver=25,
            result=40,
            invoke_kind="interface",
            arguments=[
                CallArgument(kind="unresolved", source=30),
                CallArgument(kind="lambda", symbol=CREATE_ORDER),
            ],
        ),
        _site(
            ROUTES,
            5,
            ROUTERS,
            "nest",
            result=59,
            arguments=[
                CallArgument(kind="unresolved", source=3),
                CallArgument(kind="unresolved", source=40),
            ],
        ),
        *_handler_symbols(),
    ]
    workspace = _resolve(tmp_path, facts)
    rows = _rows(workspace)
    workspace.close()

    assert _identities(rows) == [
        ("GET", "/fn/a", _MODULE + LIST_ORDERS, "resolved"),
        ("GET", "/fn/b", _MODULE + CREATE_ORDER, "resolved"),
    ]


def test_a_slashless_route_and_a_doubled_seam_both_derive_the_url_spring_serves(
    tmp_path: Path,
):
    """2O design §8 / ruling R8, on the ONE live catalog that reaches this seam
    outside `annotation_driven`: `spring-webflux-router.yml` is a combinator,
    `http`, and INBOUND, so its composed routes are URLs this module serves and
    their identity is the URL the framework answers at.

    Both halves of the canonicalization are exercised here because the router
    DSL composes `path_parts` by bare concatenation — there is no separator
    seam in this style to hide either one:

    * `RouterFunctions.route(GET("orders"), …)` is served at `/orders`. Spring
      combines the predicate path the same way it combines a mapping (CP-1,
      confirmed live), so recording `orders` would be a second identity for one
      URL — the split this seam exists to close.
    * a `nest("/")` prefix over a `GET("/chat")` route composes `//chat` by
      concatenation, and is served at `/chat`. That is the second live failure
      D02's prefix-seam note records, reached here by the other style.

    Deleting the `canonical_http_path` call in `_path_of` passes every other
    test in this file — every other fixture path already spells its leading
    separator — so this case is the whole of what pins it.
    """
    facts = [
        _site(
            ROUTES,
            0,
            PREDICATES,
            "GET",
            result=3,
            arguments=[CallArgument(kind="string", value="orders")],
        ),
        _site(
            ROUTES,
            1,
            ROUTERS,
            "route",
            result=25,
            arguments=[
                CallArgument(kind="unresolved", source=3),
                CallArgument(kind="lambda", symbol=LIST_ORDERS),
            ],
        ),
        _site(
            ROUTES,
            2,
            PREDICATES,
            "path",
            result=30,
            arguments=[CallArgument(kind="string", value="/")],
        ),
        _site(
            ROUTES,
            3,
            PREDICATES,
            "GET",
            result=34,
            arguments=[CallArgument(kind="string", value="/chat")],
        ),
        _site(
            ROUTES,
            4,
            ROUTERS,
            "route",
            result=40,
            arguments=[
                CallArgument(kind="unresolved", source=34),
                CallArgument(kind="lambda", symbol=CREATE_ORDER),
            ],
        ),
        _site(
            ROUTES,
            5,
            ROUTERS,
            "nest",
            result=59,
            arguments=[
                CallArgument(kind="unresolved", source=30),
                CallArgument(kind="unresolved", source=40),
            ],
        ),
        *_handler_symbols(),
    ]
    workspace = _resolve(tmp_path, facts)
    rows = _rows(workspace)
    workspace.close()

    assert _identities(rows) == [
        ("GET", "/chat", _MODULE + CREATE_ORDER, "resolved"),
        ("GET", "/orders", _MODULE + LIST_ORDERS, "resolved"),
    ]


# --- (3) `or` duplicates the route per branch, over any predicate kind -----


def test_or_over_verbs_duplicates_the_route_and_over_media_unions_into_one_row(
    tmp_path: Path,
):
    """`or` fans a route out per branch over ANY predicate kind (spec §1a's
    `all_methods` precedent) — but two branches that differ ONLY in the media
    they declare are one endpoint, not two, so the batch unions them before it
    is ever inserted (spec §4, the same rule the annotation pass applies in
    SQL). Two verbs on one path stay two rows; two media types on one route
    become one row with both."""
    verbs = ROUTES
    media = DECLARER + "mediaRoutes(sig_r0)."
    facts = [
        _site(
            verbs,
            0,
            PREDICATES,
            "GET",
            result=51,
            arguments=[CallArgument(kind="string", value="/health")],
        ),
        _site(
            verbs,
            1,
            PREDICATES,
            "HEAD",
            result=53,
            arguments=[CallArgument(kind="string", value="/health")],
        ),
        _site(
            verbs,
            2,
            PREDICATE_TYPE,
            "or",
            receiver=51,
            result=54,
            invoke_kind="interface",
            arguments=[CallArgument(kind="unresolved", source=53)],
        ),
        _site(
            verbs,
            3,
            ROUTERS,
            "route",
            result=56,
            arguments=[
                CallArgument(kind="unresolved", source=54),
                CallArgument(kind="lambda", symbol=INLINE_BODY),
            ],
        ),
        _site(
            media,
            0,
            PREDICATES,
            "GET",
            result=5,
            arguments=[CallArgument(kind="string", value="/m")],
        ),
        _site(
            media,
            1,
            PREDICATES,
            "accept",
            result=10,
            arguments=[CallArgument(kind="enum", symbol=MEDIA_TYPE + "APPLICATION_JSON.")],
        ),
        _site(
            media,
            2,
            PREDICATES,
            "accept",
            result=12,
            arguments=[CallArgument(kind="enum", symbol=MEDIA_TYPE + "APPLICATION_XML.")],
        ),
        _site(
            media,
            3,
            PREDICATE_TYPE,
            "or",
            receiver=10,
            result=14,
            invoke_kind="interface",
            arguments=[CallArgument(kind="unresolved", source=12)],
        ),
        _site(
            media,
            4,
            PREDICATE_TYPE,
            "and",
            receiver=5,
            result=16,
            invoke_kind="interface",
            arguments=[CallArgument(kind="unresolved", source=14)],
        ),
        _site(
            media,
            5,
            ROUTERS,
            "route",
            result=20,
            arguments=[
                CallArgument(kind="unresolved", source=16),
                CallArgument(kind="lambda", symbol=HEALTH),
            ],
        ),
        *_handler_symbols(),
    ]
    workspace = _resolve(tmp_path, facts)
    rows = _rows(workspace)
    workspace.close()

    by_path = {row["path"]: row for row in rows}
    assert sorted(_identities([row for row in rows if row["path"] == "/health"])) == [
        ("GET", "/health", _MODULE + INLINE_BODY, "resolved"),
        ("HEAD", "/health", _MODULE + INLINE_BODY, "resolved"),
    ]
    assert len([row for row in rows if row["path"] == "/m"]) == 1
    assert by_path["/m"]["produces"] == f'["{JSON}","{XML}"]'
    assert by_path["/m"]["method"] == "GET"
    assert by_path["/m"]["resolution"] == "resolved"


# --- (4) `and` merges constraints onto one row ----------------------------


def test_and_merges_verb_path_and_media_into_a_single_row(tmp_path: Path):
    """`and` is the merge half of the composer pair: the verb, the path and the
    media predicate reached through it all land on one route, and the media
    column the rule declares (`contentType` fills `consumes`, never
    `produces`) is the one that fills."""
    facts = [
        _site(
            ROUTES,
            0,
            PREDICATES,
            "POST",
            result=29,
            arguments=[CallArgument(kind="string", value="/orders")],
        ),
        _site(
            ROUTES,
            1,
            PREDICATES,
            "contentType",
            result=38,
            arguments=[CallArgument(kind="enum", symbol=MEDIA_TYPE + "APPLICATION_JSON.")],
        ),
        _site(
            ROUTES,
            2,
            PREDICATE_TYPE,
            "and",
            receiver=29,
            result=39,
            invoke_kind="interface",
            arguments=[CallArgument(kind="unresolved", source=38)],
        ),
        _site(
            ROUTES,
            3,
            ROUTERS,
            "route",
            result=47,
            arguments=[
                CallArgument(kind="unresolved", source=39),
                CallArgument(kind="lambda", symbol=CREATE_ORDER),
            ],
        ),
        *_handler_symbols(),
    ]
    workspace = _resolve(tmp_path, facts)
    [row] = _rows(workspace)
    workspace.close()

    assert (row["method"], row["path"]) == ("POST", "/orders")
    assert row["consumes"] == f'["{JSON}"]'
    assert row["produces"] is None
    assert row["resolution"] == "resolved"


def test_a_string_kind_media_argument_reads_as_its_literal_value(tmp_path: Path):
    """`_media_value`'s `string` branch — some frameworks spell their media
    type inline rather than through an enum constant — is otherwise
    untested: every other media fact in this file arrives `enum`-kind. Built
    the same way as the `and`-merge test above, but the `accept` predicate
    here carries a bare string literal instead of a `MediaType` constant."""
    facts = [
        _site(
            ROUTES,
            0,
            PREDICATES,
            "GET",
            result=3,
            arguments=[CallArgument(kind="string", value="/orders")],
        ),
        _site(
            ROUTES,
            1,
            PREDICATES,
            "accept",
            result=5,
            arguments=[CallArgument(kind="string", value=JSON)],
        ),
        _site(
            ROUTES,
            2,
            PREDICATE_TYPE,
            "and",
            receiver=3,
            result=7,
            invoke_kind="interface",
            arguments=[CallArgument(kind="unresolved", source=5)],
        ),
        _site(
            ROUTES,
            3,
            ROUTERS,
            "route",
            result=9,
            arguments=[
                CallArgument(kind="unresolved", source=7),
                CallArgument(kind="lambda", symbol=LIST_ORDERS),
            ],
        ),
        *_handler_symbols(),
    ]
    workspace = _resolve(tmp_path, facts)
    [row] = _rows(workspace)
    workspace.close()

    assert (row["method"], row["path"]) == ("GET", "/orders")
    assert row["produces"] == f'["{JSON}"]'
    assert row["resolution"] == "resolved"


def test_a_vararg_media_arrays_elements_fill_the_media_column(tmp_path: Path):
    """The shape a REAL media predicate compiles to, and the one this engine
    could not read until 2O Task 13: `accept(MediaType...)` is varargs, so
    every constant the author wrote arrives inside ONE `array` slot rather
    than as one argument each.

    Two elements, deliberately: a one-element array would pass even for a
    reader that mistook the array slot itself for a single value, and the
    column is a distinct sorted UNION, so both spellings have to survive the
    read to reach it. `_media_value` translates each element through the
    catalog's own `media_values` table exactly as it already does for a
    non-vararg constant — the array changes where the constants live, not what
    they mean.
    """
    facts = [
        _site(
            ROUTES,
            0,
            PREDICATES,
            "GET",
            result=3,
            arguments=[CallArgument(kind="string", value="/orders")],
        ),
        _site(
            ROUTES,
            1,
            PREDICATES,
            "accept",
            result=5,
            arguments=[
                CallArgument(
                    kind="array",
                    elements=[
                        CallArgument(kind="enum", symbol=MEDIA_TYPE + "APPLICATION_JSON."),
                        CallArgument(kind="enum", symbol=MEDIA_TYPE + "APPLICATION_XML."),
                    ],
                )
            ],
        ),
        _site(
            ROUTES,
            2,
            PREDICATE_TYPE,
            "and",
            receiver=3,
            result=7,
            invoke_kind="interface",
            arguments=[CallArgument(kind="unresolved", source=5)],
        ),
        _site(
            ROUTES,
            3,
            ROUTERS,
            "route",
            result=9,
            arguments=[
                CallArgument(kind="unresolved", source=7),
                CallArgument(kind="lambda", symbol=LIST_ORDERS),
            ],
        ),
        *_handler_symbols(),
    ]
    workspace = _resolve(tmp_path, facts)
    [row] = _rows(workspace)
    workspace.close()

    assert (row["method"], row["path"]) == ("GET", "/orders")
    assert row["produces"] == f'["{JSON}","{XML}"]'
    assert row["consumes"] is None
    assert row["resolution"] == "resolved"


def test_a_vararg_media_array_holding_an_undeclared_constant_contributes_nothing(
    tmp_path: Path,
):
    """The near-miss beside the positive above, one level down: reading an
    array's `elements` widens WHERE constants are found, never WHICH ones
    count. An element whose member the catalog's `media_values` table does not
    declare contributes nothing at all — the media column stays NULL rather
    than gaining the constant's own member name, a symbol fragment no wire
    ever carried.

    This is `_media_value`'s pre-existing rule, and it is pinned here because
    the array read is what first lets a real `enum` element reach it: before
    9.15 the enum never arrived, so the rule declined by accident rather than
    by design."""
    facts = [
        _site(
            ROUTES,
            0,
            PREDICATES,
            "GET",
            result=3,
            arguments=[CallArgument(kind="string", value="/orders")],
        ),
        _site(
            ROUTES,
            1,
            PREDICATES,
            "accept",
            result=5,
            arguments=[
                CallArgument(
                    kind="array",
                    elements=[CallArgument(kind="enum", symbol=MEDIA_TYPE + "TEXT_HTML.")],
                )
            ],
        ),
        _site(
            ROUTES,
            2,
            PREDICATE_TYPE,
            "and",
            receiver=3,
            result=7,
            invoke_kind="interface",
            arguments=[CallArgument(kind="unresolved", source=5)],
        ),
        _site(
            ROUTES,
            3,
            ROUTERS,
            "route",
            result=9,
            arguments=[
                CallArgument(kind="unresolved", source=7),
                CallArgument(kind="lambda", symbol=LIST_ORDERS),
            ],
        ),
        *_handler_symbols(),
    ]
    workspace = _resolve(tmp_path, facts)
    [row] = _rows(workspace)
    workspace.close()

    assert (row["method"], row["path"]) == ("GET", "/orders")
    assert row["produces"] is None
    assert row["resolution"] == "resolved"


def test_a_second_verb_inside_one_and_chain_poisons_only_the_verb(tmp_path: Path):
    """A request carries exactly one verb, so two of them merged by a single
    `and` is a constraint no route satisfies. Picking either would be a guess;
    the verb column goes NULL and the row goes unresolved, while the path — read
    from the same chain and not in doubt — survives intact. (`or` is how two
    verbs on one path are really expressed, and test (3) pins that it stays two
    rows.)

    The second predicate declares the empty path a nest-relative root really
    compiles to, which isolates the verb in the assertion below: within one
    conjunction, path parts concatenate exactly as a prefix's do, because the
    vocabulary cannot tell a prefix predicate from a full-path one and
    inventing that distinction would be a guess."""
    facts = [
        _site(
            ROUTES,
            0,
            PREDICATES,
            "GET",
            result=3,
            arguments=[CallArgument(kind="string", value="/both")],
        ),
        _site(
            ROUTES,
            1,
            PREDICATES,
            "POST",
            result=5,
            arguments=[CallArgument(kind="string", value="")],
        ),
        _site(
            ROUTES,
            2,
            PREDICATE_TYPE,
            "and",
            receiver=3,
            result=7,
            invoke_kind="interface",
            arguments=[CallArgument(kind="unresolved", source=5)],
        ),
        _site(
            ROUTES,
            3,
            ROUTERS,
            "route",
            result=9,
            arguments=[
                CallArgument(kind="unresolved", source=7),
                CallArgument(kind="lambda", symbol=HEALTH),
            ],
        ),
        *_handler_symbols(),
    ]
    workspace = _resolve(tmp_path, facts)
    [row] = _rows(workspace)
    workspace.close()

    assert row["method"] is None
    assert row["path"] == "/both"
    assert row["resolution"] == "unresolved"
    assert row["handler"] == _MODULE + HEALTH


# --- (5) poisoning is per column ------------------------------------------


def test_an_unreadable_path_poisons_the_path_while_an_unreadable_media_constant_does_not(
    tmp_path: Path,
):
    """The two halves of spec §1c's poisoning rule, side by side.

    A path the scanner could not read is a wire identity nobody knows: `path`
    goes NULL and the row goes unresolved, while the verb — read from the same
    call and not in doubt — stays. A media constant that could not be read is
    the opposite case: it is carried data, the verb and path are the identity
    and both are known, so only that column goes NULL and the row stays
    resolved (checkpoint F1's ruling, which the real vararg constants make the
    common case rather than the corner one).
    """
    variable = ROUTES
    unread = DECLARER + "unreadMedia(sig_r0)."
    facts = [
        _site(
            variable, 0, PREDICATES, "GET", result=3, arguments=[CallArgument(kind="unresolved")]
        ),
        _site(
            variable,
            1,
            ROUTERS,
            "route",
            result=9,
            arguments=[
                CallArgument(kind="unresolved", source=3),
                CallArgument(kind="lambda", symbol=LIST_ORDERS),
            ],
        ),
        _site(
            unread,
            0,
            PREDICATES,
            "GET",
            result=3,
            arguments=[CallArgument(kind="string", value="/x")],
        ),
        # A vararg media call whose array the extractor could NOT read end to
        # end: one bare `unresolved` argument, no `source` and no `symbol` to
        # follow. This was the frozen shape of every such call at checkpoint
        # (3); since 9.15 it is the shape only of the five rejection rules'
        # own output, and the readable case is pinned by
        # `test_a_vararg_media_arrays_elements_fill_the_media_column` below.
        _site(
            unread, 1, PREDICATES, "accept", result=5, arguments=[CallArgument(kind="unresolved")]
        ),
        _site(
            unread,
            2,
            PREDICATE_TYPE,
            "and",
            receiver=3,
            result=7,
            invoke_kind="interface",
            arguments=[CallArgument(kind="unresolved", source=5)],
        ),
        _site(
            unread,
            3,
            ROUTERS,
            "route",
            result=9,
            arguments=[
                CallArgument(kind="unresolved", source=7),
                CallArgument(kind="lambda", symbol=LIST_ORDERS),
            ],
        ),
        *_handler_symbols(),
    ]
    workspace = _resolve(tmp_path, facts)
    by_caller = {row["caller"]: row for row in _rows(workspace)}
    workspace.close()

    assert by_caller[variable]["method"] == "GET"
    assert by_caller[variable]["path"] is None
    assert by_caller[variable]["resolution"] == "unresolved"
    assert by_caller[variable]["handler"] == _MODULE + LIST_ORDERS

    assert (by_caller[unread]["method"], by_caller[unread]["path"]) == ("GET", "/x")
    assert by_caller[unread]["produces"] is None
    assert by_caller[unread]["resolution"] == "resolved"


# --- (6) the three handler cases ------------------------------------------


def test_the_three_handler_cases_all_derive_their_row(tmp_path: Path):
    """A bound method reference names the real target method; an inline block
    names the synthetic body the compiler emitted for it; an adapted function
    object names a generated CLASS, which is not a method symbol at all. The
    first two join `method_symbols` and are written module-prefixed; the third
    reads NULL rather than being invented — and its route still derives, since
    the wire identity never depended on the handler."""
    reference = ROUTES
    inline = DECLARER + "inline(sig_r0)."
    adapted = DECLARER + "adapted(sig_r0)."
    facts = [
        _site(
            reference,
            0,
            PREDICATES,
            "GET",
            result=3,
            arguments=[CallArgument(kind="string", value="/ref")],
        ),
        _site(
            reference,
            1,
            ROUTERS,
            "route",
            result=9,
            arguments=[
                CallArgument(kind="unresolved", source=3),
                CallArgument(kind="lambda", source=8, symbol=LIST_ORDERS),
            ],
        ),
        _site(
            inline,
            0,
            PREDICATES,
            "GET",
            result=3,
            arguments=[CallArgument(kind="string", value="/inline")],
        ),
        _site(
            inline,
            1,
            ROUTERS,
            "route",
            result=9,
            arguments=[
                CallArgument(kind="unresolved", source=3),
                CallArgument(kind="lambda", source=8, symbol=INLINE_BODY),
            ],
        ),
        _site(
            adapted,
            0,
            PREDICATES,
            "GET",
            result=3,
            arguments=[CallArgument(kind="string", value="/adapted")],
        ),
        _site(
            adapted,
            1,
            ROUTERS,
            "route",
            result=9,
            arguments=[
                CallArgument(kind="unresolved", source=3),
                CallArgument(kind="instance", source=8, symbol=HANDLER_CLASS),
            ],
        ),
        *_handler_symbols(),
    ]
    workspace = _resolve(tmp_path, facts)
    by_path = {row["path"]: row for row in _rows(workspace)}
    workspace.close()

    assert by_path["/ref"]["handler"] == _MODULE + LIST_ORDERS
    assert by_path["/inline"]["handler"] == _MODULE + INLINE_BODY
    assert by_path["/adapted"]["handler"] is None
    assert {row["resolution"] for row in by_path.values()} == {"resolved"}


def test_a_handler_name_no_scanned_document_declares_is_never_fabricated(tmp_path: Path):
    """The no-fabrication rule (the 2E-prep interface-engine ruling, kept
    verbatim here): a `lambda` argument naming a method outside the scanned
    module joins no symbol fact, so `handler` is NULL. Writing the bare name
    would produce a column nothing else in the graph could ever follow."""
    facts = [
        _site(
            ROUTES,
            0,
            PREDICATES,
            "GET",
            result=3,
            arguments=[CallArgument(kind="string", value="/x")],
        ),
        _site(
            ROUTES,
            1,
            ROUTERS,
            "route",
            result=9,
            arguments=[
                CallArgument(kind="unresolved", source=3),
                CallArgument(kind="lambda", symbol="com/elsewhere/NotScanned#handle(sig_zz)."),
            ],
        ),
    ]
    workspace = _resolve(tmp_path, facts)
    [row] = _rows(workspace)
    workspace.close()

    assert row["handler"] is None
    assert (row["method"], row["path"], row["resolution"]) == ("GET", "/x", "resolved")


# --- (7) a cross-method router reference is one unresolved row ------------


def test_a_router_composed_from_another_methods_return_derives_one_unresolved_row(
    tmp_path: Path,
):
    """The walk is per-method by design (spec §1c). Checkpoint (1a) shows the
    facts would support following the reference — the argument's `source` names
    a call whose own owner+name is the other method — so this is a deliberate
    boundary, not a limit of the evidence, and the boundary must be VISIBLE:
    one unresolved row for the reference, never a silent absence. The route
    declared beside it in the same chain is unaffected."""
    facts = [
        _site(
            ROUTES,
            0,
            PREDICATES,
            "GET",
            result=3,
            arguments=[CallArgument(kind="string", value="/extra")],
        ),
        _site(
            ROUTES,
            1,
            ROUTERS,
            "route",
            result=9,
            arguments=[
                CallArgument(kind="unresolved", source=3),
                CallArgument(kind="lambda", symbol=HEALTH),
            ],
        ),
        _site(ROUTES, 2, DECLARER, "other", result=11, invoke_kind="virtual"),
        _site(
            ROUTES,
            3,
            ROUTER_TYPE,
            "and",
            receiver=9,
            result=12,
            invoke_kind="interface",
            arguments=[CallArgument(kind="unresolved", source=11)],
        ),
        *_handler_symbols(),
    ]
    workspace = _resolve(tmp_path, facts)
    rows = _rows(workspace)
    workspace.close()

    assert _identities(rows) == [
        ("GET", "/extra", _MODULE + HEALTH, "resolved"),
        (None, None, None, "unresolved"),
    ]


# --- (8) chain continuations merge route sets ----------------------------


def test_a_continuation_chain_merges_every_route_it_links_exactly_once(tmp_path: Path):
    """Continuations link `result` → `receiver`, so a three-call chain declares
    three routes — and only three. Each link is consumed as the next link's
    receiver, which is exactly what stops the middle of the chain from being
    rooted a second time on its own."""
    facts = [
        _site(
            ROUTES,
            0,
            PREDICATES,
            "GET",
            result=3,
            arguments=[CallArgument(kind="string", value="/a")],
        ),
        _site(
            ROUTES,
            1,
            ROUTERS,
            "route",
            result=9,
            arguments=[
                CallArgument(kind="unresolved", source=3),
                CallArgument(kind="lambda", symbol=LIST_ORDERS),
            ],
        ),
        _site(
            ROUTES,
            2,
            PREDICATES,
            "POST",
            result=11,
            arguments=[CallArgument(kind="string", value="/b")],
        ),
        _site(
            ROUTES,
            3,
            ROUTER_TYPE,
            "andRoute",
            receiver=9,
            result=13,
            invoke_kind="interface",
            arguments=[
                CallArgument(kind="unresolved", source=11),
                CallArgument(kind="lambda", symbol=CREATE_ORDER),
            ],
        ),
        _site(
            ROUTES,
            4,
            PREDICATES,
            "GET",
            result=15,
            arguments=[CallArgument(kind="string", value="/c")],
        ),
        _site(
            ROUTES,
            5,
            ROUTER_TYPE,
            "andRoute",
            receiver=13,
            result=17,
            invoke_kind="interface",
            arguments=[
                CallArgument(kind="unresolved", source=15),
                CallArgument(kind="lambda", symbol=HEALTH),
            ],
        ),
        *_handler_symbols(),
    ]
    workspace = _resolve(tmp_path, facts)
    rows = _rows(workspace)
    workspace.close()

    assert _identities(rows) == [
        ("GET", "/a", _MODULE + LIST_ORDERS, "resolved"),
        ("GET", "/c", _MODULE + HEALTH, "resolved"),
        ("POST", "/b", _MODULE + CREATE_ORDER, "resolved"),
    ]


def test_a_nest_shaped_continuation_folds_its_whole_subtree_under_its_prefix(
    tmp_path: Path,
):
    """The nest-shaped continuation (`{name, owner, path_arg, subtree_arg}`):
    its second argument is a whole router, not a handler.

    Read as a PLAIN continuation it would be a silent disaster — the second
    argument falls in the global handler slot and is skipped, the first is
    taken as this call's own predicate, and the result is a fabricated
    handler-less `resolved` row where the subtree's routes should have been.
    Declared shape, folded shape: the chain to the left keeps its own routes
    untouched, and the prefix lands on the SUBTREE's routes only.
    """
    facts = [
        _site(
            ROUTES,
            0,
            PREDICATES,
            "GET",
            result=3,
            arguments=[CallArgument(kind="string", value="/a")],
        ),
        _site(
            ROUTES,
            1,
            ROUTERS,
            "route",
            result=9,
            arguments=[
                CallArgument(kind="unresolved", source=3),
                CallArgument(kind="lambda", symbol=LIST_ORDERS),
            ],
        ),
        _site(
            ROUTES,
            2,
            PREDICATES,
            "GET",
            result=11,
            arguments=[CallArgument(kind="string", value="/b")],
        ),
        _site(
            ROUTES,
            3,
            ROUTER_TYPE,
            "andRoute",
            receiver=9,
            result=13,
            invoke_kind="interface",
            arguments=[
                CallArgument(kind="unresolved", source=11),
                CallArgument(kind="lambda", symbol=CREATE_ORDER),
            ],
        ),
        _site(
            ROUTES,
            4,
            PREDICATES,
            "path",
            result=15,
            arguments=[CallArgument(kind="string", value="/x")],
        ),
        _site(
            ROUTES,
            5,
            PREDICATES,
            "GET",
            result=17,
            arguments=[CallArgument(kind="string", value="/y")],
        ),
        _site(
            ROUTES,
            6,
            ROUTERS,
            "route",
            result=19,
            arguments=[
                CallArgument(kind="unresolved", source=17),
                CallArgument(kind="lambda", symbol=HEALTH),
            ],
        ),
        _site(
            ROUTES,
            7,
            ROUTER_TYPE,
            "andNest",
            receiver=13,
            result=21,
            invoke_kind="interface",
            arguments=[
                CallArgument(kind="unresolved", source=15),
                CallArgument(kind="unresolved", source=19),
            ],
        ),
        *_handler_symbols(),
    ]
    workspace = _resolve(tmp_path, facts)
    rows = _rows(workspace)
    workspace.close()

    assert _identities(rows) == [
        ("GET", "/a", _MODULE + LIST_ORDERS, "resolved"),
        ("GET", "/b", _MODULE + CREATE_ORDER, "resolved"),
        ("GET", "/x/y", _MODULE + HEALTH, "resolved"),
    ]


def test_a_nest_shaped_continuation_with_an_unreadable_subtree_stays_one_unresolved_row(
    tmp_path: Path,
):
    """Poison discipline through the nest-shaped continuation: a subtree
    nobody can read is one unresolved row for the nest — never silence, and
    never a `resolved` row carrying only the prefix, which would claim the
    router declares an endpoint at `/x` that nobody wrote. The chain to its
    left is untouched."""
    facts = [
        _site(
            ROUTES,
            0,
            PREDICATES,
            "GET",
            result=3,
            arguments=[CallArgument(kind="string", value="/a")],
        ),
        _site(
            ROUTES,
            1,
            ROUTERS,
            "route",
            result=9,
            arguments=[
                CallArgument(kind="unresolved", source=3),
                CallArgument(kind="lambda", symbol=LIST_ORDERS),
            ],
        ),
        _site(
            ROUTES,
            2,
            PREDICATES,
            "path",
            result=15,
            arguments=[CallArgument(kind="string", value="/x")],
        ),
        _site(
            ROUTES,
            3,
            ROUTER_TYPE,
            "andNest",
            receiver=9,
            result=21,
            invoke_kind="interface",
            arguments=[
                CallArgument(kind="unresolved", source=15),
                CallArgument(kind="unresolved"),
            ],
        ),
        *_handler_symbols(),
    ]
    workspace = _resolve(tmp_path, facts)
    rows = _rows(workspace)
    workspace.close()

    assert _identities(rows) == [
        ("GET", "/a", _MODULE + LIST_ORDERS, "resolved"),
        (None, None, None, "unresolved"),
    ]


def test_a_nest_shaped_continuations_lambda_kind_subtree_folds_its_bodys_routes(
    tmp_path: Path,
):
    """`_subtree_routes`' `lambda`-kind branch, deferred from Task 8's own
    review: a shaped continuation's `subtree_arg` is ordinarily a same-method
    expression reached through `source` (the two tests above), but the
    grammar lets it be a `lambda`-kind argument instead — a whole router
    folded from a body method, the same jump a body-linked entry or prefix
    makes elsewhere. `andNest` declares `path_arg`/`subtree_arg` only —
    continuations carry no `body_arg` of their own — so this IS the only way
    a continuation ever reaches a linked body, and it is coded once in
    `_subtree_routes` for every shaped continuation to share.

    The body here itself contains a bare `RouterFunctions.route(...)` call —
    an argument-rooted ENTRY, not a body-linked one — so it is independently
    rootable on its own terms, exactly checkpoint (1a)'s frozen `other()`
    case: two distinct facts about one method, `GET /y` from the body's own
    walk and `GET /x/y` folded under the continuation's prefix, neither
    suppressing the other."""
    body = DECLARER + "andNestBody(sig_b1)."
    facts = [
        _site(
            ROUTES,
            0,
            PREDICATES,
            "GET",
            result=3,
            arguments=[CallArgument(kind="string", value="/a")],
        ),
        _site(
            ROUTES,
            1,
            ROUTERS,
            "route",
            result=9,
            arguments=[
                CallArgument(kind="unresolved", source=3),
                CallArgument(kind="lambda", symbol=LIST_ORDERS),
            ],
        ),
        _site(
            ROUTES,
            2,
            PREDICATES,
            "path",
            result=15,
            arguments=[CallArgument(kind="string", value="/x")],
        ),
        _site(
            ROUTES,
            3,
            ROUTER_TYPE,
            "andNest",
            receiver=9,
            result=21,
            invoke_kind="interface",
            arguments=[
                CallArgument(kind="unresolved", source=15),
                CallArgument(kind="lambda", symbol=body),
            ],
        ),
        _site(
            body,
            0,
            PREDICATES,
            "GET",
            result=5,
            arguments=[CallArgument(kind="string", value="/y")],
        ),
        _site(
            body,
            1,
            ROUTERS,
            "route",
            result=11,
            arguments=[
                CallArgument(kind="unresolved", source=5),
                CallArgument(kind="lambda", symbol=CREATE_ORDER),
            ],
        ),
        *_handler_symbols(),
    ]
    workspace = _resolve(tmp_path, facts)
    rows = _rows(workspace)
    workspace.close()

    assert sorted(_identities(rows)) == sorted(
        [
            ("GET", "/a", _MODULE + LIST_ORDERS, "resolved"),
            ("GET", "/x/y", _MODULE + CREATE_ORDER, "resolved"),
            ("GET", "/y", _MODULE + CREATE_ORDER, "resolved"),
        ]
    )


# --- owner-free continuations extend walks but never root them ------------


def test_an_owner_free_continuation_extends_a_real_root_but_never_roots_one(
    tmp_path: Path,
):
    """A continuation name is matched owner-free by design (`fluent`'s steps
    discipline: an owner narrows a step, its absence reaches one wherever it
    appears) — but matching a bare name against every owner is right for
    REACHING a step inside a chain already known to be this catalog's, and
    reckless for deciding a chain is this catalog's at all.

    So an owner-free continuation folds normally when a real root walks back
    through it (`/b` below, declared on a type the catalog never names), and a
    call that merely shares the name — the same `and` on the predicate type
    that the catalog declares as a COMPOSER, or on some unrelated type
    entirely — roots nothing and derives nothing at all.
    """
    chain = ROUTES
    lone_composer = DECLARER + "loneComposer(sig_r0)."
    lone_stranger = DECLARER + "loneStranger(sig_r0)."
    lone_owner_free = DECLARER + "loneOwnerFree(sig_r0)."
    facts = [
        _site(
            chain,
            0,
            PREDICATES,
            "GET",
            result=3,
            arguments=[CallArgument(kind="string", value="/a")],
        ),
        _site(
            chain,
            1,
            ROUTERS,
            "route",
            result=9,
            arguments=[
                CallArgument(kind="unresolved", source=3),
                CallArgument(kind="lambda", symbol=LIST_ORDERS),
            ],
        ),
        _site(
            chain,
            2,
            PREDICATES,
            "GET",
            result=11,
            arguments=[CallArgument(kind="string", value="/b")],
        ),
        # Owner-free: declared as the bare name `withRoute`, and reached here
        # on a type the catalog never mentions.
        _site(
            chain,
            3,
            "com/example/web/RouterExtensions#",
            "withRoute",
            receiver=9,
            result=13,
            invoke_kind="static",
            arguments=[
                CallArgument(kind="unresolved", source=11),
                CallArgument(kind="lambda", symbol=CREATE_ORDER),
            ],
        ),
        _site(
            chain,
            4,
            PREDICATES,
            "GET",
            result=15,
            arguments=[CallArgument(kind="string", value="/c")],
        ),
        _site(
            chain,
            5,
            ROUTER_TYPE,
            "andRoute",
            receiver=13,
            result=17,
            invoke_kind="interface",
            arguments=[
                CallArgument(kind="unresolved", source=15),
                CallArgument(kind="lambda", symbol=HEALTH),
            ],
        ),
        _site(
            lone_composer,
            0,
            PREDICATE_TYPE,
            "and",
            receiver=2,
            result=4,
            invoke_kind="interface",
            arguments=[CallArgument(kind="unresolved")],
        ),
        _site(
            lone_stranger,
            0,
            "com/example/util/Conditions#",
            "and",
            result=4,
            arguments=[CallArgument(kind="unresolved"), CallArgument(kind="unresolved")],
        ),
        _site(
            lone_owner_free,
            0,
            "com/example/util/Conditions#",
            "withRoute",
            result=4,
            arguments=[CallArgument(kind="unresolved"), CallArgument(kind="unresolved")],
        ),
        *_handler_symbols(),
    ]
    workspace = _resolve(tmp_path, facts)
    rows = _rows(workspace)
    workspace.close()

    assert _identities(rows) == [
        ("GET", "/a", _MODULE + LIST_ORDERS, "resolved"),
        ("GET", "/b", _MODULE + CREATE_ORDER, "resolved"),
        ("GET", "/c", _MODULE + HEALTH, "resolved"),
    ]
    assert {row["caller"] for row in rows} == {chain}


# --- (9) the body-linked entry, and the no-independent-rooting rule -------


def _body_linked_facts() -> list:
    """One body-linked tree, three methods deep, plus one method holding a
    vocabulary call that no entry links to. The shapes are checkpoint (1b)'s
    verbatim: the entry names its body through a `lambda` argument, the body's
    own calls carry `receiver: null` and `result: null`, the media predicate is
    the one exception that carries a result and is consumed by the nest beside
    it, and a nested block is linked exactly the same way its parent was."""
    return [
        _site(
            DSL_ROUTES,
            0,
            "java/lang/invoke/LambdaMetafactory#",
            "invoke",
            result=3,
            invoke_kind="dynamic",
        ),
        _site(
            DSL_ROUTES,
            1,
            DSL_FACADE,
            "router",
            result=4,
            arguments=[CallArgument(kind="lambda", source=3, symbol=DSL_BODY)],
        ),
        _site(
            DSL_BODY,
            0,
            "kotlin/jvm/internal/Intrinsics#",
            "checkNotNullParameter",
            arguments=[
                CallArgument(kind="unresolved"),
                CallArgument(kind="string", value="$this$router"),
            ],
        ),
        _site(
            DSL_BODY,
            1,
            "java/lang/invoke/LambdaMetafactory#",
            "invoke",
            result=9,
            invoke_kind="dynamic",
        ),
        _site(
            DSL_BODY,
            2,
            DSL,
            "nest",
            invoke_kind="virtual",
            arguments=[
                CallArgument(kind="string", value="/kt"),
                CallArgument(kind="lambda", source=9, symbol=DSL_CHILD),
            ],
        ),
        _site(DSL_CHILD, 0, HANDLER_CLASS, "<init>", receiver=8, invoke_kind="special"),
        _site(
            DSL_CHILD,
            1,
            DSL,
            "GET",
            invoke_kind="virtual",
            arguments=[
                CallArgument(kind="string", value="/orders"),
                CallArgument(kind="instance", source=8, symbol=HANDLER_CLASS),
            ],
        ),
        _site(
            DSL_CHILD,
            2,
            DSL,
            "accept",
            result=39,
            invoke_kind="virtual",
            arguments=[CallArgument(kind="unresolved")],
        ),
        _site(
            DSL_CHILD,
            3,
            "java/lang/invoke/LambdaMetafactory#",
            "invoke",
            result=40,
            invoke_kind="dynamic",
        ),
        _site(
            DSL_CHILD,
            4,
            DSL,
            "nest",
            invoke_kind="virtual",
            arguments=[
                CallArgument(kind="unresolved", source=39),
                CallArgument(kind="lambda", source=40, symbol=DSL_GRANDCHILD),
            ],
        ),
        _site(
            DSL_GRANDCHILD,
            0,
            DSL,
            "GET",
            invoke_kind="virtual",
            arguments=[
                CallArgument(kind="string", value="/rich"),
                CallArgument(kind="lambda", symbol=INLINE_BODY),
            ],
        ),
        *_handler_symbols(),
    ]


def test_a_body_linked_entry_folds_its_bodies_under_the_entrys_own_prefixes(tmp_path: Path):
    """The entry roots the tree and the walk jumps to the body its `lambda`
    argument names, then jumps again through the nested block's own link
    (checkpoint (1b)). Every prefix on the way composes, so the leaf route
    carries both; the unreadable media predicate a nest was built from poisons
    only its own column; and every row of the tree carries the ENTRY's
    containing method as `caller` — one router, one declarer — never the
    compiler-generated body a route was folded from."""
    workspace = _resolve(tmp_path, _body_linked_facts())
    rows = _rows(workspace)
    workspace.close()

    assert _identities(rows) == [
        ("GET", "/kt/orders", None, "resolved"),
        ("GET", "/kt/rich", _MODULE + INLINE_BODY, "resolved"),
    ]
    assert {row["caller"] for row in rows} == {DSL_ROUTES}
    assert [row["produces"] for row in rows] == [None, None]


def test_a_vocabulary_call_in_a_method_no_entry_links_to_derives_nothing(tmp_path: Path):
    """Checkpoint F4, pinned. Rooting a method because it merely CONTAINS a
    vocabulary call would derive every nested route twice — once under its
    prefixes, once bare — and would also invent routes for a helper that holds
    DSL calls no entry ever links to. Bodies are reached only through an
    entry's or a nest's `lambda` argument, so the orphan below contributes
    nothing at all, and the linked bodies contribute nothing SECOND."""
    orphan = DECLARER + "orphan(sig_r0)."
    facts = [
        *_body_linked_facts(),
        _site(
            orphan,
            0,
            DSL,
            "GET",
            invoke_kind="virtual",
            arguments=[
                CallArgument(kind="string", value="/orphan"),
                CallArgument(kind="lambda", symbol=HEALTH),
            ],
        ),
    ]
    workspace = _resolve(tmp_path, facts)
    rows = _rows(workspace)
    workspace.close()

    assert [row["path"] for row in rows] == ["/kt/orders", "/kt/rich"]
    assert all(row["caller"] == DSL_ROUTES for row in rows)


# --- overload discrimination (spec §3) ---------------------------------------

_HANDLER_TYPE = "kotlin.jvm.functions.Function1"
_PREDICATE_TYPE = "com.example.web.Predicate"
_STRING = "java.lang.String"
_DSL_GET_FIVE = [
    # The five overloads the servlet DSL declares (`javap -p -s RouterFunctionDsl`),
    # each pinned to what its positions carry. `arity` splits 1/2/3; `arg_types` splits
    # the two arity-2 forms on position 0.
    {
        "owner": "com.example.web.RouterDsl",
        "method": "GET",
        "verb": "GET",
        "arity": 1,
        "handler_arg": 0,
    },
    {
        "owner": "com.example.web.RouterDsl",
        "method": "GET",
        "verb": "GET",
        "arity": 2,
        "arg_types": {0: _STRING},
        "path_arg": 0,
        "handler_arg": 1,
    },
    {
        "owner": "com.example.web.RouterDsl",
        "method": "GET",
        "verb": "GET",
        "arity": 2,
        "arg_types": {0: _PREDICATE_TYPE},
        "predicate_arg": 0,
        "handler_arg": 1,
    },
    {
        "owner": "com.example.web.RouterDsl",
        "method": "GET",
        "verb": "GET",
        "arity": 3,
        "path_arg": 0,
        "predicate_arg": 1,
        "handler_arg": 2,
    },
]


def _overload_matches() -> dict[str, object]:
    matches = _matches()
    vocabulary = dict(matches["vocabulary"])  # type: ignore[arg-type]
    vocabulary["verbs"] = [
        rule
        for rule in vocabulary["verbs"]
        if rule["owner"] != "com.example.web.RouterDsl"  # type: ignore[index]
    ] + _DSL_GET_FIVE
    vocabulary["prefixes"] = list(vocabulary["prefixes"]) + [  # type: ignore[arg-type]
        {"owner": "com.example.web.RouterDsl", "method": "path", "path_arg": 0},
    ]
    return {**matches, "vocabulary": vocabulary}


def _four_get_overloads_in_one_body() -> list:
    """`router { GET(h); GET("/two", h); GET(path("/three"), h); GET("/four", path("/p"), h) }`
    as the facts arrive: the entry in the declaring method, four verb calls in the body,
    each `path(...)` a call of its own whose result the verb consumes through `source`."""
    entry = _site(
        DECLARER + "routes(sig_r).",
        0,
        DSL_FACADE,
        "router",
        arguments=[CallArgument(kind="lambda", symbol=INLINE_BODY, source=0)],
        result=1,
    )
    body = [
        _site(
            INLINE_BODY,
            0,
            DSL,
            "GET",
            invoke_kind="virtual",
            descriptor=f"(L{_HANDLER_TYPE.replace('.', '/')};)V",
            arguments=[CallArgument(kind="lambda", symbol=LIST_ORDERS, source=0)],
        ),
        _site(
            INLINE_BODY,
            1,
            DSL,
            "GET",
            invoke_kind="virtual",
            descriptor=f"(Ljava/lang/String;L{_HANDLER_TYPE.replace('.', '/')};)V",
            arguments=[
                CallArgument(kind="string", value="/two"),
                CallArgument(kind="lambda", symbol=LIST_ORDERS, source=1),
            ],
        ),
        _site(
            INLINE_BODY,
            2,
            DSL,
            "path",
            invoke_kind="virtual",
            result=2,
            descriptor="(Ljava/lang/String;)Lcom/example/web/Predicate;",
            arguments=[CallArgument(kind="string", value="/three")],
        ),
        _site(
            INLINE_BODY,
            3,
            DSL,
            "GET",
            invoke_kind="virtual",
            descriptor=f"(Lcom/example/web/Predicate;L{_HANDLER_TYPE.replace('.', '/')};)V",
            arguments=[
                CallArgument(kind="unresolved", source=2),
                CallArgument(kind="lambda", symbol=LIST_ORDERS, source=3),
            ],
        ),
        _site(
            INLINE_BODY,
            4,
            DSL,
            "path",
            invoke_kind="virtual",
            result=4,
            descriptor="(Ljava/lang/String;)Lcom/example/web/Predicate;",
            arguments=[CallArgument(kind="string", value="/p")],
        ),
        _site(
            INLINE_BODY,
            5,
            DSL,
            "GET",
            invoke_kind="virtual",
            descriptor=f"(Ljava/lang/String;Lcom/example/web/Predicate;L{_HANDLER_TYPE.replace('.', '/')};)V",
            arguments=[
                CallArgument(kind="string", value="/four"),
                CallArgument(kind="unresolved", source=4),
                CallArgument(kind="lambda", symbol=LIST_ORDERS, source=5),
            ],
        ),
    ]
    return [*_handler_symbols(), _method_symbol(INLINE_BODY), entry, *body]


def test_the_four_verb_overloads_each_derive_what_their_positions_carry(tmp_path: Path):
    """Spec §8 test 1. Against the shipped one-rule-per-name grammar it failed the way
    spec §2 says a dict keyed on (owner, name) must: the LAST `GET` rule (arity 3)
    silently overwrote the other three, so the catch-all read `unresolved`, both
    two-argument forms lost their handler, and the three-argument form lost its
    predicate (`/four`, not `/four/p`). `arity` + `arg_types` make each overload its
    own rule.

    The catch-all `GET(h)` serves every path, and its row says so with the framework's
    any-path pattern `/**` at RESOLVED (spec §7 case 3 as ruled: a resolved NULL path
    is what the addresses-nothing gate drops by doctrine, and a catch-all is the
    opposite of an absent address)."""
    workspace = _resolve(tmp_path, _four_get_overloads_in_one_body(), _catalog(_overload_matches()))
    handler = _MODULE + LIST_ORDERS
    assert _identities(_rows(workspace)) == [
        ("GET", "/**", handler, "resolved"),  # GET(h): a catch-all, deliberately open
        ("GET", "/four/p", handler, "resolved"),  # GET("/four", path("/p"), h)
        ("GET", "/three", handler, "resolved"),  # GET(path("/three"), h)
        ("GET", "/two", handler, "resolved"),  # GET("/two", h)
    ]


@pytest.mark.pins("combinator.unrecognised-overload-is-a-row")
def test_a_named_call_no_overload_accepts_derives_one_unresolved_row(tmp_path: Path):
    """Spec §3's G-13 guard: a site whose owner and name the vocabulary knows, at an
    arity no rule declares, is one honest unresolved row — never silence, never a
    position read off the wrong overload."""
    facts = _four_get_overloads_in_one_body()
    facts.append(
        _site(
            INLINE_BODY,
            6,
            DSL,
            "GET",
            invoke_kind="virtual",
            descriptor="(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)V",
            arguments=[CallArgument(kind="string", value="/a")] * 4,
        )
    )
    workspace = _resolve(tmp_path, facts, _catalog(_overload_matches()))
    unresolved = [row for row in _rows(workspace) if row["resolution"] == "unresolved"]
    assert [(row["method"], row["path"]) for row in unresolved] == [(None, None)]


def test_two_rules_that_could_accept_one_call_are_refused_at_load(tmp_path: Path):
    """Spec §3c: never file order. Two arity-2 rules typing DIFFERENT positions could
    both accept `GET(String, Predicate)`, so the catalog is refused naming both; two
    rules typing the SAME position with different types cannot both match, so that
    pair loads."""
    matches = _overload_matches()
    vocabulary = matches["vocabulary"]
    vocabulary["verbs"] = [r for r in vocabulary["verbs"] if r.get("arity") != 2] + [  # type: ignore[index]
        {
            "owner": "com.example.web.RouterDsl",
            "method": "GET",
            "verb": "GET",
            "arity": 2,
            "arg_types": {0: _STRING},
            "path_arg": 0,
            "handler_arg": 1,
        },
        {
            "owner": "com.example.web.RouterDsl",
            "method": "GET",
            "verb": "GET",
            "arity": 2,
            "arg_types": {1: _HANDLER_TYPE},
            "predicate_arg": 0,
            "handler_arg": 1,
        },
    ]
    with pytest.raises(CatalogError, match=r"GET.*arity 2.*both") as refused:
        _resolve(tmp_path, _four_get_overloads_in_one_body(), _catalog(matches))
    assert _STRING in str(refused.value) and _HANDLER_TYPE in str(refused.value)


def test_a_rule_typing_a_position_beyond_its_arity_is_refused(tmp_path: Path):
    matches = _overload_matches()
    matches["vocabulary"]["verbs"].append(  # type: ignore[index]
        {
            "owner": "com.example.web.RouterDsl",
            "method": "HEAD",
            "verb": "HEAD",
            "arity": 1,
            "arg_types": {1: _STRING},
            "handler_arg": 0,
        }
    )
    with pytest.raises(CatalogError, match=r"HEAD.*position 1.*arity 1"):
        _resolve(tmp_path, _four_get_overloads_in_one_body(), _catalog(matches))


# --- (10) dedup: identity-known only, and the handler is part of it -------


def test_only_identity_known_rows_dedup_and_the_key_includes_the_handler(tmp_path: Path):
    """Two rules in one batch.

    A row whose path nobody could read carries nothing to compare, so it takes
    part in NEITHER the media union nor the dedup key, and each such reference
    stays its own row — two IDENTICAL unresolved rows below, same handler and
    all, and both survive. That is `derive_call_endpoints.sql`'s own written
    contract (SQL's `NULL = NULL` is unknown rather than true, so two
    unresolved rows are two distinct facts about two distinct call sites), and
    a batch that collapsed them here would hide one before the insert ever saw
    it.

    `handler` IS part of the wire identity for an inbound handler row (the
    `interface_implementation` parity rule): the same verb and path bound to
    two different handlers are two facts, and a key without the handler would
    silently discard the second. The same handler on the same identity, from
    two methods, still collapses to one.
    """
    first = DECLARER + "first(sig_r0)."
    second = DECLARER + "second(sig_r0)."
    third = DECLARER + "third(sig_r0)."
    unreadable = DECLARER + "unreadable(sig_r0)."

    def _same_route(caller: str, handler: str) -> list:
        return [
            _site(
                caller,
                0,
                PREDICATES,
                "GET",
                result=3,
                arguments=[CallArgument(kind="string", value="/dup")],
            ),
            _site(
                caller,
                1,
                ROUTERS,
                "route",
                result=9,
                arguments=[
                    CallArgument(kind="unresolved", source=3),
                    CallArgument(kind="lambda", symbol=handler),
                ],
            ),
        ]

    facts = [
        *_same_route(first, LIST_ORDERS),
        *_same_route(second, LIST_ORDERS),
        *_same_route(third, CREATE_ORDER),
        _site(
            unreadable,
            0,
            ROUTERS,
            "route",
            result=9,
            arguments=[
                CallArgument(kind="unresolved"),
                CallArgument(kind="lambda", symbol=LIST_ORDERS),
            ],
        ),
        # Byte-identical to the row above — SAME handler, same everything —
        # and it must still survive as its own row.
        _site(
            unreadable,
            1,
            ROUTERS,
            "route",
            result=11,
            arguments=[
                CallArgument(kind="unresolved"),
                CallArgument(kind="lambda", symbol=LIST_ORDERS),
            ],
        ),
        *_handler_symbols(),
    ]
    workspace = _resolve(tmp_path, facts)
    rows = _rows(workspace)
    workspace.close()

    duplicated = [row for row in rows if row["path"] == "/dup"]
    assert sorted(row["handler"] for row in duplicated) == [
        _MODULE + CREATE_ORDER,
        _MODULE + LIST_ORDERS,
    ]
    assert sorted(row["caller"] for row in duplicated) == sorted([first, third])
    unresolved = [row for row in rows if row["resolution"] == "unresolved"]
    assert len(unresolved) == 2
    assert {row["path"] for row in unresolved} == {None}
    # Both carry the SAME handler: it is the path being unread, not any
    # difference between them, that keeps them apart.
    assert {row["handler"] for row in unresolved} == {_MODULE + LIST_ORDERS}


# --- catalog validation ---------------------------------------------------


def test_an_entry_that_is_neither_declared_shape_is_refused(tmp_path: Path):
    """An unchecked value does not stay in the file (`ports/catalogs.py`'s
    discipline): an entry declaring neither `{methods, handler_arg}` nor
    `{method, body_arg}` matches no call site at all, which reads as "this
    router declares nothing" — the silent degradation the refusal exists to
    prevent."""
    matches = _matches()
    matches["entries"] = [{"owner": "com.example.web.Routers", "methods": ["route"]}]
    with pytest.raises(CatalogError, match="every `entries` item"):
        _resolve(tmp_path, [], _catalog(matches))


def test_a_media_rule_filling_a_column_that_does_not_exist_is_refused(tmp_path: Path):
    """A `fills` typo would file every value the rule reads under the wrong
    column — or none at all — and nothing downstream could tell that from a
    framework that declares no media."""
    matches = _matches()
    vocabulary = matches["vocabulary"]
    assert isinstance(vocabulary, dict)
    vocabulary["media"] = [
        {"owner": "com.example.web.Predicates", "method": "accept", "fills": "produce"}
    ]
    with pytest.raises(CatalogError, match="fills"):
        _resolve(tmp_path, [], _catalog(matches))


def test_a_name_declared_as_both_composer_and_owner_free_continuation_is_refused(
    tmp_path: Path,
):
    """The two roles fold a call completely differently — one merges
    constraints, the other merges route sets — so a name claimed by both with
    nothing to tell them apart leaves dispatch order, not the catalog,
    deciding which wins. The catalog says which; an owner-free continuation
    cannot."""
    matches = _matches()
    matches["continuations"] = ["and"]
    with pytest.raises(CatalogError, match="both a composer and a continuation"):
        _resolve(tmp_path, [], _catalog(matches))


def test_the_same_name_on_two_different_owners_is_allowed_for_the_two_roles(
    tmp_path: Path,
):
    """The counterpart the refusal above must NOT catch: a predicate type and a
    router type each declaring `and` is the frozen reality this style was built
    for (checkpoint (1a)), and there the owners make the reading exact. The
    default catalog declares exactly that pair, so this asserts the two roles
    really do fold differently — the predicate `and` merges constraints onto
    one row, the router `and` merges route sets."""
    facts = [
        _site(
            ROUTES,
            0,
            PREDICATES,
            "GET",
            result=3,
            arguments=[CallArgument(kind="string", value="/x")],
        ),
        _site(
            ROUTES,
            1,
            PREDICATES,
            "accept",
            result=5,
            arguments=[CallArgument(kind="enum", symbol=MEDIA_TYPE + "APPLICATION_JSON.")],
        ),
        _site(
            ROUTES,
            2,
            PREDICATE_TYPE,
            "and",
            receiver=3,
            result=7,
            invoke_kind="interface",
            arguments=[CallArgument(kind="unresolved", source=5)],
        ),
        _site(
            ROUTES,
            3,
            ROUTERS,
            "route",
            result=9,
            arguments=[
                CallArgument(kind="unresolved", source=7),
                CallArgument(kind="lambda", symbol=LIST_ORDERS),
            ],
        ),
        _site(ROUTES, 4, DECLARER, "other", result=11, invoke_kind="virtual"),
        _site(
            ROUTES,
            5,
            ROUTER_TYPE,
            "and",
            receiver=9,
            result=13,
            invoke_kind="interface",
            arguments=[CallArgument(kind="unresolved", source=11)],
        ),
        *_handler_symbols(),
    ]
    workspace = _resolve(tmp_path, facts)
    rows = _rows(workspace)
    workspace.close()

    assert _identities(rows) == [
        ("GET", "/x", _MODULE + LIST_ORDERS, "resolved"),
        (None, None, None, "unresolved"),
    ]
    assert rows[0]["produces"] == f'["{JSON}"]'


def test_half_a_nest_shaped_continuation_is_refused(tmp_path: Path):
    """`path_arg` without `subtree_arg` would fold as the PLAIN shape and drop
    the subtree the author was declaring — the exact defect the shaped form
    exists to prevent, arriving through a half-written declaration instead."""
    matches = _matches()
    matches["continuations"] = [
        {"name": "andNest", "owner": "com.example.web.Router", "path_arg": 0}
    ]
    with pytest.raises(CatalogError, match="needs `path_arg` and `subtree_arg` together"):
        _resolve(tmp_path, [], _catalog(matches))


def test_two_continuations_sharing_a_name_need_distinct_owners(tmp_path: Path):
    """`fluent._validate_steps`' rule, for the same reason: silent last-wins
    would hide exactly the bug the check exists for. An owner-free entry
    matches every owner, so it collides with any sibling regardless of what
    that sibling declares."""
    matches = _matches()
    matches["continuations"] = ["andRoute", {"name": "andRoute", "owner": "com.example.web.Router"}]
    with pytest.raises(CatalogError, match="need distinct `owner`s"):
        _resolve(tmp_path, [], _catalog(matches))


def test_a_continuation_entry_of_neither_declared_form_is_refused(tmp_path: Path):
    matches = _matches()
    matches["continuations"] = [{"owner": "com.example.web.Router"}]
    with pytest.raises(CatalogError, match="every `continuations` item"):
        _resolve(tmp_path, [], _catalog(matches))


# --- `A-M9` (principles sweep §3.3): the shipped catalog's verb vocabulary ---
#
# Everything above drives an INVENTED catalog, deliberately — an engine that
# only works for one library's fqns is what spec §1d forbids. These two drive
# the SHIPPED `spring-webflux-router.yml`, because the finding is not about the
# engine at all: the encoded verb list was a projection of the fixture's own
# routes, which is §8.1 rule 1's failure shape said in the catalog's own words
# ("exactly what 2E's checkpoint froze against a real scan").

_ROUTER_FUNCTIONS = "org/springframework/web/reactive/function/server/RouterFunctions#"
_REQUEST_PREDICATES = "org/springframework/web/reactive/function/server/RequestPredicates#"
_CO_ROUTER_DSL = "org/springframework/web/reactive/function/server/CoRouterFunctionDsl#"
_CO_ROUTER_FACADE = "org/springframework/web/reactive/function/server/CoRouterFunctionDslKt#"


def _shipped_router_catalog() -> Catalog:
    from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
    from sextant.resources import catalogs_dir

    return next(
        c for c in YamlCatalogSource(catalogs_dir()).load() if c.id == "spring-webflux-router"
    )


def _java_route(ordinal: int, verb: str, path: str, handler: str) -> list[CallSiteFact]:
    """`RouterFunctions.route(RequestPredicates.<VERB>(path), handler)` — the
    shape `fixtures/orders-service/.../routes/OrderRoutes.java` writes, spelled
    once so each verb below differs from its siblings in one cell."""
    predicate = 100 + ordinal * 10
    return [
        _site(
            ROUTES,
            ordinal * 2,
            _REQUEST_PREDICATES,
            verb,
            result=predicate,
            arguments=[CallArgument(kind="string", value=path)],
        ),
        _site(
            ROUTES,
            ordinal * 2 + 1,
            _ROUTER_FUNCTIONS,
            "route",
            result=predicate + 5,
            arguments=[
                CallArgument(kind="unresolved", source=predicate),
                CallArgument(kind="lambda", symbol=handler),
            ],
        ),
    ]


def test_the_shipped_router_catalog_reads_every_verb_the_framework_declares(tmp_path: Path):
    """`A-M9`, the positive half. `RequestPredicates` declares seven per-verb
    factories at spring-webflux 6.1.6 and 7.0.2 (CP-12 Q11) and the catalog
    encoded GET, POST and HEAD — which is exactly the verb vocabulary
    `OrderRoutes.java` uses. `RouterFunctions.route(RequestPredicates.PUT(…),
    …)`, an entirely ordinary WebFlux route, derived nothing, and
    `docs/COVERAGE.md` stated two WebFlux boundaries and named no verb gap.

    All seven asserted in one tree rather than one test per verb: the finding
    is about the SET, and a per-verb test would pass while the set was still
    short."""
    verbs = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    facts: list = [_method_symbol(LIST_ORDERS)]
    for index, verb in enumerate(verbs):
        facts += _java_route(index, verb, f"/orders/{verb.lower()}", LIST_ORDERS)
    workspace = _resolve(tmp_path, facts, _shipped_router_catalog())
    derived = sorted((str(row["method"]), str(row["path"])) for row in _rows(workspace))
    workspace.close()

    assert derived == sorted((verb, f"/orders/{verb.lower()}") for verb in verbs)


_BUILDER = "org/springframework/web/reactive/function/server/RouterFunctions$Builder#"


def test_the_router_builder_dsl_derives_nothing_and_that_is_a_stated_boundary(tmp_path: Path):
    """The round-1 review's MAJOR 3, pinned so that closing it is visible.

    `RouterFunctions.route().GET("/orders", handler).build()` is the BUILDER
    DSL — a third WebFlux routing surface, seven verbs x four overloads on
    `RouterFunctions$Builder` (`javap`, spring-webflux 6.1.6). It is undeclared
    in `spring-webflux-router.yml` and derives NOTHING, while `docs/COVERAGE.md`
    listed this exact call as "✅ shipped" and the `A-M9` pass added a sentence
    saying both routing DSLs now read all seven verbs. Two of four surfaces do;
    the COVERAGE rows now say which.

    The catalog's `entries` are argument-rooted (`route(predicate, handler)`) or
    body-linked (`coRouter`), and a builder is neither: the verb call sits on a
    RECEIVER returned by an argument-less `route()`, which this grammar has no
    word for. So this is an under-report and NOT a fabrication — the argument-
    less `route()` is not a root candidate, so no poisoned row is minted either,
    which is what the emptiness here asserts.

    **It goes red the moment the surface starts deriving**, which is the point:
    a boundary nothing pins is a boundary that quietly becomes a lie in either
    direction. The `@HTTP` exclusion in `retrofit.yml` is the same pattern.

    Its paired positive is
    `test_the_shipped_router_catalog_reads_every_verb_the_framework_declares`: the
    predicate form of the same route, on the same catalog, deriving."""
    facts: list = [
        _method_symbol(LIST_ORDERS),
        _site(ROUTES, 0, _ROUTER_FUNCTIONS, "route", result=200, arguments=[]),
        _site(
            ROUTES,
            1,
            _BUILDER,
            "GET",
            receiver=200,
            result=201,
            invoke_kind="interface",
            arguments=[
                CallArgument(kind="string", value="/orders"),
                CallArgument(kind="lambda", symbol=LIST_ORDERS),
            ],
        ),
        _site(ROUTES, 2, _BUILDER, "build", receiver=201, result=202, arguments=[]),
    ]
    workspace = _resolve(tmp_path, facts, _shipped_router_catalog())
    rows = _rows(workspace)
    workspace.close()

    assert rows == []


def test_a_media_only_route_serves_every_path_and_names_no_verb(tmp_path: Path):
    """`A-M9`'s near-miss for the VERB vocabulary, now asserting the row it derives.
    `accept` is a real `RequestPredicates` factory (`javap -p` lists it beside `all`,
    `path`, `headers`, `contentType`, `method` and `methods`) and it constrains a media
    type rather than naming a verb — CP-12 Q11 excludes it because it is not spelled in
    upper case, which is the framework's own way of marking the verb factories, and
    `"application/json"` is a string argument in exactly the position a path would
    occupy. So `method` is NULL: no `ACCEPT` verb is fabricated, and adding an `accept`
    row to `verbs` makes this fail with `("ACCEPT", "application/json")`.

    The route itself IS served — at every path, for clients accepting JSON — and the
    row says so: `/**`, the framework's any-path pattern, at `resolved`, carrying the
    media it read (spec §7 case 3 as ruled). **This test used to assert NOTHING was
    derived**: the engine emitted a resolved row with a NULL path, which
    `derive_call_endpoints.sql`'s addresses-nothing gate dropped by doctrine, and the
    under-report was recorded as a boundary in `docs/COVERAGE.md`. The gate stays;
    `combinator` now never hands it a resolved NULL path."""
    facts: list = [_method_symbol(LIST_ORDERS)]
    facts += _java_route(0, "accept", "application/json", LIST_ORDERS)
    workspace = _resolve(tmp_path, facts, _shipped_router_catalog())
    rows = _rows(workspace)
    workspace.close()

    assert _identities(rows) == [(None, "/**", _MODULE + LIST_ORDERS, "resolved")]
    assert [(row["consumes"], row["produces"]) for row in rows] == [(None, '["application/json"]')]


_MVC_ROUTER_FUNCTIONS = "org/springframework/web/servlet/function/RouterFunctions#"
_MVC_REQUEST_PREDICATES = "org/springframework/web/servlet/function/RequestPredicates#"


def _shipped_mvc_router_catalog() -> Catalog:
    from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
    from sextant.resources import catalogs_dir

    return next(c for c in YamlCatalogSource(catalogs_dir()).load() if c.id == "spring-mvc-router")


def _mvc_java_route(ordinal: int, verb: str, path: str, handler: str) -> list[CallSiteFact]:
    """The servlet twin of `_java_route`: identical call shape, `servlet` owners."""
    predicate = 100 + ordinal * 10
    return [
        _site(
            ROUTES,
            ordinal * 2,
            _MVC_REQUEST_PREDICATES,
            verb,
            result=predicate,
            arguments=[CallArgument(kind="string", value=path)],
        ),
        _site(
            ROUTES,
            ordinal * 2 + 1,
            _MVC_ROUTER_FUNCTIONS,
            "route",
            result=predicate + 5,
            arguments=[
                CallArgument(kind="unresolved", source=predicate),
                CallArgument(kind="lambda", symbol=handler),
            ],
        ),
    ]


def test_the_mvc_router_catalog_reads_every_verb_the_servlet_package_declares(tmp_path: Path):
    """W44's positive half. `org.springframework.web.servlet.function.RequestPredicates`
    declares the same seven per-verb factories the reactive package does, each
    `(Ljava/lang/String;)LRequestPredicate;` at spring-webmvc 6.1.6 — measured with
    `javap -p -s` rather than assumed from the twin, which is the mistake W43 caught one
    catalog earlier.

    All seven in one tree, not one test per verb: the finding this shape exists for is
    about the SET, and a per-verb test passes while the set is still short."""
    verbs = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    facts: list = [_method_symbol(LIST_ORDERS)]
    for index, verb in enumerate(verbs):
        facts += _mvc_java_route(index, verb, f"/{verb.lower()}", LIST_ORDERS)
    workspace = _resolve(tmp_path, facts, _shipped_mvc_router_catalog())
    identities = _identities(_rows(workspace))
    workspace.close()

    assert [(row[0], row[1]) for row in identities] == [
        (verb, f"/{verb.lower()}") for verb in sorted(verbs)
    ]
    # Every one `resolved`, and every one attributed to the handler the route names —
    # a verb read without its handler would be an address nobody serves.
    assert {row[3] for row in identities} == {"resolved"}
    assert {row[2].endswith("Handlers#listOrders(sig_a1).") for row in identities} == {True}


def test_an_mvc_media_only_route_serves_every_path_and_names_no_verb(tmp_path: Path):
    """The servlet twin of the reactive media-only route above: `accept` is a real
    `RequestPredicates` factory on this owner too, constrains a media type rather than
    naming a verb, and the route it guards serves every path — `method` NULL, `/**`,
    `resolved`, its media carried (spec §7 case 3 as ruled).

    *This slot first held an owner-varying input carrying the reactive twin's `pins`
    marker, which `scripts/guard_check.py` reported passing with that guard disabled — a
    marker naming a guard the test does not pin. The owner case is the near-miss below,
    which pins the entry-owner guard.*
    """
    facts: list = [_method_symbol(LIST_ORDERS)]
    facts += _mvc_java_route(0, "accept", "application/json", LIST_ORDERS)
    workspace = _resolve(tmp_path, facts, _shipped_mvc_router_catalog())
    rows = _rows(workspace)
    workspace.close()

    assert _identities(rows) == [(None, "/**", _MODULE + LIST_ORDERS, "resolved")]
    assert [(row["consumes"], row["produces"]) for row in rows] == [(None, '["application/json"]')]


@pytest.mark.declines("spring-mvc-router")
@pytest.mark.pins("combinator.entry-owner-is-the-declared-type")
def test_the_mvc_router_declines_a_reactive_owner_at_the_same_call_shape(tmp_path: Path):
    """§10 near-miss, and it is the one this catalog could actually get wrong.

    Every conjunct of the shipped rule holds — the same `route(predicate, handler)` call,
    the same verb factory name, the same string argument, the same handler — and only the
    PACKAGE differs: these are the reactive owners, which belong to `spring-webflux-router`.
    A catalog written by copying its twin and forgetting an owner would match both and
    publish a servlet row for a reactive route, or vice versa.

    Nothing at all is the required answer, not "something different": the reactive twin
    derives this tree correctly, and a second catalog deriving it as well is a duplicate
    row for one boundary."""
    facts: list = [_method_symbol(LIST_ORDERS)]
    facts += _java_route(0, "GET", "/orders", LIST_ORDERS)
    workspace = _resolve(tmp_path, facts, _shipped_mvc_router_catalog())
    identities = _identities(_rows(workspace))
    workspace.close()

    assert identities == []


@pytest.mark.declines("spring-webflux-router")
@pytest.mark.pins("combinator.entry-owner-is-the-declared-type")
def test_the_reactive_router_declines_a_servlet_owner_at_the_same_call_shape(tmp_path: Path):
    """The mirror near-miss for the reactive catalog: the servlet package's `route` and
    `GET`, identical in every other cell, derive nothing here — that tree belongs to
    `spring-mvc-router`, and a second row for one boundary is a duplicate. Both twins
    pin the entry's owner conjunct: with it gone, `route` on either package roots a
    tree, its predicate is read by neither vocabulary, and one unresolved row appears
    for a router the other catalog already derived correctly."""
    facts: list = [_method_symbol(LIST_ORDERS)]
    facts += _mvc_java_route(0, "GET", "/orders", LIST_ORDERS)
    workspace = _resolve(tmp_path, facts, _shipped_router_catalog())
    identities = _identities(_rows(workspace))
    workspace.close()

    assert identities == []


def _kotlin_route(ordinal: int, verb: str, path: str, handler: str) -> CallSiteFact:
    """`coRouter { <VERB>("/x") { … } }` — the DSL's own two-argument form,
    which declares a whole route in one call (2E checkpoint (1b))."""
    return _site(
        INLINE_BODY,
        ordinal,
        _CO_ROUTER_DSL,
        verb,
        receiver=None,
        arguments=[
            CallArgument(kind="string", value=path),
            CallArgument(kind="lambda", symbol=handler),
        ],
        invoke_kind="virtual",
    )


def test_the_kotlin_router_dsl_reads_every_verb_the_framework_declares(tmp_path: Path):
    """`A-M9` on the Kotlin half, where the catalog encoded GET and POST alone
    — again exactly what `KotlinOrderRoutes.kt` writes. `CoRouterFunctionDsl`
    declares the same seven verbs at both measured minors (CP-12 Q12), each in
    four overloads; the two-argument `(String, handler)` form is the one this
    vocabulary reads."""
    verbs = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    facts: list = [
        _method_symbol(LIST_ORDERS),
        _site(
            DSL_ROUTES,
            0,
            _CO_ROUTER_FACADE,
            "coRouter",
            result=9,
            arguments=[CallArgument(kind="lambda", symbol=INLINE_BODY)],
        ),
    ]
    facts += [
        _kotlin_route(index, verb, f"/kt/{verb.lower()}", LIST_ORDERS)
        for index, verb in enumerate(verbs)
    ]
    workspace = _resolve(tmp_path, facts, _shipped_router_catalog())
    derived = sorted((str(row["method"]), str(row["path"])) for row in _rows(workspace))
    workspace.close()

    assert derived == sorted((verb, f"/kt/{verb.lower()}") for verb in verbs)
