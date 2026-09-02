"""Tests for the `schema_operations` engine (D02 §2's ninth style, 2H design
§3): a schema's own root operations become endpoints.

Everything here is built by hand — invented type names, invented field names,
a catalog written in the test — for the reason every other engine test in this
directory states: a behaviour per test, isolated and fast, with the shipped
catalog's live answers pinned once in `test_pipeline.py` and `tests/e2e`
against a real schema on disk. None of the type or field names below is one a
real schema would use, which is what keeps these tests honest about the engine
reading catalog data rather than knowing a format.

The one thing NOT invented is `DeclaredShapeFact.role`. Root identification is
settled upstream, in the one interpreter that may read a schema format (2H
design §2): a `schema { query: MyQuery }` block, an `extend schema`, or the
format's default root names where nothing binds, with a conflicting binding
already failing into a gap before any fact is written. These tests therefore
state the role directly, which is exactly what this engine sees.
"""

import json
from pathlib import Path

import pytest

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.application.resolve.engines import schema_operations
from sextant.application.resolve.shapes import derive_endpoint_shapes
from sextant.cli.resources import catalogs_dir
from sextant.domain.closed_sets import ConstructKind, OriginTier
from sextant.domain.factfile import write_fact_file
from sextant.domain.facts import (
    AnnotationFact,
    AnnotationUse,
    DeclaredFieldFact,
    DeclaredShapeFact,
    Document,
    Parameter,
    Signature,
    SymbolFact,
    TypeRef,
)
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.storage.duckdb.workspace import DuckDbWorkspace

# The one thing that cannot be invented: `schema_format` is a closed Literal
# on the fact itself (D00 §5), so a test format would not survive validation.
# The pair is what proves the format gate is a gate — `role` is declared on
# EVERY shape kind, so nothing but this gate keeps a root some other format
# named out of this catalog's protocol.
FORMAT = "graphql"
OTHER_FORMAT = "avro"
# `role == "operation"` (2I Task 4) is the one role this engine hardcodes
# rather than reading off catalog data, so its tests need a real schema
# format beside `FORMAT` to gate on — `wsdl` is the one D00 actually closes
# over, same reason `OTHER_FORMAT` above cannot be invented either.
WSDL_FORMAT = "wsdl"


def _document(document_id: str = "doc_1", path: str = "schema/orders.invented") -> Document:
    return Document(
        document_id=document_id,
        relative_path=path,
        module_id="com.acme:orders-service",
        language="invented-sdl",
        sextant_version="0.1.0",
        fact_schema_version="1.0.0",
        scanner_id="reader",
        scanner_version="1.0",
        content_hash="sha256:a",
        origin_entry="src/main/resources/schema",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )


def _field(
    name: str,
    *,
    wire_type: str = "object",
    shape_ref: str | None = None,
    item: dict[str, object] | None = None,
    nullable: bool = True,
) -> DeclaredFieldFact:
    """One field of a declared type, already in D00 §5b's wire vocabulary —
    which is what the interpreter writes and this engine only reshapes."""
    return DeclaredFieldFact(
        name=name,
        wire_name=name,
        wire_type=wire_type,
        wire_format=None,
        required=not nullable,
        nullable=nullable,
        item=item,
        shape_ref=shape_ref,
    )


def _shape(
    symbol: str,
    *fields: DeclaredFieldFact,
    role: str | None = None,
    schema_format: str = FORMAT,
    document_id: str = "doc_1",
) -> DeclaredShapeFact:
    return DeclaredShapeFact(
        document_id=document_id,
        symbol=symbol,
        schema_name=symbol,
        schema_format=schema_format,  # type: ignore[arg-type]
        origin="source",
        evidence="declared",
        role=role,  # type: ignore[arg-type]
        fields=list(fields),
    )


def _catalog(
    operations: dict[str, str] | None = None,
    *,
    source: Path = Path("tests/invented-schema.yml"),
    protocol: str = "graphql",
    **block: object,
) -> Catalog:
    declared: dict[str, object] = {
        "schema_format": FORMAT,
        "operations": {"query": "query", "mutation": "mutation", "subscription": "subscription"}
        if operations is None
        else operations,
    }
    declared.update(block)
    return Catalog(
        id="invented-schema",
        style="schema_operations",
        protocol=protocol,
        direction="inbound",
        requires=(),
        matches={"schema_operations": declared},
        source=source,
    )


def _workspace(tmp_path: Path, *shapes: DeclaredShapeFact) -> DuckDbWorkspace:
    """A workspace holding the given declared shapes, ONE FACT FILE PER
    `document_id` — because that is what a document is: a schema split across
    two files is two documents, and a helper that flattened them into one
    would let a test claim a multi-file schema it never built."""
    for document_id in dict.fromkeys(shape.document_id for shape in shapes):
        write_fact_file(
            tmp_path / "facts" / f"{document_id}.jsonl",
            _document(document_id, f"schema/{document_id}.invented"),
            [shape for shape in shapes if shape.document_id == document_id],
        )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    return workspace


# The module-coordinates prefix every real symbol fact carries (D00 §5a).
_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "
_RESOLVER = "com/acme/orders/Resolvers#"
_RESOLVER_METHOD = "com/acme/orders/Resolvers#orders(sig_1)."


def _annotated_facts(root: Path, signature: Signature | None = None) -> None:
    """One `@Controller` carrying one `@QueryMapping` with no attribute — the
    shape the shipped `spring-graphql` catalog reads, whose `path_fallback`
    makes the method's own name the field it implements.

    `signature` is what decides whether the derived row carries a
    `handler_signature` at all, which is the column
    `derive_endpoint_contracts.sql` guards on — so it is the difference
    between a row the shape pass re-answers and one it leaves alone."""
    document = Document(
        document_id="doc_2",
        relative_path="com/acme/orders/Resolvers.java",
        module_id="com.acme:orders-service",
        language="java",
        sextant_version="0.1.0",
        fact_schema_version="1.0.0",
        scanner_id="asm",
        scanner_version="9.12",
        content_hash="sha256:c",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )
    write_fact_file(
        root / "Resolvers.jsonl",
        document,
        [
            SymbolFact(
                document_id="doc_2",
                symbol=_MODULE + _RESOLVER,
                construct_kind=ConstructKind.CLASS,
            ),
            SymbolFact(
                document_id="doc_2",
                symbol=_MODULE + _RESOLVER_METHOD,
                construct_kind=ConstructKind.METHOD,
                enclosing=_MODULE + _RESOLVER,
                signature=signature,
            ),
            AnnotationFact(
                document_id="doc_2",
                target=_MODULE + _RESOLVER,
                retention="runtime",
                use=AnnotationUse(annotation="org/springframework/stereotype/Controller#", args={}),
            ),
            AnnotationFact(
                document_id="doc_2",
                target=_MODULE + _RESOLVER_METHOD,
                retention="runtime",
                use=AnnotationUse(
                    annotation=("org/springframework/graphql/data/method/annotation/QueryMapping#"),
                    args={},
                ),
            ),
        ],
    )


def _annotation_row(method: str | None, path: str, **overrides: object) -> dict[str, object]:
    """A row standing in for one an annotation engine already derived: it
    knows the handler symbol, which is the whole thing a schema cannot say."""
    row: dict[str, object] = {
        "protocol": "graphql",
        "direction": "inbound",
        "method": method,
        "path": path,
        "handler": "com/acme/orders/Resolvers#orders(sig_1).",
        "caller": None,
        "peer": None,
        "handler_signature": None,
        "resolution": "resolved",
        "evidence": "compiler",
        "catalog_id": "invented-annotations",
        "request_shape": None,
        "response_shape": None,
        "consumes": None,
        "produces": None,
    }
    row.update(overrides)
    return row


def _run(workspace: DuckDbWorkspace, catalog: Catalog, *existing: dict[str, object]) -> None:
    """The engine alone, over a table already holding `existing` rows.

    `derive_endpoints` is what a whole resolve calls, and it empties the table
    first — so seeding a pre-existing row and running the style over it is the
    only way to state the agreement rules as their own behaviours. That the
    ORDER really puts this style after the annotation engines is a separate
    claim, tested through `derive_endpoints` below and pinned live on real
    bytecode in `test_pipeline.py`.
    """
    workspace.derive("endpoints_reset")
    if existing:
        workspace.derive("call_endpoints", rows=list(existing))
    schema_operations.run(workspace, catalog)


def _rows(workspace: DuckDbWorkspace) -> list[dict[str, object]]:
    return workspace.query("endpoints")


def test_root_fields_become_operations(tmp_path: Path):
    """The style's whole reason to exist: a schema-first service declares its
    boundary in a file and no annotation anywhere, so each field of each root
    type is an endpoint or the module reports none at all."""
    workspace = _workspace(
        tmp_path,
        _shape("Roots", _field("orders"), _field("orderById"), role="query"),
        _shape("Writes", _field("placeOrder"), role="mutation"),
        _shape("Streams", _field("orderUpdates"), role="subscription"),
    )
    _run(workspace, _catalog())
    rows = _rows(workspace)
    workspace.close()

    assert {(r["protocol"], r["method"], r["path"]) for r in rows} == {
        ("graphql", "query", "orders"),
        ("graphql", "query", "orderById"),
        ("graphql", "mutation", "placeOrder"),
        ("graphql", "subscription", "orderUpdates"),
    }
    # Every row states the same four things about itself, and each is a
    # statement rather than a default: the schema is a repository file
    # (`declared`), it addressed the operation outright (`resolved`), it names
    # no code (`handler`/`caller` NULL), and it says nothing about what the
    # operation TAKES — a root field's arguments are not projected at all.
    assert all(r["direction"] == "inbound" for r in rows)
    assert all(r["evidence"] == "declared" for r in rows)
    assert all(r["resolution"] == "resolved" for r in rows)
    assert all(r["handler"] is None and r["caller"] is None for r in rows)
    assert all(r["request_shape"] is None for r in rows)
    assert all(r["catalog_id"] == "invented-schema" for r in rows)


def test_a_renamed_root_is_honored_because_the_role_is_a_fact(tmp_path: Path):
    """The rename case, and the reason `role` had to become a fact at all
    (D00 §5): a schema may bind its query root to any type it likes, so a
    type's NAME can never answer the question. `Query` here is an ordinary
    payload that happens to be called that, and `MyQ` is the root — which is
    precisely the answer a name-matching engine would get backwards."""
    workspace = _workspace(
        tmp_path,
        _shape("MyQ", _field("orders"), role="query"),
        _shape("Query", _field("notAnOperation"), role=None),
    )
    _run(workspace, _catalog())
    rows = _rows(workspace)
    workspace.close()

    assert [(r["method"], r["path"]) for r in rows] == [("query", "orders")]


def test_non_root_types_derive_nothing(tmp_path: Path):
    """A payload type's fields are what the payload carries, never operations.
    Deriving them would publish `(graphql, query, id)` for every record in the
    schema — a boundary per field of every message the service sends."""
    workspace = _workspace(
        tmp_path,
        _shape("Order", _field("id"), _field("total"), role=None),
        _shape("OrderFilter", _field("sku"), role=None),
    )
    _run(workspace, _catalog())
    rows = _rows(workspace)
    workspace.close()

    assert rows == []


def test_a_role_the_catalog_does_not_name_derives_nothing(tmp_path: Path):
    """An unmapped role is a gap to grow the catalog from, never a `method`
    column value to invent — the same answer `config_join` gives an unmapped
    binder name. The catalog here knows queries only."""
    workspace = _workspace(
        tmp_path,
        _shape("Roots", _field("orders"), role="query"),
        _shape("Writes", _field("placeOrder"), role="mutation"),
    )
    _run(workspace, _catalog(operations={"query": "query"}))
    rows = _rows(workspace)
    workspace.close()

    assert [(r["method"], r["path"]) for r in rows] == [("query", "orders")]


def test_a_root_declared_by_another_schema_format_derives_nothing(tmp_path: Path):
    """`role` is neutral across formats (D00 §5) and this catalog's `protocol`
    is not: a root some other format declares is some other protocol's
    operation. Without the gate this row would be minted as `graphql` because
    one catalog happened to be loaded."""
    workspace = _workspace(
        tmp_path,
        _shape("Roots", _field("orders"), role="query"),
        _shape("Others", _field("elsewhere"), role="query", schema_format=OTHER_FORMAT),
    )
    _run(workspace, _catalog())
    rows = _rows(workspace)
    workspace.close()

    assert [(r["method"], r["path"]) for r in rows] == [("query", "orders")]


def test_sdl_only_operation_inserts(tmp_path: Path):
    """The RuntimeWiring case (2H design §3): one operation in the schema that
    no annotation implements, beside several that do. Only the unimplemented
    one becomes a new row, and it carries the declared response the schema
    states — which is the whole answer such a service can give."""
    workspace = _workspace(
        tmp_path,
        _shape(
            "Roots",
            _field("orders", shape_ref="Order"),
            _field("auditTrail", shape_ref="AuditEntry"),
            role="query",
        ),
    )
    _run(workspace, _catalog(), _annotation_row("query", "orders"))
    rows = {str(r["path"]): r for r in _rows(workspace)}
    workspace.close()

    assert set(rows) == {"orders", "auditTrail"}
    assert rows["auditTrail"]["catalog_id"] == "invented-schema"
    assert rows["auditTrail"]["handler"] is None
    assert json.loads(str(rows["auditTrail"]["response_shape"])) == {
        "wire_type": "object",
        "wire_format": None,
        "nullable": True,
        "shape_id": "AuditEntry",
    }


def test_agreement_annotation_wins_identity(tmp_path: Path):
    """First-writer, through the guard every call-site style already meets:
    the annotation row knows the handler symbol and the schema row does not,
    so folding them the other way would lose the only thing that connects this
    boundary to code."""
    workspace = _workspace(tmp_path, _shape("Roots", _field("orders"), role="query"))
    _run(workspace, _catalog(), _annotation_row("query", "orders"))
    rows = _rows(workspace)
    workspace.close()

    assert len(rows) == 1
    assert rows[0]["handler"] == "com/acme/orders/Resolvers#orders(sig_1)."
    assert rows[0]["catalog_id"] == "invented-annotations"
    assert rows[0]["evidence"] == "compiler"


def test_agreement_coalesces_response_shape(tmp_path: Path):
    """The merge-carry half: the handler symbol is the annotation's alone and
    the declared response type is the schema's alone, so the surviving row
    takes each from whichever side has it — and a shape the annotation side
    already answered is never overwritten, because a Java class is what that
    handler really serializes (2H design §4)."""
    java_shape = json.dumps(
        {"nullable": True, "shape_id": "com/acme/orders/OrderView#", "wire_type": "object"},
        sort_keys=True,
        separators=(",", ":"),
    )
    workspace = _workspace(
        tmp_path,
        _shape(
            "Roots",
            _field("orders", shape_ref="Order"),
            _field("orderById", shape_ref="Order"),
            role="query",
        ),
    )
    _run(
        workspace,
        _catalog(),
        _annotation_row("query", "orders"),
        _annotation_row("query", "orderById", response_shape=java_shape),
    )
    rows = {str(r["path"]): r for r in _rows(workspace)}
    workspace.close()

    # NULL gains the schema's declared type — a shape reference into the
    # DECLARED universe (a schema name), never a join to a Java class.
    assert json.loads(str(rows["orders"]["response_shape"]))["shape_id"] == "Order"
    # Non-NULL is left exactly as it was.
    assert rows["orderById"]["response_shape"] == java_shape


def test_a_collection_response_carries_what_it_holds(tmp_path: Path):
    """D01 §5's `item` chain, reshaped rather than re-derived: the interpreter
    already said what the collection holds, and the shape reference has to
    survive into the column or `shapes/contracts.py` cannot expand it."""
    workspace = _workspace(
        tmp_path,
        _shape(
            "Roots",
            _field(
                "auditTrail",
                wire_type="array",
                item={
                    "wire_type": "object",
                    "wire_format": None,
                    "nullable": False,
                    "shape_id": "AuditEntry",
                },
            ),
            role="query",
        ),
    )
    _run(workspace, _catalog())
    rows = _rows(workspace)
    workspace.close()

    assert json.loads(str(rows[0]["response_shape"])) == {
        "wire_type": "array",
        "wire_format": None,
        "nullable": True,
        "item": {
            "wire_type": "object",
            "wire_format": None,
            "nullable": False,
            "shape_id": "AuditEntry",
        },
    }


def test_one_identity_declared_by_two_facts_is_one_row(tmp_path: Path):
    """`derive_call_endpoints.sql`'s guard is evaluated against the table as
    it stood before the statement began (its own header), so two same-identity
    rows in one batch would BOTH insert. A shared type name legitimately
    arrives twice — once per document that declares it — and one operation
    counted twice is a boundary that does not exist.

    Two genuinely different documents, which is the only way the fixture is
    the case it describes: one root type declared in two files of a multi-file
    schema."""
    workspace = _workspace(
        tmp_path,
        _shape("Roots", _field("orders"), role="query"),
        _shape("Roots", _field("orders"), role="query", document_id="doc_2"),
    )
    _run(workspace, _catalog())
    rows = _rows(workspace)
    workspace.close()

    assert len(rows) == 1


def test_the_style_runs_after_the_annotation_engines_when_a_resolve_orders_them(
    tmp_path: Path,
):
    """The ordering claim itself, through the real `derive_endpoints` loop and
    a real shipped annotation catalog.

    Every other agreement test above seeds the pre-existing row by hand, which
    states what the guard does but not that this style ever meets a written
    table. Ordering is what connects the two, and a catalog file cannot ask
    for it: the position is a property of the style (`_RUNS_LAST`), so the
    only honest way to assert it is to hand the loop both catalogs and read
    which row survived.

    The schema catalog's `source` is deliberately a path that sorts FIRST.
    Without it the filename tiebreak happens to put the shipped catalog ahead
    anyway, and this test would pass with the style's ranking removed — an
    assertion about ordering that ordering did not decide.
    """
    spring = next(c for c in YamlCatalogSource(catalogs_dir()).load() if c.id == "spring-graphql")
    _annotated_facts(tmp_path / "facts")
    workspace = _workspace(
        tmp_path,
        _shape("Roots", _field("orders"), _field("auditTrail"), role="query"),
    )

    skipped = derive_endpoints(
        workspace,
        [_catalog(source=Path("/00-invented-schema.yml")), spring],
        capabilities={"annotation_args", "type_annotations"},
    )
    rows = {str(r["path"]): r for r in _rows(workspace)}
    workspace.close()

    assert skipped == []
    assert set(rows) == {"orders", "auditTrail"}
    # The annotated operation kept the annotation's row — handler and all —
    # even though the catalogs were handed to the loop in the opposite order.
    assert rows["orders"]["catalog_id"] == "spring-graphql"
    assert rows["orders"]["handler"] == _MODULE + _RESOLVER_METHOD
    # And the operation nothing implements is the schema's, at `declared`.
    assert rows["auditTrail"]["catalog_id"] == "invented-schema"
    assert (rows["auditTrail"]["handler"], rows["auditTrail"]["evidence"]) == (None, "declared")


def test_a_handler_with_a_request_and_no_response_ends_with_response_shape_null(
    tmp_path: Path,
):
    """The stamp's exact reach, pinned AS SHIPPED (2H Task 4 review, IMPORTANT
    2 — the controller ruled that this behaviour stands).

    The stamp runs inside `derive_endpoints`, where every annotation row still
    carries `response_shape` NULL, so it lands on this row. The shape pass then
    runs, and `derive_endpoint_contracts.sql` re-answers BOTH payload columns
    for any row still carrying its own `handler_signature` — this owner is in
    `$contracts` because it has a request payload, and its response answer is
    `None`, so the stamped declared type is nulled again.

    That is the honest reading of the ordering: an annotated operation
    publishes what its own handler really serializes, and where the handler
    serializes nothing the schema's answer does not survive either. What is
    pinned here is that the outcome cannot change SILENTLY — a future
    reordering of the stamp (below the shape pass, say) has to fail this test
    and be argued for, rather than quietly flipping a published column.

    The transient value is asserted too: without it a passing test could not
    tell "the stamp was overwritten" from "the stamp never reached the row",
    which are opposite defects.
    """
    spring = next(c for c in YamlCatalogSource(catalogs_dir()).load() if c.id == "spring-graphql")
    payload = TypeRef(
        symbol="com/acme/orders/OrderFilter#",
        arguments=[],
        wire_type="object",
        wire_format="",
        nullable=True,
    )
    # One bare parameter (the catalog's `sole_unannotated` fallback marks it as
    # the body) and NO return type at all — a handler that takes something and
    # declares nothing on the way back.
    _annotated_facts(
        tmp_path / "facts",
        Signature(parameters=[Parameter(name="filter", type=payload)], returns=None),
    )
    workspace = _workspace(
        tmp_path, _shape("Roots", _field("orders", shape_ref="Order"), role="query")
    )
    capabilities = {"annotation_args", "type_annotations", "typed_signatures"}

    derive_endpoints(workspace, [_catalog(), spring], capabilities=capabilities)
    seeded = _rows(workspace)
    stamped = seeded[0]["response_shape"]
    derive_endpoint_shapes(workspace, [_catalog(), spring], capabilities=capabilities)
    final = _rows(workspace)[0]
    workspace.close()

    # One row, and it is the ANNOTATION's — otherwise this would be a test
    # about the schema's own row, which the contracts pass never touches.
    assert [row["catalog_id"] for row in seeded] == ["spring-graphql"]
    # The stamp DID reach that row: the schema's own declared type.
    assert json.loads(str(stamped))["shape_id"] == "Order"
    # And the shape pass then re-answered the row from its own signature: a
    # request it really declares, and no response at all.
    assert json.loads(str(final["request_shape"]))["shape_id"] == "com/acme/orders/OrderFilter#"
    assert final["response_shape"] is None


def test_deterministic(tmp_path: Path):
    """NFR-1: two resolves over one fact tree are the same answer, down to the
    bytes of every column. The `declared_shapes` query's own ordering and the
    pass's dedup are what make that true — a `set` anywhere on this path would
    reorder rows between runs."""
    shapes = (
        _shape("Roots", _field("orders"), _field("orderById"), role="query"),
        _shape("Writes", _field("placeOrder"), role="mutation"),
    )
    answers = []
    for run in ("a", "b"):
        workspace = _workspace(tmp_path / run, *shapes)
        _run(workspace, _catalog())
        answers.append(json.dumps(_rows(workspace), sort_keys=True, default=str))
        workspace.close()

    assert answers[0] == answers[1]


def test_a_catalog_declaring_no_operations_block_is_refused_by_file(tmp_path: Path):
    workspace = _workspace(tmp_path, _shape("Roots", _field("orders"), role="query"))
    catalog = Catalog(
        id="broken",
        style="schema_operations",
        protocol="graphql",
        direction="inbound",
        requires=(),
        matches={},
        source=Path("tests/broken.yml"),
    )

    with pytest.raises(CatalogError, match="schema_operations"):
        schema_operations.run(workspace, catalog)
    workspace.close()


@pytest.mark.parametrize(
    ("block", "expected"),
    [
        ({"schema_format": "", "operations": {"query": "query"}}, "schema_format"),
        ({"schema_format": FORMAT, "operations": {}}, "operations"),
        ({"schema_format": FORMAT, "operations": {"query": ""}}, "operations"),
        ({"schema_format": FORMAT, "operations": ["query"]}, "operations"),
    ],
)
def test_a_broken_operations_block_is_refused_before_anything_is_read(
    tmp_path: Path, block: dict[str, object], expected: str
):
    """Every value below reaches either a derived row's identity columns or
    the fact filter that decides which shapes this catalog speaks for, where a
    typo is indistinguishable from an observation."""
    workspace = _workspace(tmp_path, _shape("Roots", _field("orders"), role="query"))
    catalog = Catalog(
        id="broken",
        style="schema_operations",
        protocol="graphql",
        direction="inbound",
        requires=(),
        matches={"schema_operations": block},
        source=Path("tests/broken.yml"),
    )

    with pytest.raises(CatalogError, match=expected):
        schema_operations.run(workspace, catalog)
    workspace.close()


def test_the_shipped_catalog_declares_the_style_the_protocol_and_the_fixed_format():
    """The one shipped `schema_operations` catalog, read off the file: it owns
    `graphql` without owning a framework, which is why it carries rung 1's
    `format_fixed` like the three annotation catalogs do — a schema-first
    module pulls none of them in, and rung 4 would otherwise stamp the
    schema's own format name into a column D00 closes at six values.

    Rung 4 no longer publishes such a value at all (`resolve/format.py`'s
    `_WIRE_FORMATS`, review round 1), so this entry is now belt as well as
    braces — but it is what makes a schema-first module's rows read `json` at
    `resolved` instead of falling to `unresolved`, which is a different and
    still necessary claim."""
    catalog = next(c for c in YamlCatalogSource(catalogs_dir()).load() if c.id == "graphql-schema")

    assert catalog.style == "schema_operations"
    assert (catalog.protocol, catalog.direction) == ("graphql", "inbound")
    assert catalog.requires == ()
    assert catalog.format_fixed == {"graphql": "json"}
    assert catalog.matches["schema_operations"] == {
        "schema_format": "graphql",
        "operations": {"query": "query", "mutation": "mutation", "subscription": "subscription"},
    }


# ---------------------------------------------------------------------------
# 2I Task 4: `role == "operation"` derives one row per SHAPE, never per
# field — the WSDL case, where the input element's shape IS the operation
# (2I Task 3) rather than a root type whose fields are operations. `wsdl` is
# the one real schema format this role is ever set on; every symbol and field
# name below is still invented, same as every test above (this file's own
# docstring rule) — the exact live QNames
# (`{http://orders.example.com/ws}placeOrderRequest`/`quoteOrderRequest`) are
# pinned against the real fixture in `test_pipeline.py` and
# `tests/e2e/test_vertical_slice.py`, not here.
# ---------------------------------------------------------------------------


def test_an_operation_role_shape_derives_one_row_from_itself(tmp_path: Path):
    """The whole ruling this task adds (2I design §3/§4): a WSDL input
    element's shape IS the operation, so the row derives from the SHAPE
    itself, never from one of its fields. `path` is the shape's own schema
    name — `symbol` here, since `declared_shapes` does not select
    `schema_name` and a schema-only fact writes the two identically
    (`wsdl_xsd.py`'s own `_add_shape`); `method` is NULL, SOAP being verbless
    like every other non-HTTP protocol (D02 §2, amended); and
    `request_shape` self-references the shape by `shape_id` — the wrapper is
    wire-true (2I design §4), unlike a GraphQL root field's un-projected
    arguments, which is why the per-field branch above always leaves this
    column NULL and this branch never does."""
    workspace = _workspace(
        tmp_path,
        _shape(
            "{urn:invented}Op",
            _field("sku"),
            _field("count"),
            role="operation",
            schema_format=WSDL_FORMAT,
        ),
    )
    _run(
        workspace,
        _catalog(operations={"operation": "operation"}, schema_format=WSDL_FORMAT, protocol="soap"),
    )
    rows = _rows(workspace)
    workspace.close()

    assert len(rows) == 1
    row = rows[0]
    assert (row["protocol"], row["method"], row["path"]) == ("soap", None, "{urn:invented}Op")
    assert (row["evidence"], row["resolution"]) == ("declared", "resolved")
    assert row["handler"] is None and row["caller"] is None
    # No stamp reaches this branch at all (2I Task 3 marks INPUT elements
    # only, so no fact links an operation to an output message) — the
    # boundary this task states rather than guesses past.
    assert row["response_shape"] is None
    assert json.loads(str(row["request_shape"])) == {
        "wire_type": "object",
        "wire_format": None,
        "nullable": False,
        "shape_id": "{urn:invented}Op",
    }


def test_an_operation_roles_fields_derive_no_rows_of_their_own(tmp_path: Path):
    """The per-shape-not-per-field pin: deriving one row per FIELD (the
    branch immediately below, for `query`/`mutation`/`subscription`) would
    mint an endpoint per element of the request body — the same defect a
    per-field pass over an ordinary payload type would commit. Two fields,
    one row, and neither field's own name appears as a `path` anywhere."""
    workspace = _workspace(
        tmp_path,
        _shape(
            "{urn:invented}Op",
            _field("sku"),
            _field("count"),
            role="operation",
            schema_format=WSDL_FORMAT,
        ),
    )
    _run(
        workspace,
        _catalog(operations={"operation": "operation"}, schema_format=WSDL_FORMAT, protocol="soap"),
    )
    rows = _rows(workspace)
    workspace.close()

    assert {str(r["path"]) for r in rows} == {"{urn:invented}Op"}


def test_an_operation_role_shape_of_another_schema_format_derives_nothing(tmp_path: Path):
    """The format gate runs BEFORE the `role == "operation"` branch, not
    after it — `test_a_root_declared_by_another_schema_format_derives_
    nothing`'s own case, for the one role that fix round 1 flagged as
    unpinned: a shape carrying the literal role string `"operation"` derives
    no row through `wsdl-schema.yml` when its OWN `schema_format` is not
    `wsdl`. `role` is neutral across every format (D00 §5); nothing about the
    role's spelling exempts it from the gate every other role already meets."""
    workspace = _workspace(
        tmp_path,
        _shape("{urn:invented}Op", _field("sku"), role="operation", schema_format=FORMAT),
    )
    _run(
        workspace,
        _catalog(operations={"operation": "operation"}, schema_format=WSDL_FORMAT, protocol="soap"),
    )
    rows = _rows(workspace)
    workspace.close()

    assert rows == []


def test_a_query_role_shape_beside_an_operation_role_shape_still_derives_per_field(
    tmp_path: Path,
):
    """The graphql regression this task must not touch, proven in the
    presence of the new branch rather than merely beside it (the brief's own
    contrast case): one catalog run holding both a `query`-role shape
    (per-field, the pre-existing behaviour) and an `operation`-role shape
    (per-shape, this task's own) derives BOTH correctly, byte-identical to
    what the per-field branch alone would produce, and neither leaks a row
    into the other's identity space."""
    workspace = _workspace(
        tmp_path,
        _shape(
            "Roots", _field("orders"), _field("orderById"), role="query", schema_format=WSDL_FORMAT
        ),
        _shape("{urn:invented}Op", _field("sku"), role="operation", schema_format=WSDL_FORMAT),
    )
    _run(
        workspace,
        _catalog(
            operations={"query": "query", "operation": "operation"},
            schema_format=WSDL_FORMAT,
            protocol="soap",
        ),
    )
    rows = _rows(workspace)
    workspace.close()

    assert {(r["method"], r["path"]) for r in rows} == {
        ("query", "orders"),
        ("query", "orderById"),
        (None, "{urn:invented}Op"),
    }
    # The per-field rows keep the per-field branch's own answer exactly —
    # `request_shape` NULL, unlike the per-shape row beside them.
    assert all(r["request_shape"] is None for r in rows if r["method"] == "query")
    assert (
        json.loads(str(next(r["request_shape"] for r in rows if r["path"] == "{urn:invented}Op")))[
            "shape_id"
        ]
        == "{urn:invented}Op"
    )


def test_agreement_a_pre_existing_annotation_row_blocks_the_operation_twin(tmp_path: Path):
    """First-writer, through the same insert-if-absent guard the per-field
    branch already meets (`test_agreement_annotation_wins_identity`'s own
    precedent) — and the live case this exercises: `wsdl-schema.yml`'s
    `{http://orders.example.com/ws}placeOrderRequest` row is blocked by
    `spring-ws.yml`'s own `@PayloadRoot` row at that identity (2I Task 2), so
    only `quoteOrderRequest` — which carries no annotation twin — becomes a
    new row live (pinned in `test_pipeline.py` /
    `tests/e2e/test_vertical_slice.py`). Here: one shape, one pre-existing
    row at its identity, and the schema-derived twin never lands."""
    workspace = _workspace(
        tmp_path,
        _shape("{urn:invented}Op", _field("sku"), role="operation", schema_format=WSDL_FORMAT),
    )
    existing = _annotation_row(None, "{urn:invented}Op", protocol="soap", catalog_id="spring-ws")
    _run(
        workspace,
        _catalog(operations={"operation": "operation"}, schema_format=WSDL_FORMAT, protocol="soap"),
        existing,
    )
    rows = _rows(workspace)
    workspace.close()

    assert len(rows) == 1
    assert rows[0]["catalog_id"] == "spring-ws"
    assert rows[0]["handler"] == "com/acme/orders/Resolvers#orders(sig_1)."


def test_the_shipped_wsdl_catalog_declares_the_style_the_protocol_and_the_fixed_format():
    """The one shipped `schema_operations` catalog for SOAP, read off the
    file: same shape as `graphql-schema.yml`'s own regression pin above, and
    the second live proof (2I design §1) that rung 1's `format_fixed`
    mechanism is protocol-generic rather than a GraphQL special case."""
    catalog = next(c for c in YamlCatalogSource(catalogs_dir()).load() if c.id == "wsdl-schema")

    assert catalog.style == "schema_operations"
    assert (catalog.protocol, catalog.direction) == ("soap", "inbound")
    assert catalog.requires == ()
    assert catalog.format_fixed == {"soap": "xml"}
    assert catalog.matches["schema_operations"] == {
        "schema_format": "wsdl",
        "operations": {"operation": "operation"},
    }
