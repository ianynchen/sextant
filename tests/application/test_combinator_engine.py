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

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.application.resolve.request_requirements import record_request_requirements
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import CallArgument, CallSiteFact, CallTarget, Document, SymbolFact
from sextant.domain.symbols import method_descriptor
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
    receiver_parameter: int | None = None,
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
        receiver_parameter=receiver_parameter,
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


def _type_symbol(bare: str, *, lambda_body: str) -> SymbolFact:
    """A class-compiled lambda's own TYPE fact, carrying the body method it stands for
    (D00 §5 `lambda_body`) — what `effective_call_sites` reads to hand the engine an
    `instance` of that class as the `lambda` it is (spec 2026-09-19 §3b)."""
    return SymbolFact(
        document_id="doc_1",
        symbol=_MODULE + bare,
        construct_kind=ConstructKind.CLASS,
        lambda_body=lambda_body,
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
    an argument-rooted ENTRY, not a body-linked one. *Until the A1 final
    review (I-1) this test pinned that call as independently rootable, "two
    distinct facts about one method": `GET /y` from the body's own walk beside
    `GET /x/y` under the prefix. That was the same route twice — the body is a
    block written inside the continuation's own method, and checkpoint (1a)'s
    `other()` is a real helper called from the tree, not a linked body.* A
    method a linking call names is folded exactly once, by the root that
    reaches that call, so `GET /x/y` is the body's only row."""
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
        ]
    )
    assert {row["caller"] for row in rows} == {ROUTES}


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


_MVC_DSL = "org/springframework/web/servlet/function/RouterFunctionDsl#"
_MVC_DSL_FACADE = "org/springframework/web/servlet/function/RouterFunctionDslKt#"


@pytest.mark.pins("combinator.media-with-a-handler-is-a-row")
def test_a_media_predicate_that_carries_a_handler_derives_one_unresolved_row(tmp_path: Path):
    """`router { accept(JSON) { h } }` on a media name NO verb rule reads: the call is
    claimed into the tree (its name is in the media vocabulary) and a media rule
    contributes constraints, never routes, so the declaration would derive NOTHING
    (A1 Task 5 review) — spec §3's forbidden outcome, a declared route absent with
    nothing saying so. One unresolved row, no handler (the handler position is not
    something a media rule declares).

    Since `dsl-media-route` (spec 2026-09-21 §7a) the shipped router catalogs declare the
    handler-taking overload as a VERB rule and this arm no longer fires for them —
    `test_a_route_declared_under_a_media_guard_alone_derives_its_any_path_row_with_its_media`
    below is that reading. The guard stays for every media name a catalog declares no
    such rule for, and this test pins it on exactly that shape: the invented catalog's
    `RouterDsl.accept` is a media rule alone. The other half — a media call WITHOUT a
    handler, consumed by a route, still folds as media and nothing else — is
    `test_a_vararg_media_arrays_elements_fill_the_media_column` above, unchanged by this."""
    facts = [
        _site(
            DSL_ROUTES,
            0,
            DSL_FACADE,
            "router",
            result=4,
            arguments=[CallArgument(kind="lambda", source=3, symbol=DSL_BODY)],
        ),
        _site(
            DSL_BODY,
            0,
            DSL,
            "accept",
            invoke_kind="virtual",
            descriptor="(Lcom/example/web/MediaType;Lkotlin/jvm/functions/Function1;)V",
            arguments=[
                CallArgument(kind="enum", symbol=MEDIA_TYPE + "APPLICATION_JSON."),
                CallArgument(kind="lambda", symbol=LIST_ORDERS, source=0),
            ],
        ),
        *_handler_symbols(),
    ]
    workspace = _resolve(tmp_path, facts)
    rows = _rows(workspace)
    workspace.close()

    assert [(row["method"], row["path"], row["handler"], row["resolution"]) for row in rows] == [
        (None, None, None, "unresolved")
    ]


def _media_route_matches() -> dict[str, object]:
    """The invented DSL with `dsl-media-route`'s two verb rules (spec 2026-09-21 §7a): the
    handler-taking `accept`/`contentType` overloads, arity 2, media at 0, handler at 1,
    no verb of their own — beside the media rules of the same names, which keep reading
    the arity-1 vararg factories."""
    matches = _matches()
    vocabulary = dict(matches["vocabulary"])  # type: ignore[arg-type]
    vocabulary["verbs"] = list(vocabulary["verbs"]) + [  # type: ignore[arg-type]
        {
            "owner": "com.example.web.RouterDsl",
            "method": "accept",
            "arity": 2,
            "media_arg": 0,
            "fills": "produces",
            "handler_arg": 1,
            "verb": None,
        },
        {
            "owner": "com.example.web.RouterDsl",
            "method": "contentType",
            "arity": 2,
            "media_arg": 0,
            "fills": "consumes",
            "handler_arg": 1,
            "verb": None,
        },
    ]
    vocabulary["media"] = list(vocabulary["media"]) + [  # type: ignore[arg-type]
        {"owner": "com.example.web.RouterDsl", "method": "contentType", "fills": "consumes"},
    ]
    return {**matches, "vocabulary": vocabulary}


def _media_guarded_body(name: str, media: str, handler: str) -> list:
    return [
        _site(
            DSL_ROUTES,
            0,
            DSL_FACADE,
            "router",
            result=4,
            arguments=[CallArgument(kind="lambda", source=3, symbol=DSL_BODY)],
        ),
        _site(
            DSL_BODY,
            0,
            DSL,
            name,
            invoke_kind="virtual",
            descriptor="(Lcom/example/web/MediaType;Lkotlin/jvm/functions/Function1;)V",
            arguments=[
                CallArgument(kind="enum", symbol=MEDIA_TYPE + media + "."),
                CallArgument(kind="lambda", symbol=handler, source=0),
            ],
        ),
        *_handler_symbols(),
    ]


def test_a_route_declared_under_a_media_guard_alone_derives_its_any_path_row_with_its_media(
    tmp_path: Path,
):
    """`dsl-media-route` (spec 2026-09-21 §7a): `router { accept(JSON) { h } }` is a
    route declared under a media guard and nothing else — no verb, no path. A verb rule
    on the handler-taking overload reads the media at `media_arg` into the column
    `fills` names, the handler at `handler_arg`, and no verb (`verb: null`, as
    `route(predicate, handler)` reads): one row, `method` NULL, path `/**` (the served
    any-path pattern, `_served`), RESOLVED — nothing was poisoned, the author wrote the
    route open. The `contentType` twin fills `consumes`. No `all_methods` fan-out
    (§0b A1): a verb-less route is one row, exactly as it renders everywhere else."""
    catalog = _catalog(_media_route_matches())
    workspace = _resolve(
        tmp_path, _media_guarded_body("accept", "APPLICATION_JSON", LIST_ORDERS), catalog
    )
    rows = _rows(workspace)
    workspace.close()
    assert _identities(rows) == [(None, "/**", _MODULE + LIST_ORDERS, "resolved")]
    assert (rows[0]["produces"], rows[0]["consumes"]) == (f'["{JSON}"]', None)
    assert rows[0]["caller"] == DSL_ROUTES

    workspace = _resolve(
        tmp_path / "consumes",
        _media_guarded_body("contentType", "APPLICATION_XML", CREATE_ORDER),
        catalog,
    )
    rows = _rows(workspace)
    workspace.close()
    assert _identities(rows) == [(None, "/**", _MODULE + CREATE_ORDER, "resolved")]
    assert (rows[0]["produces"], rows[0]["consumes"]) == (None, f'["{XML}"]')


def test_the_vararg_media_factory_still_reads_as_media_beside_its_verb_rule_twin(
    tmp_path: Path,
):
    """The other overload of the same name, and the reason the verb rule declares an
    `arity`: `accept(MediaType...)` is a predicate FACTORY, arity 1 (one array slot), and
    a verb rule on `accept` must not swallow it. A call the verb rules do not accept
    falls through to the media rule of the same name rather than to the G-13 poison —
    so `accept(JSON).nest { GET("/rich") { } }` reads its prefix's media exactly as it
    did before the verb rule existed, and an UNREADABLE vararg still contributes nothing
    (`_body_linked_facts`' own arm, unchanged)."""
    catalog = _catalog(_media_route_matches())
    facts = _body_linked_facts()
    workspace = _resolve(tmp_path, facts, catalog)
    rows = _rows(workspace)
    workspace.close()
    assert _identities(rows) == [
        ("GET", "/kt/orders", None, "resolved"),
        ("GET", "/kt/rich", _MODULE + INLINE_BODY, "resolved"),
    ]
    assert [row["produces"] for row in rows] == [None, None]

    readable = [
        fact.model_copy(
            update={
                "arguments": [
                    CallArgument(
                        kind="array",
                        elements=[
                            CallArgument(kind="enum", symbol=MEDIA_TYPE + "APPLICATION_JSON.")
                        ],
                    )
                ]
            }
        )
        if isinstance(fact, CallSiteFact) and fact.target.name == "accept"
        else fact
        for fact in facts
    ]
    workspace = _resolve(tmp_path / "readable", readable, catalog)
    rows = _rows(workspace)
    workspace.close()
    assert [(row["path"], row["produces"]) for row in rows] == [
        ("/kt/orders", None),
        ("/kt/rich", f'["{JSON}"]'),
    ]


@pytest.mark.parametrize(
    ("rule", "message"),
    [
        (
            {"method": "accept", "arity": 2, "fills": "produces", "handler_arg": 1, "verb": None},
            r"accept.*media_arg",
        ),
        (
            {"method": "accept", "arity": 2, "media_arg": 0, "handler_arg": 1, "verb": None},
            r"accept.*fills",
        ),
        (
            {
                "method": "accept",
                "arity": 2,
                "media_arg": 5,
                "fills": "produces",
                "handler_arg": 1,
                "verb": None,
            },
            r"accept.*media_arg",
        ),
        (
            {
                "method": "accept",
                "media_arg": 0,
                "fills": "produces",
                "handler_arg": 1,
                "verb": None,
            },
            r"accept.*arity",
        ),
    ],
    ids=[
        "fills-without-media_arg",
        "media_arg-without-fills",
        "media_arg-outside-arity",
        "no-arity-on-a-media-name",
    ],
)
def test_a_verb_rule_with_half_a_media_position_or_no_arity_on_a_media_name_is_refused(
    tmp_path: Path, rule: dict, message: str
):
    """`media_arg` and `fills` come together on a verb as on a prefix — one names where,
    the other which column — and the position lies inside the rule's arity. And a verb
    rule on a name a `media` rule also reads MUST declare an `arity`: without one it
    accepts every call of that name, and the vararg factory the media rule exists to
    read would never be reached — silently, the media column NULL on every route under
    that guard."""
    matches = _matches()
    vocabulary = dict(matches["vocabulary"])  # type: ignore[arg-type]
    vocabulary["verbs"] = list(vocabulary["verbs"]) + [  # type: ignore[arg-type]
        {"owner": "com.example.web.RouterDsl", **rule}
    ]
    with pytest.raises(CatalogError, match=message):
        _resolve(tmp_path, [], _catalog({**matches, "vocabulary": vocabulary}))


def test_the_shipped_servlet_dsl_reads_its_media_guarded_route(tmp_path: Path):
    """The shipped servlet catalog on the real DSL owner — the line `KotlinMvcRoutes.kt`
    writes, `accept(MediaType.APPLICATION_JSON) { h }`: a resolved row with its handler
    and `produces`, where it derived the unresolved gap row before `dsl-media-route`."""
    from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
    from sextant.resources import catalogs_dir

    catalog = next(
        c for c in YamlCatalogSource(catalogs_dir()).load() if c.id == "spring-mvc-router"
    )
    entry = _site(
        DECLARER + "routes(sig_r).",
        0,
        _MVC_DSL_FACADE,
        "router",
        arguments=[CallArgument(kind="lambda", symbol=INLINE_BODY, source=0)],
        result=1,
    )
    body = [
        _site(
            INLINE_BODY,
            0,
            _MVC_DSL,
            "accept",
            invoke_kind="virtual",
            descriptor="(Lorg/springframework/http/MediaType;Lkotlin/jvm/functions/Function1;)V",
            arguments=[
                CallArgument(
                    kind="enum", symbol="org/springframework/http/MediaType#APPLICATION_JSON."
                ),
                CallArgument(kind="lambda", symbol=LIST_ORDERS, source=0),
            ],
        ),
    ]
    workspace = _resolve(
        tmp_path, [*_handler_symbols(), _method_symbol(INLINE_BODY), entry, *body], catalog
    )
    rows = _rows(workspace)
    workspace.close()

    assert [
        (row["method"], row["path"], row["handler"], row["resolution"], row["produces"])
        for row in rows
    ] == [(None, "/**", _MODULE + LIST_ORDERS, "resolved", f'["{JSON}"]')]


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


# --- the builder chain (spec §4) ----------------------------------------------

BUILDER = "com/example/web/RouterBuilder#"
BUILDER_TYPE = "com.example.web.RouterBuilder"
_BUILDER_DESC = "Lcom/example/web/RouterBuilder;"
_BUILDER_BODY = DECLARER + "lambda$routes$1(sig_b1)."


def _builder_matches() -> dict[str, object]:
    matches = _overload_matches()
    vocabulary = matches["vocabulary"]
    vocabulary["verbs"] = list(vocabulary["verbs"]) + [  # type: ignore[arg-type]
        # `builder.GET("/x", h)`: declares a route AND carries the chain on.
        {
            "owner": BUILDER_TYPE,
            "method": "GET",
            "verb": "GET",
            "arity": 2,
            "arg_types": {0: _STRING},
            "path_arg": 0,
            "handler_arg": 1,
            "extends_receiver": True,
        },
        {
            "owner": BUILDER_TYPE,
            "method": "GET",
            "verb": "GET",
            "arity": 1,
            "handler_arg": 0,
            "extends_receiver": True,
        },
        {
            "owner": BUILDER_TYPE,
            "method": "POST",
            "verb": "POST",
            "arity": 2,
            "arg_types": {0: _STRING},
            "path_arg": 0,
            "handler_arg": 1,
            "extends_receiver": True,
        },
        {
            "owner": BUILDER_TYPE,
            "method": "DELETE",
            "verb": "DELETE",
            "arity": 2,
            "arg_types": {0: _STRING},
            "path_arg": 0,
            "handler_arg": 1,
            "extends_receiver": True,
        },
        # `builder.resources("/static/**", location)`: served, no handler method (§6).
        {
            "owner": BUILDER_TYPE,
            "method": "resources",
            "verb": "GET",
            "arity": 2,
            "arg_types": {0: _STRING},
            "path_arg": 0,
            "handler": "none",
            "extends_receiver": True,
        },
    ]
    vocabulary["prefixes"] = list(vocabulary["prefixes"]) + [  # type: ignore[arg-type]
        # `builder.path("/x", b -> b.GET(h))`: a prefix over a lambda-bodied subtree that
        # ALSO carries the chain on (spec §5).
        {
            "owner": BUILDER_TYPE,
            "method": "path",
            "arity": 2,
            "path_arg": 0,
            "body_arg": 1,
            "extends_receiver": True,
        },
    ]
    return {
        **matches,
        "vocabulary": vocabulary,
        # `arity: 0`: the argument-less factory, NOT the `route(predicate, handler)` entry
        # of the same name — read as an origin, that one's route would vanish.
        "origins": [{"owner": "com.example.web.Routers", "method": "route", "arity": 0}],
        "continuations": list(matches["continuations"])
        + [  # type: ignore[arg-type]
            {"name": "build", "owner": BUILDER_TYPE},
            {"name": "filter", "owner": BUILDER_TYPE, "pass_through": True},
            # `builder.add(router)`: a whole router folded into the chain (spec §7 case 4).
            {"name": "add", "owner": BUILDER_TYPE},
        ],
    }


def _builder_chain(*, with_filter: bool, declared_origin: bool = True) -> list:
    """`Routers.route().GET("/a", h).filter(f).POST("/b", h).build()` — each call's
    receiver is the previous call's result, `route()` produces the first one, `build()`
    is returned and so consumed by nothing."""
    caller = DECLARER + "routes(sig_r)."
    origin = "route" if declared_origin else "routeFrom"
    sites = [
        _site(caller, 0, ROUTERS, origin, result=0, descriptor=f"(){_BUILDER_DESC}"),
        _site(
            caller,
            1,
            BUILDER,
            "GET",
            invoke_kind="virtual",
            receiver=0,
            result=1,
            descriptor=f"(Ljava/lang/String;Lcom/example/web/Handler;){_BUILDER_DESC}",
            arguments=[
                CallArgument(kind="string", value="/a"),
                CallArgument(kind="lambda", symbol=LIST_ORDERS, source=1),
            ],
        ),
    ]
    last = 1
    if with_filter:
        sites.append(
            _site(
                caller,
                2,
                BUILDER,
                "filter",
                invoke_kind="virtual",
                receiver=1,
                result=2,
                descriptor=f"(Lcom/example/web/Filter;){_BUILDER_DESC}",
                arguments=[CallArgument(kind="lambda", symbol=HEALTH, source=2)],
            )
        )
        last = 2
    sites.append(
        _site(
            caller,
            last + 1,
            BUILDER,
            "POST",
            invoke_kind="virtual",
            receiver=last,
            result=last + 1,
            descriptor=f"(Ljava/lang/String;Lcom/example/web/Handler;){_BUILDER_DESC}",
            arguments=[
                CallArgument(kind="string", value="/b"),
                CallArgument(kind="lambda", symbol=CREATE_ORDER, source=last + 1),
            ],
        )
    )
    sites.append(
        _site(
            caller,
            last + 2,
            BUILDER,
            "build",
            invoke_kind="virtual",
            receiver=last + 1,
            result=last + 2,
            descriptor="()Lcom/example/web/Router;",
        )
    )
    return [*_handler_symbols(), *sites]


def test_a_builder_chain_derives_every_verb_it_carries_rooted_at_build(tmp_path: Path):
    """Spec §4: `build()` is the outermost unconsumed call, so it roots; each verb both
    declares its route and extends its receiver; `route()` is a declared origin, so the
    chain's head contributes zero routes WITHOUT poisoning (§4b)."""
    workspace = _resolve(tmp_path, _builder_chain(with_filter=False), _catalog(_builder_matches()))
    assert _identities(_rows(workspace)) == [
        ("GET", "/a", _MODULE + LIST_ORDERS, "resolved"),
        ("POST", "/b", _MODULE + CREATE_ORDER, "resolved"),
    ]


def test_a_declared_pass_through_carries_the_chain_and_reads_no_argument(tmp_path: Path):
    """Spec §8 test 5: a `filter(f)` mid-chain neither declares a route nor reads its
    lambda as a handler; the routes on both sides of it survive."""
    workspace = _resolve(tmp_path, _builder_chain(with_filter=True), _catalog(_builder_matches()))
    assert _identities(_rows(workspace)) == [
        ("GET", "/a", _MODULE + LIST_ORDERS, "resolved"),
        ("POST", "/b", _MODULE + CREATE_ORDER, "resolved"),
    ]


def test_an_undeclared_chain_head_is_one_unresolved_row_beside_the_chains_own_routes(
    tmp_path: Path,
):
    """Spec §4b's consequence, pinned in the refusing direction: a chain whose head is
    NOT a declared origin carries one unresolved row for it — the engine cannot tell
    "the chain starts here" from "I could not read the receiver", and does not guess.
    The verbs to its right still declare their own routes, exactly as a router composed
    from another method's return does beside an `and` (spec §7 case 4: "one unresolved
    row, per the existing rule") — the unread head is never a silent absence, and the
    routes the author wrote beside it are never lost to it."""
    workspace = _resolve(
        tmp_path,
        _builder_chain(with_filter=False, declared_origin=False),
        _catalog(_builder_matches()),
    )
    assert _identities(_rows(workspace)) == [
        ("GET", "/a", _MODULE + LIST_ORDERS, "resolved"),
        ("POST", "/b", _MODULE + CREATE_ORDER, "resolved"),
        (None, None, None, "unresolved"),
    ]


def _statement_form(*, chained_first: bool) -> list:
    """`var b = Routers.route(); b.GET("/a", h); b.POST("/b", h); return b.build();` —
    the builder is mutable and every method returns it, so each statement's receiver is
    the ORIGIN's result and nothing consumes the statement's own. `chained_first` writes
    the mixed form, `var b = route().GET("/a", h); b.POST("/b", h); return b.build();`,
    where `POST` and `build()` sit on `GET`'s result instead. The lambda arguments'
    `source` ids name the bootstrap sites the real facts carry (no site here produces
    them), never the verb's own result — that would read as the verb consuming itself."""
    caller = DECLARER + "routes(sig_r)."
    head = 1 if chained_first else 0
    return [
        *_handler_symbols(),
        _site(caller, 0, ROUTERS, "route", result=0, descriptor=f"(){_BUILDER_DESC}"),
        _site(
            caller,
            1,
            BUILDER,
            "GET",
            invoke_kind="virtual",
            receiver=0,
            result=1,
            descriptor=f"(Ljava/lang/String;Lcom/example/web/Handler;){_BUILDER_DESC}",
            arguments=[
                CallArgument(kind="string", value="/a"),
                CallArgument(kind="lambda", symbol=LIST_ORDERS, source=101),
            ],
        ),
        _site(
            caller,
            2,
            BUILDER,
            "POST",
            invoke_kind="virtual",
            receiver=head,
            result=2,
            descriptor=f"(Ljava/lang/String;Lcom/example/web/Handler;){_BUILDER_DESC}",
            arguments=[
                CallArgument(kind="string", value="/b"),
                CallArgument(kind="lambda", symbol=CREATE_ORDER, source=102),
            ],
        ),
        _site(
            caller,
            3,
            BUILDER,
            "build",
            invoke_kind="virtual",
            receiver=head,
            result=3,
            descriptor="()Lcom/example/web/Router;",
        ),
    ]


def test_the_statement_form_of_the_builder_roots_at_each_verb(tmp_path: Path):
    """Spec §4 as ruled at review: the builder is mutable, so real code writes one
    statement per route — conditional registration is written no other way — and
    that form derived NOTHING: verbs never rooted, `build()` rooted, its receiver was
    the origin, and the origin contributes `[]`. A receiver-extending verb whose own
    result nothing consumes, and whose receiver a call in this method produced, is a
    root of its own."""
    workspace = _resolve(
        tmp_path, _statement_form(chained_first=False), _catalog(_builder_matches())
    )
    assert _identities(_rows(workspace)) == [
        ("GET", "/a", _MODULE + LIST_ORDERS, "resolved"),
        ("POST", "/b", _MODULE + CREATE_ORDER, "resolved"),
    ]


def test_the_mixed_form_derives_each_route_exactly_once(tmp_path: Path):
    """`var b = route().GET("/a", h); b.POST("/b", h); return b.build();` — `POST` and
    `build()` both sit on `GET`'s result and both root; both reach `GET /a` through
    their chain, and identity dedup keeps one row of it."""
    workspace = _resolve(
        tmp_path, _statement_form(chained_first=True), _catalog(_builder_matches())
    )
    assert _identities(_rows(workspace)) == [
        ("GET", "/a", _MODULE + LIST_ORDERS, "resolved"),
        ("POST", "/b", _MODULE + CREATE_ORDER, "resolved"),
    ]


def test_a_body_verb_never_roots_and_derives_once_prefixed(tmp_path: Path):
    """Checkpoint F4, re-pinned now that a verb CAN root: inside `path("/x", b ->
    b.GET("/inner", h).DELETE("/inner/{id}", h))` the chain's HEAD sits on the
    lambda's own parameter (`receiver_parameter`, no producing call in its method) —
    and the `DELETE` after it sits on `GET`'s result, a call in the same method, which
    is exactly the receiver a statement-form verb has. The head is what tells them
    apart: neither verb roots, and the body walk alone folds both, once, under the
    prefix, never bare. The live fixture's `/bld/nested/inner` pair derived bare the
    first time this test held one verb."""
    caller = DECLARER + "routes(sig_r)."
    facts = [
        *_handler_symbols(),
        _method_symbol(_BUILDER_BODY),
        _site(caller, 0, ROUTERS, "route", result=20, descriptor=f"(){_BUILDER_DESC}"),
        _site(
            caller,
            1,
            BUILDER,
            "path",
            invoke_kind="virtual",
            receiver=20,
            result=21,
            descriptor=f"(Ljava/lang/String;Ljava/util/function/Consumer;){_BUILDER_DESC}",
            arguments=[
                CallArgument(kind="string", value="/x"),
                CallArgument(kind="lambda", symbol=_BUILDER_BODY, source=1),
            ],
        ),
        _site(
            caller,
            2,
            BUILDER,
            "build",
            invoke_kind="virtual",
            receiver=21,
            result=22,
            descriptor="()Lcom/example/web/Router;",
        ),
        _site(
            _BUILDER_BODY,
            0,
            BUILDER,
            "GET",
            invoke_kind="virtual",
            receiver=None,
            receiver_parameter=1,
            result=1,
            descriptor=f"(Ljava/lang/String;Lcom/example/web/Handler;){_BUILDER_DESC}",
            arguments=[
                CallArgument(kind="string", value="/inner"),
                CallArgument(kind="lambda", symbol=HEALTH, source=101),
            ],
        ),
        _site(
            _BUILDER_BODY,
            1,
            BUILDER,
            "DELETE",
            invoke_kind="virtual",
            receiver=1,
            result=None,
            descriptor=f"(Ljava/lang/String;Lcom/example/web/Handler;){_BUILDER_DESC}",
            arguments=[
                CallArgument(kind="string", value="/inner/{id}"),
                CallArgument(kind="lambda", symbol=HEALTH, source=102),
            ],
        ),
    ]
    workspace = _resolve(tmp_path, facts, _catalog(_builder_matches()))
    assert _identities(_rows(workspace)) == [
        ("DELETE", "/x/inner/{id}", _MODULE + HEALTH, "resolved"),
        ("GET", "/x/inner", _MODULE + HEALTH, "resolved"),
    ]


def _prefixed_body_facts(*, statement: bool) -> list:
    """`route().path("/api", api -> api.GET("/x", h)).build()` chained, or as the statement
    form `var b = route(); b.path("/api", …); return b.build();` — the prefix's receiver
    is the origin's result either way; only what consumes the prefix's own result
    differs (`build()` in the chain, nothing in the statement)."""
    caller = DECLARER + "routes(sig_r)."
    return [
        *_handler_symbols(),
        _method_symbol(_BUILDER_BODY),
        _site(caller, 0, ROUTERS, "route", result=20, descriptor=f"(){_BUILDER_DESC}"),
        _site(
            caller,
            1,
            BUILDER,
            "path",
            invoke_kind="virtual",
            receiver=20,
            result=21,
            descriptor=f"(Ljava/lang/String;Ljava/util/function/Consumer;){_BUILDER_DESC}",
            arguments=[
                CallArgument(kind="string", value="/api"),
                CallArgument(kind="lambda", symbol=_BUILDER_BODY, source=101),
            ],
        ),
        _site(
            caller,
            2,
            BUILDER,
            "build",
            invoke_kind="virtual",
            receiver=20 if statement else 21,
            result=22,
            descriptor="()Lcom/example/web/Router;",
        ),
        _site(
            _BUILDER_BODY,
            0,
            BUILDER,
            "GET",
            invoke_kind="virtual",
            receiver=None,
            receiver_parameter=1,
            result=None,
            descriptor=f"(Ljava/lang/String;Lcom/example/web/Handler;){_BUILDER_DESC}",
            arguments=[
                CallArgument(kind="string", value="/x"),
                CallArgument(kind="lambda", symbol=HEALTH, source=102),
            ],
        ),
    ]


def test_a_statement_form_prefix_roots_like_a_verb(tmp_path: Path):
    """Fix round 3: `var b = route(); b.path("/api", api -> api.GET("/x", h)); return
    b.build();` rooted NOWHERE — the statement-form rule admitted verbs only, and the
    builder's `path`/`nest` are prefix rules. A receiver-extending prefix roots under the
    same head test, and the chained spelling still derives the route once: the prefix
    is a candidate there too, but `build()` consumes its result."""
    for statement in (True, False):
        workspace = _resolve(
            tmp_path / str(statement),
            _prefixed_body_facts(statement=statement),
            _catalog(_builder_matches()),
        )
        assert _identities(_rows(workspace)) == [("GET", "/api/x", _MODULE + HEALTH, "resolved")], (
            statement
        )


_SUPPLIER_BODY = DECLARER + "lambda$routes$2(sig_b2)."
_FREE_BODY = DECLARER + "lambda$routes$3(sig_b3)."


def _supplier_body_facts() -> list:
    """`route().path("/api", () -> route().GET("/x", h).build()).build()` — the Supplier
    overload, Spring's own Javadoc example for `Builder.nest(RequestPredicate, Supplier)`:
    the body is a whole chain of its own, origin to `build()`, whose `build()` nothing in
    the body consumes."""
    caller = DECLARER + "routes(sig_r)."
    return [
        *_handler_symbols(),
        _method_symbol(_SUPPLIER_BODY),
        _site(caller, 0, ROUTERS, "route", result=20, descriptor=f"(){_BUILDER_DESC}"),
        _site(
            caller,
            1,
            BUILDER,
            "path",
            invoke_kind="virtual",
            receiver=20,
            result=21,
            descriptor=f"(Ljava/lang/String;Ljava/util/function/Supplier;){_BUILDER_DESC}",
            arguments=[
                CallArgument(kind="string", value="/api"),
                CallArgument(kind="lambda", symbol=_SUPPLIER_BODY, source=101),
            ],
        ),
        _site(
            caller,
            2,
            BUILDER,
            "build",
            invoke_kind="virtual",
            receiver=21,
            result=22,
            descriptor="()Lcom/example/web/Router;",
        ),
        _site(_SUPPLIER_BODY, 0, ROUTERS, "route", result=0, descriptor=f"(){_BUILDER_DESC}"),
        _site(
            _SUPPLIER_BODY,
            1,
            BUILDER,
            "GET",
            invoke_kind="virtual",
            receiver=0,
            result=1,
            descriptor=f"(Ljava/lang/String;Lcom/example/web/Handler;){_BUILDER_DESC}",
            arguments=[
                CallArgument(kind="string", value="/x"),
                CallArgument(kind="lambda", symbol=HEALTH, source=102),
            ],
        ),
        _site(
            _SUPPLIER_BODY,
            2,
            BUILDER,
            "build",
            invoke_kind="virtual",
            receiver=1,
            result=2,
            descriptor="()Lcom/example/web/Router;",
        ),
    ]


@pytest.mark.pins("combinator.linked-body-never-roots")
def test_a_linked_body_is_never_scanned_for_roots_of_its_own(tmp_path: Path):
    """A1 final review, I-1. The module docstring said "body methods are never rooted on
    their own" and the code relied on bodies holding nothing but vocabulary calls — the
    chain-head test protects receiver-extending verbs and prefixes only. A Supplier body
    holds a whole chain, and its `build()` is an owner-declaring continuation that nothing
    in the body consumes, so it rooted: `GET /api/x` from the prefix's fold AND a bare
    `GET /x` with the lambda as `caller`, the same route twice. A method some linking
    call names as its body is folded exactly once, by whichever root reaches that call,
    and is never scanned for roots of its own."""
    caller = DECLARER + "routes(sig_r)."
    workspace = _resolve(tmp_path, _supplier_body_facts(), _catalog(_builder_matches()))
    rows = _rows(workspace)
    workspace.close()

    assert _identities(rows) == [("GET", "/api/x", _MODULE + HEALTH, "resolved")]
    assert [row["caller"] for row in rows] == [caller]


def test_an_add_inside_a_consumer_body_derives_its_router_once_prefixed(tmp_path: Path):
    """The same finding on the Consumer overload: `path("/api", b ->
    b.add(RouterFunctions.route(GET("/z"), h)))`. `add` is an owner-declaring
    continuation, so it was a root candidate wherever it sat, and inside the body its
    result is consumed by nothing — `GET /api/z` under the prefix and a bare `GET /z`
    beside it. Exactly one row now."""
    caller = DECLARER + "routes(sig_r)."
    facts = [
        *_handler_symbols(),
        _method_symbol(_BUILDER_BODY),
        _site(caller, 0, ROUTERS, "route", result=20, descriptor=f"(){_BUILDER_DESC}"),
        _site(
            caller,
            1,
            BUILDER,
            "path",
            invoke_kind="virtual",
            receiver=20,
            result=21,
            descriptor=f"(Ljava/lang/String;Ljava/util/function/Consumer;){_BUILDER_DESC}",
            arguments=[
                CallArgument(kind="string", value="/api"),
                CallArgument(kind="lambda", symbol=_BUILDER_BODY, source=101),
            ],
        ),
        _site(
            caller,
            2,
            BUILDER,
            "build",
            invoke_kind="virtual",
            receiver=21,
            result=22,
            descriptor="()Lcom/example/web/Router;",
        ),
        _site(
            _BUILDER_BODY,
            0,
            PREDICATES,
            "GET",
            result=5,
            arguments=[CallArgument(kind="string", value="/z")],
        ),
        _site(
            _BUILDER_BODY,
            1,
            ROUTERS,
            "route",
            result=11,
            arguments=[
                CallArgument(kind="unresolved", source=5),
                CallArgument(kind="lambda", symbol=HEALTH, source=102),
            ],
        ),
        _site(
            _BUILDER_BODY,
            2,
            BUILDER,
            "add",
            invoke_kind="virtual",
            receiver=None,
            receiver_parameter=1,
            result=12,
            descriptor=f"(Lcom/example/web/Router;){_BUILDER_DESC}",
            arguments=[CallArgument(kind="unresolved", source=11)],
        ),
    ]
    workspace = _resolve(tmp_path, facts, _catalog(_builder_matches()))
    rows = _rows(workspace)
    workspace.close()

    assert _identities(rows) == [("GET", "/api/z", _MODULE + HEALTH, "resolved")]
    assert [row["caller"] for row in rows] == [caller]


def test_a_lambda_no_linking_call_names_still_roots_as_any_method_does(tmp_path: Path):
    """The boundary of the skip: only a method some LINKING call names as its body is
    left out of the root scan. A lambda handed to a method the catalog does not claim —
    `Optional.map(x -> route().GET("/y", h).build())` — is a method like any other, and
    the chain it holds roots at its `build()` exactly as before, with the lambda as
    `caller`."""
    caller = DECLARER + "routes(sig_r)."
    facts = [
        *_handler_symbols(),
        _method_symbol(_FREE_BODY),
        _site(
            caller,
            0,
            "java/util/Optional#",
            "map",
            invoke_kind="virtual",
            receiver=None,
            receiver_parameter=1,
            result=30,
            arguments=[CallArgument(kind="lambda", symbol=_FREE_BODY, source=101)],
        ),
        _site(_FREE_BODY, 0, ROUTERS, "route", result=0, descriptor=f"(){_BUILDER_DESC}"),
        _site(
            _FREE_BODY,
            1,
            BUILDER,
            "GET",
            invoke_kind="virtual",
            receiver=0,
            result=1,
            descriptor=f"(Ljava/lang/String;Lcom/example/web/Handler;){_BUILDER_DESC}",
            arguments=[
                CallArgument(kind="string", value="/y"),
                CallArgument(kind="lambda", symbol=HEALTH, source=102),
            ],
        ),
        _site(
            _FREE_BODY,
            2,
            BUILDER,
            "build",
            invoke_kind="virtual",
            receiver=1,
            result=2,
            descriptor="()Lcom/example/web/Router;",
        ),
    ]
    workspace = _resolve(tmp_path, facts, _catalog(_builder_matches()))
    rows = _rows(workspace)
    workspace.close()

    assert _identities(rows) == [("GET", "/y", _MODULE + HEALTH, "resolved")]
    assert [row["caller"] for row in rows] == [_FREE_BODY]


def _pass_through_on_the_origin(*, head_read: bool) -> list:
    """`route().filter(f).GET("/a", h).build()`; with `head_read=False` the `filter` sits
    on a call this method cannot read (`routeFrom()`, no origin declares it)."""
    caller = DECLARER + "routes(sig_r)."
    return [
        *_handler_symbols(),
        _site(
            caller,
            0,
            ROUTERS,
            "route" if head_read else "routeFrom",
            result=0,
            descriptor=f"(){_BUILDER_DESC}",
        ),
        _site(
            caller,
            1,
            BUILDER,
            "filter",
            invoke_kind="virtual",
            receiver=0,
            result=1,
            descriptor=f"(Lcom/example/web/Filter;){_BUILDER_DESC}",
            arguments=[CallArgument(kind="lambda", symbol=HEALTH, source=101)],
        ),
        _site(
            caller,
            2,
            BUILDER,
            "GET",
            invoke_kind="virtual",
            receiver=1,
            result=2,
            descriptor=f"(Ljava/lang/String;Lcom/example/web/Handler;){_BUILDER_DESC}",
            arguments=[
                CallArgument(kind="string", value="/a"),
                CallArgument(kind="lambda", symbol=LIST_ORDERS, source=102),
            ],
        ),
        _site(
            caller,
            3,
            BUILDER,
            "build",
            invoke_kind="virtual",
            receiver=2,
            result=3,
            descriptor="()Lcom/example/web/Router;",
        ),
    ]


def test_a_pass_through_directly_on_the_origin_contributes_nothing(tmp_path: Path):
    """Fix round 3: `route().filter(f).GET("/a", h).build()` derived a spurious
    unresolved row — `filter`'s own routes are `[]` because its chain reaches the
    origin, and the verb after it read that `[]` as an unread receiver. A pass-through
    contributes nothing by definition, so the chain steps THROUGH it to its own
    receiver before deciding, and reaches the origin clean."""
    workspace = _resolve(
        tmp_path, _pass_through_on_the_origin(head_read=True), _catalog(_builder_matches())
    )
    assert _identities(_rows(workspace)) == [("GET", "/a", _MODULE + LIST_ORDERS, "resolved")]


def test_a_pass_through_whose_own_receiver_is_unread_still_poisons_once(tmp_path: Path):
    """The other side of stepping through: the pass-through hides nothing. Its receiver
    unread is one unresolved row, exactly once, beside the verb's own route."""
    workspace = _resolve(
        tmp_path, _pass_through_on_the_origin(head_read=False), _catalog(_builder_matches())
    )
    assert _identities(_rows(workspace)) == [
        ("GET", "/a", _MODULE + LIST_ORDERS, "resolved"),
        (None, None, None, "unresolved"),
    ]


def test_two_equal_verbs_merge_to_that_verb(tmp_path: Path):
    """Spec §4 as ruled: `resource(RequestPredicates.GET("/favicon.ico"), r)` folds the
    `resource` rule's own `GET` against the predicate's, and `GET` ∧ `GET` is `GET` —
    a request carries one verb, and this is it. Only two DIFFERENT verbs poison
    (`test_a_second_verb_inside_one_and_chain_poisons_only_the_verb`)."""
    caller = DECLARER + "routes(sig_r)."
    matches = _builder_matches()
    matches["vocabulary"]["verbs"].append(  # type: ignore[index]
        {
            "owner": BUILDER_TYPE,
            "method": "resource",
            "verb": "GET",
            "arity": 2,
            "predicate_arg": 0,
            "handler": "none",
            "extends_receiver": True,
        }
    )
    facts = [
        *_handler_symbols(),
        _site(caller, 0, ROUTERS, "route", result=0, descriptor=f"(){_BUILDER_DESC}"),
        _site(
            caller,
            1,
            PREDICATES,
            "GET",
            result=1,
            arguments=[CallArgument(kind="string", value="/favicon.ico")],
        ),
        _site(
            caller,
            2,
            BUILDER,
            "resource",
            invoke_kind="virtual",
            receiver=0,
            result=2,
            descriptor=f"(Lcom/example/web/Predicate;Lcom/example/web/Resource;){_BUILDER_DESC}",
            arguments=[CallArgument(kind="unresolved", source=1), CallArgument(kind="unresolved")],
        ),
        _site(
            caller,
            3,
            BUILDER,
            "build",
            invoke_kind="virtual",
            receiver=2,
            result=3,
            descriptor="()Lcom/example/web/Router;",
        ),
    ]
    workspace = _resolve(tmp_path, facts, _catalog(matches))
    assert _identities(_rows(workspace)) == [("GET", "/favicon.ico", None, "resolved")]


def test_a_static_resource_rule_derives_a_served_route_with_no_handler(tmp_path: Path):
    """Spec §6: `resources("/static/**", location)` is an inbound boundary a client can
    GET; the row carries the pattern, the verb, and a NULL handler — the row shape
    `derived_resource` and `schema_operations` already ship."""
    caller = DECLARER + "routes(sig_r)."
    facts = [
        *_handler_symbols(),
        _site(caller, 0, ROUTERS, "route", result=0, descriptor=f"(){_BUILDER_DESC}"),
        _site(
            caller,
            1,
            BUILDER,
            "resources",
            invoke_kind="virtual",
            receiver=0,
            result=1,
            descriptor=f"(Ljava/lang/String;Lcom/example/web/Resource;){_BUILDER_DESC}",
            arguments=[
                CallArgument(kind="string", value="/static/**"),
                CallArgument(kind="unresolved"),
            ],
        ),
        _site(
            caller,
            2,
            BUILDER,
            "build",
            invoke_kind="virtual",
            receiver=1,
            result=2,
            descriptor="()Lcom/example/web/Router;",
        ),
    ]
    workspace = _resolve(tmp_path, facts, _catalog(_builder_matches()))
    assert _identities(_rows(workspace)) == [("GET", "/static/**", None, "resolved")]


def test_a_prefix_over_a_catch_all_derives_the_prefix_plus_the_any_path_pattern(tmp_path: Path):
    """Ruled after Task 3's review: a catch-all under a prefix serves `/api/**`, which is
    the prefix composed OVER the any-path part — so the any-path part must be contributed
    by the route that read no path, not filled in at the end where the prefix is already
    gone (`_path_of`'s fallback alone would publish `/api`). Two shapes in one tree, one
    per grammar: the static `nest(path("/api"), route(accept(JSON), h))` — a media-only
    predicate route, which must still read `/**` on its own (Task 3's shipped-catalog
    tests pin that) — and the builder's `path("/x", b -> b.GET(h))`, whose body verb
    names no path at all."""
    caller = DECLARER + "routes(sig_r)."
    facts = [
        *_handler_symbols(),
        _method_symbol(_BUILDER_BODY),
        # nest(path("/api"), route(accept(JSON), h)) — rooted at the nest.
        _site(
            caller,
            0,
            PREDICATES,
            "path",
            result=10,
            arguments=[CallArgument(kind="string", value="/api")],
        ),
        _site(
            caller,
            1,
            PREDICATES,
            "accept",
            result=11,
            arguments=[CallArgument(kind="enum", symbol=MEDIA_TYPE + "APPLICATION_JSON.")],
        ),
        _site(
            caller,
            2,
            ROUTERS,
            "route",
            result=12,
            arguments=[
                CallArgument(kind="unresolved", source=11),
                CallArgument(kind="lambda", symbol=LIST_ORDERS, source=2),
            ],
        ),
        _site(
            caller,
            3,
            ROUTERS,
            "nest",
            result=13,
            arguments=[
                CallArgument(kind="unresolved", source=10),
                CallArgument(kind="unresolved", source=12),
            ],
        ),
        # route().path("/x", b -> b.GET(h)).build() — rooted at the build.
        _site(caller, 4, ROUTERS, "route", result=20, descriptor=f"(){_BUILDER_DESC}"),
        _site(
            caller,
            5,
            BUILDER,
            "path",
            invoke_kind="virtual",
            receiver=20,
            result=21,
            descriptor=f"(Ljava/lang/String;Ljava/util/function/Consumer;){_BUILDER_DESC}",
            arguments=[
                CallArgument(kind="string", value="/x"),
                CallArgument(kind="lambda", symbol=_BUILDER_BODY, source=5),
            ],
        ),
        _site(
            caller,
            6,
            BUILDER,
            "build",
            invoke_kind="virtual",
            receiver=21,
            result=22,
            descriptor="()Lcom/example/web/Router;",
        ),
        # The body: the builder is the lambda's own parameter, so the verb's receiver is
        # no call this method can see — and that is a chain that starts here, not one
        # the walk could not read.
        _site(
            _BUILDER_BODY,
            0,
            BUILDER,
            "GET",
            invoke_kind="virtual",
            receiver=None,
            result=None,
            descriptor=f"(Lcom/example/web/Handler;){_BUILDER_DESC}",
            arguments=[CallArgument(kind="lambda", symbol=HEALTH, source=0)],
        ),
    ]
    workspace = _resolve(tmp_path, facts, _catalog(_builder_matches()))
    assert _identities(_rows(workspace)) == [
        ("GET", "/x/**", _MODULE + HEALTH, "resolved"),
        (None, "/api/**", _MODULE + LIST_ORDERS, "resolved"),
    ]


# An all-static nesting DSL (A2 Task 3): the entry links a body, the prefix links a body
# one level deeper, and every verb inside is a static call with no receiver at all. The
# framework this mirrors keeps its own prefix stack, and its path-less verb overload
# registers the prefix ITSELF — `join(prefixes) + ""` — not every path under it.
STATIC_CONFIG = "com/example/web/StaticConfig#"
STATIC_ROUTES = "com/example/web/StaticRoutes#"
_STATIC_BODY = DECLARER + "lambda$staticRoutes$0(sig_b0)."
_STATIC_INNER = DECLARER + "lambda$staticRoutes$1(sig_b0)."


def _static_dsl_matches(*, path_less_serves_the_prefix: bool) -> dict[str, object]:
    verb: dict[str, object] = {
        "owner": "com.example.web.StaticRoutes",
        "method": "get",
        "verb": "GET",
        "arity": 1,
        "handler_arg": 0,
    }
    if path_less_serves_the_prefix:
        verb["path"] = ""
    return {
        "entries": [{"owner": "com.example.web.StaticConfig", "method": "routes", "body_arg": 0}],
        "vocabulary": {
            "verbs": [verb],
            "prefixes": [
                {
                    "owner": "com.example.web.StaticRoutes",
                    "method": "path",
                    "arity": 2,
                    "path_arg": 0,
                    "body_arg": 1,
                }
            ],
        },
    }


def _static_dsl_facts() -> list:
    """`config.routes(() -> { path("/x", () -> { get(h); }); })`."""
    caller = DECLARER + "staticRoutes(sig_r)."
    return [
        *_handler_symbols(),
        _method_symbol(_STATIC_BODY),
        _method_symbol(_STATIC_INNER),
        _site(
            caller,
            0,
            STATIC_CONFIG,
            "routes",
            invoke_kind="virtual",
            receiver=None,
            result=None,
            descriptor="(Lcom/example/web/Group;)V",
            arguments=[CallArgument(kind="lambda", symbol=_STATIC_BODY, source=0)],
        ),
        _site(
            _STATIC_BODY,
            0,
            STATIC_ROUTES,
            "path",
            result=None,
            descriptor="(Ljava/lang/String;Lcom/example/web/Group;)V",
            arguments=[
                CallArgument(kind="string", value="/x"),
                CallArgument(kind="lambda", symbol=_STATIC_INNER, source=0),
            ],
        ),
        _site(
            _STATIC_INNER,
            0,
            STATIC_ROUTES,
            "get",
            result=None,
            descriptor="(Lcom/example/web/Handler;)V",
            arguments=[CallArgument(kind="lambda", symbol=HEALTH, source=0)],
        ),
    ]


def test_a_verb_rule_declaring_the_empty_literal_path_serves_its_prefix_alone(tmp_path: Path):
    """The one engine word A2 Task 3 adds: `path: ""` on a verb rule is a literal path
    contribution — the empty string — so the route DID read a path and `_served` never
    fills in the any-path pattern. `path("/x", () -> get(h))` is `GET /x`: the prefix
    alone, which is what a framework whose path-less overload registers
    `prefix + ""` serves it at. Without the word the same rule is the catch-all of the
    test above and publishes `/x/**` — every path under the prefix, which that framework
    never serves; the sibling assertion pins that the word, not the shape, is what
    tells the two apart."""
    workspace = _resolve(
        tmp_path,
        _static_dsl_facts(),
        _catalog(_static_dsl_matches(path_less_serves_the_prefix=True)),
    )
    assert _identities(_rows(workspace)) == [("GET", "/x", _MODULE + HEALTH, "resolved")]
    workspace.close()

    workspace = _resolve(
        tmp_path / "catch_all",
        _static_dsl_facts(),
        _catalog(_static_dsl_matches(path_less_serves_the_prefix=False)),
    )
    assert _identities(_rows(workspace)) == [("GET", "/x/**", _MODULE + HEALTH, "resolved")]
    workspace.close()


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


def test_a_pass_through_declaring_a_subtree_is_refused(tmp_path: Path):
    """A pass-through reads no argument (spec §4b), so a nest-shaped pair beside it is
    two contradictory instructions for one call — refused rather than resolved by
    dispatch order."""
    matches = _matches()
    matches["continuations"] = [
        {
            "name": "filter",
            "owner": "com.example.web.Router",
            "path_arg": 0,
            "subtree_arg": 1,
            "pass_through": True,
        }
    ]
    with pytest.raises(CatalogError, match=r"filter.*pass_through.*reads no argument"):
        _resolve(tmp_path, [], _catalog(matches))


def test_a_verb_rule_with_two_handler_answers_or_none_while_extending_is_refused(tmp_path: Path):
    """A verb says where its handler sits OR that there is none; both is two answers, and
    `extends_receiver` on a rule saying neither is a builder verb that declares no route —
    a continuation misfiled as a verb. Three refusals, one per conjunct; the `handler`
    key's only value is `none`, so any other spelling is the fourth."""
    both = {
        "owner": BUILDER_TYPE,
        "method": "GET",
        "verb": "GET",
        "arity": 2,
        "path_arg": 0,
        "handler_arg": 1,
        "handler": "none",
    }
    neither = {
        "owner": BUILDER_TYPE,
        "method": "GET",
        "verb": "GET",
        "arity": 2,
        "path_arg": 0,
        "extends_receiver": True,
    }
    misspelt = {
        "owner": BUILDER_TYPE,
        "method": "GET",
        "verb": "GET",
        "arity": 2,
        "path_arg": 0,
        "handler": "nothing",
    }
    for rule, message in (
        (both, r"GET.*both `handler_arg` and `handler: none`"),
        (neither, r"GET.*`extends_receiver` without"),
        (misspelt, r"GET.*the only value is `none`"),
    ):
        matches = _matches()
        matches["vocabulary"]["verbs"] = [rule]  # type: ignore[index]
        with pytest.raises(CatalogError, match=message):
            _resolve(tmp_path, [], _catalog(matches))


def test_an_origin_naming_no_owner_or_no_method_is_refused(tmp_path: Path):
    """An origin is compared against a receiver's producing call on owner AND method;
    half of that matches nothing, and a chain head the catalog meant to declare would
    poison every chain instead."""
    for origin in ({"owner": "com.example.web.Routers"}, {"method": "route"}, "route"):
        matches = {**_matches(), "origins": [origin]}
        with pytest.raises(CatalogError, match=r"every `origins` item is `\{owner, method\}`"):
            _resolve(tmp_path, [], _catalog(matches))


def test_a_path_join_that_is_not_the_one_declared_value_is_refused(tmp_path: Path):
    """`path_join` is `leading_slash` or absent. A misspelling read as absent would fall
    back to verbatim concatenation and publish the glued address the word exists to
    prevent — silently, since every row would still be resolved."""
    matches = {**_matches(), "path_join": "leading-slash"}
    with pytest.raises(CatalogError, match=r"`path_join: 'leading-slash'` — the only value"):
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


def test_the_router_builder_dsl_derives_its_route_on_the_shipped_catalog(tmp_path: Path):
    """`G-37` closed (spec §4). `RouterFunctions.route().GET("/orders", handler).build()`
    is the BUILDER DSL — the reference documentation's recommended shape since 5.2 — and
    it derived NOTHING through the shipped catalog: the verb sits on a receiver returned
    by an argument-less `route()`, and this grammar had no word for that. **This test
    asserted `rows == []`** so that the boundary was pinned rather than quietly a lie in
    either direction; it went red the moment the surface started deriving, which is now.

    The chain roots at `build()` (consumed by nothing), the verb extends its receiver,
    and `route()` is a declared origin, so the chain's head contributes zero routes
    without poisoning. The descriptors are the jar's own (`javap -p -s`, spring-webflux
    6.1.6), because the arity-2 rules are told apart on position 0's type."""
    facts: list = [
        _method_symbol(LIST_ORDERS),
        _site(
            ROUTES,
            0,
            _ROUTER_FUNCTIONS,
            "route",
            result=200,
            arguments=[],
            descriptor="()Lorg/springframework/web/reactive/function/server/RouterFunctions$Builder;",
        ),
        _site(
            ROUTES,
            1,
            _BUILDER,
            "GET",
            receiver=200,
            result=201,
            invoke_kind="interface",
            descriptor=(
                "(Ljava/lang/String;Lorg/springframework/web/reactive/function/server/HandlerFunction;)"
                "Lorg/springframework/web/reactive/function/server/RouterFunctions$Builder;"
            ),
            arguments=[
                CallArgument(kind="string", value="/orders"),
                CallArgument(kind="lambda", symbol=LIST_ORDERS),
            ],
        ),
        _site(
            ROUTES,
            2,
            _BUILDER,
            "build",
            receiver=201,
            result=202,
            arguments=[],
            descriptor="()Lorg/springframework/web/reactive/function/server/RouterFunction;",
        ),
    ]
    workspace = _resolve(tmp_path, facts, _shipped_router_catalog())
    rows = _rows(workspace)
    workspace.close()

    assert _identities(rows) == [("GET", "/orders", _MODULE + LIST_ORDERS, "resolved")]


def test_the_origin_is_the_argument_less_factory_not_the_route_of_the_same_name(tmp_path: Path):
    """The regression the live fixture caught the first time `origins` shipped: the
    argument-less `route()` and `route(predicate, handler)` share owner and name, and an
    origin matched on those alone reads the two-argument form — the HEAD of every
    `andRoute` chain — as a chain start contributing nothing, so its route vanished
    (`GET /fn/orders`, `GET /mvcfn/invoices`, `GET /extra`, all gone). `arity: 0` on the
    origin is spec §3's own discriminator, and this pins that the head still declares."""
    facts: list = [_method_symbol(LIST_ORDERS), _method_symbol(CREATE_ORDER)]
    facts += _java_route(0, "GET", "/a", LIST_ORDERS)  # route(GET("/a"), h) → result 105
    facts += [
        _site(
            ROUTES,
            2,
            _REQUEST_PREDICATES,
            "POST",
            result=110,
            arguments=[CallArgument(kind="string", value="/b")],
        ),
        _site(
            ROUTES,
            3,
            "org/springframework/web/reactive/function/server/RouterFunction#",
            "andRoute",
            receiver=105,
            result=111,
            invoke_kind="interface",
            arguments=[
                CallArgument(kind="unresolved", source=110),
                CallArgument(kind="lambda", symbol=CREATE_ORDER),
            ],
        ),
    ]
    workspace = _resolve(tmp_path, facts, _shipped_router_catalog())
    rows = _rows(workspace)
    workspace.close()

    assert _identities(rows) == [
        ("GET", "/a", _MODULE + LIST_ORDERS, "resolved"),
        ("POST", "/b", _MODULE + CREATE_ORDER, "resolved"),
    ]


@pytest.mark.declines("spring-webflux-router")
@pytest.mark.pins("combinator.origin-is-declared")
def test_a_builder_chain_headed_by_an_undeclared_call_derives_one_unresolved_row(tmp_path: Path):
    """§10 near-miss on the `origins` conjunct (spec §8 test 6). Every other cell is the
    positive above — verbs on the real `RouterFunctions$Builder`, `build()` at the end —
    and only the chain's HEAD differs: a call named `route`, argument-less, on
    `com.example.NotRouters`, which the shipped catalog does not declare as an origin.

    What must NOT be produced is a clean chain start: the head is one unresolved row
    with no verb and no path, the "I could not read the receiver" fact. With the origin
    check gone every zero-route receiver — a field, a helper's result, a parameter —
    would read as a clean start, and that row would vanish. The verb's own route still
    declares beside it (spec §7 case 4: one unresolved row, per the existing rule)."""
    facts: list = [
        _method_symbol(LIST_ORDERS),
        _site(
            ROUTES,
            0,
            "com/example/NotRouters#",
            "route",
            result=200,
            arguments=[],
            descriptor="()Lorg/springframework/web/reactive/function/server/RouterFunctions$Builder;",
        ),
        _site(
            ROUTES,
            1,
            _BUILDER,
            "GET",
            receiver=200,
            result=201,
            invoke_kind="interface",
            descriptor=(
                "(Ljava/lang/String;Lorg/springframework/web/reactive/function/server/HandlerFunction;)"
                "Lorg/springframework/web/reactive/function/server/RouterFunctions$Builder;"
            ),
            arguments=[
                CallArgument(kind="string", value="/x"),
                CallArgument(kind="lambda", symbol=LIST_ORDERS),
            ],
        ),
        _site(
            ROUTES,
            2,
            _BUILDER,
            "build",
            receiver=201,
            result=202,
            arguments=[],
            descriptor="()Lorg/springframework/web/reactive/function/server/RouterFunction;",
        ),
    ]
    workspace = _resolve(tmp_path, facts, _shipped_router_catalog())
    rows = _rows(workspace)
    workspace.close()

    assert _identities(rows) == [
        ("GET", "/x", _MODULE + LIST_ORDERS, "resolved"),
        (None, None, None, "unresolved"),
    ]


def test_a_static_resources_call_roots_and_serves_its_pattern_handler_less(tmp_path: Path):
    """Spec §6 on the STATIC spelling: `RouterFunctions.resources("/static/**", location)`
    returned on its own is a router a client can GET, and the shipped catalog roots it
    through the `entries` item — the way `nest` roots — while its `verbs` rule reads it.
    Without the entry a verb never roots (checkpoint F4) and this spelling would derive
    nothing while the builder's `resources` derived; the row has no handler and says so."""
    facts: list = [
        _site(
            ROUTES,
            0,
            _ROUTER_FUNCTIONS,
            "resources",
            result=300,
            descriptor=(
                "(Ljava/lang/String;Lorg/springframework/core/io/Resource;)"
                "Lorg/springframework/web/reactive/function/server/RouterFunction;"
            ),
            arguments=[
                CallArgument(kind="string", value="/static/**"),
                CallArgument(kind="unresolved"),
            ],
        ),
    ]
    workspace = _resolve(tmp_path, facts, _shipped_router_catalog())
    rows = _rows(workspace)
    workspace.close()

    assert _identities(rows) == [("GET", "/static/**", None, "resolved")]


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


# --- `javalin-apibuilder` (A2 Task 3): the all-static nesting form on the shipped catalog ---

_ROUTER_CONFIG = "io/javalin/config/RouterConfig#"
_API_BUILDER = "io/javalin/apibuilder/ApiBuilder#"
_HANDLER_DESC = "Lio/javalin/http/Handler;"
_GROUP_DESC = "Lio/javalin/apibuilder/EndpointGroup;"
_CONFIG_LAMBDA = DECLARER + "lambda$nested$0(sig_c0)."
_GROUP_BODY = DECLARER + "lambda$nested$1(sig_g0)."
_GROUP_INNER = DECLARER + "lambda$nested$2(sig_g0)."


def _shipped_apibuilder_catalog() -> Catalog:
    from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
    from sextant.resources import catalogs_dir

    return next(c for c in YamlCatalogSource(catalogs_dir()).load() if c.id == "javalin-apibuilder")


def _apibuilder_facts(entry_owner: str) -> list:
    """`config.router.apiBuilder(() -> { path("/orders", () -> { get("/{id}", h);
    post(h); }); })` — the shape `fixtures/orders-javalin/.../OrderApp.java`'s `nested()`
    compiles to (`javap -c`, 2026-09-13): the entry call in the `config -> …` lambda, each
    `EndpointGroup` block a method of its own, every `ApiBuilder` call `invokestatic` with
    no receiver. `entry_owner` is the one cell the near-miss below varies."""
    return [
        *_handler_symbols(),
        _method_symbol(_GROUP_BODY),
        _method_symbol(_GROUP_INNER),
        _site(
            _CONFIG_LAMBDA,
            0,
            entry_owner,
            "apiBuilder",
            invoke_kind="virtual",
            receiver=None,
            result=1,
            descriptor=f"({_GROUP_DESC})Lio/javalin/config/RouterConfig;",
            arguments=[CallArgument(kind="lambda", symbol=_GROUP_BODY, source=0)],
        ),
        _site(
            _GROUP_BODY,
            0,
            _API_BUILDER,
            "path",
            result=None,
            descriptor=f"(Ljava/lang/String;{_GROUP_DESC})V",
            arguments=[
                CallArgument(kind="string", value="/orders"),
                CallArgument(kind="lambda", symbol=_GROUP_INNER, source=0),
            ],
        ),
        _site(
            _GROUP_INNER,
            0,
            _API_BUILDER,
            "get",
            result=None,
            descriptor=f"(Ljava/lang/String;{_HANDLER_DESC})V",
            arguments=[
                CallArgument(kind="string", value="/{id}"),
                CallArgument(kind="lambda", symbol=LIST_ORDERS, source=0),
            ],
        ),
        _site(
            _GROUP_INNER,
            1,
            _API_BUILDER,
            "post",
            result=None,
            descriptor=f"({_HANDLER_DESC})V",
            arguments=[CallArgument(kind="lambda", symbol=CREATE_ORDER, source=1)],
        ),
    ]


def test_the_apibuilder_catalog_derives_the_nested_tree_from_the_real_entry(tmp_path: Path):
    """The paired positive (GUIDELINES §10): the shipped rules fire on the real entry
    owner. `get("/{id}", h)` under `path("/orders", …)` is `GET /orders/{id}`; the
    path-less `post(h)` is `POST /orders` — the prefix alone, Javalin's `prefixPath("")`
    — and both rows' caller is the method holding `apiBuilder`."""
    workspace = _resolve(tmp_path, _apibuilder_facts(_ROUTER_CONFIG), _shipped_apibuilder_catalog())
    rows = _rows(workspace)
    workspace.close()

    assert _identities(rows) == [
        ("GET", "/orders/{id}", _MODULE + LIST_ORDERS, "resolved"),
        ("POST", "/orders", _MODULE + CREATE_ORDER, "resolved"),
    ]
    assert {row["caller"] for row in rows} == {_CONFIG_LAMBDA}


@pytest.mark.declines("javalin-apibuilder")
@pytest.mark.pins("combinator.entry-owner-is-the-declared-type")
def test_the_apibuilder_catalog_declines_an_api_builder_call_on_another_owner(tmp_path: Path):
    """§10 near-miss on the entry's owner conjunct. Every other cell is the positive
    above — the same `apiBuilder` name, the same `EndpointGroup` lambda, the same static
    `path`/`get`/`post` inside it — and only the entry's OWNER differs:
    `com.example.NotRouter#apiBuilder`, which is not `io.javalin.config.RouterConfig`.

    Nothing is the required answer. A body-linked entry is the ONLY place this catalog
    roots — every `ApiBuilder` call is static, receiver-less and never a root of its own —
    so with the owner check gone any method named `apiBuilder` handed a lambda would
    root a tree, and a router nobody registered with Javalin would be published under
    this catalog's id."""
    workspace = _resolve(
        tmp_path, _apibuilder_facts("com/example/NotRouter#"), _shipped_apibuilder_catalog()
    )
    identities = _identities(_rows(workspace))
    workspace.close()

    assert identities == []


def _slashless_tree(prefix: str, inner: str, leaf: str) -> list:
    """`path(prefix, () -> { get(h); path(inner, () -> { get(h); post(leaf, h); }); })` —
    the reviewer's tree (Task 3 fix round 1), every segment spelled as the caller passes
    it, so the same shape serves the slashless, the slashed and the `*` spellings."""
    grandchild = DECLARER + "lambda$nested$3(sig_g0)."
    return [
        *_handler_symbols(),
        _method_symbol(_GROUP_BODY),
        _method_symbol(_GROUP_INNER),
        _method_symbol(grandchild),
        _site(
            _CONFIG_LAMBDA,
            0,
            _ROUTER_CONFIG,
            "apiBuilder",
            invoke_kind="virtual",
            receiver=None,
            result=1,
            descriptor=f"({_GROUP_DESC})Lio/javalin/config/RouterConfig;",
            arguments=[CallArgument(kind="lambda", symbol=_GROUP_BODY, source=0)],
        ),
        _site(
            _GROUP_BODY,
            0,
            _API_BUILDER,
            "path",
            result=None,
            descriptor=f"(Ljava/lang/String;{_GROUP_DESC})V",
            arguments=[
                CallArgument(kind="string", value=prefix),
                CallArgument(kind="lambda", symbol=_GROUP_INNER, source=0),
            ],
        ),
        _site(
            _GROUP_INNER,
            0,
            _API_BUILDER,
            "get",
            result=None,
            descriptor=f"({_HANDLER_DESC})V",
            arguments=[CallArgument(kind="lambda", symbol=LIST_ORDERS, source=0)],
        ),
        _site(
            _GROUP_INNER,
            1,
            _API_BUILDER,
            "path",
            result=None,
            descriptor=f"(Ljava/lang/String;{_GROUP_DESC})V",
            arguments=[
                CallArgument(kind="string", value=inner),
                CallArgument(kind="lambda", symbol=grandchild, source=1),
            ],
        ),
        _site(
            grandchild,
            0,
            _API_BUILDER,
            "get",
            result=None,
            descriptor=f"({_HANDLER_DESC})V",
            arguments=[CallArgument(kind="lambda", symbol=HEALTH, source=0)],
        ),
        _site(
            grandchild,
            1,
            _API_BUILDER,
            "post",
            result=None,
            descriptor=f"(Ljava/lang/String;{_HANDLER_DESC})V",
            arguments=[
                CallArgument(kind="string", value=leaf),
                CallArgument(kind="lambda", symbol=CREATE_ORDER, source=1),
            ],
        ),
    ]


def test_a_catalog_declaring_leading_slash_joins_slashless_segments_as_its_framework_does(
    tmp_path: Path,
):
    """Task 3 fix round 1 (the reviewer's finding). Javalin documents `path("api", …)` and
    `path("/api", …)` as the same registration — `prefixPath` prepends `/` to a segment
    that does not start with one — so `path("users", () -> { get(h); path("{id}", () ->
    { get(h); post("items", h); }); })` serves `/users`, `/users/{id}` and
    `/users/{id}/items`. Verbatim concatenation published `GET /users{id}` and
    `POST /users{id}items`, RESOLVED: a confident wrong address, the row this project
    forbids. The catalog now says how its framework joins segments (`path_join:
    leading_slash`), and every literal the engine reads for it is joined that way."""
    workspace = _resolve(
        tmp_path, _slashless_tree("users", "{id}", "items"), _shipped_apibuilder_catalog()
    )
    identities = _identities(_rows(workspace))
    workspace.close()

    assert identities == [
        ("GET", "/users", _MODULE + LIST_ORDERS, "resolved"),
        ("GET", "/users/{id}", _MODULE + HEALTH, "resolved"),
        ("POST", "/users/{id}/items", _MODULE + CREATE_ORDER, "resolved"),
    ]


def test_leading_slash_leaves_a_slashed_tree_exactly_as_written(tmp_path: Path):
    """The join's first exception: a segment already starting with `/` is untouched, so a
    router written the documented way reads back identically with and without the word."""
    workspace = _resolve(
        tmp_path, _slashless_tree("/users", "/{id}", "/items"), _shipped_apibuilder_catalog()
    )
    identities = _identities(_rows(workspace))
    workspace.close()

    assert identities == [
        ("GET", "/users", _MODULE + LIST_ORDERS, "resolved"),
        ("GET", "/users/{id}", _MODULE + HEALTH, "resolved"),
        ("POST", "/users/{id}/items", _MODULE + CREATE_ORDER, "resolved"),
    ]


def test_leading_slash_never_prefixes_the_wildcard_segment(tmp_path: Path):
    """The join's third exception, `prefixPath`'s own `"*"` check: `path("*", …)` is NOT
    `/*`. Pinned on the segment alone, because the address Javalin serves a `*` prefix
    under is a matcher question this catalog does not answer — what matters here is
    that the join does not invent a slash the framework's rule explicitly withholds."""
    workspace = _resolve(
        tmp_path, _slashless_tree("/users", "*", "/items"), _shipped_apibuilder_catalog()
    )
    paths = [row["path"] for row in _rows(workspace)]
    workspace.close()

    assert paths == ["/users", "/users*", "/users*/items"]


# --- origin_param / receiver_arg (spec §12 words 1–2) ---------------------------


def _origin_matches(origin_param: int | None) -> dict[str, object]:
    matches = _overload_matches()
    entry = {"owner": "com.example.web.RouterDslFacade", "method": "router", "body_arg": 0}
    if origin_param is not None:
        entry["origin_param"] = origin_param
    matches["entries"] = [e for e in matches["entries"] if e.get("method") != "router"] + [entry]  # type: ignore[index]
    return matches


def _dsl_body(*, receiver_parameter: int | None, captures: int) -> list:
    """`router { GET("/x") { h } }` where the DSL call sits on the body's parameter —
    `receiver_parameter` — and the linking lambda captured `captures` values."""
    entry = _site(
        DECLARER + "routes(sig_r).",
        0,
        DSL_FACADE,
        "router",
        result=1,
        arguments=[CallArgument(kind="lambda", symbol=INLINE_BODY, source=0, captures=captures)],
    )
    verb = _site(
        INLINE_BODY,
        0,
        DSL,
        "GET",
        invoke_kind="virtual",
        receiver=None,
        receiver_parameter=receiver_parameter,
        descriptor="(Ljava/lang/String;Lkotlin/jvm/functions/Function1;)V",
        arguments=[
            CallArgument(kind="string", value="/x"),
            CallArgument(kind="lambda", symbol=LIST_ORDERS, source=0),
        ],
    )
    return [*_handler_symbols(), _method_symbol(INLINE_BODY), entry, verb]


def test_a_body_chain_on_the_declared_origin_parameter_derives_clean(tmp_path: Path):
    """`captures + k`: the lambda captured one value, so the DSL parameter is the body's
    parameter 1; a rule declaring `origin_param: 0` accepts a head on parameter 1."""
    workspace = _resolve(
        tmp_path, _dsl_body(receiver_parameter=1, captures=1), _catalog(_origin_matches(0))
    )
    assert _identities(_rows(workspace)) == [("GET", "/x", _MODULE + LIST_ORDERS, "resolved")]


@pytest.mark.pins("combinator.origin-parameter-is-the-chains-head")
def test_a_body_chain_on_a_field_or_another_parameter_poisons(tmp_path: Path):
    """A null receiver is a field or an unreadable value; another index is not the origin.
    Both are one unresolved row — the fixed-index design's wrong row, refused."""
    for head in (None, 0):
        workspace = _resolve(
            tmp_path / str(head),
            _dsl_body(receiver_parameter=head, captures=1),
            _catalog(_origin_matches(0)),
        )
        assert [row["resolution"] for row in _rows(workspace)] == ["unresolved"], head


def test_a_body_linked_without_an_origin_parameter_keeps_the_permissive_rule(tmp_path: Path):
    """Stated in D02: without `origin_param` a null receiver in a body is read as the body's
    own parameter, as every shipped rule did before this word existed."""
    workspace = _resolve(
        tmp_path, _dsl_body(receiver_parameter=None, captures=0), _catalog(_origin_matches(None))
    )
    assert _identities(_rows(workspace)) == [("GET", "/x", _MODULE + LIST_ORDERS, "resolved")]


@pytest.mark.pins("combinator.receiver-arg-is-the-origin")
def test_a_receiver_argument_must_be_the_origin_parameter(tmp_path: Path):
    """The extension-receiver form: `get(route, "/x", h)` is a STATIC call whose argument 0
    is the route; inside `route("/api") { … }` that argument must be the body's own
    parameter, else the row is not under `/api` and poisons (spec §12 word 2)."""
    matches = _origin_matches(0)
    matches["vocabulary"]["verbs"].append(  # type: ignore[index]
        {
            "owner": "com.example.web.RoutingKt",
            "method": "get",
            "verb": "GET",
            "arity": 3,
            "receiver_arg": 0,
            "path_arg": 1,
            "handler_arg": 2,
        }
    )

    def body(argument: CallArgument) -> list:
        entry = _site(
            DECLARER + "routes(sig_r).",
            0,
            DSL_FACADE,
            "router",
            result=1,
            arguments=[CallArgument(kind="lambda", symbol=INLINE_BODY, source=0, captures=0)],
        )
        verb = _site(
            INLINE_BODY,
            0,
            "com/example/web/RoutingKt#",
            "get",
            descriptor="(Lcom/example/web/Route;Ljava/lang/String;Lkotlin/jvm/functions/Function2;)Lcom/example/web/Route;",
            arguments=[
                argument,
                CallArgument(kind="string", value="/x"),
                CallArgument(kind="lambda", symbol=LIST_ORDERS, source=0),
            ],
        )
        return [*_handler_symbols(), _method_symbol(INLINE_BODY), entry, verb]

    good = _resolve(
        tmp_path / "good", body(CallArgument(kind="parameter", value=0)), _catalog(matches)
    )
    assert _identities(_rows(good)) == [("GET", "/x", _MODULE + LIST_ORDERS, "resolved")]
    bad = _resolve(
        tmp_path / "bad", body(CallArgument(kind="parameter", value=1)), _catalog(matches)
    )
    assert [row["resolution"] for row in _rows(bad)] == ["unresolved"]
    unread = _resolve(tmp_path / "unread", body(CallArgument(kind="unresolved")), _catalog(matches))
    assert [row["resolution"] for row in _rows(unread)] == ["unresolved"]


def test_a_body_linked_entry_handed_no_lambda_derives_one_unresolved_row(tmp_path: Path):
    """Spec §14 test 16 (§13 case 10): the entry's `body_arg` is an `instance`-kind
    argument — a lambda a Kotlin 1.x compiler wrote as a class, so no `lambda` link
    names a body — and the walk has nothing to jump into. One unresolved row, never
    silence: a router the source declares is reported as unread, not absent. Pinned so
    the register's Kotlin 1.x item has a measurable starting point."""
    caller = DECLARER + "routes(sig_r)."
    facts = [
        *_handler_symbols(),
        _site(caller, 0, DECLARER + "Routes$routes$1#", "<init>", result=8, invoke_kind="special"),
        _site(
            caller,
            1,
            DSL_FACADE,
            "router",
            result=9,
            arguments=[
                CallArgument(kind="instance", source=8, symbol=DECLARER + "Routes$routes$1#")
            ],
        ),
    ]
    workspace = _resolve(tmp_path, facts)
    rows = _rows(workspace)
    workspace.close()

    assert _identities(rows) == [(None, None, None, "unresolved")]
    assert [row["caller"] for row in rows] == [caller]


def test_an_origin_param_away_from_a_body_and_a_receiver_arg_beyond_the_arity_are_refused(
    tmp_path: Path,
):
    """`origin_param` names a parameter of the BODY a `body_arg` links — on a rule that
    links none it names nothing, and a rule that meant to declare a body's origin would
    check nothing. `receiver_arg` names an argument position: at or beyond a declared
    `arity` no call the rule accepts carries it, so every row it reads would poison
    with nothing saying the rule was miswritten."""
    matches = _matches()
    matches["vocabulary"]["prefixes"].append(  # type: ignore[index]
        {
            "owner": "com.example.web.Predicates",
            "method": "prefix",
            "path_arg": 0,
            "origin_param": 0,
        }
    )
    with pytest.raises(CatalogError, match=r"`origin_param: 0` — a parameter index of the body"):
        _resolve(tmp_path / "origin", [], _catalog(matches))
    matches = _matches()
    matches["vocabulary"]["verbs"].append(  # type: ignore[index]
        {
            "owner": "com.example.web.RoutingKt",
            "method": "get",
            "verb": "GET",
            "arity": 2,
            "receiver_arg": 2,
            "path_arg": 1,
            "handler_arg": 0,
        }
    )
    with pytest.raises(CatalogError, match=r"`receiver_arg: 2` — a position from 0 below"):
        _resolve(tmp_path / "receiver", [], _catalog(matches))
    # The words on rules that cannot read them: `origin_param` on a verb and on a
    # continuation, `receiver_arg` on an entry and on a continuation — D02 says
    # "refused anywhere else", so each is.
    matches = _matches()
    matches["vocabulary"]["verbs"].append(  # type: ignore[index]
        {"owner": "com.example.web.Predicates", "method": "PUT", "verb": "PUT", "origin_param": 0}
    )
    with pytest.raises(CatalogError, match=r"`PUT` declares `origin_param: 0`"):
        _resolve(tmp_path / "verb", [], _catalog(matches))
    matches = _matches()
    matches["continuations"].append(  # type: ignore[union-attr]
        {"name": "also", "owner": "com.example.web.Router", "origin_param": 0}
    )
    with pytest.raises(CatalogError, match=r"`also` declares `origin_param: 0`"):
        _resolve(tmp_path / "continuation", [], _catalog(matches))
    matches = _matches()
    matches["entries"].append(  # type: ignore[union-attr]
        {
            "owner": "com.example.web.Routers",
            "methods": ["route"],
            "handler_arg": 1,
            "receiver_arg": 0,
        }
    )
    with pytest.raises(CatalogError, match=r"`\['route'\]` declares `receiver_arg: 0`"):
        _resolve(tmp_path / "entry", [], _catalog(matches))
    matches = _matches()
    matches["continuations"].append(  # type: ignore[union-attr]
        {"name": "also", "owner": "com.example.web.Router", "receiver_arg": 0}
    )
    with pytest.raises(CatalogError, match=r"`also` declares `receiver_arg: 0`"):
        _resolve(tmp_path / "continuation-receiver", [], _catalog(matches))


def _origin_builder_matches() -> dict[str, object]:
    """The builder catalog with the `Consumer` `path` declaring `origin_param: 0`."""
    matches = _builder_matches()
    vocabulary = dict(matches["vocabulary"])  # type: ignore[arg-type]
    vocabulary["prefixes"] = [
        {**rule, "origin_param": 0} if rule.get("body_arg") == 1 else rule
        for rule in vocabulary["prefixes"]  # type: ignore[index]
    ]
    return {**matches, "vocabulary": vocabulary}


def _body_chain(*, head: int | None, verbs: int, through_filter: bool) -> list:
    """`route().path("/api", b -> …).build()` where the body's chain starts on `head`
    (the body's parameter index, or None for a field) — `head.GET("/a", h)`, then
    `.GET("/b", h)` when `verbs == 2`; `head.filter(f).GET("/a", h)` when
    `through_filter`. The linking lambda captures nothing, so the origin is 0."""
    caller = DECLARER + "routes(sig_r)."
    facts = [
        *_handler_symbols(),
        _method_symbol(_BUILDER_BODY),
        _site(caller, 0, ROUTERS, "route", result=20, descriptor=f"(){_BUILDER_DESC}"),
        _site(
            caller,
            1,
            BUILDER,
            "path",
            invoke_kind="virtual",
            receiver=20,
            result=21,
            descriptor=f"(Ljava/lang/String;Ljava/util/function/Consumer;){_BUILDER_DESC}",
            arguments=[
                CallArgument(kind="string", value="/api"),
                CallArgument(kind="lambda", symbol=_BUILDER_BODY, source=101, captures=0),
            ],
        ),
        _site(
            caller,
            2,
            BUILDER,
            "build",
            invoke_kind="virtual",
            receiver=21,
            result=22,
            descriptor="()Lcom/example/web/Router;",
        ),
    ]
    ordinal, receiver = 0, None
    if through_filter:
        facts.append(
            _site(
                _BUILDER_BODY,
                ordinal,
                BUILDER,
                "filter",
                invoke_kind="virtual",
                receiver=None,
                receiver_parameter=head,
                result=1,
                descriptor=f"(Lcom/example/web/Filter;){_BUILDER_DESC}",
                arguments=[CallArgument(kind="lambda", symbol=HEALTH, source=99)],
            )
        )
        ordinal, receiver = 1, 1
    for path in ("/a", "/b")[:verbs]:
        facts.append(
            _site(
                _BUILDER_BODY,
                ordinal,
                BUILDER,
                "GET",
                invoke_kind="virtual",
                receiver=receiver,
                receiver_parameter=head if receiver is None else None,
                result=ordinal + 10,
                descriptor=f"(Ljava/lang/String;Lcom/example/web/Handler;){_BUILDER_DESC}",
                arguments=[
                    CallArgument(kind="string", value=path),
                    CallArgument(kind="lambda", symbol=HEALTH, source=100 + ordinal),
                ],
            )
        )
        ordinal, receiver = ordinal + 1, ordinal + 10
    return facts


def test_an_extending_chain_off_the_origin_poisons_every_route_it_yields(tmp_path: Path):
    """Spec §13 case 6: a chain in a linked body that does not start at the origin
    parameter — a field, another parameter — is never attributed to the origin. The
    builder form declares its route AND carries the chain, and the fix-round-1 engine
    published that route resolved under `/api` beside one unresolved row: a route
    registered on ANOTHER builder, at an address this router never serves. Every route
    the chain yields is poisoned instead — one unresolved row per route, each with its
    own handler, none beside them. Two routes with the same handler are two unresolved
    rows: only identity-known rows dedup, and these have no identity."""
    unresolved = (None, None, _MODULE + HEALTH, "unresolved")
    for shape, expected in (
        ({"verbs": 1, "through_filter": False}, [unresolved]),
        ({"verbs": 2, "through_filter": False}, [unresolved, unresolved]),
        ({"verbs": 1, "through_filter": True}, [unresolved]),
    ):
        for head in (None, 1):
            workspace = _resolve(
                tmp_path / f"{shape['verbs']}-{shape['through_filter']}-{head}",
                _body_chain(head=head, **shape),  # type: ignore[arg-type]
                _catalog(_origin_builder_matches()),
            )
            assert _identities(_rows(workspace)) == expected, (shape, head)


def test_an_extending_chain_on_the_origin_derives_every_route_unchanged(tmp_path: Path):
    """The control for the test above: the same three chains on the body's parameter 0
    — the origin — derive exactly what they did before the word existed."""
    resolved = _MODULE + HEALTH
    for shape, expected in (
        ({"verbs": 1, "through_filter": False}, [("GET", "/api/a", resolved, "resolved")]),
        (
            {"verbs": 2, "through_filter": False},
            [("GET", "/api/a", resolved, "resolved"), ("GET", "/api/b", resolved, "resolved")],
        ),
        ({"verbs": 1, "through_filter": True}, [("GET", "/api/a", resolved, "resolved")]),
    ):
        workspace = _resolve(
            tmp_path / f"{shape['verbs']}-{shape['through_filter']}",
            _body_chain(head=0, **shape),  # type: ignore[arg-type]
            _catalog(_origin_builder_matches()),
        )
        assert _identities(_rows(workspace)) == expected, shape


# --- `ktor-routing` (A2 Task 5): the extension-receiver form on the shipped catalog ---

_ROUTING_ROOT = "io/ktor/server/routing/RoutingRootKt#"
_ROUTING_BUILDER = "io/ktor/server/routing/RoutingBuilderKt#"
_ROUTE = "Lio/ktor/server/routing/Route;"
_ROUTING_DESC = "(Lio/ktor/server/application/Application;Lkotlin/jvm/functions/Function1;)Lio/ktor/server/routing/RoutingRoot;"
_ROUTE_DESC = f"({_ROUTE}Ljava/lang/String;Lkotlin/jvm/functions/Function1;){_ROUTE}"
_VERB_DESC = f"({_ROUTE}Ljava/lang/String;Lkotlin/jvm/functions/Function2;){_ROUTE}"
_PATHLESS_VERB_DESC = f"({_ROUTE}Lkotlin/jvm/functions/Function2;){_ROUTE}"
_ROUTING_BODY = DECLARER + "orders$lambda$1(sig_k0)."
_API_BODY = DECLARER + "orders$lambda$1$lambda$0(sig_k1)."
_HELPER_DESC = f"({_ROUTE})V"
# A module-local `Route`-extension helper — `fun Route.api() { get("/helper") { } }` — is a
# STATIC method taking the receiver as argument 0, and its symbol is what `method_descriptor`
# composes from the call's own owner, name and JVM descriptor (D00 §5a): spelled through
# that function here so the helper the routing body CALLS is the method whose body the
# facts carry.
_API_HELPER = method_descriptor(DECLARER, "api", _HELPER_DESC)
_SUSPEND_HANDLER = DECLARER + "Routes$orders$1$1$1#"
# The body a suspend handler class compiles into (CP-23: `invokeSuspend(Object)`), spelled
# as the extractor spells `lambda_body` — bare, with the hashed disambiguator.
_SUSPEND_BODY = method_descriptor(
    _SUSPEND_HANDLER, "invokeSuspend", "(Ljava/lang/Object;)Ljava/lang/Object;"
)


def _shipped_ktor_catalog() -> Catalog:
    from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
    from sextant.resources import catalogs_dir

    return next(c for c in YamlCatalogSource(catalogs_dir()).load() if c.id == "ktor-routing")


def _ktor_facts(entry_owner: str) -> list:
    """`routing { route("/api") { get("/orders") { }; get { } } }` — the shape
    `fixtures/orders-ktor/.../KtorRoutes.kt`'s `orders()` compiles to (its fact file, read
    2026-09-13): every DSL call `invokestatic` with the block's own parameter as argument
    0, each `Function1` block an `invokedynamic` body linked as a `lambda` argument with
    `captures: 0`, and each `suspend` handler an `instance` of a `SuspendLambda` class —
    whose type fact carries `lambda_body` naming its `invokeSuspend`, and whose body has
    a method fact of its own (the class is scanned), so the handler join lands. Plus the
    fixture's `api()` helper (spec 2026-09-19 §4a, `ktor-route-extensions`): `routing {
    api() }` is `invokestatic KtorRoutesKt.api(Route)` with the block's own parameter as
    its one argument, and `fun Route.api() { get("/helper") { } }` is a method of its own
    whose verb sits on ITS parameter 0 — the origin, once the walk carries it in.
    `entry_owner` is the one cell the near-miss below varies."""
    return [
        _method_symbol(_ROUTING_BODY),
        _method_symbol(_API_BODY),
        _method_symbol(_API_HELPER),
        _type_symbol(_SUSPEND_HANDLER, lambda_body=_SUSPEND_BODY),
        _method_symbol(_SUSPEND_BODY),
        _site(
            DECLARER + "orders(sig_o0).",
            0,
            entry_owner,
            "routing",
            result=1,
            descriptor=_ROUTING_DESC,
            arguments=[
                CallArgument(kind="parameter", value=0),
                CallArgument(kind="lambda", symbol=_ROUTING_BODY, source=0, captures=0),
            ],
        ),
        _site(
            _ROUTING_BODY,
            0,
            _ROUTING_BUILDER,
            "route",
            result=2,
            descriptor=_ROUTE_DESC,
            arguments=[
                CallArgument(kind="parameter", value=0),
                CallArgument(kind="string", value="/api"),
                CallArgument(kind="lambda", symbol=_API_BODY, source=1, captures=0),
            ],
        ),
        _site(
            _API_BODY,
            0,
            _ROUTING_BUILDER,
            "get",
            result=3,
            descriptor=_VERB_DESC,
            arguments=[
                CallArgument(kind="parameter", value=0),
                CallArgument(kind="string", value="/orders"),
                CallArgument(kind="instance", symbol=_SUSPEND_HANDLER, source=2),
            ],
        ),
        _site(
            _API_BODY,
            1,
            _ROUTING_BUILDER,
            "get",
            result=5,
            descriptor=_PATHLESS_VERB_DESC,
            arguments=[
                CallArgument(kind="parameter", value=0),
                CallArgument(kind="instance", symbol=_SUSPEND_HANDLER, source=4),
            ],
        ),
        _site(
            _ROUTING_BODY,
            1,
            DECLARER,
            "api",
            descriptor=_HELPER_DESC,
            arguments=[CallArgument(kind="parameter", value=0)],
        ),
        _site(
            _API_HELPER,
            0,
            _ROUTING_BUILDER,
            "get",
            result=13,
            descriptor=_VERB_DESC,
            arguments=[
                CallArgument(kind="parameter", value=0),
                CallArgument(kind="string", value="/helper"),
                CallArgument(kind="instance", symbol=_SUSPEND_HANDLER, source=8),
            ],
        ),
    ]


def test_the_ktor_catalog_derives_the_nested_tree_from_the_real_entry(tmp_path: Path):
    """The paired positive (GUIDELINES §10): the shipped rules fire on the real entry
    owner. `get("/orders") { }` under `route("/api") { }` is `GET /api/orders`; the
    path-less `get { }` is `GET /api` — the prefix alone, Ktor's `method(Get)` child of
    the receiver itself (`path: ""`). Both handlers are the suspend lambda's own
    `invokeSuspend`: the handler arrives as an `instance` of a class, and the projection
    every engine reads through (`effective_call_sites`, spec 2026-09-19 §3b) hands it
    over as the `lambda` its type fact's `lambda_body` names — `kotlin-null-handler`
    closes here, where spec §13 case 8 had pinned NULL.

    And the helper: `api()` inside the routing body hands the block's parameter — the
    origin — to a module-local method as its argument 0, so the walk follows the call
    into `api`'s body with parameter 0 as the new origin (spec 2026-09-19 §4a), and the
    `get("/helper")` written there is `GET /helper`, resolved, on the entry's caller —
    `ktor-route-extensions` closes here, where the catalog had pinned silence."""
    workspace = _resolve(tmp_path, _ktor_facts(_ROUTING_ROOT), _shipped_ktor_catalog())
    rows = _rows(workspace)
    workspace.close()

    handler = _MODULE + _SUSPEND_BODY
    assert _identities(rows) == [
        ("GET", "/api", handler, "resolved"),
        ("GET", "/api/orders", handler, "resolved"),
        ("GET", "/helper", handler, "resolved"),
    ]
    assert {row["caller"] for row in rows} == {DECLARER + "orders(sig_o0)."}


@pytest.mark.declines("ktor-routing")
@pytest.mark.pins("combinator.entry-owner-is-the-declared-type")
def test_the_ktor_catalog_declines_a_routing_call_on_another_owner(tmp_path: Path):
    """§10 near-miss on the entry's owner conjunct. Every other cell is the positive
    above — the same `routing` name, the same `Function1` lambda with `captures: 0`, the
    same static `route`/`get` on the block's parameter inside it — and only the entry's
    OWNER differs: `com.example.NotRouting#routing`, which is not
    `io.ktor.server.routing.RoutingRootKt`.

    Nothing is the required answer. The body-linked entry is the ONLY place this catalog
    roots — every `RoutingBuilderKt` call is static and receiver-less, never a root of its
    own — so with the owner check gone any method named `routing` handed a lambda would
    root a tree, and a router Ktor never installed would be published under this
    catalog's id."""
    workspace = _resolve(tmp_path, _ktor_facts("com/example/NotRouting#"), _shipped_ktor_catalog())
    identities = _identities(_rows(workspace))
    workspace.close()

    assert identities == []


# --- helper following: the origin as an argument, the visited set, the depth bound, `follow_calls` (spec 2026-09-19 §4a) ---


def _helper(name: str) -> str:
    return method_descriptor(DECLARER, name, _HELPER_DESC)


def _helper_call(caller: str, ordinal: int, name: str, *, argument: CallArgument) -> CallSiteFact:
    """`invokestatic <DECLARER>.<name>(Route)` — a module-local helper handed one value,
    normally the calling body's own parameter."""
    return _site(caller, ordinal, DECLARER, name, descriptor=_HELPER_DESC, arguments=[argument])


def _deep_verb(caller: str, ordinal: int, path: str) -> CallSiteFact:
    return _site(
        caller,
        ordinal,
        _ROUTING_BUILDER,
        "get",
        result=ordinal + 100,
        descriptor=_VERB_DESC,
        arguments=[
            CallArgument(kind="parameter", value=0),
            CallArgument(kind="string", value=path),
            CallArgument(kind="instance", symbol=_SUSPEND_HANDLER, source=ordinal + 50),
        ],
    )


def _routing_entry() -> list:
    """`routing { … }` on the real entry owner, its body `_ROUTING_BODY` with `captures:
    0`, plus the suspend handler's type and body facts — the frame every chain below
    hangs off."""
    return [
        _method_symbol(_ROUTING_BODY),
        _type_symbol(_SUSPEND_HANDLER, lambda_body=_SUSPEND_BODY),
        _method_symbol(_SUSPEND_BODY),
        _site(
            DECLARER + "orders(sig_o0).",
            0,
            _ROUTING_ROOT,
            "routing",
            result=1,
            descriptor=_ROUTING_DESC,
            arguments=[
                CallArgument(kind="parameter", value=0),
                CallArgument(kind="lambda", symbol=_ROUTING_BODY, source=0, captures=0),
            ],
        ),
    ]


def _helper_chain(length: int) -> list:
    """`routing { h1() }`, `fun Route.h1() { h2() }`, … `fun Route.h<length>() {
    get("/deep") { } }` — every hop hands its own parameter 0 on as argument 0."""
    facts = _routing_entry()
    names = [f"h{i}" for i in range(1, length + 1)]
    facts.append(
        _helper_call(_ROUTING_BODY, 0, names[0], argument=CallArgument(kind="parameter", value=0))
    )
    for i, name in enumerate(names):
        body = _helper(name)
        facts.append(_method_symbol(body))
        if i + 1 < len(names):
            facts.append(
                _helper_call(
                    body, 0, names[i + 1], argument=CallArgument(kind="parameter", value=0)
                )
            )
        else:
            facts.append(_deep_verb(body, 0, "/deep"))
    return facts


def _questions(workspace: DuckDbWorkspace) -> list[dict]:
    return [dict(row) for row in workspace.query("open_questions")]


def test_a_helper_chain_within_the_bound_derives_its_route_on_the_entrys_caller(tmp_path: Path):
    """Spec 2026-09-19 §4a's guard is a BOUND, not a budget: sixteen helper calls deep — the
    bound itself — every hop still carries the origin as argument 0, and the verb at the
    end derives `GET /deep`, resolved, attributed to the entry's caller (one router, one
    declarer), with nothing filed in the ledger. Ktor's own documented structures nest
    three or four deep; the bound is where a walk that never returns is stopped, and a
    chain that stays inside it is ordinary routing."""
    workspace = _resolve(tmp_path, _helper_chain(16), _shipped_ktor_catalog())
    rows, questions = _rows(workspace), _questions(workspace)
    workspace.close()

    assert _identities(rows) == [("GET", "/deep", _MODULE + _SUSPEND_BODY, "resolved")]
    assert rows[0]["caller"] == DECLARER + "orders(sig_o0)."
    assert questions == []


def test_a_helper_chain_deeper_than_the_bound_files_one_question_and_no_row(tmp_path: Path):
    """The seventeenth hop is not followed. What is published is ONE `open_questions` row of
    kind `routing_depth` — the entry's caller as its evidence, the first unread callee as
    its candidate — and NO endpoint row: an unresolved row there would claim an address
    nobody read, where the verb may be on any route or on none (spec 2026-09-19 §0b A2).
    The question's own identity columns are NULL because both halves genuinely are unread.
    The same catalog, the same frame, the same hops as the test above; only the length
    differs by one, so this is the bound and nothing else."""
    workspace = _resolve(tmp_path, _helper_chain(17), _shipped_ktor_catalog())
    rows, questions = _rows(workspace), _questions(workspace)
    workspace.close()

    assert rows == []
    assert [
        (
            q["protocol"],
            q["method"],
            q["path"],
            q["question"],
            json.loads(str(q["candidates"])),
            q["evidence"],
        )
        for q in questions
    ] == [
        (
            "http",
            None,
            None,
            "routing_depth",
            [
                {
                    "callee": _MODULE + _helper("h17"),
                    "caller": DECLARER + "orders(sig_o0).",
                    "depth": 16,
                }
            ],
            DECLARER + "orders(sig_o0).",
        )
    ]


def test_two_deep_chains_in_one_run_are_one_question_with_two_candidates(tmp_path: Path):
    """An `open_questions` row is identified by `(protocol, method, path, question)`
    (`open_question_identity`), and a `routing_depth` row's method and path are NULL on
    purpose — so every deep chain in one run shares ONE identity. Two rows would render
    as two lines a `beside-open-question` verdict cannot tell apart, and the verdict
    would anchor under the first and leave the second unanswered forever: the defect
    `service_identity._merged` was written for. So two entry callers each exhausting the
    bound — `orders()` through `h1…h17` and `more()` through `m1…m17` — file ONE row, its
    candidates one per chain (sorted, NFR-1) and its evidence naming both callers."""
    facts = _helper_chain(17)
    more_body = DECLARER + "more$lambda$1(sig_m0)."
    facts += [
        _method_symbol(more_body),
        _site(
            DECLARER + "more(sig_m1).",
            0,
            _ROUTING_ROOT,
            "routing",
            result=1,
            descriptor=_ROUTING_DESC,
            arguments=[
                CallArgument(kind="parameter", value=0),
                CallArgument(kind="lambda", symbol=more_body, source=0, captures=0),
            ],
        ),
        _helper_call(more_body, 0, "m1", argument=CallArgument(kind="parameter", value=0)),
    ]
    names = [f"m{i}" for i in range(1, 18)]
    for i, name in enumerate(names):
        body = _helper(name)
        facts.append(_method_symbol(body))
        if i + 1 < len(names):
            facts.append(
                _helper_call(
                    body, 0, names[i + 1], argument=CallArgument(kind="parameter", value=0)
                )
            )
        else:
            facts.append(_deep_verb(body, 0, "/deeper"))
    workspace = _resolve(tmp_path, facts, _shipped_ktor_catalog())
    rows, questions = _rows(workspace), _questions(workspace)
    workspace.close()

    assert rows == []
    assert len(questions) == 1
    assert json.loads(str(questions[0]["candidates"])) == [
        {"callee": _MODULE + _helper("h17"), "caller": DECLARER + "orders(sig_o0).", "depth": 16},
        {"callee": _MODULE + _helper("m17"), "caller": DECLARER + "more(sig_m1).", "depth": 16},
    ]
    assert questions[0]["evidence"] == (
        DECLARER + "more(sig_m1)." + "; and " + DECLARER + "orders(sig_o0)."
    )


def test_a_helper_calling_itself_is_followed_once(tmp_path: Path):
    """The visited set, keyed `(callee, origin index)`: `fun Route.loop() { loop();
    get("/loop") { } }` calls itself with the same origin, and the second entry is
    refused where the first was taken — so the verb derives exactly once and the walk
    terminates on its own, well inside the depth bound, with nothing to file. Without
    the set the same body would be re-entered until the bound stopped it and a
    `routing_depth` question would be asked of a chain that is not deep at all."""
    loop = _helper("loop")
    facts = [
        *_routing_entry(),
        _method_symbol(loop),
        _helper_call(_ROUTING_BODY, 0, "loop", argument=CallArgument(kind="parameter", value=0)),
        _helper_call(loop, 0, "loop", argument=CallArgument(kind="parameter", value=0)),
        _deep_verb(loop, 1, "/loop"),
    ]
    workspace = _resolve(tmp_path, facts, _shipped_ktor_catalog())
    rows, questions = _rows(workspace), _questions(workspace)
    workspace.close()

    assert _identities(rows) == [("GET", "/loop", _MODULE + _SUSPEND_BODY, "resolved")]
    assert questions == []


@pytest.mark.pins("combinator.helper-follows-the-origin-only")
def test_a_module_local_call_the_origin_does_not_reach_is_not_followed(tmp_path: Path):
    """§10 near-miss on the origin conjunct, paired with the `/helper` positive on
    `_ktor_facts`. Every cell is that positive — a module-local method with a body, called
    from a body whose rule named its origin, a verb on the callee's parameter 0 — except
    the ARGUMENT handed over: a field value the extractor could not follow, and the body's
    OTHER parameter. Neither is the origin, so neither call is followed and the verb inside
    derives nothing, not even an unresolved row: a route on a builder this body never
    touched is not this tree's, and a row would say it was (spec §4a: "a verb on any other
    `Route` inside the callee is silence, as today"). A callee with NO body — an interface
    or abstract method, whose call sites the facts cannot carry — is the third cell: not
    followed either (A10), and nothing is fabricated for it."""
    stray = _helper("stray")
    facts = [
        *_routing_entry(),
        _method_symbol(stray),
        _method_symbol(_helper("abstractly")),
        _helper_call(_ROUTING_BODY, 0, "stray", argument=CallArgument(kind="unresolved")),
        _helper_call(_ROUTING_BODY, 1, "stray", argument=CallArgument(kind="parameter", value=1)),
        _helper_call(
            _ROUTING_BODY, 2, "abstractly", argument=CallArgument(kind="parameter", value=0)
        ),
        _deep_verb(stray, 0, "/stray"),
    ]
    workspace = _resolve(tmp_path, facts, _shipped_ktor_catalog())
    rows, questions = _rows(workspace), _questions(workspace)
    workspace.close()

    assert rows == []
    assert questions == []


_HELPED = method_descriptor(DECLARER, "helped", "()V")


def _apibuilder_with_a_helper_call() -> list:
    """`_apibuilder_facts` plus a static, argument-less `helped()` CALL inside the inner
    group and `static void helped() { get("/h", h); }` as a method of its own — the thread-
    local builder's helper shape: no origin flows anywhere, because `ApiBuilder` keeps the
    current prefix in a `ThreadLocal` and every verb is static."""
    return [
        *_apibuilder_facts(_ROUTER_CONFIG),
        _method_symbol(_HELPED),
        _site(_GROUP_INNER, 2, DECLARER, "helped", descriptor="()V", arguments=[]),
        _site(
            _HELPED,
            0,
            _API_BUILDER,
            "get",
            descriptor=f"(Ljava/lang/String;{_HANDLER_DESC})V",
            arguments=[
                CallArgument(kind="string", value="/h"),
                CallArgument(kind="lambda", symbol=HEALTH, source=0),
            ],
        ),
    ]


def _without_follow_calls(catalog: Catalog) -> Catalog:
    """The shipped catalog with `follow_calls` struck from every rule that declares it —
    the default, which follows origin-carrying calls only."""
    matches = copy.deepcopy(catalog.matches)
    for rule in (*matches["entries"], *matches["vocabulary"]["prefixes"]):
        rule.pop("follow_calls", None)
    return replace(catalog, matches=matches)


def test_an_origin_less_body_follows_a_module_local_call_under_follow_calls_all(tmp_path: Path):
    """The paired positive: the shipped `javalin-apibuilder` rules declare `follow_calls:
    all` on the entry and on `path`, because `ApiBuilder.staticInstance()` throws
    `IllegalStateException` outside the block (measured on the 6.4.0 jar) — a helper that
    reaches a verb can only ever have been called from inside one. So `helped()` inside
    `path("/orders", …)` is followed with no origin at all, and its `get("/h", h)` folds
    under the prefix: `GET /orders/h`, on the entry's caller."""
    workspace = _resolve(tmp_path, _apibuilder_with_a_helper_call(), _shipped_apibuilder_catalog())
    rows = _rows(workspace)
    workspace.close()

    assert _identities(rows) == [
        ("GET", "/orders/h", _MODULE + HEALTH, "resolved"),
        ("GET", "/orders/{id}", _MODULE + LIST_ORDERS, "resolved"),
        ("POST", "/orders", _MODULE + CREATE_ORDER, "resolved"),
    ]
    assert {row["caller"] for row in rows} == {_CONFIG_LAMBDA}


@pytest.mark.pins("combinator.origin-less-following-is-opt-in")
def test_an_origin_less_body_does_not_follow_a_module_local_call_by_default(tmp_path: Path):
    """§10 near-miss on the `follow_calls` conjunct: the same facts, the same catalog with
    the word struck. An origin-less body — a `Supplier<RouterFunction>` body is one too —
    may call a helper that builds routers nobody returns, and following it would attach
    routes the framework never registered (spec 2026-09-19 §0b A1). Nothing is derived
    for `helped()`; the two routes written in the body itself derive exactly as before,
    and nothing is filed: not following is the default, not a failure."""
    catalog = _without_follow_calls(_shipped_apibuilder_catalog())
    workspace = _resolve(tmp_path, _apibuilder_with_a_helper_call(), catalog)
    rows, questions = _rows(workspace), _questions(workspace)
    workspace.close()

    assert _identities(rows) == [
        ("GET", "/orders/{id}", _MODULE + LIST_ORDERS, "resolved"),
        ("POST", "/orders", _MODULE + CREATE_ORDER, "resolved"),
    ]
    assert questions == []


def test_follow_calls_away_from_a_body_link_or_with_another_value_is_refused(tmp_path: Path):
    """`follow_calls` is a word for a rule that LINKS a body — a body-linked entry or a
    prefix with `body_arg` — and its one value is `all`. On a verb it names nothing the
    engine could follow from; misspelt (`always`) it would be read as absent and the
    thread-local builder's helpers would go silently unfollowed, which is the outcome the
    word exists to prevent."""
    matches = _matches()
    matches["vocabulary"]["verbs"][0]["follow_calls"] = "all"
    with pytest.raises(CatalogError, match="follow_calls"):
        _resolve(tmp_path / "a", [], _catalog(matches))

    matches = _matches()
    matches["entries"].append(
        {
            "owner": "com.example.web.RouterDslFacade",
            "method": "dsl",
            "body_arg": 0,
            "follow_calls": "always",
        }
    )
    with pytest.raises(CatalogError, match="follow_calls"):
        _resolve(tmp_path / "b", [], _catalog(matches))


# --- chain-form composers, negators, a terminal, `verb_arg`, array paths (A2 Task 6, spec §12 words 3–5) ---

SPEC = "com/example/gw/PredicateSpec#"
BOOL = "com/example/gw/BooleanSpec#"
GW = "com/example/gw/Routes#"


def _gateway_matches() -> dict[str, object]:
    """An invented gateway-shaped vocabulary: a route is a RECEIVER chain of predicate
    calls on the body's parameter, composed by the zero-argument `and()`/`or()`, and
    emitted by the chain's last call — the terminal `uri`, which carries no handler."""
    return {
        "entries": [
            {"owner": "com.example.gw.Routes", "method": "route", "body_arg": 1, "origin_param": 0}
        ],
        "origins": [{"owner": "com.example.gw.Routes", "method": "routes", "arity": 0}],
        "vocabulary": {
            "prefixes": [
                {
                    "owner": "com.example.gw.PredicateSpec",
                    "method": "path",
                    "arity": 1,
                    "path_arg": 0,
                }
            ],
            "verbs": [
                {
                    "owner": "com.example.gw.PredicateSpec",
                    "method": "method",
                    "arity": 1,
                    "verb_arg": 0,
                },
                {
                    "owner": "com.example.gw.BooleanSpec",
                    "method": "uri",
                    "arity": 1,
                    "terminal": True,
                    "handler": "none",
                },
            ],
            "chain_composers": {
                "and": [{"owner": "com.example.gw.BooleanSpec", "method": "and"}],
                "or": [{"owner": "com.example.gw.BooleanSpec", "method": "or"}],
            },
            "negators": [
                {"owner": "com.example.gw.PredicateSpec", "method": "not"},
                {"owner": "com.example.gw.BooleanSpec", "method": "negate"},
            ],
        },
        "continuations": [
            {"name": "build", "owner": "com.example.gw.Routes"},
            {"name": "filters", "owner": "com.example.gw.BooleanSpec", "pass_through": True},
            {"name": "host", "owner": "com.example.gw.BooleanSpec", "pass_through": True},
        ],
    }


def _gateway_body(chain: list[tuple[str, str, list[CallArgument]]]) -> list:
    """`routes().route("id", r -> r.<chain>).build()`: `chain` is (owner, name, args) from
    the head; each call's receiver is the previous call's result, the head's is the body's
    parameter 0 (the lambda captures nothing)."""
    caller = DECLARER + "routes(sig_r)."
    entry_sites = [
        _site(caller, 0, GW, "routes", result=0, descriptor="()Lcom/example/gw/Builder;"),
        _site(
            caller,
            1,
            GW,
            "route",
            invoke_kind="virtual",
            receiver=0,
            result=1,
            descriptor="(Ljava/lang/String;Ljava/util/function/Function;)Lcom/example/gw/Builder;",
            arguments=[
                CallArgument(kind="string", value="id"),
                CallArgument(kind="lambda", symbol=INLINE_BODY, source=1, captures=0),
            ],
        ),
        _site(
            caller,
            2,
            GW,
            "build",
            invoke_kind="virtual",
            receiver=1,
            result=2,
            descriptor="()Lcom/example/gw/Locator;",
        ),
    ]
    body: list[CallSiteFact] = []
    previous: int | None = None
    for ordinal, (owner, name, args) in enumerate(chain):
        body.append(
            CallSiteFact(
                document_id="doc_1",
                caller=INLINE_BODY,
                invoke_kind="virtual",
                ordinal=ordinal,
                target=CallTarget(owner=owner, name=name, descriptor="(...)V"),
                receiver=previous,
                receiver_parameter=0 if previous is None else None,
                result=ordinal,
                arguments=args,
            )
        )
        previous = ordinal
    return [_method_symbol(INLINE_BODY), *entry_sites, *body]


def _enum(name: str) -> CallArgument:
    return CallArgument(kind="enum", symbol="org/springframework/http/HttpMethod#" + name + ".")


def _uri() -> tuple[str, str, list[CallArgument]]:
    return (BOOL, "uri", [CallArgument(kind="string", value="http://x")])


def test_a_predicate_chain_ending_at_a_terminal_is_one_route(tmp_path: Path):
    """Spec §12 word 4: the terminal's routes are its receiver chain folded as
    CONSTRAINTS — `path` and `method` merged across the chain-form `and()` — one row,
    handler NULL as the rule says, `caller` the method holding the tree's root."""
    chain = [
        (SPEC, "path", [CallArgument(kind="string", value="/orders/**")]),
        (BOOL, "and", []),
        (SPEC, "method", [_enum("GET")]),
        _uri(),
    ]
    workspace = _resolve(tmp_path, _gateway_body(chain), _catalog(_gateway_matches()))
    rows = _rows(workspace)
    workspace.close()

    assert _identities(rows) == [("GET", "/orders/**", None, "resolved")]
    assert [row["caller"] for row in rows] == [DECLARER + "routes(sig_r)."]


def test_or_opens_a_branch_and_and_binds_to_the_left(tmp_path: Path):
    """`(a or b) and GET`, left-associative as the framework composes it: `or()` makes
    the next contribution a branch of its own, and the `method` after the `and()` merges
    into BOTH branches."""
    chain = [
        (SPEC, "path", [CallArgument(kind="string", value="/a")]),
        (BOOL, "or", []),
        (SPEC, "path", [CallArgument(kind="string", value="/b")]),
        (BOOL, "and", []),
        (SPEC, "method", [_enum("GET")]),
        _uri(),
    ]
    workspace = _resolve(tmp_path, _gateway_body(chain), _catalog(_gateway_matches()))
    identities = _identities(_rows(workspace))
    workspace.close()

    assert identities == [("GET", "/a", None, "resolved"), ("GET", "/b", None, "resolved")]


def test_a_verb_only_route_serves_every_path_and_a_vararg_of_verbs_is_one_branch_each(
    tmp_path: Path,
):
    """Spec §12 word 5: `method(GET, POST)` is a vararg, one branch per verb; a route
    whose constraints read no path serves every path — `/**` (§7 case 3), contributed
    ONCE, after the chain and the terminal's own constraints are merged."""
    chain = [
        (SPEC, "method", [CallArgument(kind="array", elements=[_enum("GET"), _enum("POST")])]),
        _uri(),
    ]
    workspace = _resolve(tmp_path, _gateway_body(chain), _catalog(_gateway_matches()))
    identities = _identities(_rows(workspace))
    workspace.close()

    assert identities == [("GET", "/**", None, "resolved"), ("POST", "/**", None, "resolved")]


def test_a_terminal_directly_on_the_origin_parameter_is_a_catch_all(tmp_path: Path):
    """`r.uri(x)` — a chain of nothing but the terminal: no constraint was read and
    nothing was poisoned, so the route serves every path and names no verb."""
    workspace = _resolve(tmp_path, _gateway_body([_uri()]), _catalog(_gateway_matches()))
    identities = _identities(_rows(workspace))
    workspace.close()

    assert identities == [(None, "/**", None, "resolved")]


def test_a_string_verb_reads_as_written_and_an_unreadable_one_poisons_only_the_verb(
    tmp_path: Path,
):
    """The verb argument as a string literal is that verb AS WRITTEN — measured on
    spring-web 7.0.9, `HttpMethod.valueOf` compares case-sensitively and otherwise wraps
    the string unchanged, so upper-casing here would publish a verb the framework never
    matches; an argument of any other kind poisons `method` alone, the path intact."""
    written = _resolve(
        tmp_path / "written",
        _gateway_body([(SPEC, "method", [CallArgument(kind="string", value="GET")]), _uri()]),
        _catalog(_gateway_matches()),
    )
    assert _identities(_rows(written)) == [("GET", "/**", None, "resolved")]
    written.close()
    unread = _resolve(
        tmp_path / "unread",
        _gateway_body(
            [
                (SPEC, "path", [CallArgument(kind="string", value="/a")]),
                (BOOL, "and", []),
                (SPEC, "method", [CallArgument(kind="unresolved")]),
                _uri(),
            ]
        ),
        _catalog(_gateway_matches()),
    )
    assert _identities(_rows(unread)) == [(None, "/a", None, "unresolved")]
    unread.close()


@pytest.mark.pins("combinator.negator-poisons")
def test_a_negator_anywhere_in_the_chain_poisons_the_route(tmp_path: Path):
    """Spec §12 word 3: a negated predicate still serves SOMETHING, and what it serves
    is not readable from the negation — one unresolved row, never the un-negated path
    published as resolved."""
    chain = [
        (SPEC, "path", [CallArgument(kind="string", value="/a")]),
        (BOOL, "negate", []),
        _uri(),
    ]
    workspace = _resolve(tmp_path, _gateway_body(chain), _catalog(_gateway_matches()))
    rows = _rows(workspace)
    workspace.close()

    assert [(row["path"], row["resolution"]) for row in rows] == [(None, "unresolved")]


def test_an_or_branch_opened_onto_a_pass_through_is_a_branch_of_its_own(tmp_path: Path):
    """`path("/a").or().host(h)`: the alternative `or()` opened is the host predicate,
    which the walk reads as nothing — a branch with NO path constraint, which serves
    every path (spec §12 word 4). The framework serves `/a` AND `/**`; a fold that left
    the branch pending across the pass-through would publish `/a` alone, and the
    catch-all half of the route would vanish (Task 6 review, Important). Left-associative
    still: `((a or host) and b)` merges `/b` into both branches."""
    opened = _resolve(
        tmp_path / "opened",
        _gateway_body(
            [
                (SPEC, "path", [CallArgument(kind="string", value="/a")]),
                (BOOL, "or", []),
                (BOOL, "host", [CallArgument(kind="string", value="**.x.com")]),
                _uri(),
            ]
        ),
        _catalog(_gateway_matches()),
    )
    assert _identities(_rows(opened)) == [
        (None, "/**", None, "resolved"),
        (None, "/a", None, "resolved"),
    ]
    opened.close()
    bound = _resolve(
        tmp_path / "bound",
        _gateway_body(
            [
                (SPEC, "path", [CallArgument(kind="string", value="/a")]),
                (BOOL, "or", []),
                (BOOL, "host", [CallArgument(kind="string", value="**.x.com")]),
                (BOOL, "and", []),
                (SPEC, "path", [CallArgument(kind="string", value="/b")]),
                _uri(),
            ]
        ),
        _catalog(_gateway_matches()),
    )
    assert _identities(_rows(bound)) == [
        (None, "/a/b", None, "resolved"),
        (None, "/b", None, "resolved"),
    ]
    bound.close()


def test_an_or_dangling_before_the_terminal_opens_nothing(tmp_path: Path):
    """`path("/a").or().uri(x)`: the `or()` is followed by no predicate at all, so no
    alternative was written — one route, `/a`. The terminal is not a predicate and is
    never the branch an `or()` opens."""
    workspace = _resolve(
        tmp_path,
        _gateway_body(
            [(SPEC, "path", [CallArgument(kind="string", value="/a")]), (BOOL, "or", []), _uri()]
        ),
        _catalog(_gateway_matches()),
    )
    identities = _identities(_rows(workspace))
    workspace.close()

    assert identities == [(None, "/a", None, "resolved")]


def test_a_pass_through_in_the_chain_contributes_nothing(tmp_path: Path):
    """`filters(fn)` between the predicates and the terminal is a declared pass-through:
    stepped over, its lambda never read as a handler or a route."""
    chain = [
        (SPEC, "path", [CallArgument(kind="string", value="/a")]),
        (BOOL, "filters", [CallArgument(kind="lambda", symbol=HEALTH, source=0, captures=0)]),
        _uri(),
    ]
    workspace = _resolve(tmp_path, _gateway_body(chain), _catalog(_gateway_matches()))
    identities = _identities(_rows(workspace))
    workspace.close()

    assert identities == [(None, "/a", None, "resolved")]


def test_a_path_vararg_is_one_branch_per_literal_and_a_non_literal_element_poisons(
    tmp_path: Path,
):
    """Spec §12 word 4's last sentence: `path("/a", "/b")` is one branch per element,
    read through the same literal-path join every other path is; an array holding
    anything but string literals is an unreadable path."""
    literals = _resolve(
        tmp_path / "literals",
        _gateway_body(
            [
                (
                    SPEC,
                    "path",
                    [
                        CallArgument(
                            kind="array",
                            elements=[
                                CallArgument(kind="string", value="/a"),
                                CallArgument(kind="string", value="/b"),
                            ],
                        )
                    ],
                ),
                _uri(),
            ]
        ),
        _catalog(_gateway_matches()),
    )
    assert _identities(_rows(literals)) == [
        (None, "/a", None, "resolved"),
        (None, "/b", None, "resolved"),
    ]
    literals.close()
    mixed = _resolve(
        tmp_path / "mixed",
        _gateway_body(
            [
                (
                    SPEC,
                    "path",
                    [
                        CallArgument(
                            kind="array",
                            elements=[
                                CallArgument(kind="string", value="/a"),
                                CallArgument(kind="unresolved"),
                            ],
                        )
                    ],
                ),
                _uri(),
            ]
        ),
        _catalog(_gateway_matches()),
    )
    assert _identities(_rows(mixed)) == [(None, None, None, "unresolved")]
    mixed.close()


def test_a_chain_whose_head_is_not_the_origin_parameter_poisons(tmp_path: Path):
    """Spec §13 case 6 on the chain form: a head on a field receiver is not the body's
    origin parameter, so the whole route is one unresolved row — and so is a chain with
    a call the vocabulary does not know in it, since what that call constrains is
    unreadable."""
    facts = _gateway_body([(SPEC, "path", [CallArgument(kind="string", value="/a")]), _uri()])
    head = next(f for f in facts if isinstance(f, CallSiteFact) and f.target.name == "path")
    facts[facts.index(head)] = head.model_copy(update={"receiver_parameter": None})
    field = _resolve(tmp_path / "field", facts, _catalog(_gateway_matches()))
    assert [row["resolution"] for row in _rows(field)] == ["unresolved"]
    field.close()
    unknown = _resolve(
        tmp_path / "unknown",
        _gateway_body(
            [
                (SPEC, "path", [CallArgument(kind="string", value="/a")]),
                (BOOL, "and", []),
                (SPEC, "header", [CallArgument(kind="string", value="X-Id")]),
                _uri(),
            ]
        ),
        _catalog(_gateway_matches()),
    )
    assert _identities(_rows(unknown)) == [(None, None, None, "unresolved")]
    unknown.close()


def test_an_outbound_terminal_route_reading_no_path_poisons_the_path(tmp_path: Path):
    """The any-path address is what a SERVED route with no path constraint is (§7 case
    3); an outbound catalog serves nothing, so a terminal route that read no path has no
    address to publish and the path is poisoned instead. No shipped outbound combinator
    catalog exists — pinned hand-built so the gate is stated, not assumed."""
    catalog = Catalog(
        id="test-outbound-chain",
        style="combinator",
        protocol="http",
        direction="outbound",
        requires=("call_site", "string_constants", "chain_reconstruction"),
        matches=_gateway_matches(),
        source=Path("test-outbound-chain.yml"),
    )
    workspace = _resolve(
        tmp_path, _gateway_body([(SPEC, "method", [_enum("GET")]), _uri()]), catalog
    )
    identities = _identities(_rows(workspace))
    workspace.close()

    assert identities == [("GET", None, None, "unresolved")]


def test_a_chain_word_on_a_name_another_role_claims_and_a_terminal_without_a_handler_answer_are_refused(
    tmp_path: Path,
):
    """A chain composer or negator on an (owner, method) a verb, prefix or media rule
    already names is two readings of one call decided by dispatch order, never by the
    catalog; a terminal declares a whole route, so it says where its handler sits or
    that there is none; `verb_arg` names an argument position and is the rule's ONE
    answer for its verb — beside `verb`, or at a position the arity cannot carry, it is
    a rule that cannot mean what it says."""
    colliding = _gateway_matches()
    colliding["vocabulary"]["negators"].append(  # type: ignore[index]
        {"owner": "com.example.gw.PredicateSpec", "method": "path"}
    )
    with pytest.raises(CatalogError, match="`path`.*negator"):
        _resolve(tmp_path / "colliding", _gateway_body([_uri()]), _catalog(colliding))
    handler_less = _gateway_matches()
    del handler_less["vocabulary"]["verbs"][1]["handler"]  # type: ignore[index]
    with pytest.raises(CatalogError, match="`uri`.*terminal"):
        _resolve(tmp_path / "handler_less", _gateway_body([_uri()]), _catalog(handler_less))
    two_verbs = _gateway_matches()
    two_verbs["vocabulary"]["verbs"][0]["verb"] = "GET"  # type: ignore[index]
    with pytest.raises(CatalogError, match="`method`.*verb_arg"):
        _resolve(tmp_path / "two_verbs", _gateway_body([_uri()]), _catalog(two_verbs))
    beyond = _gateway_matches()
    beyond["vocabulary"]["verbs"][0]["verb_arg"] = 1  # type: ignore[index]
    with pytest.raises(CatalogError, match="`method`.*verb_arg"):
        _resolve(tmp_path / "beyond", _gateway_body([_uri()]), _catalog(beyond))
    both_forms = _gateway_matches()
    both_forms["vocabulary"]["composers"] = {  # type: ignore[index]
        "and": [{"owner": "com.example.gw.BooleanSpec", "method": "and"}]
    }
    with pytest.raises(CatalogError, match="`and`.*chain_composers.*composers"):
        _resolve(tmp_path / "both_forms", _gateway_body([_uri()]), _catalog(both_forms))
    extending = _gateway_matches()
    extending["vocabulary"]["verbs"][1]["extends_receiver"] = True  # type: ignore[index]
    with pytest.raises(CatalogError, match="`uri`.*terminal.*extends_receiver"):
        _resolve(tmp_path / "extending", _gateway_body([_uri()]), _catalog(extending))


# --- body-linked entries told apart by arity (A2 Task 7, spec §3 applied to entries) ---

_UNNAMED_BODY = DECLARER + "lambda$routes$1(sig_a2)."


def _two_route_overloads_matches() -> dict[str, object]:
    """The invented gateway vocabulary with BOTH `route` overloads as body-linked entries:
    `route(String, Function)` with the body at 1, `route(Function)` with it at 0 — one
    owner, one name, told apart by `arity` (and `arg_types` on the named one)."""
    matches = _gateway_matches()
    matches["entries"] = [
        {
            "owner": "com.example.gw.Routes",
            "method": "route",
            "arity": 2,
            "arg_types": {0: "java.lang.String"},
            "body_arg": 1,
            "origin_param": 0,
        },
        {
            "owner": "com.example.gw.Routes",
            "method": "route",
            "arity": 1,
            "body_arg": 0,
            "origin_param": 0,
        },
    ]
    return matches


def _two_route_overloads_body() -> list:
    """`routes().route("id", r -> r.path("/a").uri(x)).route(r -> r.path("/b").uri(x)).build()`
    — the two overloads in one chain, each linking a body of its own."""
    caller = DECLARER + "routes(sig_r)."
    sites = [
        _site(caller, 0, GW, "routes", result=0, descriptor="()Lcom/example/gw/Builder;"),
        _site(
            caller,
            1,
            GW,
            "route",
            invoke_kind="virtual",
            receiver=0,
            result=1,
            descriptor="(Ljava/lang/String;Ljava/util/function/Function;)Lcom/example/gw/Builder;",
            arguments=[
                CallArgument(kind="string", value="id"),
                CallArgument(kind="lambda", symbol=INLINE_BODY, source=10, captures=0),
            ],
        ),
        _site(
            caller,
            2,
            GW,
            "route",
            invoke_kind="virtual",
            receiver=1,
            result=2,
            descriptor="(Ljava/util/function/Function;)Lcom/example/gw/Builder;",
            arguments=[CallArgument(kind="lambda", symbol=_UNNAMED_BODY, source=11, captures=0)],
        ),
        _site(
            caller,
            3,
            GW,
            "build",
            invoke_kind="virtual",
            receiver=2,
            result=3,
            descriptor="()Lcom/example/gw/Locator;",
        ),
    ]
    for body, path in ((INLINE_BODY, "/a"), (_UNNAMED_BODY, "/b")):
        sites.extend(
            [
                _site(
                    body,
                    0,
                    SPEC,
                    "path",
                    invoke_kind="virtual",
                    receiver_parameter=0,
                    result=0,
                    arguments=[CallArgument(kind="string", value=path)],
                ),
                _site(
                    body,
                    1,
                    BOOL,
                    "uri",
                    invoke_kind="virtual",
                    receiver=0,
                    result=1,
                    arguments=[CallArgument(kind="string", value="http://x")],
                ),
            ]
        )
    return [_method_symbol(INLINE_BODY), _method_symbol(_UNNAMED_BODY), *sites]


def test_two_body_linked_overloads_of_one_name_each_fold_their_own_body(tmp_path: Path):
    """Spec §3's discriminator applies to every rule kind, and a body-linked entry was the
    one kind it skipped: matched on owner and name alone, the first `route` entry claimed
    both overloads, so `route(Function)` was read at `body_arg: 1` — no lambda there, one
    unresolved row — and the route it links was never folded. With `arity` (and
    `arg_types`) read on entries as on verbs, each overload jumps to its OWN body and
    both routes derive, under the one method holding the chain."""
    workspace = _resolve(
        tmp_path, _two_route_overloads_body(), _catalog(_two_route_overloads_matches())
    )
    rows = _rows(workspace)
    workspace.close()

    assert _identities(rows) == [
        (None, "/a", None, "resolved"),
        (None, "/b", None, "resolved"),
    ]
    assert {row["caller"] for row in rows} == {DECLARER + "routes(sig_r)."}


def test_two_body_linked_entries_that_could_both_accept_one_call_are_refused(tmp_path: Path):
    """Spec §3c, on entries as on every other rule kind: two entries sharing owner, method
    and arity that type no shared position differently could both accept one call, and
    file order would decide — refused at load, naming both. And `arg_types` without an
    `arity` is an entry that cannot mean what it says."""
    same_arity = _two_route_overloads_matches()
    same_arity["entries"][1]["arity"] = 2  # type: ignore[index]
    del same_arity["entries"][1]["body_arg"]  # type: ignore[index]
    same_arity["entries"][1]["body_arg"] = 1  # type: ignore[index]
    with pytest.raises(CatalogError, match=r"`entries` rules for `route` at arity 2 could both"):
        _resolve(tmp_path / "same", _two_route_overloads_body(), _catalog(same_arity))
    untyped = _two_route_overloads_matches()
    del untyped["entries"][0]["arity"]  # type: ignore[index]
    with pytest.raises(CatalogError, match="`route` declares `arg_types` without `arity`"):
        _resolve(tmp_path / "untyped", _two_route_overloads_body(), _catalog(untyped))


# --- `spring-cloud-gateway` (A2 Task 7): the chain form on the shipped catalog ---

_GW_BUILDER = "org/springframework/cloud/gateway/route/builder/RouteLocatorBuilder$Builder#"
_GW_LOCATOR_BUILDER = "org/springframework/cloud/gateway/route/builder/RouteLocatorBuilder#"
_GW_PREDICATE_SPEC = "org/springframework/cloud/gateway/route/builder/PredicateSpec#"
_GW_BOOLEAN_SPEC = "org/springframework/cloud/gateway/route/builder/BooleanSpec#"
_GW_ROUTE_DESC = (
    "(Ljava/lang/String;Ljava/util/function/Function;)"
    "Lorg/springframework/cloud/gateway/route/builder/RouteLocatorBuilder$Builder;"
)
_GW_ROUTES = DECLARER + "routes(sig_g0)."
_GW_BODY = DECLARER + "lambda$routes$0(sig_g1)."


def _shipped_gateway_catalog() -> Catalog:
    from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
    from sextant.resources import catalogs_dir

    return next(
        c for c in YamlCatalogSource(catalogs_dir()).load() if c.id == "spring-cloud-gateway"
    )


def _gateway_facts(chain_owner: str) -> list:
    """`builder.routes().route("orders", r -> r.path("/orders/**").uri("http://x")).build()`
    — the shape `fixtures/orders-gateway/.../GatewayRoutes.java`'s `routes()` compiles to
    (`javap -c`, 2026-09-13): `routes()` on `RouteLocatorBuilder`, `route`/`build` on its
    `$Builder`, the lambda an `invokedynamic` body linked with `captures: 0`, and inside
    it `PredicateSpec.path` on the body's parameter 0 then `BooleanSpec.uri` on that
    result — the OWNER of each call being the receiver's static type. `chain_owner` is
    the type the outer chain is written on: the one cell the near-miss below varies."""
    return [
        _method_symbol(_GW_BODY),
        # Value ids as the fixture's own fact file carries them: `routes()` on the method's
        # `RouteLocatorBuilder` parameter, the lambda's `source` the `LambdaMetafactory`
        # site's result (a value of its own, never the `route` call's), `build()` on the
        # `route` call's result.
        _site(
            _GW_ROUTES,
            0,
            _GW_LOCATOR_BUILDER,
            "routes",
            invoke_kind="virtual",
            receiver_parameter=0,
            result=7,
            descriptor=f"()L{_GW_BUILDER[:-1]};",
        ),
        _site(
            _GW_ROUTES,
            1,
            chain_owner,
            "route",
            invoke_kind="virtual",
            receiver=7,
            result=12,
            descriptor=_GW_ROUTE_DESC,
            arguments=[
                CallArgument(kind="string", value="orders"),
                CallArgument(kind="lambda", symbol=_GW_BODY, source=9, captures=0),
            ],
        ),
        _site(
            _GW_ROUTES,
            2,
            chain_owner,
            "build",
            invoke_kind="virtual",
            receiver=12,
            result=46,
            descriptor="()Lorg/springframework/cloud/gateway/route/RouteLocator;",
        ),
        _site(
            _GW_BODY,
            0,
            _GW_PREDICATE_SPEC,
            "path",
            invoke_kind="virtual",
            receiver_parameter=0,
            result=0,
            descriptor=f"([Ljava/lang/String;)L{_GW_BOOLEAN_SPEC[:-1]};",
            arguments=[
                CallArgument(
                    kind="array", elements=[CallArgument(kind="string", value="/orders/**")]
                )
            ],
        ),
        _site(
            _GW_BODY,
            1,
            _GW_BOOLEAN_SPEC,
            "uri",
            invoke_kind="virtual",
            receiver=0,
            result=1,
            descriptor="(Ljava/lang/String;)Lorg/springframework/cloud/gateway/route/builder/Buildable;",
            arguments=[CallArgument(kind="string", value="http://orders-service")],
        ),
    ]


def test_the_gateway_catalog_derives_a_route_from_the_real_entry(tmp_path: Path):
    """The paired positive (GUIDELINES §10): the shipped rules fire on the real owners.
    `path("/orders/**")` — a vararg, one literal — then `uri(…)`: one route, `/orders/**`,
    no handler (a gateway route forwards), caller = the method holding `build()`.

    **ONE ROW PER METHOD since 2026-10-17, where this read one verbless row.** Ruled by the
    user — *fan out, but only to methods that are supported, not invalid ones* — and the
    catalog now declares `all_methods`, so `_fanned` applies. What makes that honest here is
    measured at `scripts/probes/cp29_gateway_properties.md` Q11: `combinePredicates` with no
    predicates returns a predicate that always holds, and `HttpMethod` is mentioned ZERO
    times in `RouteDefinitionRouteLocator`, so route construction cannot constrain a method
    it never names. Spec §13 case 7's "a catch-all one column over" is the rendering this
    supersedes; `RouterFunctions.resources(...)`, which serves three methods and not eight,
    is why its own catalog still declines `all_methods`."""
    workspace = _resolve(tmp_path, _gateway_facts(_GW_BUILDER), _shipped_gateway_catalog())
    rows = _rows(workspace)
    workspace.close()

    assert _identities(rows) == [
        (verb, "/orders/**", None, "resolved")
        for verb in ("DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT", "TRACE")
    ]
    assert [row["caller"] for row in rows] == [_GW_ROUTES] * 8


@pytest.mark.declines("spring-cloud-gateway")
@pytest.mark.pins("combinator.entry-owner-is-the-declared-type")
def test_the_gateway_catalog_declines_a_route_call_on_another_owner(tmp_path: Path):
    """§10 near-miss on the entry's owner conjunct. Every other cell is the positive
    above — the same `route` name and descriptor, the same `Function` lambda with
    `captures: 0`, the same `PredicateSpec.path` then `BooleanSpec.uri` chain on the
    body's parameter inside it — and only the OWNER the outer chain is written on
    differs: `com.example.NotABuilder#route`, which is not `RouteLocatorBuilder$Builder`
    (and so its `build()` is not this catalog's continuation either: a `route` on another
    type returns that type).

    Nothing is the required answer. The body-linked entries and the `build()` continuation
    are the ONLY roots this catalog has — a predicate chain inside a body is never a root
    of its own — so with the owner check gone any method named `route` handed a lambda
    would root a tree, and `/orders/**` would be published under this catalog's id for a
    route the gateway never registered."""
    workspace = _resolve(
        tmp_path, _gateway_facts("com/example/NotABuilder#"), _shipped_gateway_catalog()
    )
    identities = _identities(_rows(workspace))
    workspace.close()

    assert identities == []


# --- selector prefixes and getter-valued constants (spec 2026-09-19 §4b) ---------------

_HTTP_METHOD_COMPANION = "io/ktor/http/HttpMethod$Companion#"
_CONTENT_TYPE_APPLICATION = "io/ktor/http/ContentType$Application#"
_HTTP_METHOD = "Lio/ktor/http/HttpMethod;"
_CONTENT_TYPE = "Lio/ktor/http/ContentType;"
_FN1 = "Lkotlin/jvm/functions/Function1;"
_SELECTOR_DESCS = {
    "method": f"({_ROUTE}{_HTTP_METHOD}{_FN1}){_ROUTE}",
    "route": f"({_ROUTE}Ljava/lang/String;{_HTTP_METHOD}{_FN1}){_ROUTE}",
    "accept": f"({_ROUTE}[{_CONTENT_TYPE}{_FN1}){_ROUTE}",
    "contentType": f"({_ROUTE}{_CONTENT_TYPE}{_FN1}){_ROUTE}",
    "header": f"({_ROUTE}Ljava/lang/String;Ljava/lang/String;{_FN1}){_ROUTE}",
    "param": f"({_ROUTE}Ljava/lang/String;{_FN1}){_ROUTE}",
    "param2": f"({_ROUTE}Ljava/lang/String;Ljava/lang/String;{_FN1}){_ROUTE}",
    "optionalParam": f"({_ROUTE}Ljava/lang/String;{_FN1}){_ROUTE}",
}
# A getter this catalog's tables never name — `_getter_value`'s unknown case.
_UNKNOWN_GETTERS = "com/example/Constants#"


def _selector_body(index: int) -> str:
    return DECLARER + f"orders$lambda$1$lambda${index}(sig_s{index})."


def _getter(ordinal: int, owner: str, name: str, *, result: int) -> CallSiteFact:
    """`getstatic Owner.Companion|INSTANCE ; invokevirtual Owner.getX()` — the getter call
    a Kotlin `HttpMethod.Get` or `ContentType.Application.Json` compiles to (CP-24 rows 3
    and 4): a `virtual` call on the object read one value id earlier, whose RESULT is what
    the selector is handed as `{kind: unresolved, source: <result>}`."""
    return _site(
        _ROUTING_BODY,
        ordinal,
        owner,
        name,
        receiver=result - 1,
        result=result,
        invoke_kind="virtual",
        descriptor="()Ljava/lang/Object;",
    )


def _selector(
    ordinal: int, name: str, between: list[CallArgument], *, body: str, descriptor: str
) -> CallSiteFact:
    """One selector block in the routing body — `invokestatic RoutingBuilderKt.<name>(this,
    …, block)`: the body's parameter 0 first, the block last with `captures: 0`, exactly
    as `route` is written (the fixture's `selectors()`, read 2026-09-20)."""
    return _site(
        _ROUTING_BODY,
        ordinal,
        _ROUTING_BUILDER,
        name,
        result=ordinal + 300,
        descriptor=descriptor,
        arguments=[
            CallArgument(kind="parameter", value=0),
            *between,
            CallArgument(kind="lambda", symbol=body, source=ordinal + 200, captures=0),
        ],
    )


def _verb_in(body: str, ordinal: int, name: str, path: str | None) -> CallSiteFact:
    """A verb inside a selector block, on the block's own parameter — with a path, or the
    path-less overload that serves the prefix itself."""
    arguments = [CallArgument(kind="parameter", value=0)]
    if path is not None:
        arguments.append(CallArgument(kind="string", value=path))
    arguments.append(CallArgument(kind="instance", symbol=_SUSPEND_HANDLER, source=ordinal + 50))
    return _site(
        body,
        ordinal,
        _ROUTING_BUILDER,
        name,
        result=ordinal + 100,
        descriptor=_VERB_DESC if path is not None else _PATHLESS_VERB_DESC,
        arguments=arguments,
    )


def _selector_tree(*blocks: tuple[str, list[CallArgument], list[tuple[str, str | None]]]) -> list:
    """`routing { <selector>(…) { <verbs> } … }`: one block per tuple — the selector's
    name (`param2` is the two-argument `param`), the arguments between the receiver and
    the block, and the verbs written inside it as `(name, path)`."""
    facts = _routing_entry()
    for index, (name, between, verbs) in enumerate(blocks):
        body = _selector_body(index)
        facts.append(_method_symbol(body))
        facts.append(
            _selector(
                10 + index,
                "param" if name == "param2" else name,
                between,
                body=body,
                descriptor=_SELECTOR_DESCS[name],
            )
        )
        for ordinal, (verb, path) in enumerate(verbs):
            facts.append(_verb_in(body, ordinal, verb, path))
    return facts


def _by_source(result: int) -> CallArgument:
    return CallArgument(kind="unresolved", source=result)


def _literal(value: str) -> CallArgument:
    return CallArgument(kind="string", value=value)


def test_a_verb_selector_sets_the_verb_beneath_it_and_a_disagreeing_route_is_silence(
    tmp_path: Path,
):
    """Spec 2026-09-19 §4b. `method(HttpMethod.Get) { get("/x") { }; get { }; post("/y") { } }`
    on the shipped catalog: `HttpMethod.Get` is `HttpMethod$Companion.getGet()`, a getter
    whose RESULT the selector is handed, so the verb is read through
    `verb_values.getters` (CP-24 row 3) and the scope it opens is `GET`. `get("/x")`
    agrees and derives `GET /x`; the path-less `get { }` serves the prefix itself — here
    the routing root, `/`. `post("/y")` DISAGREES, and that subtree is a node the framework
    registers and can never dispatch (`HttpMethodRouteSelector.evaluate` returns the
    failure constant on a mismatch, CP-24 row 7): NOT a row of either verb, not an
    unresolved row, nothing — the A2 ruling, dropped before `_merged` could poison it."""
    facts = _selector_tree(
        ("method", [_by_source(9)], [("get", "/x"), ("get", None), ("post", "/y")]),
    )
    facts.append(_getter(0, _HTTP_METHOD_COMPANION, "getGet", result=9))
    workspace = _resolve(tmp_path, facts, _shipped_ktor_catalog())
    rows = _rows(workspace)
    workspace.close()

    handler = _MODULE + _SUSPEND_BODY
    assert _identities(rows) == [
        ("GET", "/", handler, "resolved"),
        ("GET", "/x", handler, "resolved"),
    ]


def test_a_route_prefix_carrying_a_verb_sets_both_the_path_and_the_verb(tmp_path: Path):
    """`ktor-route-with-verb`: the four-argument `route("/v", HttpMethod.Put) { put("/x") {
    }; get("/never") { } }` (CP-24 row 1a) is a prefix that sets the path AND the verb —
    `path_arg: 1, verb_arg: 2` on one rule — so `put("/x")` is `PUT /v/x`, and the
    disagreeing `get` is the same silence as under `method`. Before the rule this arity
    was one unresolved row (spec §7 case 1's G-13 guard) and every route inside it lost."""
    facts = _selector_tree(
        (
            "route",
            [CallArgument(kind="string", value="/v"), _by_source(9)],
            [("put", "/x"), ("get", "/never")],
        ),
    )
    facts.append(_getter(0, _HTTP_METHOD_COMPANION, "getPut", result=9))
    workspace = _resolve(tmp_path, facts, _shipped_ktor_catalog())
    rows = _rows(workspace)
    workspace.close()

    assert _identities(rows) == [("PUT", "/v/x", _MODULE + _SUSPEND_BODY, "resolved")]


def test_an_unknown_verb_getter_poisons_the_method_alone(tmp_path: Path):
    """A verb read through a getter the `verb_values.getters` table does not name —
    `method(Constants.weird) { get("/x") { } }` — poisons `method` and nothing else: the
    verb WAS written and is unreadable, so the row is unresolved with its path intact,
    exactly as an undeclared enum member reads. Not a phantom — a route is declared at
    `/x` — and not `GET`: with the selector's verb unknown, whether the inner `get` agrees
    with it is unknown too, and picking either would be a guess presented as fact."""
    facts = _selector_tree(("method", [_by_source(9)], [("get", "/x")]))
    facts.append(_getter(0, _UNKNOWN_GETTERS, "getWeird", result=9))
    workspace = _resolve(tmp_path, facts, _shipped_ktor_catalog())
    rows = _rows(workspace)
    workspace.close()

    assert _identities(rows) == [(None, "/x", _MODULE + _SUSPEND_BODY, "unresolved")]


_HTTP_METHOD = "io/ktor/http/HttpMethod#"


@pytest.mark.pins("ktor.a-VERB-read-from-a-static-field")
def test_a_ktor3_method_block_reads_its_verb_from_the_static_field(tmp_path: Path):
    """Spec 2026-10-26 §2d/§3a. Ktor 3.6.0 compiles `HttpMethod.Get` to a `getstatic` of a
    static field, so the selector is handed a `field`-kind argument carrying the field's
    symbol and no getter call at all (CP-54 row (a) rows 1-2). Before `verb_values.fields`
    the verb read as nothing, `method` was poisoned and the route inside was one
    unresolved row; now the scope is `GET` and `post` disagreeing with it is silence, as
    on 3.0.3. The four-argument `route(path, HttpMethod.Put)` reads the field the same
    way."""
    facts = _selector_tree(
        (
            "method",
            [CallArgument(kind="field", symbol=_HTTP_METHOD + "Get.")],
            [("get", "/x"), ("post", "/never")],
        ),
        (
            "route",
            [
                CallArgument(kind="string", value="/v"),
                CallArgument(kind="field", symbol=_HTTP_METHOD + "Put."),
            ],
            [("put", "/y")],
        ),
    )
    workspace = _resolve(tmp_path, facts, _shipped_ktor_catalog())
    rows = _rows(workspace)
    workspace.close()

    handler = _MODULE + _SUSPEND_BODY
    assert _identities(rows) == [
        ("GET", "/x", handler, "resolved"),
        ("PUT", "/v/y", handler, "resolved"),
    ]


def test_the_ktor303_getter_form_still_reads(tmp_path: Path):
    """The same `method(HttpMethod.Get) { get("/x") }` on Ktor 3.0.3 — the Companion getter
    — reads `GET` exactly as before the field form was added: the two forms sit beside each
    other in `verb_values`, neither replacing the other."""
    facts = _selector_tree(("method", [_by_source(9)], [("get", "/x")]))
    facts.append(_getter(0, _HTTP_METHOD_COMPANION, "getGet", result=9))
    workspace = _resolve(tmp_path, facts, _shipped_ktor_catalog())
    rows = _rows(workspace)
    workspace.close()

    assert _identities(rows) == [("GET", "/x", _MODULE + _SUSPEND_BODY, "resolved")]


def test_an_undeclared_field_is_no_verb(tmp_path: Path):
    """A static field the table does not name — `method(Constants.WEIRD)`, or a field of
    `HttpMethod` that is not a verb word — is no verb: `method` is poisoned, the row is
    unresolved with its path intact, exactly as an undeclared getter reads. The field
    form reads one declared member at a time and never a name guessed to be its value."""
    facts = _selector_tree(
        (
            "method",
            [CallArgument(kind="field", symbol=_UNKNOWN_GETTERS + "WEIRD.")],
            [("get", "/x")],
        ),
        (
            "method",
            [CallArgument(kind="field", symbol=_HTTP_METHOD + "DefaultMethods.")],
            [("get", "/y")],
        ),
    )
    workspace = _resolve(tmp_path, facts, _shipped_ktor_catalog())
    rows = _rows(workspace)
    workspace.close()

    handler = _MODULE + _SUSPEND_BODY
    assert _identities(rows) == [
        (None, "/x", handler, "unresolved"),
        (None, "/y", handler, "unresolved"),
    ]


def test_a_verb_fields_table_of_the_wrong_shape_is_refused(tmp_path: Path):
    """`verb_values.fields` is validated at load as `getters` is: a key without its `#` (no
    field named), or a `verb_values` block holding a key besides `getters` and `fields`,
    is a broken file, not a degraded run."""
    for broken in (
        {"fields": {"io.ktor.http.HttpMethod.Get": "GET"}},
        {"fields": ["io.ktor.http.HttpMethod#Get"]},
        {"owner": "io.ktor.http.HttpMethod"},
    ):
        matches = copy.deepcopy(_matches())
        matches["vocabulary"]["verb_values"] = broken  # type: ignore[index]
        with pytest.raises(CatalogError, match="verb_values"):
            _resolve(tmp_path, [], _catalog(matches))


def test_media_selectors_read_their_getter_valued_constants_and_an_unknown_one_reads_nothing(
    tmp_path: Path,
):
    """`accept(ContentType.Application.Json) { get("/j") { } }` fills `produces` and
    `contentType(ContentType.Application.Json) { post("/c") { } }` fills `consumes`
    (`media_arg` + `fills`). `ContentType.Application.Json` is `ContentType$Application.
    getJson()`, a getter on the nested object (CP-24 row 4), read through
    `media_values.getters`; `accept` is a VARARG, so its constant arrives inside one
    `array` slot whose element carries the getter's `source` (the fixture's compiled
    shape), and the existing vararg reader walks it. A getter the table does not name —
    `accept(Constants.weird) { get("/w") { } }` — contributes nothing: `produces` NULL and
    the row RESOLVED, the media rule's own honesty (the verb and path are the identity,
    both known)."""
    facts = _selector_tree(
        ("accept", [CallArgument(kind="array", elements=[_by_source(9)])], [("get", "/j")]),
        ("contentType", [_by_source(19)], [("post", "/c")]),
        ("accept", [CallArgument(kind="array", elements=[_by_source(29)])], [("get", "/w")]),
    )
    facts.append(_getter(0, _CONTENT_TYPE_APPLICATION, "getJson", result=9))
    facts.append(_getter(1, _CONTENT_TYPE_APPLICATION, "getJson", result=19))
    facts.append(_getter(2, _UNKNOWN_GETTERS, "getWeird", result=29))
    workspace = _resolve(tmp_path, facts, _shipped_ktor_catalog())
    rows = _rows(workspace)
    workspace.close()

    handler = _MODULE + _SUSPEND_BODY
    assert [
        (row["method"], row["path"], row["resolution"], row["consumes"], row["produces"])
        for row in rows
    ] == [
        ("GET", "/j", "resolved", None, json.dumps([JSON])),
        ("GET", "/w", "resolved", None, None),
        ("POST", "/c", "resolved", json.dumps([JSON]), None),
    ]
    assert {row["handler"] for row in rows} == {handler}


def test_requirement_selectors_are_scopes_whose_routes_derive_beneath_them(tmp_path: Path):
    """`header("X-Api-Version", "2") { get("/orders") { } }`, `param("debug") { … }`,
    `param("mode", "fast") { … }` and `optionalParam("page") { … }` set no path, no verb
    and no media — each is a pure scope carrying a requirement — so the route beneath
    each derives as written, resolved. Before the rules every one of these blocks derived
    NOTHING and the routes inside them were lost (the `ktor-selector-blocks` gap). What
    each block demands of the request is the route's `requirements`, written to the
    stash and asserted where it is joined to its row (`_from_stash`)."""
    facts = _selector_tree(
        ("header", [_literal("X-Api-Version"), _literal("2")], [("get", "/orders")]),
        ("param", [_literal("debug")], [("get", "/dbg")]),
        ("param2", [_literal("mode"), _literal("fast")], [("get", "/fast")]),
        ("optionalParam", [_literal("page")], [("get", "/paged")]),
    )
    workspace = _resolve(tmp_path, facts, _shipped_ktor_catalog())
    rows = _rows(workspace)
    workspace.close()

    handler = _MODULE + _SUSPEND_BODY
    assert _identities(rows) == [
        ("GET", "/dbg", handler, "resolved"),
        ("GET", "/fast", handler, "resolved"),
        ("GET", "/orders", handler, "resolved"),
        ("GET", "/paged", handler, "resolved"),
    ]


def test_selector_words_of_the_wrong_shape_are_refused(tmp_path: Path):
    """Each new prefix word is validated at load: `media_arg` without `fills` (or on an
    entry — a verb may carry it since spec 2026-09-21 §7a, a linking entry never), a
    `request_requirement` whose `kind` is not one of the four, or whose
    `name_arg` lies outside the arity, a `verb_values` block holding anything but
    `getters`, and a getter key without its `#` — every one a broken file, not a degraded
    run."""
    base = {"owner": "com.example.web.RouterDsl", "method": "path", "arity": 3, "body_arg": 2}
    for broken in (
        {**base, "media_arg": 1},
        {**base, "media_arg": 1, "fills": "accepts"},
        {**base, "request_requirement": {"kind": "form", "name_arg": 1, "requirement": "required"}},
        {
            **base,
            "request_requirement": {"kind": "query", "name_arg": 3, "requirement": "required"},
        },
        {**base, "request_requirement": {"kind": "query", "name_arg": 1, "requirement": "maybe"}},
    ):
        matches = copy.deepcopy(_matches())
        matches["vocabulary"]["prefixes"] = [broken]  # type: ignore[index]
        with pytest.raises(CatalogError):
            _resolve(tmp_path, [], _catalog(matches))
    matches = copy.deepcopy(_matches())
    matches["entries"][1]["media_arg"] = 0  # type: ignore[index]
    matches["entries"][1]["fills"] = "produces"  # type: ignore[index]
    with pytest.raises(CatalogError, match="media_arg"):
        _resolve(tmp_path, [], _catalog(matches))
    matches = copy.deepcopy(_matches())
    matches["vocabulary"]["verb_values"] = {"owner": "com.example.Verbs"}  # type: ignore[index]
    with pytest.raises(CatalogError, match="verb_values"):
        _resolve(tmp_path, [], _catalog(matches))
    matches = copy.deepcopy(_matches())
    matches["vocabulary"]["media_values"]["getters"] = {"com.example.Media.getJson": JSON}  # type: ignore[index]
    with pytest.raises(CatalogError, match="getters"):
        _resolve(tmp_path, [], _catalog(matches))


# --- the verb-less terminal and `all_methods` (spec 2026-09-19 §4c) --------------------

_KTOR_ROUTE_TYPE = "io/ktor/server/routing/Route#"
_HANDLE_DESC = "(Lkotlin/jvm/functions/Function2;)V"


def _handle_in(body: str, ordinal: int) -> CallSiteFact:
    """`handle { }` inside a block: `invokeinterface Route.handle` on the block's own
    parameter — `receiver_parameter: 0`, no `receiver` id, no result (the fixture's
    compiled shape, read 2026-09-20; CP-24 row 1b)."""
    return _site(
        body,
        ordinal,
        _KTOR_ROUTE_TYPE,
        "handle",
        receiver_parameter=0,
        invoke_kind="interface",
        descriptor=_HANDLE_DESC,
        arguments=[CallArgument(kind="instance", symbol=_SUSPEND_HANDLER, source=ordinal + 50)],
    )


def _handle_under(*blocks: tuple[str, list[CallArgument]]) -> list:
    """`routing { <selector>(…) { handle { } } … }` — one `handle` per block."""
    facts = _routing_entry()
    for index, (name, between) in enumerate(blocks):
        body = _selector_body(index)
        facts.append(_method_symbol(body))
        descriptor = _ROUTE_DESC if name == "route3" else _SELECTOR_DESCS[name]
        facts.append(
            _selector(
                10 + index,
                "route" if name == "route3" else name,
                between,
                body=body,
                descriptor=descriptor,
            )
        )
        facts.append(_handle_in(body, 0))
    return facts


def test_a_verb_less_terminal_takes_the_scopes_verb_or_expands_through_all_methods(
    tmp_path: Path,
):
    """Spec 2026-09-19 §4c on the shipped catalog. `handle { }` is a MEMBER of the `Route`
    interface (CP-24 row 1b) declared as a terminal with no `verb`: under `method(Get)`
    it takes the scope's verb — `GET /`, the routing root itself, since `handle`
    registers on the receiver node and `path: ""` at the root canonicalises to `/`;
    under `route("/legacy2", HttpMethod.Put)` it is `PUT /legacy2`; under a bare
    `route("/health2")` no verb is in scope, the route is RESOLVED with no verb, and it
    fans out through `all_methods` — `HttpMethod.DefaultMethods`' seven members (CP-24 row
    2), one row each, never `/health2/**` and never a NULL verb. Three blocks, nine rows."""
    facts = _handle_under(
        ("method", [_by_source(9)]),
        ("route3", [CallArgument(kind="string", value="/health2")]),
        ("route", [CallArgument(kind="string", value="/legacy2"), _by_source(19)]),
    )
    facts.append(_getter(0, _HTTP_METHOD_COMPANION, "getGet", result=9))
    facts.append(_getter(1, _HTTP_METHOD_COMPANION, "getPut", result=19))
    workspace = _resolve(tmp_path, facts, _shipped_ktor_catalog())
    rows = _rows(workspace)
    workspace.close()

    handler = _MODULE + _SUSPEND_BODY
    assert _identities(rows) == [
        ("DELETE", "/health2", handler, "resolved"),
        ("GET", "/", handler, "resolved"),
        ("GET", "/health2", handler, "resolved"),
        ("HEAD", "/health2", handler, "resolved"),
        ("OPTIONS", "/health2", handler, "resolved"),
        ("PATCH", "/health2", handler, "resolved"),
        ("POST", "/health2", handler, "resolved"),
        ("PUT", "/health2", handler, "resolved"),
        ("PUT", "/legacy2", handler, "resolved"),
    ]


def test_a_poisoned_verb_is_not_fanned_out(tmp_path: Path):
    """`method(Constants.weird) { handle { } }`: the selector's verb was written and could
    not be read, so the route is unresolved with `method` NULL — ONE row, not seven. The
    fan-out is for a route that read no verb at all, never for one whose verb read
    failed; seven resolved rows there would present the poison as seven facts."""
    facts = _handle_under(("method", [_by_source(9)]))
    facts.append(_getter(0, _UNKNOWN_GETTERS, "getWeird", result=9))
    workspace = _resolve(tmp_path, facts, _shipped_ktor_catalog())
    rows = _rows(workspace)
    workspace.close()

    assert _identities(rows) == [(None, "/", _MODULE + _SUSPEND_BODY, "unresolved")]


def test_a_catalog_without_all_methods_keeps_a_verb_less_route_null_and_resolved(
    tmp_path: Path,
):
    """The precedent that must not move: the builder's `route(predicate, handler)` —
    `verb: null` on the shipped reactive router catalog — with a media-only predicate
    is ONE row, `method` NULL, resolved, at `/**`. That catalog declares no
    `all_methods`, and a verb-less route there means exactly what it always has: the
    predicate supplied no verb. `route().route(accept(JSON), h).build()`, descriptors
    the jar's own."""
    facts: list = [
        _method_symbol(LIST_ORDERS),
        _site(
            ROUTES,
            0,
            _ROUTER_FUNCTIONS,
            "route",
            result=200,
            arguments=[],
            descriptor="()Lorg/springframework/web/reactive/function/server/RouterFunctions$Builder;",
        ),
        _site(
            ROUTES,
            1,
            _REQUEST_PREDICATES,
            "accept",
            result=150,
            arguments=[CallArgument(kind="array", elements=[_enum_member("APPLICATION_JSON")])],
            descriptor=(
                "([Lorg/springframework/http/MediaType;)"
                "Lorg/springframework/web/reactive/function/server/RequestPredicate;"
            ),
        ),
        _site(
            ROUTES,
            2,
            _BUILDER,
            "route",
            receiver=200,
            result=201,
            invoke_kind="interface",
            descriptor=(
                "(Lorg/springframework/web/reactive/function/server/RequestPredicate;"
                "Lorg/springframework/web/reactive/function/server/HandlerFunction;)"
                "Lorg/springframework/web/reactive/function/server/RouterFunctions$Builder;"
            ),
            arguments=[
                CallArgument(kind="unresolved", source=150),
                CallArgument(kind="lambda", symbol=LIST_ORDERS),
            ],
        ),
        _site(
            ROUTES,
            3,
            _BUILDER,
            "build",
            receiver=201,
            result=202,
            arguments=[],
            descriptor="()Lorg/springframework/web/reactive/function/server/RouterFunction;",
        ),
    ]
    workspace = _resolve(tmp_path, facts, _shipped_router_catalog())
    rows = _rows(workspace)
    workspace.close()

    assert _identities(rows) == [(None, "/**", _MODULE + LIST_ORDERS, "resolved")]
    assert [row["produces"] for row in rows] == [json.dumps([JSON])]


def _enum_member(name: str) -> CallArgument:
    return CallArgument(kind="enum", symbol=f"org/springframework/http/MediaType#{name}.")


def test_all_methods_and_a_verb_less_non_terminal_are_validated(tmp_path: Path):
    """`all_methods` is a non-empty list of upper-case tokens — a lower-case one would
    publish a verb the framework never matches, an empty one would fan a route out to
    nothing. And a verb rule that is NOT a terminal must still answer for its verb
    (`verb`, null included, or `verb_arg`): only a terminal may leave it to the scope."""
    for broken in ([], ["get"], "GET", [7]):
        matches = copy.deepcopy(_matches())
        matches["all_methods"] = broken
        with pytest.raises(CatalogError, match="all_methods"):
            _resolve(tmp_path, [], _catalog(matches))
    matches = copy.deepcopy(_matches())
    del matches["vocabulary"]["verbs"][0]["verb"]  # type: ignore[index]
    with pytest.raises(CatalogError, match="neither `verb` nor `verb_arg`"):
        _resolve(tmp_path, [], _catalog(matches))


# --- `_Route.requirements` → the stash → `endpoint_metadata` (spec 2026-09-19 §4d, §5c) ---


def _stash(workspace: DuckDbWorkspace) -> list[tuple]:
    """The `route_requirements` rows the engine wrote, as `(method, path, handler, kind,
    name, value, requirement, resolution)`, in the query's own total order."""
    return [
        (
            row["method"],
            row["path"],
            row["handler"],
            row["kind"],
            row["name"],
            row["value"],
            row["requirement"],
            row["resolution"],
        )
        for row in workspace.query("route_requirements")
    ]


def _metadata(workspace: DuckDbWorkspace) -> list[tuple]:
    return [
        (
            row["method"],
            row["path"],
            row["caller"],
            row["kind"],
            row["name"],
            row["value"],
            row["requirement"],
            row["resolution"],
        )
        for row in workspace.query("endpoint_metadata")
    ]


def test_selector_requirements_reach_the_stash_and_the_stash_reaches_endpoint_metadata(
    tmp_path: Path,
):
    """The end-to-end of the stash on synthetic facts. `header("X-Api-Version", "2") {
    get("/orders") { } }`, `param("debug") { … }`, `param("mode", "fast") { … }` and
    `optionalParam("page") { … }` each put ONE requirement on the route beneath them,
    and `run` writes it to `route_requirements` under the SAME `caller`, `handler`,
    `method`, `path` and `catalog_id` the endpoint row was inserted with — post
    `_path_of`, post fan-out. Then the requirements pass, run as the pipeline runs it
    after the engines, joins the stash to its rows and writes `endpoint_metadata`:
    `caller` = the handler (§4d), `required` for the three the tree refuses a request
    without, `optional` for `optionalParam`, `value` the literal where one was given.
    A join that missed — a `method` or `path` spelled differently in the stash than in
    the row — would leave this table empty, which is what this test refuses."""
    facts = _selector_tree(
        ("header", [_literal("X-Api-Version"), _literal("2")], [("get", "/orders")]),
        ("param", [_literal("debug")], [("get", "/dbg")]),
        ("param2", [_literal("mode"), _literal("fast")], [("get", "/fast")]),
        ("optionalParam", [_literal("page")], [("get", "/paged")]),
    )
    catalog = _shipped_ktor_catalog()
    workspace = _resolve(tmp_path, facts, catalog)
    stash = _stash(workspace)
    workspace.derive("endpoint_metadata_reset")
    record_request_requirements(workspace, [catalog])
    metadata = _metadata(workspace)
    workspace.close()

    handler = _MODULE + _SUSPEND_BODY
    expected = [
        ("GET", "/dbg", handler, "query", "debug", None, "required", "resolved"),
        ("GET", "/fast", handler, "query", "mode", "fast", "required", "resolved"),
        ("GET", "/orders", handler, "header", "X-Api-Version", "2", "required", "resolved"),
        ("GET", "/paged", handler, "query", "page", None, "optional", "resolved"),
    ]
    assert stash == expected
    assert metadata == expected


def test_a_fanned_out_route_carries_its_requirements_to_every_row_and_collapsing_alternatives_intersect(
    tmp_path: Path,
):
    """Two shapes of one rule, and they differ. `param("debug") { route("/h") { handle { } } }`
    fans out through `all_methods`: ONE route seven times, and every one of the seven rows
    carries the `debug` requirement — the stash is per (row × requirement), keyed by the
    row's own verb. But two routes that COLLAPSE to one row — `header("A", "1") { get("/x")
    { } }` beside `header("B", "2") { get("/x") { } }`, one address, one handler — are two
    ALTERNATIVES for that address: a request carrying only `A=1` is served, so `B=2` is
    not a demand the tree makes at `/x`. The kept row keeps only what every alternative
    demands — here nothing (fix round 1, spec §4d): the stash holds no row for `/x`, and
    the two demands are a stated miss, never a union the framework does not enforce."""
    facts = _selector_tree(
        ("param", [_literal("debug")], []),
        ("header", [_literal("A"), _literal("1")], [("get", "/x")]),
        ("header", [_literal("B"), _literal("2")], [("get", "/x")]),
    )
    # `route("/h") { handle { } }` inside the `param` block (`_selector_body(0)`).
    inner = DECLARER + "orders$lambda$1$lambda$0$lambda$0(sig_i0)."
    facts.append(_method_symbol(inner))
    facts.append(
        _site(
            _selector_body(0),
            0,
            _ROUTING_BUILDER,
            "route",
            result=900,
            descriptor=_ROUTE_DESC,
            arguments=[
                CallArgument(kind="parameter", value=0),
                CallArgument(kind="string", value="/h"),
                CallArgument(kind="lambda", symbol=inner, source=899, captures=0),
            ],
        )
    )
    facts.append(_handle_in(inner, 0))
    workspace = _resolve(tmp_path, facts, _shipped_ktor_catalog())
    rows = _rows(workspace)
    stash = _stash(workspace)
    workspace.close()

    handler = _MODULE + _SUSPEND_BODY
    verbs = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")
    assert _identities(rows) == sorted(
        [*((verb, "/h", handler, "resolved") for verb in verbs), ("GET", "/x", handler, "resolved")]
    )
    assert sorted(stash, key=str) == sorted(
        [(verb, "/h", handler, "query", "debug", None, "required", "resolved") for verb in verbs],
        key=str,
    )


def test_collapsing_alternatives_keep_the_requirements_they_share(tmp_path: Path):
    """The positive half of the intersection: three `header` blocks over one `get("/x")`,
    every one also under `param("v", "2")` — `param("v", "2") { header("A", "1") { get } ;
    header("A", "1") { get } ; header("C", "3") { get } }`. The three alternatives collapse
    to one row; `v=2` is demanded by all of them and is kept, `A=1` by two of three and is
    dropped with `C=3`. The gateway's header-versioning idiom is this shape: two
    `route()`s on `/api/**` differing only in `header("X-Version", …)` publish `/api/**`
    demanding neither version, not both."""
    outer = _selector_body(0)
    facts = _selector_tree(("param2", [_literal("v"), _literal("2")], []))
    for index, (name, value) in enumerate((("A", "1"), ("A", "1"), ("C", "3"))):
        body = DECLARER + f"orders$lambda$1$lambda$0$lambda${index}(sig_h{index})."
        facts.append(_method_symbol(body))
        facts.append(
            _site(
                outer,
                index,
                _ROUTING_BUILDER,
                "header",
                result=700 + index,
                descriptor=_SELECTOR_DESCS["header"],
                arguments=[
                    CallArgument(kind="parameter", value=0),
                    _literal(name),
                    _literal(value),
                    CallArgument(kind="lambda", symbol=body, source=600 + index, captures=0),
                ],
            )
        )
        facts.append(_verb_in(body, 0, "get", "/x"))
    workspace = _resolve(tmp_path, facts, _shipped_ktor_catalog())
    rows = _rows(workspace)
    stash = _stash(workspace)
    workspace.close()

    handler = _MODULE + _SUSPEND_BODY
    assert _identities(rows) == [("GET", "/x", handler, "resolved")]
    assert stash == [("GET", "/x", handler, "query", "v", "2", "required", "resolved")]


def test_a_requirement_whose_name_is_not_a_literal_is_recorded_unresolved(tmp_path: Path):
    """`header(name, "2") { get("/x") { } }` with `name` a variable: the requirement EXISTS
    — the tree demands a header — and its name could not be read, so the stash row
    carries `name` NULL and `resolution: unresolved` (§5a: "demands a header it does not
    name" is a different statement from "demands none"). The route itself is untouched:
    resolved, `GET /x`."""
    facts = _selector_tree(
        ("header", [CallArgument(kind="unresolved"), _literal("2")], [("get", "/x")]),
    )
    workspace = _resolve(tmp_path, facts, _shipped_ktor_catalog())
    rows = _rows(workspace)
    stash = _stash(workspace)
    workspace.close()

    handler = _MODULE + _SUSPEND_BODY
    assert _identities(rows) == [("GET", "/x", handler, "resolved")]
    assert stash == [("GET", "/x", handler, "header", None, "2", "required", "unresolved")]


def _gateway_requirement_matches() -> dict[str, object]:
    """The invented gateway with `header`/`query`/`cookie` as REQUIREMENT continuations —
    pass-throughs that also state what the route demands (spec §5c)."""
    matches = copy.deepcopy(_gateway_matches())
    continuations: list = matches["continuations"]  # type: ignore[assignment]
    for name, kind in (("header", "header"), ("query", "query"), ("cookie", "cookie")):
        continuations.append(
            {
                "name": name,
                "owner": "com.example.gw.BooleanSpec",
                "pass_through": True,
                "request_requirement": {
                    "kind": kind,
                    "name_arg": 0,
                    "value_arg": 1,
                    "requirement": "required",
                },
            }
        )
    return matches


def test_requirement_continuations_carry_their_demand_onto_every_branch_of_the_chain(
    tmp_path: Path,
):
    """`path("/a").or().path("/b").and().header("X-Api", "v2").and().query("debug").and().
    cookie("session", ".*").uri(x)`: the three requirement pass-throughs contribute no
    path and no verb — the chain still folds to `/a` and `/b` — and each puts its demand
    on BOTH branches (an `and()` binds to everything to its left). `header(String,
    String)` and `cookie(String, String)` carry the regex as their value; `query(String)`
    — the one-argument overload of a name one continuation rule covers — has no value to
    read and stays resolved with `value` NULL. Handler-less routes stash `handler` NULL,
    which is the identity the gateway's rows carry."""
    chain = [
        (SPEC, "path", [CallArgument(kind="string", value="/a")]),
        (BOOL, "or", []),
        (SPEC, "path", [CallArgument(kind="string", value="/b")]),
        (BOOL, "and", []),
        (BOOL, "header", [_literal("X-Api"), _literal("v2")]),
        (BOOL, "and", []),
        (BOOL, "query", [_literal("debug")]),
        (BOOL, "and", []),
        (BOOL, "cookie", [_literal("session"), _literal(".*")]),
        _uri(),
    ]
    workspace = _resolve(tmp_path, _gateway_body(chain), _catalog(_gateway_requirement_matches()))
    rows = _rows(workspace)
    stash = _stash(workspace)
    workspace.close()

    assert _identities(rows) == [(None, "/a", None, "resolved"), (None, "/b", None, "resolved")]
    assert stash == [
        (None, path, None, kind, name, value, "required", "resolved")
        for path in ("/a", "/b")
        for kind, name, value in (
            ("cookie", "session", ".*"),
            ("header", "X-Api", "v2"),
            ("query", "debug", None),
        )
    ]


def test_a_requirement_whose_value_is_a_predicate_is_name_only_and_an_or_onto_one_is_a_branch(
    tmp_path: Path,
):
    """Two edges of the chain fold. `query("debug", p)` — the `Predicate` overload — carries a
    second argument that is not a literal: the demand is recorded by its NAME, `value`
    NULL, and the row is RESOLVED — "debug required, value unread", the same statement the
    router's `queryParam(name, predicate)` makes (fix round 1). And `path("/a").or().
    header("X")`: the alternative an `or()` opened IS the requirement pass-through, so it
    is a branch of its own — every path, header `X` required — beside `/a`, which demands
    nothing."""
    chain = [
        (SPEC, "path", [CallArgument(kind="string", value="/a")]),
        (BOOL, "or", []),
        (BOOL, "header", [_literal("X")]),
        (BOOL, "and", []),
        (BOOL, "query", [_literal("debug"), CallArgument(kind="lambda", symbol=HEALTH)]),
        _uri(),
    ]
    workspace = _resolve(tmp_path, _gateway_body(chain), _catalog(_gateway_requirement_matches()))
    rows = _rows(workspace)
    stash = _stash(workspace)
    workspace.close()

    assert _identities(rows) == [(None, "/**", None, "resolved"), (None, "/a", None, "resolved")]
    assert stash == [
        (None, "/**", None, "header", "X", None, "required", "resolved"),
        (None, "/**", None, "query", "debug", None, "required", "resolved"),
        (None, "/a", None, "query", "debug", None, "required", "resolved"),
    ]


def _query_param(ordinal: int, *, result: int, value: CallArgument) -> CallSiteFact:
    """`RequestPredicates.queryParam(String, String | Predicate)` — the two overloads share a
    name and an arity and differ at position 1's type (spring-webflux 6.1.6, CP-26 row 1)."""
    typed = "Ljava/lang/String;" if value.kind == "string" else "Ljava/util/function/Predicate;"
    return _site(
        ROUTES,
        ordinal,
        _REQUEST_PREDICATES,
        "queryParam",
        result=result,
        descriptor=(
            f"(Ljava/lang/String;{typed})"
            "Lorg/springframework/web/reactive/function/server/RequestPredicate;"
        ),
        arguments=[_literal("v"), value],
    )


def test_query_param_predicates_fold_their_requirement_through_and_on_the_shipped_router(
    tmp_path: Path,
):
    """Spec §5c on the shipped reactive router catalog. `RouterFunctions.route(GET("/orders").
    and(queryParam("v", "2")), h)` is `GET /orders` — the `queryParam` constrains no path
    and no verb — with ONE stashed requirement: `query v = 2, required`. The `Predicate`
    overload, `GET("/x").and(queryParam("v", p))`, is told apart by `arg_types` and has
    no `value_arg`: `v` required, value NULL, resolved. Both rules ride the `and`
    composer exactly as a media predicate does."""
    facts: list = [
        _method_symbol(LIST_ORDERS),
        _method_symbol(HEALTH),
        *_java_route(0, "GET", "/orders", LIST_ORDERS)[:1],
        _query_param(2, result=300, value=_literal("2")),
        _site(
            ROUTES,
            3,
            "org/springframework/web/reactive/function/server/RequestPredicate#",
            "and",
            receiver=100,
            result=301,
            invoke_kind="interface",
            arguments=[CallArgument(kind="unresolved", source=300)],
        ),
        _site(
            ROUTES,
            4,
            _ROUTER_FUNCTIONS,
            "route",
            result=302,
            arguments=[
                CallArgument(kind="unresolved", source=301),
                CallArgument(kind="lambda", symbol=LIST_ORDERS),
            ],
        ),
        *_java_route(5, "GET", "/x", HEALTH)[:1],
        _query_param(12, result=400, value=CallArgument(kind="lambda", symbol=HEALTH)),
        _site(
            ROUTES,
            13,
            "org/springframework/web/reactive/function/server/RequestPredicate#",
            "and",
            receiver=150,
            result=401,
            invoke_kind="interface",
            arguments=[CallArgument(kind="unresolved", source=400)],
        ),
        _site(
            ROUTES,
            14,
            _ROUTER_FUNCTIONS,
            "route",
            result=402,
            arguments=[
                CallArgument(kind="unresolved", source=401),
                CallArgument(kind="lambda", symbol=HEALTH),
            ],
        ),
    ]
    workspace = _resolve(tmp_path, facts, _shipped_router_catalog())
    rows = _rows(workspace)
    stash = _stash(workspace)
    workspace.close()

    assert _identities(rows) == [
        ("GET", "/orders", _MODULE + LIST_ORDERS, "resolved"),
        ("GET", "/x", _MODULE + HEALTH, "resolved"),
    ]
    # The stash query orders on `handler` first: `health` before `listOrders`.
    assert stash == [
        ("GET", "/x", _MODULE + HEALTH, "query", "v", None, "required", "resolved"),
        ("GET", "/orders", _MODULE + LIST_ORDERS, "query", "v", "2", "required", "resolved"),
    ]


def test_the_servlet_twin_reads_param_as_kind_param(tmp_path: Path):
    """CP-26 rows 2 and 2b: the servlet `RequestPredicates` has NO `queryParam` — its
    predicate is `param(String, String)`, and `ServerRequest.param` reads the servlet
    parameter map, query string and form body alike — so `spring-mvc-router.yml` declares
    `param` with `kind: param`, the §5a kind for the one API that cannot tell the two
    apart. `route(GET("/x").and(param("v", "2")), h)` on servlet owners: `GET /x`, one
    requirement, kind `param`. A catalog copied from the reactive twin would match
    nothing here, silently."""
    facts: list = [
        _method_symbol(HEALTH),
        *_mvc_java_route(0, "GET", "/x", HEALTH)[:1],
        _site(
            ROUTES,
            2,
            _MVC_REQUEST_PREDICATES,
            "param",
            result=300,
            descriptor=(
                "(Ljava/lang/String;Ljava/lang/String;)"
                "Lorg/springframework/web/servlet/function/RequestPredicate;"
            ),
            arguments=[_literal("v"), _literal("2")],
        ),
        _site(
            ROUTES,
            3,
            "org/springframework/web/servlet/function/RequestPredicate#",
            "and",
            receiver=100,
            result=301,
            invoke_kind="interface",
            arguments=[CallArgument(kind="unresolved", source=300)],
        ),
        _site(
            ROUTES,
            4,
            _MVC_ROUTER_FUNCTIONS,
            "route",
            result=302,
            arguments=[
                CallArgument(kind="unresolved", source=301),
                CallArgument(kind="lambda", symbol=HEALTH),
            ],
        ),
    ]
    workspace = _resolve(tmp_path, facts, _shipped_mvc_router_catalog())
    rows = _rows(workspace)
    stash = _stash(workspace)
    workspace.close()

    assert _identities(rows) == [("GET", "/x", _MODULE + HEALTH, "resolved")]
    assert stash == [("GET", "/x", _MODULE + HEALTH, "param", "v", "2", "required", "resolved")]


def test_requirement_words_of_the_wrong_shape_are_refused(tmp_path: Path):
    """`request_requirement` on a continuation that is not a `pass_through` is two readings of
    one call (it would read an argument a plain continuation treats as a handler slot); a
    vocabulary `request_requirement` rule missing its owner, or naming a kind outside the
    four, is a broken file; and two such rules that could both accept one call are refused
    as two verbs would be (spec §3c)."""
    matches = copy.deepcopy(_gateway_matches())
    matches["continuations"].append(  # type: ignore[attr-defined]
        {
            "name": "header",
            "owner": "com.example.gw.BooleanSpec",
            "request_requirement": {"kind": "header", "name_arg": 0, "requirement": "required"},
        }
    )
    with pytest.raises(CatalogError, match="request_requirement"):
        _resolve(tmp_path, [], _catalog(matches))
    rule = {
        "owner": "com.example.web.Predicates",
        "method": "queryParam",
        "arity": 2,
        "kind": "query",
        "name_arg": 0,
        "requirement": "required",
    }
    for broken in (
        [{**rule, "kind": "form"}],
        [{k: v for k, v in rule.items() if k != "owner"}],
        [rule, {**rule, "value_arg": 1}],
    ):
        matches = copy.deepcopy(_matches())
        matches["vocabulary"]["request_requirement"] = broken  # type: ignore[index]
        with pytest.raises(CatalogError):
            _resolve(tmp_path, [], _catalog(matches))


# --- WebSocket and SSE routes in the routing tree (spec 2026-10-26 §3b, §3g item 5) ------

_WEBSOCKET_ROUTING = "io/ktor/server/websocket/RoutingKt#"
_SSE_ROUTING = "io/ktor/server/sse/RoutingKt#"
_JVM_STRING = "Ljava/lang/String;"
_JVM_FN2 = "Lkotlin/jvm/functions/Function2;"
# The `serialize` lambda of the SSE overloads that take one — a plain `Function2`, linked
# as a `lambda` (CP-54 row 18); never the handler.
_SERIALIZE = DECLARER + "orders$lambda$9(sig_z0)."


def _session(
    owner: str, name: str, between: list[tuple[str, CallArgument]], *, mask: int | None = None
) -> tuple[str, str, list[tuple[str, CallArgument]], int | None]:
    """One WebSocket or SSE route call as it is written inside a block: its owner and JVM
    name, the `(type, argument)` pairs between the receiver and the handler, and — for a
    `$default` bridge — the mask the compiler passes (CP-54 rows 19-27)."""
    return (owner, name, between, mask)


def _session_call(
    body: str,
    ordinal: int,
    call: tuple[str, str, list[tuple[str, CallArgument]], int | None],
) -> CallSiteFact:
    """`invokestatic <owner>.<name>(this, …, handler[, mask, null])` on the block's own
    parameter, the handler a `SuspendLambda` instance, the descriptor composed from the
    declared types — a `$default` bridge adds the `int` mask and the `Object` marker the
    Kotlin compiler always appends (CP-54 rows 19, 21, 23, 27)."""
    owner, name, between, mask = call
    types = "".join(jvm_type for jvm_type, _ in between) + _JVM_FN2
    arguments = [
        CallArgument(kind="parameter", value=0),
        *(argument for _, argument in between),
        CallArgument(kind="instance", symbol=_SUSPEND_HANDLER, source=ordinal + 50),
    ]
    if mask is not None:
        types += "ILjava/lang/Object;"
        arguments += [CallArgument(kind="int", value=mask), CallArgument(kind="null")]
    return _site(
        body,
        ordinal,
        owner,
        name,
        result=ordinal + 100,
        descriptor=f"({_ROUTE}{types}){_ROUTE}",
        arguments=arguments,
    )


def _sessions_under(*blocks: tuple[str, list[CallArgument], list]) -> list:
    """`routing { <selector>(…) { <session calls> } … }` — `route3` is the plain
    `route(path) { }`, every other name a `_SELECTOR_DESCS` selector."""
    facts = _routing_entry()
    for index, (name, between, calls) in enumerate(blocks):
        body = _selector_body(index)
        facts.append(_method_symbol(body))
        descriptor = _ROUTE_DESC if name == "route3" else _SELECTOR_DESCS[name]
        facts.append(
            _selector(
                10 + index,
                "route" if name == "route3" else name,
                between,
                body=body,
                descriptor=descriptor,
            )
        )
        facts.extend(_session_call(body, ordinal, call) for ordinal, call in enumerate(calls))
    return facts


def _protocol_identities(rows: list[dict]) -> list[tuple]:
    """`_identities` with the row's protocol in front: these rows differ from the catalog's
    own `http` rows in exactly that column."""
    return [
        (row["protocol"], row["method"], row["path"], row["handler"], row["resolution"])
        for row in rows
    ]


def _web_socket_default(path: str) -> tuple:
    """`webSocket("/x") { }` — `webSocket$default` with mask 2, the protocol left to its
    default (CP-54 rows 19, 27)."""
    return _session(
        _WEBSOCKET_ROUTING,
        "webSocket$default",
        [(_JVM_STRING, _literal(path)), (_JVM_STRING, CallArgument(kind="null"))],
        mask=2,
    )


@pytest.mark.pins("ktor.a-WEBSOCKET-route-is-a-verbless-inbound-row")
def test_a_ktor_websocket_route_nests_under_its_prefix(tmp_path: Path):
    """Spec 2026-10-26 §3b. `routing { route("/api") { webSocket("/chat") { } } }` is ONE
    inbound `websocket` row at `/api/chat`, `method` NULL, resolved: the WebSocket verb
    nests through the same `route` prefix every HTTP verb does, and its row carries the
    rule's own protocol instead of the catalog's `http`. No verb is in scope under the
    bare `route`, and the route is still one row — a verbless rule is never expanded
    through `all_methods`, which would be seven HTTP-verbed WebSocket rows. The direct
    four-argument `webSocket(path, protocol)` and `webSocketRaw(path)` read the same way
    (CP-54 rows 16, 17, 20, 23)."""
    facts = _sessions_under(
        (
            "route3",
            [_literal("/api")],
            [
                _web_socket_default("/chat"),
                _session(
                    _WEBSOCKET_ROUTING,
                    "webSocket",
                    [(_JVM_STRING, _literal("/proto")), (_JVM_STRING, _literal("chat"))],
                ),
                _session(
                    _WEBSOCKET_ROUTING,
                    "webSocketRaw$default",
                    [(_JVM_STRING, _literal("/raw")), (_JVM_STRING, CallArgument(kind="null"))],
                    mask=2,
                ),
            ],
        ),
    )
    workspace = _resolve(tmp_path, facts, _shipped_ktor_catalog())
    rows = _rows(workspace)
    workspace.close()

    handler = _MODULE + _SUSPEND_BODY
    assert _protocol_identities(rows) == [
        ("websocket", None, "/api/chat", handler, "resolved"),
        ("websocket", None, "/api/proto", handler, "resolved"),
        ("websocket", None, "/api/raw", handler, "resolved"),
    ]
    assert {row["direction"] for row in rows} == {"inbound"}


@pytest.mark.pins("ktor.an-SSE-route-is-a-get-sse-row")
def test_a_ktor_sse_route_is_a_get_sse_row(tmp_path: Path):
    """Spec 2026-10-26 §3b, §3g item 5. `routing { route("/api") { sse("/events") { } } }`
    is one inbound `sse` row, `GET /api/events`: `sse(path, handler)` is
    `route(path, HttpMethod.Get) { … }` (read off the 3.6.0 jar), so the row carries GET as
    the JAX-RS SSE rows do. The serializer overload with a path, `sse(path, serialize,
    handler)`, is the same route; its handler is argument 3, never the serializer at 2
    (CP-54 rows 18, 25, 27)."""
    facts = _sessions_under(
        (
            "route3",
            [_literal("/api")],
            [
                _session(_SSE_ROUTING, "sse", [(_JVM_STRING, _literal("/events"))]),
                _session(
                    _SSE_ROUTING,
                    "sse",
                    [
                        (_JVM_STRING, _literal("/typed")),
                        (_JVM_FN2, CallArgument(kind="lambda", symbol=_SERIALIZE, captures=0)),
                    ],
                ),
            ],
        ),
    )
    workspace = _resolve(tmp_path, facts, _shipped_ktor_catalog())
    rows = _rows(workspace)
    workspace.close()

    handler = _MODULE + _SUSPEND_BODY
    assert _protocol_identities(rows) == [
        ("sse", "GET", "/api/events", handler, "resolved"),
        ("sse", "GET", "/api/typed", handler, "resolved"),
    ]


@pytest.mark.pins("ktor.a-GET-bound-websocket-under-a-disagreeing-scope-is-dropped")
def test_a_websocket_route_under_a_disagreeing_verb_scope_is_dropped_like_get(tmp_path: Path):
    """DR-6, read off the 3.6.0 jar: every `webSocket`/`webSocketRaw` form WITH a path is
    `route(path, HttpMethod.Get) { … }`, so `method(HttpMethod.Post) { webSocket("/ws") { } }`
    is a GET node under a POST selector that Ktor never dispatches — NO row, the A2
    silence `get("/ws")` gets there; `route("/v", HttpMethod.Put) { webSocket("/in") }` the
    same. Under `method(HttpMethod.Get)` it agrees and is one row, verbless. Under a scope
    whose verb could not be read it is unresolved, as `get` is: whether it is dispatched
    is what could not be read. The PATH-LESS `webSocket { }` has no verb selector in Ktor
    (header selectors and `handle`), so under the POST scope it is still one verbless
    row."""
    pathless = _session(
        _WEBSOCKET_ROUTING,
        "webSocket$default",
        [(_JVM_STRING, CallArgument(kind="null"))],
        mask=1,
    )
    facts = _sessions_under(
        (
            "method",
            [CallArgument(kind="field", symbol="io/ktor/http/HttpMethod#Post.")],
            [_web_socket_default("/ws"), pathless],
        ),
        (
            "route",
            [_literal("/v"), CallArgument(kind="field", symbol="io/ktor/http/HttpMethod#Put.")],
            [_web_socket_default("/in")],
        ),
        (
            "method",
            [CallArgument(kind="field", symbol="io/ktor/http/HttpMethod#Get.")],
            [_web_socket_default("/ok")],
        ),
        (
            "method",
            [CallArgument(kind="field", symbol=_UNKNOWN_GETTERS + "WEIRD.")],
            [_web_socket_default("/odd")],
        ),
    )
    workspace = _resolve(tmp_path, facts, _shipped_ktor_catalog())
    rows = _rows(workspace)
    workspace.close()

    handler = _MODULE + _SUSPEND_BODY
    assert _protocol_identities(rows) == [
        ("websocket", None, "/", handler, "resolved"),
        ("websocket", None, "/odd", handler, "unresolved"),
        ("websocket", None, "/ok", handler, "resolved"),
    ]


@pytest.mark.pins("ktor.a-websocket-under-a-verb-scope-is-NOT-expanded")
def test_a_websocket_route_under_a_bare_route_is_one_verbless_row(tmp_path: Path):
    """`route("/api") { webSocket("/ws") { } }`: no verb is in scope, and the route is ONE
    `websocket` row with `method` NULL — never fanned out through `all_methods` into seven
    HTTP-verbed WebSocket rows, as a verb-less `handle { }` there would be. The path-less
    `webSocket { }` under `route("/b")` is one row at `/b` the same way."""
    facts = _sessions_under(
        ("route3", [_literal("/api")], [_web_socket_default("/ws")]),
        (
            "route3",
            [_literal("/b")],
            [
                _session(
                    _WEBSOCKET_ROUTING,
                    "webSocket$default",
                    [(_JVM_STRING, CallArgument(kind="null"))],
                    mask=1,
                )
            ],
        ),
    )
    workspace = _resolve(tmp_path, facts, _shipped_ktor_catalog())
    rows = _rows(workspace)
    workspace.close()

    handler = _MODULE + _SUSPEND_BODY
    assert _protocol_identities(rows) == [
        ("websocket", None, "/api/ws", handler, "resolved"),
        ("websocket", None, "/b", handler, "resolved"),
    ]


def test_the_websocket_protocol_overload_is_not_read_as_a_path(tmp_path: Path):
    """CP-54 rows 16-17, 21-22. In the three-argument `webSocket(Route, String, Function2)`
    argument 1 is the PROTOCOL, not a path: `webSocket(protocol = "chat") { }` under
    `route("/api")` serves `/api` itself, never `/api/chat`. The same holds for its
    `$default` bridge (`webSocket { }`, mask 1), for `webSocketRaw(protocol) { }`, and for
    `webSocketRaw(protocol, negotiateExtensions)`, which shares arity 4 with
    `webSocketRaw(path, protocol)` and is told apart by the `boolean` at argument 2."""
    facts = _sessions_under(
        (
            "route3",
            [_literal("/api")],
            [
                _session(_WEBSOCKET_ROUTING, "webSocket", [(_JVM_STRING, _literal("chat"))]),
                _session(
                    _WEBSOCKET_ROUTING,
                    "webSocket$default",
                    [(_JVM_STRING, CallArgument(kind="null"))],
                    mask=1,
                ),
                _session(_WEBSOCKET_ROUTING, "webSocketRaw", [(_JVM_STRING, _literal("raw"))]),
                _session(
                    _WEBSOCKET_ROUTING,
                    "webSocketRaw",
                    [
                        (_JVM_STRING, _literal("ext")),
                        ("Z", CallArgument(kind="boolean", value=True)),
                    ],
                ),
                _session(
                    _WEBSOCKET_ROUTING,
                    "webSocketRaw",
                    [(_JVM_STRING, _literal("/pathed")), (_JVM_STRING, _literal("chat"))],
                ),
            ],
        ),
    )
    workspace = _resolve(tmp_path, facts, _shipped_ktor_catalog())
    rows = _rows(workspace)
    workspace.close()

    handler = _MODULE + _SUSPEND_BODY
    assert _protocol_identities(rows) == [
        ("websocket", None, "/api", handler, "resolved"),
        ("websocket", None, "/api/pathed", handler, "resolved"),
    ]
    assert len(rows) == 2


def test_a_pathless_sse_route_is_the_handle_it_compiles_to(tmp_path: Path):
    """`sse { }` carries no path and, read off the 3.6.0 jar, no verb either: it is
    `processSSE`, which installs the plugin and calls `handle { }` on the receiver itself —
    no `route(path, HttpMethod.Get)` around it, unlike `sse(path)`. So it reads as the
    verb-less terminal `handle` does: under `method(HttpMethod.Get)` it is `GET /`, and
    under a bare `route("/stream")` it serves every verb `all_methods` lists, one `sse` row
    each. The serializer overload `sse(serialize, handler)`, arity 3 like `sse(path,
    handler)`, is told apart by argument 1's type (CP-54 row 18)."""
    facts = _sessions_under(
        (
            "method",
            [CallArgument(kind="field", symbol="io/ktor/http/HttpMethod#Get.")],
            [_session(_SSE_ROUTING, "sse", [])],
        ),
        (
            "route3",
            [_literal("/stream")],
            [
                _session(
                    _SSE_ROUTING,
                    "sse",
                    [(_JVM_FN2, CallArgument(kind="lambda", symbol=_SERIALIZE, captures=0))],
                )
            ],
        ),
    )
    workspace = _resolve(tmp_path, facts, _shipped_ktor_catalog())
    rows = _rows(workspace)
    workspace.close()

    handler = _MODULE + _SUSPEND_BODY
    assert _protocol_identities(rows) == [
        ("sse", "DELETE", "/stream", handler, "resolved"),
        ("sse", "GET", "/", handler, "resolved"),
        ("sse", "GET", "/stream", handler, "resolved"),
        ("sse", "HEAD", "/stream", handler, "resolved"),
        ("sse", "OPTIONS", "/stream", handler, "resolved"),
        ("sse", "PATCH", "/stream", handler, "resolved"),
        ("sse", "POST", "/stream", handler, "resolved"),
        ("sse", "PUT", "/stream", handler, "resolved"),
    ]


def test_http_routes_are_unchanged(tmp_path: Path):
    """The HTTP verbs beside the new ones keep their protocol and their verbs: in one
    `route("/api") { get("/orders"); webSocket("/chat"); sse("/events"); get("/events") }`
    the two `get`s are `http` GET rows, and the `http` and `sse` rows at the SAME
    `GET /api/events` are two endpoints — the protocol is part of the identity the batch
    deduplicates on, so neither swallows the other."""
    facts = _sessions_under(
        (
            "route3",
            [_literal("/api")],
            [
                _web_socket_default("/chat"),
                _session(_SSE_ROUTING, "sse", [(_JVM_STRING, _literal("/events"))]),
            ],
        ),
    )
    body = _selector_body(0)
    facts.append(_verb_in(body, 2, "get", "/orders"))
    facts.append(_verb_in(body, 3, "get", "/events"))
    workspace = _resolve(tmp_path, facts, _shipped_ktor_catalog())
    rows = _rows(workspace)
    workspace.close()

    handler = _MODULE + _SUSPEND_BODY
    assert _protocol_identities(rows) == [
        ("http", "GET", "/api/events", handler, "resolved"),
        ("http", "GET", "/api/orders", handler, "resolved"),
        ("sse", "GET", "/api/events", handler, "resolved"),
        ("websocket", None, "/api/chat", handler, "resolved"),
    ]


def test_a_verb_rules_protocol_and_registered_verb_are_validated(tmp_path: Path):
    """A verb rule's `protocol` is one of D00's protocols — a misspelt one would publish
    rows under a protocol nothing links — and sits on a verb rule alone: a prefix or an
    entry registers no route of its own to carry it. `registered_verb` is an upper-case
    verb beside `verb: none` and nowhere else."""
    matches = copy.deepcopy(_matches())
    matches["vocabulary"]["verbs"][0]["protocol"] = "web-socket"  # type: ignore[index]
    with pytest.raises(CatalogError, match="protocol"):
        _resolve(tmp_path, [], _catalog(matches))
    matches = copy.deepcopy(_matches())
    matches["vocabulary"]["prefixes"][0]["protocol"] = "websocket"  # type: ignore[index]
    with pytest.raises(CatalogError, match="protocol"):
        _resolve(tmp_path, [], _catalog(matches))
    # `registered_verb` names the verb a VERBLESS route is registered under: beside
    # `verb: none` alone, and an upper-case verb word.
    for verb, registered in (("GET", "GET"), ("none", "get"), ("none", 7)):
        matches = copy.deepcopy(_matches())
        rule = matches["vocabulary"]["verbs"][0]  # type: ignore[index]
        rule["verb"] = verb
        rule["registered_verb"] = registered
        with pytest.raises(CatalogError, match="registered_verb"):
            _resolve(tmp_path, [], _catalog(matches))
