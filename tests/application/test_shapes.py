import json
import re
from pathlib import Path

from shape_helpers import (
    KOTLIN_ORDER,
    ORDER_REQUEST,
    ORDER_STATUS,
    ORDER_VIEW,
    SCOPED_REQUEST,
    SPRING_WRAPPERS,
    field_of,
    mono_of,
    response_entity_of,
    shape_fields_of,
    shape_of,
    type_ref,
    unknown_box_of,
)

from sextant.application.ports.catalogs import Catalog
from sextant.application.resolve.endpoints import derive_endpoints
from sextant.application.resolve.shapes import (
    ExpandedShapes,
    derive_endpoint_shapes,
    derive_shapes,
    root_type,
)
from sextant.application.resolve.shapes.contracts import _body_type, _contracts_of, _owns
from sextant.application.resolve.shapes.expansion import _rules_of
from sextant.application.resolve.shapes.nullability import _scope_nullable
from sextant.domain.closed_sets import OriginTier
from sextant.domain.facts import DeclaredFieldFact, DeclaredShapeFact, Document
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.resources import catalogs_dir
from sextant.storage.duckdb.workspace import DuckDbWorkspace


def _body_catalog() -> Catalog:
    """The smallest catalog `_body_type` reads: one `request_body` marker."""
    return Catalog(
        id="generic-body",
        style="annotation_driven",
        protocol="http",
        direction="inbound",
        requires=(),
        matches={"request_body": {"annotation": "org.example.Body"}},
        source=Path("tests/invented.yml"),
    )


def test_a_body_parameter_that_is_a_type_variable_roots_no_shape():
    """W5: reading the `Signature` attribute makes `@RequestBody T body` on a
    generic base controller report the symbol `T`.

    A shape is identified BY its symbol, and a type variable's name means
    something only inside the declaration that introduced it. Rooting here would
    mint a shape whose id is `T`, and every unrelated `T` anywhere in the module
    collides onto that one id — a single shape claiming to describe several
    unrelated payloads, which is worse than describing none. §8.1 rule 2: no
    answer beats a wrong one.
    """
    catalog = _body_catalog()
    signature = {
        "parameters": [
            {
                "annotations": [{"annotation": "org/example/Body#", "args": {}}],
                "type": {"symbol": "T", "arguments": [], "wire_type": "object"},
                "erased_symbol": "java/lang/Object#",
            }
        ]
    }

    assert _body_type(signature, catalog) is None


def test_a_body_parameter_that_names_a_real_type_still_roots_its_shape():
    """The paired positive, so the rule above cannot be satisfied by refusing
    everything: the same shape with a real symbol still returns its reference,
    type arguments included — which is the whole point of reading the signature."""
    catalog = _body_catalog()
    signature = {
        "parameters": [
            {
                "annotations": [{"annotation": "org/example/Body#", "args": {}}],
                "type": {
                    "symbol": "java/util/List#",
                    "arguments": [{"symbol": "com/acme/OrderEvent#", "arguments": []}],
                    "wire_type": "array",
                },
                "erased_symbol": "java/util/List#",
            }
        ]
    }

    rooted = _body_type(signature, catalog)

    assert rooted is not None
    assert rooted["symbol"] == "java/util/List#"
    assert rooted["arguments"][0]["symbol"] == "com/acme/OrderEvent#"


def test_unwraps_recursively_to_the_payload_type():
    rooted = root_type(mono_of(response_entity_of(ORDER_VIEW)), SPRING_WRAPPERS)
    assert rooted.symbol == "com/acme/orders/contracts/OrderView#"
    assert rooted.chain == ("async", "http_envelope")
    assert rooted.unmatched_wrapper is False


def test_stops_at_an_unfamiliar_wrapper_and_says_so():
    """An incomplete catalog must degrade visibly. Rooting at the payload of a
    wrapper nobody declared would be a guess presented as an observation."""
    rooted = root_type(unknown_box_of(ORDER_VIEW), SPRING_WRAPPERS)
    assert rooted.symbol == "com/acme/UnknownBox#"
    assert rooted.unmatched_wrapper is True


def test_a_bare_payload_type_is_not_flagged_as_an_unmatched_wrapper():
    """`OrderView` carries no type arguments, so it never looked like an
    envelope in the first place — it is the root, not a gap in the catalog."""
    rooted = root_type(ORDER_VIEW, SPRING_WRAPPERS)
    assert rooted.symbol == "com/acme/orders/contracts/OrderView#"
    assert rooted.chain == ()
    assert rooted.unmatched_wrapper is False


# --- Expansion (Task 10) -----------------------------------------------------

# The module prefix every symbol in a fact file carries (D00 §5a). The
# descriptor — everything after the last space — is what a type reference and a
# shape_id are keyed on.
_MODULE = "sextant-jvm maven com.acme/orders-service 1.0.0 "

SQL_DIR = Path(__file__).parents[2] / "src" / "sextant" / "storage" / "duckdb"

CUSTOMER_REF = "com/acme/orders/contracts/CustomerRef#"
ORDER_VIEW_SHAPE = "com/acme/orders/contracts/OrderView#"

# Hand-rolled rather than loaded from `spring-web.yml`, so the pass is exercised
# against the catalog *shape* D02 declares and not against one framework's file.
# Dotted names throughout: converting them is the pass's job.
_CATALOG = Catalog(
    id="invented-serializer",
    style="annotation_driven",
    protocol="http",
    direction="inbound",
    requires=(),
    matches={},
    source=Path("tests/invented.yml"),
    wrappers=SPRING_WRAPPERS,
    nullability={
        "nullable": ["org.jspecify.annotations.Nullable"],
        "not_null": ["org.jspecify.annotations.NonNull"],
        "scope": [
            {"annotation": "org.jspecify.annotations.NullMarked", "means": "not_null_by_default"}
        ],
    },
    serialization={
        "name_from": [
            {"annotation": "com.fasterxml.jackson.annotation.JsonProperty", "arg": "value"}
        ],
        "ignore": ["com.fasterxml.jackson.annotation.JsonIgnore"],
        "default_strategy": "as_declared",
    },
    known_types=[
        {"type": "java.time.Instant", "wire": "string", "format": "date-time"},
        {"type": "java.math.BigDecimal", "wire": "number"},
    ],
)


def _ref(
    symbol: str, wire_type: str, wire_format: str = "", *, nullable=True, arguments=()
) -> dict:
    """One level of the augmented type reference the extractor emits: D00 §5a's
    {symbol, arguments} envelope plus D1's wire projection and D3's nullability,
    at every level of the chain."""
    return {
        "symbol": symbol,
        "arguments": list(arguments),
        "wire_type": wire_type,
        "wire_format": wire_format,
        "nullable": nullable,
        "nullable_resolution": "resolved",
    }


def _string() -> dict:
    return _ref("java/lang/String#", "string")


def _document(document_id: str, relative_path: str) -> Document:
    return Document(
        document_id=document_id,
        relative_path=relative_path,
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


def _type(document_id: str, owner: str, construct_kind: str = "class") -> dict:
    return {
        "kind": "symbol",
        "document_id": document_id,
        "symbol": _MODULE + owner,
        "construct_kind": construct_kind,
        "enclosing": None,
        "signature": None,
        "visibility": "public",
        "line_start": 0,
        "line_end": 0,
    }


def _field(
    document_id: str,
    owner: str,
    name: str,
    returns: dict,
    *,
    static: bool = False,
    transient: bool = False,
) -> dict:
    """One field fact. `modifiers` carries what only the declaring language can
    say about whether the field reaches a payload at all — bound to the type
    rather than an instance, or declared not serialized."""
    return {
        "kind": "symbol",
        "document_id": document_id,
        "symbol": _MODULE + owner + name + ".",
        "construct_kind": "field",
        "enclosing": _MODULE + owner,
        "signature": {"returns": returns},
        "visibility": "public",
        "modifiers": {"static": static, "transient": transient},
        "line_start": 0,
        "line_end": 0,
    }


def _annotation(document_id: str, target: str, annotation: str, args: dict, **extra) -> dict:
    return {
        "kind": "annotation",
        "document_id": document_id,
        "target": target,
        "use": {"annotation": annotation, "args": args},
        "retention": "runtime",
        **extra,
    }


def _write(path: Path, document: Document, facts: list[dict]) -> None:
    """Writes the fact file by hand: the augmented type references the extractor
    emits carry `wire_type` and `nullable` at every level, which the domain's
    `TypeRef` model does not model — and widening it is not this task's change.
    The loader stores `payload` verbatim and validates nothing, so this is the
    same bytes a real scan produces."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [document.model_dump(mode="json"), *facts]
    path.write_text(
        "\n".join(json.dumps(line, sort_keys=True, separators=(",", ":")) for line in lines) + "\n",
        encoding="utf-8",
    )


def _contract_facts(root: Path) -> None:
    """Mirrors `fixtures/orders-service`'s contracts classes verbatim — the same
    symbols, the same annotations, and the `signature.returns` JSON exactly as
    the extractor writes it. Reading the built fixture from a unit test is what
    Task 3 got wrong; the facts are restated here instead."""
    request = _document("doc_request", "com/acme/orders/contracts/OrderRequest.java")
    request_facts = [
        _type("doc_request", ORDER_REQUEST),
        _field("doc_request", ORDER_REQUEST, "reference", _string()),
        _field("doc_request", ORDER_REQUEST, "note", _string()),
        _field("doc_request", ORDER_REQUEST, "customerId", _string()),
        _field(
            "doc_request",
            ORDER_REQUEST,
            "note2",
            _ref("java/util/Optional#", "object", arguments=[_string()]),
        ),
        _field("doc_request", ORDER_REQUEST, "internalTrace", _string()),
        _field("doc_request", ORDER_REQUEST, "customer", _ref(CUSTOMER_REF, "object")),
        _field(
            "doc_request",
            ORDER_REQUEST,
            "alternates",
            _ref("java/util/List#", "array", arguments=[_ref(CUSTOMER_REF, "object")]),
        ),
        _field(
            "doc_request", ORDER_REQUEST, "total", _ref("long#", "integer", "int64", nullable=False)
        ),
        _field(
            "doc_request", ORDER_REQUEST, "totalAmount", _ref("java/math/BigDecimal#", "object")
        ),
        # An enumeration reference is an `object` to the extractor — nothing in
        # the reference itself can say otherwise. Only ORDER_STATUS's own
        # symbol fact, below, carries the construct kind that decides it.
        _field("doc_request", ORDER_REQUEST, "status", _ref(ORDER_STATUS, "object")),
        _field("doc_request", ORDER_REQUEST, "SOURCE", _string(), static=True),
        _field("doc_request", ORDER_REQUEST, "cachedSummary", _string(), transient=True),
        _annotation(
            "doc_request",
            _MODULE + ORDER_REQUEST + "note.",
            "org/jspecify/annotations/Nullable#",
            {},
            type_path="",
        ),
        _annotation(
            "doc_request",
            _MODULE + ORDER_REQUEST + "customerId.",
            "com/fasterxml/jackson/annotation/JsonProperty#",
            {"value": "customer_id"},
        ),
        _annotation(
            "doc_request",
            _MODULE + ORDER_REQUEST + "customerId.",
            "org/jspecify/annotations/NonNull#",
            {},
            type_path="",
        ),
        _annotation(
            "doc_request",
            _MODULE + ORDER_REQUEST + "internalTrace.",
            "com/fasterxml/jackson/annotation/JsonIgnore#",
            {},
        ),
        _annotation(
            "doc_request",
            _MODULE + ORDER_REQUEST + "totalAmount.",
            "com/fasterxml/jackson/annotation/JsonProperty#",
            {"value": "total_amount"},
        ),
    ]
    _write(root / "OrderRequest.jsonl", request, request_facts)

    customer = _document("doc_customer", "com/acme/orders/contracts/CustomerRef.java")
    _write(
        root / "CustomerRef.jsonl",
        customer,
        [
            _type("doc_customer", CUSTOMER_REF),
            _field("doc_customer", CUSTOMER_REF, "id", _string()),
            _field("doc_customer", CUSTOMER_REF, "name", _string()),
        ],
    )

    # The enumeration `OrderRequest.status` points at, as the extractor writes
    # it: the type's own construct kind, and its constants as ordinary field
    # facts bound to the type. The compiler's `$VALUES` array is absent because
    # nobody declared it.
    status = _document("doc_status", "com/acme/orders/contracts/OrderStatus.java")
    _write(
        root / "OrderStatus.jsonl",
        status,
        [
            _type("doc_status", ORDER_STATUS, construct_kind="enum"),
            _field("doc_status", ORDER_STATUS, "NEW", _ref(ORDER_STATUS, "object"), static=True),
            _field("doc_status", ORDER_STATUS, "DONE", _ref(ORDER_STATUS, "object"), static=True),
        ],
    )

    view = _document("doc_view", "com/acme/orders/contracts/OrderView.java")
    _write(
        root / "OrderView.jsonl",
        view,
        [
            _type("doc_view", ORDER_VIEW_SHAPE),
            _field("doc_view", ORDER_VIEW_SHAPE, "id", _string()),
            _field(
                "doc_view",
                ORDER_VIEW_SHAPE,
                "headers",
                _ref("org/springframework/http/HttpHeaders#", "object"),
            ),
        ],
    )

    # A type whose fields arrive already resolved by the language's own type
    # system (Task 5's projection onto the shared field) rather than Java's
    # permissive default — no annotation involved either way.
    kotlin_order = _document("doc_kotlin_order", "com/acme/orders/contracts/KotlinOrder.kt")
    _write(
        root / "KotlinOrder.jsonl",
        kotlin_order,
        [
            _type("doc_kotlin_order", KOTLIN_ORDER),
            _field("doc_kotlin_order", KOTLIN_ORDER, "note", _string()),
            _field(
                "doc_kotlin_order",
                KOTLIN_ORDER,
                "id",
                _ref("java/lang/String#", "string", nullable=False),
            ),
        ],
    )

    # `code` carries no annotation of its own; the package it lives in does —
    # the scope declaration a `@NullMarked` package-info compiles onto a
    # synthetic file-class symbol for (D02 §2e).
    scoped_request = _document("doc_scoped", "com/acme/orders/scoped/ScopedRequest.java")
    _write(
        root / "ScopedRequest.jsonl",
        scoped_request,
        [
            _type("doc_scoped", SCOPED_REQUEST),
            _field("doc_scoped", SCOPED_REQUEST, "code", _string()),
            _annotation(
                "doc_scoped",
                _MODULE + "com/acme/orders/scoped/package-info#",
                "org/jspecify/annotations/NullMarked#",
                {},
            ),
        ],
    )


def _loaded_workspace(tmp_path: Path) -> DuckDbWorkspace:
    _contract_facts(tmp_path / "facts")
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(tmp_path / "facts")
    return workspace


def _expanded_workspace(tmp_path: Path, roots: list[str]) -> DuckDbWorkspace:
    workspace = _loaded_workspace(tmp_path)
    derive_shapes(workspace, _CATALOG, roots)
    return workspace


def _expand(tmp_path: Path, roots: list[str]) -> ExpandedShapes:
    workspace = _loaded_workspace(tmp_path)
    result = derive_shapes(workspace, _CATALOG, roots)
    workspace.close()
    return result


def test_expands_a_rooted_type_into_its_wire_fields(tmp_path):
    ws = _expanded_workspace(tmp_path, roots=[ORDER_REQUEST])
    fields = shape_fields_of(ws, ORDER_REQUEST)
    names = [f["wire_name"] for f in fields]
    assert "customer_id" in names  # @JsonProperty wins over the source name
    assert "customerId" not in names  # the source name is never the identity
    assert "internalTrace" not in names  # @JsonIgnore produces no field at all
    assert next(f for f in fields if f["wire_name"] == "total")["wire_format"] == "int64"


def test_a_collection_field_records_what_it_holds(tmp_path):
    """`List<String>` and `List<CustomerRef>` are both `array`. Without the
    element descriptor DR-5 matches a caller sending strings against a callee
    expecting records — a fabricated link, which is the failure the whole
    payload-comparison rule exists to prevent."""
    ws = _expanded_workspace(tmp_path, roots=[ORDER_REQUEST])
    field = field_of(ws, ORDER_REQUEST, "alternates")

    assert field["wire_type"] == "array"
    assert json.loads(field["item"])["shape_id"] == "com/acme/orders/contracts/CustomerRef#"


def test_a_known_type_is_mapped_to_its_wire_form_and_never_expanded(tmp_path):
    """Expanding BigDecimal yields intVal, scale, intCompact and precision —
    internal machinery, none of it on the wire, producing a shape no real
    payload could match."""
    ws = _expanded_workspace(tmp_path, roots=[ORDER_REQUEST])
    field = field_of(ws, ORDER_REQUEST, "total_amount")
    assert field["wire_type"] == "number"
    # Mapped, never expanded: no shape exists for it, open or otherwise.
    assert not any(s["shape_id"] == "java/math/BigDecimal#" for s in ws.query("shapes"))


def test_expansion_stops_at_an_unknown_third_party_type_and_marks_the_shape_open(tmp_path):
    ws = _expanded_workspace(tmp_path, roots=["com/acme/orders/contracts/OrderView#"])
    assert shape_of(ws, "com/acme/orders/contracts/OrderView#")["open"] is True


def test_the_report_names_the_type_that_stopped_expansion(tmp_path):
    """The catalog grows from observation. A gap nobody can see is a gap
    nobody closes."""
    result = _expand(tmp_path, roots=["com/acme/orders/contracts/OrderView#"])
    assert "org/springframework/http/HttpHeaders#" in result.unexpanded_types


def test_a_nested_object_field_carries_the_shape_it_references(tmp_path):
    """Nothing else links a field to the shape holding its fields (ruling F3):
    `wire_type: object` alone says a record is there, not which record."""
    ws = _expanded_workspace(tmp_path, roots=[ORDER_REQUEST])
    field = field_of(ws, ORDER_REQUEST, "customer")

    # D01 §5 states one item grammar, {wire_type, wire_format, nullable,
    # shape_id?, item?}. An object field's item is that same descriptor, not a
    # shorter one a consumer would have to detect before it could read.
    assert json.loads(field["item"]) == {
        "wire_type": "object",
        "wire_format": "",
        "nullable": True,
        "shape_id": CUSTOMER_REF,
    }
    assert shape_of(ws, CUSTOMER_REF)["open"] is False
    assert [f["wire_name"] for f in shape_fields_of(ws, CUSTOMER_REF)] == ["id", "name"]


def test_a_field_inside_a_declared_wrapper_is_rooted_before_it_is_described(tmp_path):
    """Without rule 3 `Optional<String>` reaches rule 5 as an unknown generic,
    and a shape covering every field is wrongly marked open."""
    ws = _expanded_workspace(tmp_path, roots=[ORDER_REQUEST])

    assert field_of(ws, ORDER_REQUEST, "note2")["wire_type"] == "string"
    assert shape_of(ws, ORDER_REQUEST)["open"] is False


def test_field_order_is_declaration_order_and_the_hash_follows_it(tmp_path):
    """`ordinal` comes from the order the field facts were declared in, never
    from a set or a dictionary — two runs that disagree on it produce two
    different content hashes for the same type (NFR-1)."""
    ws = _expanded_workspace(tmp_path, roots=[ORDER_REQUEST])

    assert [f["wire_name"] for f in shape_fields_of(ws, ORDER_REQUEST)] == [
        "reference",
        "note",
        "customer_id",
        "note2",
        "customer",
        "alternates",
        "total",
        "total_amount",
        "status",
    ]
    assert shape_of(ws, ORDER_REQUEST)["content_hash"].startswith("md5:")


def test_a_field_bound_to_the_type_is_not_a_field_of_the_payload(tmp_path):
    """A constant is a declaration, so the fact exists — but no instance of the
    type carries it, and a shape_field for it publishes a contract term nobody
    wrote. The pass cannot tell it from a payload field on its own: the
    modifier the language recorded is the only evidence there is."""
    ws = _expanded_workspace(tmp_path, roots=[ORDER_REQUEST])
    assert "SOURCE" not in [f["wire_name"] for f in shape_fields_of(ws, ORDER_REQUEST)]


def test_a_field_the_language_declares_as_not_serialized_reaches_no_payload(tmp_path):
    """The same exclusion, from a declaration rather than from staticness — and
    excluded outright rather than recorded absent, exactly as an ignored field
    is: DR-5 would otherwise compare it against a peer that correctly omits
    it."""
    ws = _expanded_workspace(tmp_path, roots=[ORDER_REQUEST])
    assert "cachedSummary" not in [f["wire_name"] for f in shape_fields_of(ws, ORDER_REQUEST)]


def test_a_type_of_only_excluded_fields_is_still_a_settled_shape(tmp_path):
    """Excluding every field of a scanned type is not the same as never having
    seen it. Filtered where the rows are built rather than where the facts are
    grouped, so the type stays expandable: dropped earlier it would be reported
    as a gap in the catalog, which is a gap nobody can close."""
    owner = "com/acme/orders/contracts/Constants#"
    root = tmp_path / "facts"
    _contract_facts(root)
    _write(
        root / "Constants.jsonl",
        _document("doc_constants", "com/acme/orders/contracts/Constants.java"),
        [
            _type("doc_constants", owner),
            _field("doc_constants", owner, "SOURCE", _string(), static=True),
        ],
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(root)
    result = derive_shapes(workspace, _CATALOG, [owner])

    assert shape_fields_of(workspace, owner) == []
    assert shape_of(workspace, owner)["open"] is False
    assert owner not in result.unexpanded_types


def test_an_enumeration_is_mapped_to_its_wire_type_and_never_expanded(tmp_path):
    """A closed set of constants is one value on the wire (D00 §5b), not a
    record. Expanded structurally it contributes NEW and DONE as payload
    fields; left as an unrecognised `object` it marks its owner open and is
    reported as a gap the catalog cannot close, because there is nothing wrong
    with it. Only the enumeration's own construct kind separates the three, and
    that is generic fact data, not language knowledge."""
    ws = _expanded_workspace(tmp_path, roots=[ORDER_REQUEST])
    field = field_of(ws, ORDER_REQUEST, "status")

    assert field["wire_type"] == "enum"
    assert field["item"] is None
    assert not any(s["shape_id"] == ORDER_STATUS for s in ws.query("shapes"))
    assert shape_of(ws, ORDER_REQUEST)["open"] is False


def test_an_enumeration_is_not_reported_as_a_type_expansion_could_not_open(tmp_path):
    """The unexpanded report is where a catalog grows from observation, so it
    must name only gaps somebody could act on. An enumeration is fully
    described; naming it would be noise burying the entries that are missing."""
    result = _expand(tmp_path, roots=[ORDER_REQUEST])
    assert ORDER_STATUS not in result.unexpanded_types


def test_the_default_strategy_names_a_field_no_annotation_names(tmp_path):
    """`default_strategy` is a declaration a module's own configuration may
    override, so a name derived from it is `declared` and never observed
    (D02 §2f). Dropping `name_from` is what puts `customerId` on that path."""
    declared = Catalog(
        **{
            **vars(_CATALOG),
            "serialization": {
                **_CATALOG.serialization,
                "name_from": [],
                "default_strategy": "snake_case",
            },
        }
    )
    workspace = _loaded_workspace(tmp_path)
    derive_shapes(workspace, declared, [ORDER_REQUEST])

    assert field_of(workspace, ORDER_REQUEST, "customer_id")["evidence"] == "declared"
    assert field_of(workspace, ORDER_REQUEST, "total_amount")["evidence"] == "declared"


def test_an_annotated_wire_name_carries_the_evidence_of_the_code_that_declared_it(tmp_path):
    ws = _expanded_workspace(tmp_path, roots=[ORDER_REQUEST])
    assert field_of(ws, ORDER_REQUEST, "customer_id")["evidence"] == "compiler"
    assert field_of(ws, ORDER_REQUEST, "reference")["evidence"] == "declared"


def test_a_second_catalog_leaves_an_existing_shapes_field_list_whole(tmp_path):
    """D02 §5 lets two catalogs both run, and the second must not edit the
    first's answer. Insert-if-absent per (shape_id, ordinal) rather than per
    shape appends the surplus of whichever catalog yields more fields, leaving
    a list no catalog produced and a content_hash describing neither — and DR-5
    compares that list."""
    permissive = Catalog(**{**vars(_CATALOG), "id": "invented-permissive", "serialization": {}})
    workspace = _loaded_workspace(tmp_path)
    derive_shapes(workspace, _CATALOG, [ORDER_REQUEST])
    settled = shape_fields_of(workspace, ORDER_REQUEST)
    hash_before = shape_of(workspace, ORDER_REQUEST)["content_hash"]

    # This catalog ignores nothing and renames nothing: on its own it would
    # yield ten fields, `internalTrace` among them.
    derive_shapes(workspace, permissive, [ORDER_REQUEST])

    assert shape_fields_of(workspace, ORDER_REQUEST) == settled
    assert shape_of(workspace, ORDER_REQUEST)["content_hash"] == hash_before
    assert len([s for s in workspace.query("shapes") if s["shape_id"] == ORDER_REQUEST]) == 1


def _array_facts(root: Path, owner: str, element: dict) -> None:
    """A type with one array field. The extractor keeps an array's element as
    the reference's single type argument, the same way `List<E>` does — the
    `[]` on the symbol is descriptor grammar, and reading it here would put
    language knowledge back in the language-blind half."""
    _write(
        root / "Arrays.jsonl",
        _document("doc_arrays", "com/acme/orders/contracts/Arrays.java"),
        [
            _type("doc_arrays", owner),
            _field(
                "doc_arrays",
                owner,
                "items",
                _ref(element["symbol"] + "[]", "array", arguments=[element]),
            ),
        ],
    )


def test_an_array_field_records_what_it_holds(tmp_path):
    """`CustomerRef[]` and `String[]` are both `array`. With the element left in
    the symbol suffix they are indistinguishable to every consumer — the same
    fabricated match `List<CustomerRef>` is protected from."""
    owner = "com/acme/orders/contracts/Alternates#"
    root = tmp_path / "facts"
    _contract_facts(root)
    _array_facts(root, owner, _ref(CUSTOMER_REF, "object"))
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(root)
    derive_shapes(workspace, _CATALOG, [owner])

    field = field_of(workspace, owner, "items")
    assert field["wire_type"] == "array"
    assert json.loads(field["item"])["shape_id"] == CUSTOMER_REF
    assert shape_of(workspace, CUSTOMER_REF)["open"] is False


def test_an_array_of_an_unexpandable_type_marks_the_shape_open_and_reports_it(tmp_path):
    """The element is subject to rules 4 and 5 exactly as any other type: a gap
    inside a collection is still a gap, and one that nobody can see is one
    nobody closes."""
    owner = "com/acme/orders/contracts/Headers#"
    unknown = "org/springframework/http/HttpHeaders#"
    root = tmp_path / "facts"
    _contract_facts(root)
    _array_facts(root, owner, _ref(unknown, "object"))
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(root)
    result = derive_shapes(workspace, _CATALOG, [owner])

    assert shape_of(workspace, owner)["open"] is True
    assert unknown in result.unexpanded_types


def test_a_type_that_refers_to_itself_terminates(tmp_path):
    """`object` is a reference to another shape, never an inlining, so a cycle
    needs no depth counter — but only while each shape is expanded once."""
    node = "com/acme/orders/contracts/Node#"
    root = tmp_path / "facts"
    _contract_facts(root)
    _write(
        root / "Node.jsonl",
        _document("doc_node", "com/acme/orders/contracts/Node.java"),
        [
            _type("doc_node", node),
            _field("doc_node", node, "parent", _ref(node, "object")),
        ],
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(root)
    derive_shapes(workspace, _CATALOG, [node])

    assert [s["shape_id"] for s in workspace.query("shapes")] == [node]
    assert json.loads(field_of(workspace, node, "parent")["item"])["shape_id"] == node


# --- Declared shapes (2G Task 5) ----------------------------------------------

# Bare descriptors in the generated-class grammar `JvmGeneratedNaming` builds
# (2G design §3) — a `declared_shape` fact's own `symbol`, and the lookup key
# expansion meets when a payload type reference names one. Mirrors the real
# fixture's `order.proto`/`common.proto` (OrderRequest.total_amount/count/
# price/lines, Money's cross-file reference, Line nested one level in).
PROTO_ORDER_REQUEST = "com/acme/orders/proto/OrderProtos$OrderRequest#"
PROTO_MONEY = "com/acme/orders/proto/CommonProtos$Money#"
PROTO_LINE = "com/acme/orders/proto/OrderProtos$OrderRequest$Line#"

# A type the scanner also reaches (bytecode fields exist for it, unlike the
# three symbols above) — the never-a-blend fixture: expansion must take only
# the declared shape's own field, never `internal`.
BLEND_TYPE = "com/acme/orders/proto/BlendType#"


def _declared_shape_facts(root: Path) -> None:
    """A hand-built `declared_shape`/`declared_field` universe standing in
    for the descriptor interpreter's own output (Task 2/4) — the same
    relationship `_contract_facts` bears to the real scanner."""
    order_fields = [
        DeclaredFieldFact(
            name="total_amount",
            wire_name="totalAmount",
            field_number=1,
            wire_type="string",
            required=True,
            nullable=False,
        ),
        DeclaredFieldFact(
            name="count",
            wire_name="explicitCount",
            field_number=2,
            wire_type="integer",
            wire_format="int32",
            required=True,
            nullable=False,
        ),
        # A cross-file reference (`price` is declared in order.proto, `Money`
        # in common.proto): `shape_ref` already carries Money's own symbol
        # (2G design §3, Task 2 decision 5), not the schema's full name — no
        # translation belongs in expansion.
        DeclaredFieldFact(
            name="price",
            wire_name="price",
            field_number=3,
            wire_type="object",
            required=False,
            nullable=True,
            shape_ref=PROTO_MONEY,
        ),
        DeclaredFieldFact(
            name="lines",
            wire_name="lines",
            field_number=4,
            wire_type="array",
            required=True,
            nullable=False,
            item={
                "wire_type": "object",
                "wire_format": None,
                "nullable": False,
                "shape_id": PROTO_LINE,
            },
        ),
    ]
    _write(
        root / "OrderProtos.jsonl",
        _document("doc_proto_order", "com/acme/orders/proto/OrderProtos.java"),
        [
            DeclaredShapeFact(
                document_id="doc_proto_order",
                symbol=PROTO_ORDER_REQUEST,
                schema_name="sextant.orders.OrderRequest",
                schema_format="protobuf",
                origin="compiled",
                evidence="compiler",
                fields=order_fields,
            ).model_dump(mode="json")
        ],
    )
    _write(
        root / "CommonProtos.jsonl",
        _document("doc_proto_money", "com/acme/orders/proto/CommonProtos.java"),
        [
            DeclaredShapeFact(
                document_id="doc_proto_money",
                symbol=PROTO_MONEY,
                schema_name="sextant.orders.Money",
                schema_format="protobuf",
                origin="compiled",
                evidence="compiler",
                fields=[
                    DeclaredFieldFact(
                        name="currency",
                        wire_name="currency",
                        field_number=1,
                        wire_type="string",
                        required=True,
                        nullable=False,
                    ),
                    DeclaredFieldFact(
                        name="amount_minor",
                        wire_name="amountMinor",
                        field_number=2,
                        wire_type="integer",
                        wire_format="int64",
                        required=True,
                        nullable=False,
                    ),
                ],
            ).model_dump(mode="json")
        ],
    )
    _write(
        root / "OrderProtosLine.jsonl",
        _document("doc_proto_line", "com/acme/orders/proto/OrderProtos$Line.java"),
        [
            DeclaredShapeFact(
                document_id="doc_proto_line",
                symbol=PROTO_LINE,
                schema_name="sextant.orders.OrderRequest.Line",
                schema_format="protobuf",
                origin="compiled",
                evidence="compiler",
                fields=[
                    DeclaredFieldFact(
                        name="sku",
                        wire_name="sku",
                        field_number=1,
                        wire_type="string",
                        required=True,
                        nullable=False,
                    )
                ],
            ).model_dump(mode="json")
        ],
    )
    _write(
        root / "BlendType.jsonl",
        _document("doc_blend", "com/acme/orders/proto/BlendType.java"),
        [
            # Bytecode fields — a real scanned class the descriptor interpreter
            # ALSO reached (a compiled schema class is a real compiled class).
            _type("doc_blend", BLEND_TYPE),
            _field("doc_blend", BLEND_TYPE, "internal", _string()),
            DeclaredShapeFact(
                document_id="doc_blend",
                symbol=BLEND_TYPE,
                schema_name="sextant.orders.BlendType",
                schema_format="protobuf",
                origin="compiled",
                evidence="compiler",
                fields=[
                    DeclaredFieldFact(
                        name="declaredOnly",
                        wire_name="declaredOnly",
                        field_number=1,
                        wire_type="string",
                        required=True,
                        nullable=False,
                    )
                ],
            ).model_dump(mode="json"),
        ],
    )


def _declared_workspace(tmp_path: Path, roots: list[str]) -> DuckDbWorkspace:
    root = tmp_path / "facts"
    _declared_shape_facts(root)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(root)
    derive_shapes(workspace, _CATALOG, roots)
    return workspace


def test_a_declared_shape_expands_to_exactly_its_own_fields(tmp_path):
    """D01 §5's `declared_shape` promise: `wire_name`, `field_number` and the
    wire vocabulary ride straight from the schema, never re-derived by the
    bytecode rules (naming strategy, nullability annotations) this catalog
    also declares."""
    ws = _declared_workspace(tmp_path, roots=[PROTO_ORDER_REQUEST])

    assert [f["wire_name"] for f in shape_fields_of(ws, PROTO_ORDER_REQUEST)] == [
        "totalAmount",
        "explicitCount",
        "price",
        "lines",
    ]
    total = field_of(ws, PROTO_ORDER_REQUEST, "totalAmount")
    assert total["field_number"] == 1
    assert total["wire_type"] == "string"
    count = field_of(ws, PROTO_ORDER_REQUEST, "explicitCount")
    assert count["field_number"] == 2
    assert count["wire_format"] == "int32"
    assert shape_of(ws, PROTO_ORDER_REQUEST)["open"] is False


def test_a_declared_shapes_cross_file_reference_resolves_to_a_shape_id(tmp_path):
    """`price`'s `Money` lives in a different schema file (`common.proto`);
    its own `declared_shape` still reaches the same expansion queue and
    settles as an ordinary, closed shape."""
    ws = _declared_workspace(tmp_path, roots=[PROTO_ORDER_REQUEST])
    price = field_of(ws, PROTO_ORDER_REQUEST, "price")

    assert json.loads(price["item"]) == {
        "wire_type": "object",
        "wire_format": None,
        "nullable": True,
        "shape_id": PROTO_MONEY,
    }
    assert shape_of(ws, PROTO_MONEY)["open"] is False
    assert [f["wire_name"] for f in shape_fields_of(ws, PROTO_MONEY)] == ["currency", "amountMinor"]
    assert field_of(ws, PROTO_MONEY, "amountMinor")["field_number"] == 2


def test_a_declared_shapes_nested_message_becomes_its_own_shape(tmp_path):
    """`Line` is declared inside `OrderRequest` in the schema, but it is still
    its own payload — its own shape row, reached through `lines`' `item`."""
    ws = _declared_workspace(tmp_path, roots=[PROTO_ORDER_REQUEST])
    lines = field_of(ws, PROTO_ORDER_REQUEST, "lines")

    assert json.loads(lines["item"]) == {
        "wire_type": "object",
        "wire_format": None,
        "nullable": False,
        "shape_id": PROTO_LINE,
    }
    assert shape_of(ws, PROTO_LINE)["open"] is False
    assert [f["wire_name"] for f in shape_fields_of(ws, PROTO_LINE)] == ["sku"]


def test_a_type_owning_a_declared_shape_never_blends_in_bytecode_fields(tmp_path):
    """The never-a-blend rule (2G design §3, Task 5 brief): a compiled schema
    class's own bytecode fields are serializer machinery, not the wire
    contract, even though the scanner reached the same class and produced
    ordinary field facts for it."""
    ws = _declared_workspace(tmp_path, roots=[BLEND_TYPE])
    names = [f["wire_name"] for f in shape_fields_of(ws, BLEND_TYPE)]

    assert names == ["declaredOnly"]
    assert "internal" not in names


def test_a_plain_dto_still_expands_from_bytecode_exactly_as_before(tmp_path):
    """No `declared_shape` fact touches `ORDER_REQUEST` in this scenario, so
    it must expand exactly as the pre-2G rules already do — the fixture other
    Task-10/11 tests pin stays whole."""
    root = tmp_path / "facts"
    _contract_facts(root)
    _declared_shape_facts(root)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(root)
    derive_shapes(workspace, _CATALOG, [ORDER_REQUEST])

    names = [f["wire_name"] for f in shape_fields_of(workspace, ORDER_REQUEST)]
    assert names == [
        "reference",
        "note",
        "customer_id",
        "note2",
        "customer",
        "alternates",
        "total",
        "total_amount",
        "status",
    ]
    assert field_of(workspace, ORDER_REQUEST, "reference")["field_number"] is None


def test_a_declared_shape_that_refers_to_itself_terminates(tmp_path):
    """Protobuf permits recursive messages (`message Node { Node parent = 1;
    }`) — mirrors `test_a_type_that_refers_to_itself_terminates` above for
    the declared-shape path: `object` is a reference to another shape, never
    an inlining (ruling F1), so a declared shape's own recursion needs no
    depth counter either, only the same each-shape-expanded-once discipline
    `derive_shapes`'s `expanded` set already provides."""
    node = "com/acme/orders/proto/NodeProtos$Node#"
    root = tmp_path / "facts"
    _write(
        root / "NodeProtos.jsonl",
        _document("doc_proto_node", "com/acme/orders/proto/NodeProtos.java"),
        [
            DeclaredShapeFact(
                document_id="doc_proto_node",
                symbol=node,
                schema_name="sextant.orders.Node",
                schema_format="protobuf",
                origin="compiled",
                evidence="compiler",
                fields=[
                    DeclaredFieldFact(
                        name="parent",
                        wire_name="parent",
                        field_number=1,
                        wire_type="object",
                        required=False,
                        nullable=True,
                        shape_ref=node,
                    )
                ],
            ).model_dump(mode="json")
        ],
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(root)
    derive_shapes(workspace, _CATALOG, [node])

    assert [s["shape_id"] for s in workspace.query("shapes")] == [node]
    assert shape_of(workspace, node)["open"] is False
    assert json.loads(field_of(workspace, node, "parent")["item"])["shape_id"] == node


# --- Nullability and presence (Task 11) --------------------------------------


def test_the_language_answer_survives_when_no_catalog_annotation_applies(tmp_path):
    """The extractor already decided. The derivation must not re-derive it, or
    the same rule ends up in two places and they will diverge."""
    ws = _expanded_workspace(tmp_path, roots=[ORDER_REQUEST])
    field = field_of(ws, ORDER_REQUEST, "reference")
    assert field["nullable"] is True
    assert field["resolution"] == "resolved"  # ruling B: Java answers outright


def test_a_not_null_annotation_overrides_javas_permissive_default(tmp_path):
    # Looked up by WIRE name: the field is `customerId` in Java and
    # `customer_id` on the wire, and D01 §5 makes the wire name the identity.
    ws = _expanded_workspace(tmp_path, roots=[ORDER_REQUEST])
    field = field_of(ws, ORDER_REQUEST, "customer_id")
    assert field["nullable"] is False
    assert field["resolution"] == "resolved"


def test_a_declared_nullable_annotation_agrees_with_the_language_default(tmp_path):
    ws = _expanded_workspace(tmp_path, roots=[ORDER_REQUEST])
    field = field_of(ws, ORDER_REQUEST, "note")
    assert field["nullable"] is True
    assert field["resolution"] == "resolved"


def test_kotlin_arrives_already_resolved_and_is_not_downgraded(tmp_path):
    ws = _expanded_workspace(tmp_path, roots=[KOTLIN_ORDER])
    assert field_of(ws, KOTLIN_ORDER, "note")["nullable"] is True
    assert field_of(ws, KOTLIN_ORDER, "id")["nullable"] is False


def test_a_null_marked_scope_inverts_the_default_for_everything_inside_it(tmp_path):
    """The scope is itself a declaration, so absence carries meaning."""
    ws = _expanded_workspace(tmp_path, roots=[SCOPED_REQUEST])
    field = field_of(ws, SCOPED_REQUEST, "code")
    assert field["nullable"] is False
    assert field["resolution"] == "resolved"


def test_presence_is_never_read_from_a_nullability_annotation(tmp_path):
    """`required` and `nullable` answer different questions (D00 §5a). Bean
    Validation's @NotNull is the trap: it constrains a value at validation time
    and says nothing about whether the field may be omitted."""
    ws = _expanded_workspace(tmp_path, roots=[ORDER_REQUEST])
    assert field_of(ws, ORDER_REQUEST, "note")["required"] is True


def test_an_optional_wrapper_makes_a_field_not_required(tmp_path):
    ws = _expanded_workspace(tmp_path, roots=[ORDER_REQUEST])
    assert field_of(ws, ORDER_REQUEST, "note2")["required"] is False


def test_a_known_types_own_nullable_overrides_the_references_answer(tmp_path):
    """D02 §2g, carried forward from Task 10's review: a `known_types` entry
    may declare its own `nullable` — a wrapper type such as protobuf's, whose
    wire behaviour the reference's own flag does not describe — which then
    overrides the reference's answer for that field. Verified only by
    hand-invocation until now; a regression here would be silent."""
    owner = "com/acme/orders/contracts/KnownOverride#"
    root = tmp_path / "facts"
    _contract_facts(root)
    _write(
        root / "KnownOverride.jsonl",
        _document("doc_known_override", "com/acme/orders/contracts/KnownOverride.java"),
        [
            _type("doc_known_override", owner),
            _field(
                "doc_known_override",
                owner,
                "value",
                _ref("com/acme/Wrapper#", "object", nullable=False),
            ),
        ],
    )
    declared = Catalog(
        **{
            **vars(_CATALOG),
            "known_types": [
                *_CATALOG.known_types,
                {"type": "com.acme.Wrapper", "wire": "string", "nullable": True},
            ],
        }
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(root)
    derive_shapes(workspace, declared, [owner])

    field = field_of(workspace, owner, "value")
    assert field["nullable"] is True
    assert field["resolution"] == "resolved"


def test_a_type_argument_annotation_does_not_flip_the_fields_own_nullable(tmp_path):
    """D00 §5a's named trap: `List<@Nullable String>` annotates the element,
    not the field. Every annotation fact in the existing test data carries
    `type_path` `""` or absent, so this guard (`_explicit_nullable`) was never
    exercised by a non-empty `type_path` before now."""
    owner = "com/acme/orders/contracts/TypeArgAnnotated#"
    root = tmp_path / "facts"
    _contract_facts(root)
    _write(
        root / "TypeArgAnnotated.jsonl",
        _document("doc_type_arg", "com/acme/orders/contracts/TypeArgAnnotated.java"),
        [
            _type("doc_type_arg", owner),
            _field(
                "doc_type_arg",
                owner,
                "tags",
                _ref("java/util/List#", "array", arguments=[_string()]),
            ),
            # Targets the field, but its `type_path` locates the list's
            # element (`0;`), not the field's own type — must not flip
            # `tags`' own `nullable`, only (an as-yet-unmodelled) element one.
            _annotation(
                "doc_type_arg",
                _MODULE + owner + "tags.",
                "org/jspecify/annotations/NonNull#",
                {},
                type_path="0;",
            ),
        ],
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(root)
    derive_shapes(workspace, _CATALOG, [owner])

    field = field_of(workspace, owner, "tags")
    assert field["nullable"] is True
    assert field["resolution"] == "resolved"


def test_a_package_scope_does_not_claim_a_sibling_package_sharing_its_prefix(tmp_path):
    """`com/acme/orders/scoped/` must not match `com/acme/orders/scopedextra/`
    by bare substring — the trailing `/` `_scope_prefix` leaves in the claimed
    prefix is the actual package boundary."""
    owner = "com/acme/orders/scopedextra/ExtraRequest#"
    root = tmp_path / "facts"
    _contract_facts(root)
    _write(
        root / "ExtraRequest.jsonl",
        _document("doc_extra", "com/acme/orders/scopedextra/ExtraRequest.java"),
        [
            _type("doc_extra", owner),
            _field("doc_extra", owner, "code", _string()),
        ],
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(root)
    derive_shapes(workspace, _CATALOG, [owner])

    field = field_of(workspace, owner, "code")
    assert field["nullable"] is True
    assert field["resolution"] == "resolved"


def test_a_package_scope_does_not_reach_into_a_subpackage_of_its_own(tmp_path):
    """`com/acme/orders/scoped/` must not claim `com/acme/orders/scoped/inner/`.

    A Java package annotation is not inherited by subpackages — JLS 7.4.1 gives
    `a.b` and `a.b.c` no relationship beyond the name — and the sibling test
    above passes without this one, because a subpackage really does start with
    its parent's full prefix, trailing `/` and all. Measured over 1,672 cached
    jars: 1,479 packages declare a field scope and 462 unmarked subpackages were
    claimed by one, Guava's `…/base/internal` and Spring Cloud AWS's
    `…/sqs/config/legacy` among them.
    """
    owner = "com/acme/orders/scoped/inner/InnerRequest#"
    root = tmp_path / "facts"
    _contract_facts(root)
    _write(
        root / "InnerRequest.jsonl",
        _document("doc_inner", "com/acme/orders/scoped/inner/InnerRequest.java"),
        [
            _type("doc_inner", owner),
            _field("doc_inner", owner, "code", _string()),
            _annotation(
                "doc_inner",
                _MODULE + "com/acme/orders/scoped/package-info#",
                "org/jspecify/annotations/NullMarked#",
                {},
            ),
        ],
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(root)
    derive_shapes(workspace, _CATALOG, [owner])

    field = field_of(workspace, owner, "code")
    assert field["nullable"] is True
    assert field["resolution"] == "resolved"


def test_a_type_level_scope_does_not_claim_a_sibling_type_sharing_its_prefix(tmp_path):
    """`…/ScopedType#` must not match `…/ScopedTypeLarge#code.` — the trailing
    `#` a type-level target already carries is the boundary."""
    scoped_owner = "com/acme/orders/contracts/ScopedType#"
    sibling_owner = "com/acme/orders/contracts/ScopedTypeLarge#"
    root = tmp_path / "facts"
    _contract_facts(root)
    _write(
        root / "ScopedType.jsonl",
        _document("doc_scoped_type", "com/acme/orders/contracts/ScopedType.java"),
        [
            _type("doc_scoped_type", scoped_owner),
            _field("doc_scoped_type", scoped_owner, "code", _string()),
            _annotation(
                "doc_scoped_type",
                _MODULE + scoped_owner,
                "org/jspecify/annotations/NullMarked#",
                {},
            ),
        ],
    )
    _write(
        root / "ScopedTypeLarge.jsonl",
        _document("doc_scoped_type_large", "com/acme/orders/contracts/ScopedTypeLarge.java"),
        [
            _type("doc_scoped_type_large", sibling_owner),
            _field("doc_scoped_type_large", sibling_owner, "code", _string()),
        ],
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(root)
    derive_shapes(workspace, _CATALOG, [scoped_owner, sibling_owner])

    # The type-level scope does reach its own field...
    assert field_of(workspace, scoped_owner, "code")["nullable"] is False
    # ...but not a sibling type whose symbol merely starts the same way.
    sibling = field_of(workspace, sibling_owner, "code")
    assert sibling["nullable"] is True
    assert sibling["resolution"] == "resolved"


def test_a_more_specific_scope_prefix_wins_over_a_broader_one():
    """D02 §2e defines one scope meaning today (`not_null_by_default`), so two
    *real*, catalog-driven nested scopes always agree — a full derive_shapes
    pass cannot yet produce a genuine conflict between them to assert on.
    This pins `_scope_nullable`'s selection rule directly instead: the
    longer, more specific prefix must win regardless of which order its
    matches were found in — the discipline an eventual `NullUnmarked` (D02
    §7's open decision) will rely on once a catalog can express it."""
    broad = (_MODULE + "com/acme/orders/scoped/", False)
    specific = (_MODULE + "com/acme/orders/scoped/Inner#", True)
    field_symbol = _MODULE + "com/acme/orders/scoped/Inner#code."

    assert _scope_nullable([broad, specific], field_symbol) is True
    assert _scope_nullable([specific, broad], field_symbol) is True


# --- Endpoints carrying their contract (Task 12) -----------------------------


def test_a_second_resolve_does_not_inherit_the_first_ones_shapes(tmp_path):
    """Both halves of the derivation are insert-if-absent, so that a type two
    catalogs reach is one shape rather than two — which means nothing in them
    clears anything. Without a reset per resolve, a reused workspace answers
    with a field list nothing in the current run produced. Unconditional, so
    it still holds for a resolve that reaches no endpoint at all."""
    workspace = _loaded_workspace(tmp_path)
    derive_shapes(workspace, _CATALOG, [ORDER_REQUEST])
    assert shape_fields_of(workspace, ORDER_REQUEST)

    derive_endpoint_shapes(workspace, [_CATALOG], capabilities=set())

    assert workspace.query("shapes") == []
    assert workspace.query("shape_fields") == []


# A declared envelope that arrives with nothing inside it. Every method
# parameter is read from the erased descriptor, which never carried a type
# argument, and a raw return type has none either — so a catalog's own wrapper
# entry matches a reference offering no payload to descend into.
_ERASED_OPTIONAL = "java/util/Optional#"
_RAW_ENVELOPE = "org/springframework/http/ResponseEntity#"

# The same invented serialiser with a mapping declaration, so a test can derive
# a real endpoint and then ask what contract it carries. Invented annotations
# throughout: reaching for a shipped catalog here would test that file rather
# than this pass.
_ENDPOINT_CATALOG = Catalog(
    **{
        **vars(_CATALOG),
        "id": "invented-endpoints",
        "matches": {
            "type_annotation": "com.acme.rest.Resource",
            "request_body": {"annotation": "com.acme.rest.Body", "fallback": "none"},
            "mapping": {
                "path_from": ["value"],
                "prefix_from": ["value"],
                "method_from": "method",
                "all_methods": ["POST"],
                "prefix_annotation": "com.acme.rest.Path",
                "annotations": [{"fqn": "com.acme.rest.Post", "method": ["POST"]}],
            },
        },
    }
)

_HANDLER_OWNER = "com/acme/orders/EdgeController#"
_HANDLER = _HANDLER_OWNER + "handle(sig_00000000)."


def _handler_facts(root: Path, signature: dict | None) -> None:
    """One annotated handler carrying the signature a test hands it — the fact
    the extractor writes for a controller method. `None` omits the key
    entirely, which is what a scanner that typed no signature leaves behind
    and what the workspace then reads back as SQL NULL."""
    handler = {
        "kind": "symbol",
        "document_id": "doc_edge",
        "symbol": _MODULE + _HANDLER,
        "construct_kind": "method",
        "enclosing": _MODULE + _HANDLER_OWNER,
        "visibility": "public",
        "line_start": 0,
        "line_end": 0,
    }
    if signature is not None:
        handler["signature"] = signature
    _write(
        root / "EdgeController.jsonl",
        _document("doc_edge", "com/acme/orders/EdgeController.java"),
        [
            _type("doc_edge", _HANDLER_OWNER),
            handler,
            _annotation("doc_edge", _MODULE + _HANDLER_OWNER, "com/acme/rest/Resource#", {}),
            _annotation(
                "doc_edge", _MODULE + _HANDLER, "com/acme/rest/Post#", {"value": ["/edge"]}
            ),
        ],
    )


def _signature(returns: dict, parameters: tuple[dict, ...] = ()) -> dict:
    return {"parameters": list(parameters), "returns": returns, "return_type_annotations": []}


def _body_parameter(reference: dict) -> dict:
    return {
        "name": "request",
        "annotations": [{"annotation": "com/acme/rest/Body#", "args": {}}],
        "type": reference,
        "type_annotations": [],
    }


def _bare_parameter(reference: dict, name: str = "request") -> dict:
    """A parameter with no annotations of its own — Feign's contract: no
    annotation marks the body, being the only bare parameter does."""
    return {
        "name": name,
        "annotations": [],
        "type": reference,
        "type_annotations": [],
    }


def _resolved_handler(tmp_path: Path, signature: dict | None) -> DuckDbWorkspace:
    """The whole endpoint-to-contract path over hand-built facts: derive the
    endpoint, then derive the shapes it declares."""
    root = tmp_path / "facts"
    _contract_facts(root)
    _handler_facts(root, signature)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(root)
    derive_endpoints(workspace, [_ENDPOINT_CATALOG], capabilities=set())
    derive_endpoint_shapes(workspace, [_ENDPOINT_CATALOG], capabilities=set())
    return workspace


def _resolved_endpoint(tmp_path: Path, signature: dict | None) -> dict:
    """The one endpoint `_resolved_handler` derives, with its workspace closed
    behind it — every test below reads only the row, never the shapes it
    settled alongside it."""
    ws = _resolved_handler(tmp_path, signature)
    endpoint = ws.query("endpoints")[0]
    ws.close()
    return endpoint


def _resolved_string_handler(tmp_path: Path) -> dict:
    return _resolved_endpoint(tmp_path, _signature(returns=_string()))


def _resolved_void_handler(tmp_path: Path) -> dict:
    return _resolved_endpoint(tmp_path, _signature(returns=_ref("void#", "")))


def test_a_declared_wrapper_with_no_payload_argument_stops_instead_of_raising():
    """The catalog said "envelope", and the reference offers nothing at the
    payload position. Descending anyway is impossible and crashing is not an
    answer: this is exactly the unmatched-wrapper case D02 §2a already names —
    something that could be an envelope, left unopened and said so."""
    rooted = root_type(type_ref(_ERASED_OPTIONAL), SPRING_WRAPPERS)

    assert rooted.symbol == _ERASED_OPTIONAL
    # The chain records envelopes actually peeled. This one was not, and a
    # semantics recorded here would let `required: false` be derived from an
    # unwrapping that never happened.
    assert rooted.chain == ()
    assert rooted.unmatched_wrapper is True


def test_an_erased_wrapper_parameter_leaves_the_request_shape_null(tmp_path):
    """A parameter reaches the signature through the erased descriptor, so a
    declared envelope around the payload arrives with the payload gone. The
    envelope is not the contract, and a shape row for it would report a type
    the catalog already describes as a payload nobody could expand."""
    ws = _resolved_handler(
        tmp_path,
        _signature(
            returns=_ref(ORDER_VIEW_SHAPE, "object"),
            parameters=(_body_parameter(_ref(_ERASED_OPTIONAL, "object")),),
        ),
    )
    endpoint = ws.query("endpoints")[0]

    assert endpoint["request_shape"] is None
    assert json.loads(endpoint["response_shape"]) == {
        "nullable": True,
        "shape_id": ORDER_VIEW_SHAPE,
        "wire_format": "",
        "wire_type": "object",
    }
    assert not any(s["shape_id"] == _ERASED_OPTIONAL for s in ws.query("shapes"))
    ws.close()


def test_a_raw_wrapper_return_leaves_the_response_shape_null(tmp_path):
    """The other half of the same case, and ordinary code: a handler declaring
    the envelope type without its argument."""
    ws = _resolved_handler(tmp_path, _signature(returns=_ref(_RAW_ENVELOPE, "object")))
    endpoint = ws.query("endpoints")[0]

    assert endpoint["response_shape"] is None
    assert not any(s["shape_id"] == _RAW_ENVELOPE for s in ws.query("shapes"))
    ws.close()


def test_a_handler_with_no_recorded_signature_declares_no_payload(tmp_path):
    """`signature` is optional in D00 §5, so the column is SQL NULL whenever
    nothing typed it. Degrading to "no shapes" is the discipline capability
    gating uses one level up; crashing would end a whole resolve over a fact
    the schema permits."""
    ws = _resolved_handler(tmp_path, signature=None)
    endpoint = ws.query("endpoints")[0]

    assert endpoint["request_shape"] is None
    assert endpoint["response_shape"] is None
    ws.close()


def test_a_collection_response_records_what_the_array_holds(tmp_path):
    """List<OrderView> was 2A's parked gap: the endpoint said nothing at all.
    The descriptor keeps the array-ness — it IS the wire contract — and points
    at the element's shape."""
    ws = _resolved_handler(
        tmp_path,
        _signature(
            returns=_ref("java/util/List#", "array", arguments=[_ref(ORDER_VIEW_SHAPE, "object")])
        ),
    )
    endpoint = ws.query("endpoints")[0]
    descriptor = json.loads(endpoint["response_shape"])
    assert descriptor["wire_type"] == "array"
    assert descriptor["item"]["shape_id"] == ORDER_VIEW_SHAPE
    # This handler's only payload is the array itself, so the element's shape
    # row reaches `shapes` solely through `referenced` — a regression back to
    # picking roots from the settled columns (the 2A path) would leave it
    # unexpanded, since no column ever holds a bare `OrderView` root here.
    assert any(s["shape_id"] == ORDER_VIEW_SHAPE for s in ws.query("shapes"))
    ws.close()


def test_an_outbound_row_with_no_handler_still_receives_contracts(tmp_path):
    """An outbound row carries `caller` with `handler` NULL (D01 §3,
    amended): the annotation-driven engine never writes a handler symbol for
    a catalog whose declared direction is `outbound`. `_contracts_of`'s owner
    falls through to `caller` in that case, and `derive_endpoint_contracts.sql`
    coalesces the same two columns to match, so the row still gets a
    descriptor rather than being silently skipped."""
    outbound_catalog = Catalog(
        **{**vars(_ENDPOINT_CATALOG), "id": "invented-outbound", "direction": "outbound"}
    )
    root = tmp_path / "facts"
    _contract_facts(root)
    _handler_facts(root, _signature(returns=_ref(ORDER_VIEW_SHAPE, "object")))
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(root)
    derive_endpoints(workspace, [outbound_catalog], capabilities=set())
    derive_endpoint_shapes(workspace, [outbound_catalog], capabilities=set())
    endpoint = workspace.query("endpoints")[0]

    assert endpoint["handler"] is None
    assert endpoint["caller"] == _MODULE + _HANDLER
    assert json.loads(endpoint["response_shape"]) == {
        "nullable": True,
        "shape_id": ORDER_VIEW_SHAPE,
        "wire_format": "",
        "wire_type": "object",
    }
    workspace.close()


# Task 7 review, Finding 1: direction ownership. `_owns` restricts a catalog
# to the rows its own direction produced, because ordering alone cannot: an
# outbound catalog's own wrapper vocabulary (Retrofit's `Call`, say) is no
# more able to describe an inbound `ResponseEntity` row than an inbound
# catalog's is able to describe an outbound `Call` row, and *some* catalog
# always sorts first. `_OUTBOUND_CATALOG` below carries its own unrelated
# annotation vocabulary (`@Client`/`@Get`, not `@Resource`/`@Post`) so its row
# is a genuinely separate path from `_ENDPOINT_CATALOG`'s — the two never
# merge (D02 §3 only merges one shared wire identity), which is what makes
# each row's ownership unambiguous to assert against.
_OUTBOUND_CALL = "com/acme/client/Call#"
_OUTBOUND_OWNER = "com/acme/orders/clients/EdgeClient#"
_OUTBOUND_CALLER = _OUTBOUND_OWNER + "call(sig_00000001)."

_OUTBOUND_CATALOG = Catalog(
    **{
        **vars(_CATALOG),
        "id": "invented-outbound-call",
        "direction": "outbound",
        # Retrofit's own shape: a `Call`-style wrapper and nothing else — no
        # `ResponseEntity` entry, so this catalog has no idea how to open one.
        "wrappers": [{"type": "com.acme.client.Call", "payload_arg": 0, "semantics": "async"}],
        "matches": {
            "type_annotation": "com.acme.client.Client",
            "request_body": {"annotation": "com.acme.client.Body", "fallback": "none"},
            "mapping": {
                "path_from": ["value"],
                "prefix_from": ["value"],
                "method_from": "method",
                "all_methods": ["GET"],
                "prefix_annotation": "com.acme.client.Path",
                "annotations": [{"fqn": "com.acme.client.Get", "method": ["GET"]}],
            },
        },
    }
)


def _outbound_caller_facts(root: Path, signature: dict) -> None:
    """One hand-built outbound client method, on its own annotation
    vocabulary so `_ENDPOINT_CATALOG`'s `@Resource`/`@Post` gate never sees
    it (and `_OUTBOUND_CATALOG`'s `@Client`/`@Get` gate never sees
    `_HANDLER`) — the fact the extractor would write for a Retrofit-style
    interface method."""
    caller = {
        "kind": "symbol",
        "document_id": "doc_client",
        "symbol": _MODULE + _OUTBOUND_CALLER,
        "construct_kind": "method",
        "enclosing": _MODULE + _OUTBOUND_OWNER,
        "visibility": "public",
        "line_start": 0,
        "line_end": 0,
        "signature": signature,
    }
    _write(
        root / "EdgeClient.jsonl",
        _document("doc_client", "com/acme/orders/clients/EdgeClient.java"),
        [
            _type("doc_client", _OUTBOUND_OWNER),
            caller,
            _annotation("doc_client", _MODULE + _OUTBOUND_OWNER, "com/acme/client/Client#", {}),
            _annotation(
                "doc_client",
                _MODULE + _OUTBOUND_CALLER,
                "com/acme/client/Get#",
                {"value": ["/edge-call"]},
            ),
        ],
    )


def _paired_direction_workspace(tmp_path: Path) -> DuckDbWorkspace:
    """One inbound row (`ResponseEntity<OrderView>`, `_ENDPOINT_CATALOG`'s own
    wrapper) beside one outbound row (`Call<OrderView>`, `_OUTBOUND_CATALOG`'s
    own wrapper), resolved together — the shape both Finding 1(a) and 1(b)
    need, from opposite ends."""
    root = tmp_path / "facts"
    _contract_facts(root)
    _handler_facts(
        root,
        _signature(
            returns=_ref(_RAW_ENVELOPE, "object", arguments=[_ref(ORDER_VIEW_SHAPE, "object")])
        ),
    )
    _outbound_caller_facts(
        root,
        _signature(
            returns=_ref(_OUTBOUND_CALL, "object", arguments=[_ref(ORDER_VIEW_SHAPE, "object")])
        ),
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(root)
    derive_endpoints(workspace, [_ENDPOINT_CATALOG, _OUTBOUND_CATALOG], capabilities=set())
    derive_endpoint_shapes(workspace, [_ENDPOINT_CATALOG, _OUTBOUND_CATALOG], capabilities=set())
    return workspace


def test_an_outbound_catalogs_own_wrapper_reaches_its_own_row(tmp_path):
    """Finding 1(a): retrofit's wrappers were unreachable dead code under
    ordering-as-correctness — an inbound catalog sorted first always answered
    first, no matter what it could actually open. With direction ownership,
    `_OUTBOUND_CATALOG`'s own `Call` wrapper is what describes its row, and
    the response roots at the real payload, not the raw `Call` envelope."""
    workspace = _paired_direction_workspace(tmp_path)
    outbound_row = next(e for e in workspace.query("endpoints") if e["direction"] == "outbound")
    descriptor = json.loads(outbound_row["response_shape"])
    workspace.close()

    assert descriptor["shape_id"] == ORDER_VIEW_SHAPE


def test_an_inbound_catalogs_own_wrapper_still_reaches_its_own_row(tmp_path):
    """Finding 1(b): the original bug's shape, kept green under the fix —
    sharing a run with an outbound catalog whose wrapper list has never heard
    of `ResponseEntity` must not leave the inbound row's own envelope
    unopened."""
    workspace = _paired_direction_workspace(tmp_path)
    inbound_row = next(e for e in workspace.query("endpoints") if e["direction"] == "inbound")
    descriptor = json.loads(inbound_row["response_shape"])
    workspace.close()

    assert descriptor["shape_id"] == ORDER_VIEW_SHAPE


def test_an_outbound_catalog_cannot_claim_an_inbound_row_even_processed_first(tmp_path):
    """Finding 1(c), made structural: the original bug's exact shape — an
    outbound catalog with a narrower wrapper list running before the inbound
    catalog that actually owns the row — called directly against
    `_contracts_of` so no sort order is in play at all. `derive_endpoint_shapes`
    always tries inbound catalogs first (readability, not correctness now);
    this test proves the guarantee holds even when an outbound catalog goes
    first, which is what `_owns` — not order — is responsible for."""
    root = tmp_path / "facts"
    _contract_facts(root)
    _handler_facts(
        root,
        _signature(
            returns=_ref(_RAW_ENVELOPE, "object", arguments=[_ref(ORDER_VIEW_SHAPE, "object")])
        ),
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(root)
    derive_endpoints(workspace, [_ENDPOINT_CATALOG], capabilities=set())
    endpoints = workspace.query("endpoints")

    settled: dict[str, dict[str, str]] = {}
    # The outbound catalog goes first — the original bug's ordering, and the
    # opposite of what `derive_endpoint_shapes` now sorts to.
    outbound_found = _contracts_of(
        endpoints, _OUTBOUND_CATALOG, settled, _rules_of(_OUTBOUND_CATALOG), set(), []
    )
    assert outbound_found == {}
    for owner, columns in outbound_found.items():
        settled.setdefault(owner, {}).update(columns)

    inbound_found = _contracts_of(
        endpoints, _ENDPOINT_CATALOG, settled, _rules_of(_ENDPOINT_CATALOG), set(), []
    )
    for owner, columns in inbound_found.items():
        settled.setdefault(owner, {}).update(columns)
    workspace.close()

    owner = _MODULE + _HANDLER
    descriptor = json.loads(settled[owner]["response_shape"])
    assert descriptor["shape_id"] == ORDER_VIEW_SHAPE


def test_owns_never_crosses_a_protocol_it_was_not_declared_for():
    """2E-prep collapse: `_owns` now reads a single fact off the row — the
    `catalog_id` Task 1 stamps on every endpoint — rather than reasoning
    about direction and protocol at all. A row naming one catalog's id must
    never read as owned by a different catalog, same-protocol or not: this
    is what used to require `_owns`'s direction/protocol scoping (Task 10's
    `spring-jms`-crosses-into-`spring-mvc` bug), and is now just the id
    comparison. Mutation-tested against `return True`: every assertion below
    that reads `is False` fails."""
    inbound_http = Catalog(**{**vars(_CATALOG), "id": "catalog-a", "protocol": "http"})
    inbound_kafka = Catalog(**{**vars(_CATALOG), "id": "catalog-b", "protocol": "kafka"})

    assert _owns(inbound_http, {"catalog_id": "catalog-a"}) is True
    assert _owns(inbound_kafka, {"catalog_id": "catalog-a"}) is False
    assert _owns(inbound_http, {"catalog_id": "catalog-b"}) is False
    # A row naming no catalog at all (impossible after Task 1) is owned by
    # nobody.
    assert _owns(inbound_http, {}) is False


def test_owns_is_the_id_comparison_even_for_a_row_level_direction_override():
    """Task 11 review round 1, finding 2, restated post-collapse: a
    `single_call` row's own `direction` override (D02 §2/§3, Task 6 —
    `spring-pubsub.yml`'s `subscribeAndConvert` row) used to need `_owns` to
    reason about `catalog.matches["methods"]`, or a catalog whose
    catalog-level `direction` is `outbound` never owned the inbound/`both`
    rows its OWN override-carrying row produces. With ownership read off
    `catalog_id` alone, the override needs no special-casing at all: every
    row a catalog's own derivation writes — override or not — carries that
    SAME catalog's id, so it stays owned regardless of the row's own
    `direction`. Proven here with only one catalog's id in play, and a
    second catalog's id alongside it to show ownership still never crosses,
    override or not."""
    pubsub = Catalog(**{**vars(_CATALOG), "id": "spring-pubsub", "direction": "outbound"})

    # The plain row and the row-level override both carry the producing
    # catalog's own id — both owned, direction plays no part in the answer.
    assert _owns(pubsub, {"catalog_id": "spring-pubsub", "direction": "outbound"}) is True
    assert _owns(pubsub, {"catalog_id": "spring-pubsub", "direction": "inbound"}) is True
    assert _owns(pubsub, {"catalog_id": "spring-pubsub", "direction": "both"}) is True

    # A different catalog's id is never owned, override or not.
    other = Catalog(**{**vars(_CATALOG), "id": "other-catalog"})
    assert _owns(other, {"catalog_id": "spring-pubsub", "direction": "inbound"}) is False


# --- Task 12 fix round 1 (coordinator review): wrapper vocabulary must be
# shared across *every* outbound catalog, not just serialization/known_types.
# Historical: before 2E-prep's `catalog_id` collapse, `_owns` scoped by
# direction and protocol alone (protocol added in Task 10 fix round 1), so
# within one same-protocol group whichever catalog sorted first described
# every outbound row's shapes under its own `wrappers` list — even a row a
# *different* catalog produced. Reviewer's repro: `okhttp` sorts before
# `retrofit` alphabetically (both `protocol: http`), and before that fix
# declared no `wrappers` at all, so a Retrofit `Call<OrderView>` response
# settled (first) as the raw `Call` envelope rather than unwrapping to
# `OrderView`. The harvested `wrappers` union this section pins for
# (`okhttp.yml` carrying `retrofit2.Call` among them) was that fix's answer,
# and stays shipped — harmless now that `_owns` reads `catalog_id`, since
# ownership can no longer cross catalogs at all regardless of sort order or
# wrapper vocabulary. ------

_RETROFIT_CALLER_OWNER = "com/acme/orders/clients/PricingClient#"
_RETROFIT_CALLER = _RETROFIT_CALLER_OWNER + "price(sig_00000002)."


def _retrofit_shaped_caller_facts(root: Path) -> None:
    """One hand-built Retrofit-annotated interface method — a real `@GET`
    mapping annotation, `Call<OrderView>` return — matched by the real,
    shipped `retrofit.yml`, not an invented stand-in: the bug is specifically
    about two *real* catalogs' wrapper lists disagreeing, so the fixture
    must be real enough for `retrofit.yml`'s own `mapping` rules to fire."""
    caller = {
        "kind": "symbol",
        "document_id": "doc_pricing",
        "symbol": _MODULE + _RETROFIT_CALLER,
        "construct_kind": "method",
        "enclosing": _MODULE + _RETROFIT_CALLER_OWNER,
        "visibility": "public",
        "line_start": 0,
        "line_end": 0,
        "signature": _signature(
            returns=_ref("retrofit2/Call#", "object", arguments=[_ref(ORDER_VIEW_SHAPE, "object")])
        ),
    }
    _write(
        root / "PricingClient.jsonl",
        _document("doc_pricing", "com/acme/orders/clients/PricingClient.java"),
        [
            # An INTERFACE, as the docstring above already said it was and as
            # the facts did not: `Retrofit.create` throws on anything else
            # (CP-11 Q4), and `retrofit.yml` gates on it since `A-C6`.
            _type("doc_pricing", _RETROFIT_CALLER_OWNER, "interface"),
            caller,
            _annotation(
                "doc_pricing",
                _MODULE + _RETROFIT_CALLER,
                "retrofit2/http/GET#",
                {"value": ["/pricing"]},
            ),
        ],
    )


def test_an_unrelated_outbound_catalogs_wrapper_list_still_unwraps_another_catalogs_row(
    tmp_path,
):
    """The real `okhttp` and `retrofit` catalogs, resolved together: `okhttp`
    sorts first (asserted below) and never itself produces this row (no
    OkHttp call site exists in these facts). Post-collapse, `_owns` reading
    `catalog_id` means `okhttp` cannot touch this row at all, sort order or
    not — it is `retrofit`'s own `wrappers` list (which independently
    declares `retrofit2.Call`) that resolves it. The response still
    correctly roots at `OrderView`, not at the raw `retrofit2/Call#`
    envelope, proving the historical cross-catalog bug this section
    documents cannot recur under the new ownership rule, pinned against the
    shipped files rather than an invented stand-in."""
    catalogs = YamlCatalogSource(catalogs_dir()).load()
    okhttp = next(c for c in catalogs if c.id == "okhttp")
    retrofit = next(c for c in catalogs if c.id == "retrofit")
    assert str(okhttp.source) < str(retrofit.source)

    root = tmp_path / "facts"
    _contract_facts(root)
    _retrofit_shaped_caller_facts(root)
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(root)
    capabilities = {
        "annotation_args",
        "typed_signatures",
        "call_site",
        "string_constants",
        "chain_reconstruction",
    }
    derive_endpoints(workspace, [okhttp, retrofit], capabilities=capabilities)
    derive_endpoint_shapes(workspace, [okhttp, retrofit], capabilities=capabilities)
    [endpoint] = workspace.query("endpoints")
    descriptor = json.loads(endpoint["response_shape"])
    workspace.close()

    assert descriptor["shape_id"] == ORDER_VIEW_SHAPE


# --- Tasks 10-12 pinned the three payload-type blocks across catalogs, because
# `derive_shapes` is a GLOBAL, insert-if-absent pass keyed on the type symbol
# alone: a payload type an HTTP endpoint and a Kafka listener both reach is
# described once, by whichever catalog sorts first, so a fork in one copy
# silently redescribed that type for every other catalog. Three tests did that
# — `known_types` against `spring-resttemplate.yml`'s, `serialization` against
# the same, `nullability` against `spring-mvc.yml`'s.
#
# **F2 retired all three, and it is not a loss of coverage.** The blocks live in
# `catalogs/shape-models/json.yml` now (D02 §1b) and a catalog names it rather
# than copying it, so those three assertions compare one object with itself:
# a tautology cannot fail, and a test that cannot fail measures nothing. The
# property that CAN still fail is a catalog holding a copy at all, and it is
# asserted where it can be asserted about every catalog at once —
# `tests/architecture/test_shape_model_is_declared_once.py`, with an EMPTY
# allowlist, plus the loader's own refusal of a catalog that names a model and
# declares a block beside it.
#
# What the three were guarding is exactly what makes the retirement safe: they
# existed because forty-two copies could drift, and `A-C3` proved they had.
# One declaration has nothing to drift from.


def test_the_producer_catalogs_wrappers_are_the_harvested_baseline_verbatim():
    """Unlike the three Task 10 listener catalogs (`spring-kafka.yml` adds a
    `ConsumerRecord` envelope entry on top of the baseline, for the one
    listener parameter shape that needs unwrapping), none of the six Task 11
    producer catalogs, nor 2E-prep Task 11's three raw-client catalogs, nor
    2E-prep Task 12's four (the Pub/Sub trio plus `spring-kafka-message`),
    add a broker-specific `wrappers` entry: a `single_call`/`fluent` row's payload
    comes from its own declared position (`body_arg`/a step's own `body`
    capture) or a `record_wrappers` constructor hop, never through an
    envelope type a `wrappers` rule would need to unwrap. So each of these
    catalogs' own `wrappers` list must be exactly `spring-resttemplate.yml`'s,
    not merely a superset of it."""
    catalogs = {c.id: c for c in YamlCatalogSource(catalogs_dir()).load()}
    baseline = catalogs["spring-resttemplate"].wrappers

    for catalog_id in (
        "spring-kafka-template",
        "spring-kafka-replying",
        "kafka-clients",
        "spring-jms-template",
        "spring-sqs-template",
        "spring-pubsub",
        # 2E-prep Task 11 (driver catalogs A).
        "aws-sqs-sdk",
        "jakarta-jms",
        "kafka-consumer",
        # 2E-prep Task 12 (driver catalogs B): the pubsub trio +
        # spring-kafka-message — none adds a broker-specific wrapper either.
        "google-pubsub-publisher",
        "google-pubsub-client",
        "google-pubsub-subscriber",
        "spring-kafka-message",
        # 2F Task 7: `spring-cloud-stream.yml` adds no broker entry either —
        # a binding row's payload comes from the functional type's own type
        # ARGUMENT, read at the declared `payload_arg` position, never
        # through an envelope a `wrappers` rule would unwrap. It matters as
        # much here as in the `known_types` sweep above: it sorts ahead of
        # every `spring-*` catalog, so it is the first to reach the shared
        # messaging payload types.
        "spring-cloud-stream",
    ):
        assert catalogs[catalog_id].wrappers == baseline, catalog_id


def test_the_messaging_catalogs_wrappers_include_the_harvested_baseline_plus_broker_entries():
    """Each new file's own `wrappers` list must still contain every entry
    `spring-resttemplate.yml` declares (the harvested baseline, verbatim);
    `spring-kafka.yml` alone adds a broker envelope entry (`ConsumerRecord`)
    on top — `spring-jms.yml`/`spring-sqs.yml` add none, since neither
    broker's listener API declares an envelope-typed parameter a wrapper
    rule could unwrap."""
    catalogs = {c.id: c for c in YamlCatalogSource(catalogs_dir()).load()}
    baseline = catalogs["spring-resttemplate"].wrappers

    for catalog_id in ("spring-kafka", "spring-jms", "spring-sqs"):
        wrappers = catalogs[catalog_id].wrappers
        for entry in baseline:
            assert entry in wrappers, (catalog_id, entry)

    kafka_extra = [w for w in catalogs["spring-kafka"].wrappers if w not in baseline]
    assert {w["type"] for w in kafka_extra} == {
        "org.apache.kafka.clients.consumer.ConsumerRecord",
    }
    assert [w for w in catalogs["spring-jms"].wrappers if w not in baseline] == []
    assert [w for w in catalogs["spring-sqs"].wrappers if w not in baseline] == []


def test_a_scalar_response_is_recorded_rather_than_dropped(tmp_path):
    endpoint = _resolved_string_handler(tmp_path)
    assert json.loads(endpoint["response_shape"]) == {
        "nullable": True,
        "wire_format": "",
        "wire_type": "string",
    }


def test_no_payload_stays_null_and_means_exactly_that(tmp_path):
    """NULL stops being ambiguous: it is `void`/no-body, never 'a payload we
    could not describe'."""
    endpoint = _resolved_void_handler(tmp_path)
    assert endpoint["response_shape"] is None


# A catalog whose request-body rule falls back to the sole unannotated
# parameter (D02 §2 as amended) — Feign's contract, invented here rather than
# reached for a shipped catalog so this test exercises the pass, not a file.
_SOLE_UNANNOTATED_CATALOG = Catalog(
    **{
        **vars(_ENDPOINT_CATALOG),
        "id": "invented-endpoints-sole-unannotated",
        "matches": {
            **_ENDPOINT_CATALOG.matches,
            "request_body": {
                "annotation": "com.acme.rest.Body",
                "fallback": "sole_unannotated",
            },
        },
    }
)


def _resolved_bare_handler(tmp_path: Path, parameters: tuple[dict, ...]) -> dict:
    """The same endpoint-to-contract path `_resolved_handler` runs, but over
    `_SOLE_UNANNOTATED_CATALOG` so the fallback rule is exercised."""
    root = tmp_path / "facts"
    _contract_facts(root)
    _handler_facts(
        root,
        _signature(returns=_ref(ORDER_VIEW_SHAPE, "object"), parameters=parameters),
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(root)
    derive_endpoints(workspace, [_SOLE_UNANNOTATED_CATALOG], capabilities=set())
    derive_endpoint_shapes(workspace, [_SOLE_UNANNOTATED_CATALOG], capabilities=set())
    endpoint = workspace.query("endpoints")[0]
    workspace.close()
    return endpoint


def _resolved_bare_body_handler(tmp_path: Path) -> dict:
    return _resolved_bare_handler(
        tmp_path, parameters=(_bare_parameter(_ref(ORDER_REQUEST, "object")),)
    )


def _resolved_two_bare_handler(tmp_path: Path) -> dict:
    return _resolved_bare_handler(
        tmp_path,
        parameters=(
            _bare_parameter(_ref(ORDER_REQUEST, "object"), name="request"),
            _bare_parameter(_ref(CUSTOMER_REF, "object"), name="customer"),
        ),
    )


def test_the_sole_unannotated_parameter_is_the_body_when_the_catalog_says_so(tmp_path):
    """Feign's contract: no annotation marks the body; being the only bare
    parameter does. The rule is catalog data — inferring it for a catalog that
    declares no fallback would be a guess presented as an observation."""
    endpoint = _resolved_bare_body_handler(tmp_path)
    assert json.loads(endpoint["request_shape"])["shape_id"] == (
        "com/acme/orders/contracts/OrderRequest#"
    )


def test_two_bare_parameters_mean_no_body_at_all(tmp_path):
    """'Sole' is load-bearing: with two candidates, picking either is a coin
    flip recorded as fact."""
    endpoint = _resolved_two_bare_handler(tmp_path)
    assert endpoint["request_shape"] is None


def test_excluded_infrastructure_types_do_not_defeat_the_sole_unannotated_fallback(tmp_path):
    """Excluded types are never considered as the sole unannotated fallback,
    allowing infrastructure parameters to be hidden so the message payload
    becomes the sole unannotated parameter."""
    catalog = Catalog(
        **{
            **vars(_SOLE_UNANNOTATED_CATALOG),
            "id": "invented-endpoints-excludes",
            "matches": {
                **_SOLE_UNANNOTATED_CATALOG.matches,
                "request_body": {
                    "annotation": "com.acme.rest.Body",
                    "fallback": "sole_unannotated",
                    "excludes": ["org.springframework.kafka.support.Acknowledgment"],
                },
            },
        }
    )
    root = tmp_path / "facts"
    _contract_facts(root)
    _handler_facts(
        root,
        _signature(
            returns=_ref(ORDER_VIEW_SHAPE, "object"),
            parameters=(
                _bare_parameter(_ref(ORDER_REQUEST, "object"), name="payload"),
                _bare_parameter(
                    _ref("org/springframework/kafka/support/Acknowledgment#", "object"), name="ack"
                ),
            ),
        ),
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(root)
    derive_endpoints(workspace, [catalog], capabilities=set())
    derive_endpoint_shapes(workspace, [catalog], capabilities=set())
    endpoint = workspace.query("endpoints")[0]
    workspace.close()

    assert json.loads(endpoint["request_shape"])["shape_id"] == ORDER_REQUEST


def test_two_non_excluded_bare_parameters_still_yield_no_body(tmp_path):
    """The `sole_unannotated` fallback needs exactly ONE bare parameter to
    survive exclusion, and here two do: the catalog declares an `excludes`
    list, but neither parameter's type is on it, so both remain candidates
    and the fallback has no sole one to pick. It yields None rather than
    guessing which of the two is the body — the excludes list narrows the
    candidates, it never breaks a tie among what it does not name."""
    catalog = Catalog(
        **{
            **vars(_SOLE_UNANNOTATED_CATALOG),
            "id": "invented-endpoints-excludes-multi",
            "matches": {
                **_SOLE_UNANNOTATED_CATALOG.matches,
                "request_body": {
                    "annotation": "com.acme.rest.Body",
                    "fallback": "sole_unannotated",
                    "excludes": ["org.springframework.kafka.support.Acknowledgment"],
                },
            },
        }
    )
    root = tmp_path / "facts"
    _contract_facts(root)
    _handler_facts(
        root,
        _signature(
            returns=_ref(ORDER_VIEW_SHAPE, "object"),
            parameters=(
                _bare_parameter(_ref(ORDER_REQUEST, "object"), name="payload"),
                _bare_parameter(_ref(CUSTOMER_REF, "object"), name="customer"),
            ),
        ),
    )
    workspace = DuckDbWorkspace(tmp_path / "ws.duckdb")
    workspace.load_facts(root)
    derive_endpoints(workspace, [catalog], capabilities=set())
    derive_endpoint_shapes(workspace, [catalog], capabilities=set())
    endpoint = workspace.query("endpoints")[0]
    workspace.close()

    assert endpoint["request_shape"] is None


def test_the_derivation_names_no_language():
    """Language-blind by test, not by intention. The per-language rules live in
    the extractors; this file must contain none of them. (The pass itself lives
    in shapes.py, which the architecture tests already scan.) DuckDB binds
    parameters only on a script's last statement, so the shape pass is split
    across two files — both are read here."""
    words: set[str] = set()
    for name in ("derive_shapes.sql", "derive_shape_fields.sql"):
        words |= set(re.findall(r"[a-z]+", (SQL_DIR / name).read_text().lower()))
    assert not {"java", "kotlin", "jvm"} & words
