"""A module reads a dependency's TYPES; it does not publish its ROWS (F4 §5.2, W24).

## What the module edge costs when it is not crossed

`CommonResult<T>` is compiled in `mall-common`; every one of `mall-admin`'s controllers
returns it. Without that module's class files, 160 of 160 endpoints carry ONE distinct
response shape with ZERO fields — the envelope, with nothing in it.

## The set is the DECLARED dependencies, not every module in the reactor

The first version of this walked the parent POM's whole `<modules>` list. `mall-admin`
declares `mall-mbg` and `mall-security`; `mall-portal` and `mall-demo` are not on its
classpath at all — and their documents entered its workspace, deriving **246** endpoints
against its own 160 and rendering `mall-portal`'s `@Scheduled` cron task inside
`mall-admin`'s own document. Reading only what the module compiles against removes that
at source: with the corrected set, the same corpus derives exactly 160 with no filter at
all, because `mall-mbg`, `mall-security` and `mall-common` declare no controllers.

## The guardrail is still needed, and where it sits is the correctness of it

A shared `-web` or `-api` sibling does carry controllers and schemas. Two placements were
wrong before this one:

* **After `endpoints_merge`.** That merge folded an inbound and an outbound row for one
  address into a single `both` row carrying the INBOUND handler, so a delete keyed on
  that handler took the module's OWN outbound call with it — silently, no gap row. W27
  deleted the merge (F5 §6.1), so the hazard cannot arise any more; the placement it
  forced is still the placement, and the behaviour it protected is still pinned below.
* **Keyed on `coalesce(handler, caller)` alone.** `schema_operations` mints rows with
  neither, by design: the schema names no code. A dependency's `.proto` published its
  service as this module's API through a route the delete could not reach.
"""

from pathlib import Path

from sextant.application.ports.catalogs import Catalog
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    AnnotationFact,
    AnnotationUse,
    CallArgument,
    CallSiteFact,
    CallTarget,
    Document,
    ModuleFact,
    Signature,
    SymbolFact,
    TypeRef,
)
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.resources import catalogs_dir
from sextant.storage.duckdb.workspace import DuckDbWorkspace

CONTROLLER = "org/springframework/web/bind/annotation/RestController#"
MAPPING = "org/springframework/web/bind/annotation/GetMapping#"
_MODULE = "sextant-jvm maven com.acme/orders 1.0.0 "

CAPABILITIES = {"annotation_args", "type_annotations", "call_site", "string_constants"}


def _catalog() -> Catalog:
    return Catalog(
        id="invented-http",
        style="annotation_driven",
        protocol="http",
        direction="inbound",
        source=Path("invented.yml"),
        requires=("annotation_args", "type_annotations"),
        matches={
            "type_annotation": "org.springframework.web.bind.annotation.RestController",
            "mapping": {
                "path_from": ["value"],
                "prefix_from": ["value"],
                "path_separator": "/",
                "method_from": "method",
                "prefix_annotation": "org.springframework.web.bind.annotation.RequestMapping",
                "all_methods": ["GET"],
                "annotations": [
                    {"fqn": "org.springframework.web.bind.annotation.GetMapping", "method": ["GET"]}
                ],
            },
        },
    )


def _document(document_id: str, tier: OriginTier, origin: str | None) -> Document:
    return Document(
        document_id=document_id,
        relative_path=f"{document_id}.java",
        module_id="com.acme:orders",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version=2,
        scanner_id="asm",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=tier,
        origin=origin,
        redaction_set_hash="sha256:b",
    )


def _controller(document_id: str, owner: str, path: str) -> list:
    """One `@RestController` with one `@GetMapping` — every conjunct a row needs."""
    handler = f"{_MODULE}{owner}serve()."
    return [
        SymbolFact(
            document_id=document_id, symbol=_MODULE + owner, construct_kind=ConstructKind.CLASS
        ),
        SymbolFact(
            document_id=document_id,
            symbol=handler,
            construct_kind=ConstructKind.METHOD,
            enclosing=_MODULE + owner,
        ),
        AnnotationFact(
            document_id=document_id,
            target=_MODULE + owner,
            retention="runtime",
            use=AnnotationUse(annotation=CONTROLLER, args={}),
        ),
        AnnotationFact(
            document_id=document_id,
            target=handler,
            retention="runtime",
            use=AnnotationUse(annotation=MAPPING, args={"value": [path]}),
        ),
    ]


def _module_fact(facts: Path) -> None:
    """The module fact naming which dependency was scanned as a reactor SIBLING.

    `drop_borrowed_endpoints.sql` keys on this rather than on the tier, because
    `extract_libraries` shares the tier and its surface is what a person asked for."""
    write_fact_file(
        facts / "module.jsonl",
        _document("module", OriginTier.MODULE_OUTPUT, None),
        [
            ModuleFact(
                document_id="module",
                module_id="com.acme:orders",
                module_kind="service",
                languages=["java"],
                source_roots=["src/main/java"],
                output_dirs=["target/classes"],
                sibling_coordinates=["com.acme:orders-common"],
            )
        ],
    )


def _resolved(tmp_path: Path) -> list[dict]:
    facts = tmp_path / "facts"
    write_fact_file(
        facts / "own.jsonl",
        _document("own", OriginTier.MODULE_OUTPUT, None),
        _controller("own", "com/acme/orders/OwnController#", "/orders"),
    )
    write_fact_file(
        facts / "sibling.jsonl",
        _document("sibling", OriginTier.DEPENDENCY, "com.acme:orders-common"),
        _controller("sibling", "com/acme/common/NeighbourController#", "/neighbour"),
    )
    _module_fact(facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)
    derive_endpoints(workspace, [_catalog()], capabilities=CAPABILITIES)
    rows = [dict(row) for row in workspace.query("endpoints")]
    workspace.close()
    return rows


def test_a_nest_host_the_class_file_states_beats_splitting_the_name(tmp_path: Path):
    """W4b. Three engines derived a nested type's top-level enclosing type by
    splitting its binary name on the first `$`. The class file STATES it —
    JVMS 4.7.28's `NestHost`, extracted since W7 — and nothing read it, because
    the fact was never projected out of `raw_facts`.

    A split is right until a name carries a `$` that is not nesting, which several
    compilers targeting this runtime emit in ordinary code. Here the two
    disagree deliberately: the symbol is `Outer$Inner$Deep#`, so the split answers
    `Outer#` — which happens to be right — while a class whose stated host is
    something else entirely proves which one is being read.

    `outer_of` takes the stated host where there is one and falls back otherwise,
    because only nested types compiled for Java 11+ carry the attribute: absence
    is ordinary, and treating it as "already top-level" would be a second guess
    dressed as a fact."""
    from sextant.application.resolve.shapes.identity_calls import nest_hosts, outer_of

    facts = tmp_path / "facts"
    nested = "com/acme/gen/Outer$Inner$Deep#"
    stated = "com/acme/gen/DifferentHost#"
    write_fact_file(
        facts / "own.jsonl",
        _document("own", OriginTier.MODULE_OUTPUT, None),
        [
            SymbolFact(
                document_id="own",
                symbol=nested,
                construct_kind=ConstructKind.CLASS,
                nest_host=stated,
            ),
            # A nested type carrying NO `NestHost` — an older target, which is the
            # case the fallback exists for.
            SymbolFact(
                document_id="own",
                symbol="com/acme/gen/Legacy$Inner#",
                construct_kind=ConstructKind.CLASS,
            ),
        ],
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)
    hosts = nest_hosts(workspace)
    workspace.close()

    # The STATED host wins, and it is not what a `$` split would have answered.
    assert outer_of(nested, hosts) == stated
    assert outer_of(nested, hosts) != "com/acme/gen/Outer#"
    # With no fact, the split still answers — an absent attribute is not a claim.
    assert outer_of("com/acme/gen/Legacy$Inner#", hosts) == "com/acme/gen/Legacy#"


def test_an_exchange_interface_a_SIBLING_declares_still_serves_this_modules_route(
    tmp_path: Path,
):
    """W56. The case that separates deriving-then-deleting from filtering at the
    root, and the reason this wave kept the former.

    `spring-http-interface`'s flip takes an `@HttpExchange` INTERFACE that a local
    `@RestController` implements and publishes the route INBOUND, rebinding the
    handler to the implementing class's method. Put that interface in a reactor
    sibling — an api module, which is exactly where such interfaces live — and the
    two keys come apart: the ANNOTATION is the sibling's, and the HANDLER is ours.

    `drop_borrowed_endpoints.sql` keys on `coalesce(handler, caller)` and keeps
    the row, correctly: this module really serves it. A filter keyed on the
    annotation's own document would drop it, and the module's whole implemented
    API would vanish with nothing saying so.

    So the apparently wasteful shape — derive from every document, then delete
    what the module does not own — is load-bearing, and the tidier-looking
    root filter is not equivalent to it."""
    facts = tmp_path / "facts"
    exchange = "org/springframework/web/service/annotation/HttpExchange#"
    get_exchange = "org/springframework/web/service/annotation/GetExchange#"
    interface = "com/acme/common/OrderApi#"
    interface_method = "com/acme/common/OrderApi#list(sig_a)."
    implementer = "com/acme/orders/OrderController#"
    implementer_method = "com/acme/orders/OrderController#list(sig_a)."

    write_fact_file(
        facts / "sibling.jsonl",
        _document("sibling", OriginTier.DEPENDENCY, "com.acme:orders-common"),
        [
            SymbolFact(
                document_id="sibling", symbol=interface, construct_kind=ConstructKind.INTERFACE
            ),
            SymbolFact(
                document_id="sibling",
                symbol=interface_method,
                construct_kind=ConstructKind.METHOD,
                enclosing=interface,
            ),
            AnnotationFact(
                document_id="sibling",
                target=interface,
                retention="runtime",
                use=AnnotationUse(annotation=exchange, args={"value": "/orders"}),
            ),
            AnnotationFact(
                document_id="sibling",
                target=interface_method,
                retention="runtime",
                use=AnnotationUse(annotation=get_exchange, args={"value": "/list"}),
            ),
        ],
    )
    write_fact_file(
        facts / "own.jsonl",
        _document("own", OriginTier.MODULE_OUTPUT, None),
        [
            SymbolFact(
                document_id="own",
                symbol=implementer,
                construct_kind=ConstructKind.CLASS,
                interfaces=[interface],
            ),
            SymbolFact(
                document_id="own",
                symbol=implementer_method,
                construct_kind=ConstructKind.METHOD,
                enclosing=implementer,
            ),
            AnnotationFact(
                document_id="own",
                target=implementer,
                retention="runtime",
                use=AnnotationUse(annotation=CONTROLLER, args={}),
            ),
        ],
    )
    _module_fact(facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)
    shipped = [
        c for c in YamlCatalogSource(catalogs_dir()).load() if c.id == "spring-http-interface"
    ]
    # `spring-http-interface` declares `requires: [annotation_args, typed_signatures]`,
    # and a catalog whose requirements are unmet is SKIPPED — which derives nothing and
    # would make this test pass for the wrong reason.
    assert (
        derive_endpoints(workspace, shipped, capabilities=CAPABILITIES | {"typed_signatures"}) == []
    )
    rows = [dict(row) for row in workspace.query("endpoints")]
    workspace.close()

    assert [(r["direction"], r["path"]) for r in rows] == [("inbound", "/orders/list")], (
        "the route this module serves through a SIBLING-declared interface was lost"
    )


def test_a_dependencys_controller_does_not_become_this_modules_endpoint(tmp_path: Path):
    """The guardrail. Both controllers satisfy every conjunct the catalog names; only
    the module's own is this module's API.

    This reaches `extract_libraries` too, which has opted library jars into the
    workspace since 2I with no such filter — the same fabrication was already available
    to anyone who opted in a jar carrying a controller."""
    paths = {str(row["path"]) for row in _resolved(tmp_path)}

    assert paths == {"/orders"}, (
        "a reactor sibling's controller is not this module's endpoint; its TYPES are "
        "what the module edge is crossed for"
    )


def test_the_modules_own_controller_still_derives(tmp_path: Path):
    """§10's paired positive. The gate is a DELETE keyed on the handler's document, and
    a gate that removed everything would satisfy the assertion above just as well."""
    rows = _resolved(tmp_path)

    assert len(rows) == 1
    assert str(rows[0]["path"]) == "/orders"
    assert "OwnController" in str(rows[0]["handler"])


def _outbound_catalog() -> Catalog:
    """A `single_call` catalog minting an OUTBOUND row from a client call."""
    return Catalog(
        id="invented-client",
        style="single_call",
        protocol="http",
        direction="outbound",
        source=Path("invented-client.yml"),
        requires=("call_site", "string_constants"),
        matches={
            "owner": "com.acme.orders.Rest",
            "methods": [
                {
                    "name": "get",
                    "arity": 1,
                    "descriptor": "(Ljava/lang/String;)Ljava/lang/Object;",
                    "url_arg": 0,
                    "http_method": "GET",
                }
            ],
        },
    )


def test_a_dependency_serving_an_address_this_module_calls_keeps_the_outbound_row(
    tmp_path: Path,
):
    """A dependency serving an address this module CALLS must not take the module's own
    call with it.

    This was the merge-ordering Critical: `endpoints_merge` folded an inbound and an
    outbound row for one address into a single `both` row carrying the INBOUND handler,
    so a delete keyed on that handler took the outbound row too — leaving no gap row, so
    nothing in the output said a call had ever been there. W27 deleted the merge, so the
    ordering argument is retired and the property is not. The delete still keys on
    `coalesce(handler, caller)`, a borrowed inbound row still has to go, and this
    module's own outbound row still has to stay — which is what is asserted here.

    The dependency serves `/orders` and this module calls it. The module's own outbound
    row must survive, and the dependency's inbound row must not appear.
    """
    facts = tmp_path / "facts"
    caller = _MODULE + "com/acme/orders/OwnClient#fetch()."
    write_fact_file(
        facts / "own.jsonl",
        _document("own", OriginTier.MODULE_OUTPUT, None),
        [
            SymbolFact(
                document_id="own",
                symbol=caller,
                construct_kind=ConstructKind.METHOD,
                signature=Signature(parameters=[], returns=TypeRef(symbol="V")),
            ),
            CallSiteFact(
                document_id="own",
                caller=caller,
                target=CallTarget(
                    owner="com/acme/orders/Rest#",
                    name="get",
                    descriptor="(Ljava/lang/String;)Ljava/lang/Object;",
                ),
                invoke_kind="virtual",
                ordinal=0,
                arguments=[CallArgument(kind="string", value="/orders")],
            ),
        ],
    )
    write_fact_file(
        facts / "dependency.jsonl",
        _document("dependency", OriginTier.DEPENDENCY, "com.acme:orders-common"),
        _controller("dependency", "com/acme/common/NeighbourController#", "/orders"),
    )
    _module_fact(facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)
    derive_endpoints(workspace, [_catalog(), _outbound_catalog()], capabilities=CAPABILITIES)
    rows = [
        (str(r["direction"]), str(r["path"]), str(r["caller"] or ""))
        for r in workspace.query("endpoints")
    ]
    workspace.close()

    assert rows == [("outbound", "/orders", caller)], (
        "the module's own outbound call must survive a dependency serving the same "
        "address; the drop runs before the merge precisely so the merged row cannot "
        "take it away"
    )


def test_an_entry_on_a_borrowed_row_is_dropped_with_it(tmp_path: Path):
    """Ruling 7 (follow the object). A reactor sibling's own client call derives an outbound
    row, and `single_call` writes the query parameter its URL carries as an
    `endpoint_metadata` entry bound to that row, in the same pass. The borrowed-row drop
    then removes the row: it is the sibling's call, not this module's. The entry goes with
    it, whichever catalogs the module loads — this one loads no protocol hint, no path
    prefix and no gRPC, so no later pass would happen to clean it up. Left behind, the
    bundle states a parameter of a call the module does not make."""
    facts = tmp_path / "facts"
    own = _MODULE + "com/acme/orders/OwnClient#fetch()."
    borrowed = _MODULE + "com/acme/common/NeighbourClient#fetch()."

    def _calling(document_id: str, caller: str, url: str) -> list:
        return [
            SymbolFact(
                document_id=document_id,
                symbol=caller,
                construct_kind=ConstructKind.METHOD,
                signature=Signature(parameters=[], returns=TypeRef(symbol="V")),
            ),
            CallSiteFact(
                document_id=document_id,
                caller=caller,
                target=CallTarget(
                    owner="com/acme/orders/Rest#",
                    name="get",
                    descriptor="(Ljava/lang/String;)Ljava/lang/Object;",
                ),
                invoke_kind="virtual",
                ordinal=0,
                arguments=[CallArgument(kind="string", value=url)],
            ),
        ]

    write_fact_file(
        facts / "own.jsonl",
        _document("own", OriginTier.MODULE_OUTPUT, None),
        _calling("own", own, "/orders?view=summary"),
    )
    write_fact_file(
        facts / "sibling.jsonl",
        _document("sibling", OriginTier.DEPENDENCY, "com.acme:orders-common"),
        _calling("sibling", borrowed, "/neighbour?v=2"),
    )
    _module_fact(facts)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(facts)
    derive_endpoints(workspace, [_outbound_catalog()], capabilities=CAPABILITIES)
    rows = [(str(r["path"]), str(r["caller"])) for r in workspace.query("endpoints")]
    entries = [
        (str(r["path"]), str(r["caller"]), str(r["name"]))
        for r in workspace.query("endpoint_metadata")
    ]
    workspace.close()

    assert rows == [("/orders", own)]
    assert entries == [("/orders", own, "view")]
