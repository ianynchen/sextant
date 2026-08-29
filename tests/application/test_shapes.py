import json
import re
from pathlib import Path

from shape_helpers import (
    KOTLIN_ORDER,
    ORDER_REQUEST,
    ORDER_VIEW,
    SCOPED_REQUEST,
    SPRING_WRAPPERS,
    field_of,
    mono_of,
    response_entity_of,
    shape_fields_of,
    shape_of,
    unknown_box_of,
)

from sextant.application.ports.catalogs import Catalog
from sextant.application.resolve.shapes import (
    ExpandedShapes,
    _scope_nullable,
    derive_shapes,
    root_type,
)
from sextant.domain.closed_sets import OriginTier
from sextant.domain.facts import Document
from sextant.storage.duckdb.workspace import DuckDbWorkspace


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
        fact_schema_version="1.0.0",
        scanner_id="asm",
        scanner_version="9.7",
        content_hash="sha256:a",
        origin_entry="target/classes",
        origin_tier=OriginTier.MODULE_OUTPUT,
        redaction_set_hash="sha256:b",
    )


def _type(document_id: str, owner: str) -> dict:
    return {
        "kind": "symbol",
        "document_id": document_id,
        "symbol": _MODULE + owner,
        "construct_kind": "class",
        "enclosing": None,
        "signature": None,
        "visibility": "public",
        "line_start": 0,
        "line_end": 0,
    }


def _field(document_id: str, owner: str, name: str, returns: dict) -> dict:
    return {
        "kind": "symbol",
        "document_id": document_id,
        "symbol": _MODULE + owner + name + ".",
        "construct_kind": "field",
        "enclosing": _MODULE + owner,
        "signature": {"returns": returns},
        "visibility": "public",
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

    assert json.loads(field["item"]) == {"wire_type": "object", "shape_id": CUSTOMER_REF}
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
    ]
    assert shape_of(ws, ORDER_REQUEST)["content_hash"].startswith("md5:")


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
    # yield nine fields, `internalTrace` among them.
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
