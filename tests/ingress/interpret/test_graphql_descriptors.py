"""The interpreter's third schema format (2H design §2): GraphQL SDL in,
`declared_shape` facts out.

The SDL here mirrors `fixtures/orders-service/src/main/resources/graphql`,
duplicated on purpose for the same reason the `.proto` copies in
`test_descriptors.py` are: the interpreter is a pure function over payloads,
and a unit test of it must not depend on a fixture build having run.

Two things separate this format from the other two, and most of the tests
below exist for them. A GraphQL file is not a schema on its own — Spring
merges every `.graphqls` under the root into one type universe, so a
cross-file reference must resolve — and SDL compiles into no class at all, so
the `GeneratedNaming` hook every other format needs is never consulted.
"""

import pytest

from sextant.domain.facts import DeclaredShapeFact, EmbeddedDescriptorFact
from sextant.ingress.interpret.descriptors import SchemaLocation, interpret_descriptors

SCHEMA_SDL = """
type Query {
  orderById(id: ID!): Order
  orders: [Order!]!
  auditTrail(id: ID!): [AuditEntry!]
}
type Mutation { placeOrder(sku: String!): Order }
type Subscription { orderUpdates: Order }

"A comment-shaped description, which is schema text and not a field."
type Order implements Node {
  id: ID!
  lines: [String!]
  totals: Long
  status: OrderStatus!
  count: Int
  ratio: Float
  active: Boolean!
}
interface Node { id: ID! }
enum OrderStatus { OPEN CLOSED }
input OrderFilter { sku: String, open: Boolean! }
scalar Long
"""

AUDIT_SDL = "type AuditEntry { at: String!, actor: String }\n"


class _RefusingNaming:
    """SDL compiles into no class, so nothing may ask this what a generated
    one would be called. A double that raises is the only way to prove the
    hook is not consulted — a recording double would pass whether the
    production code called it with a plausible location or not."""

    def class_symbol(self, location: SchemaLocation) -> str:
        raise AssertionError(f"the naming hook must not be consulted for SDL: {location}")


def _sdl(
    payload: str, symbol: str = "schema.graphqls", document_id: str = "doc:schema"
) -> EmbeddedDescriptorFact:
    return EmbeddedDescriptorFact(
        document_id=document_id,
        symbol=symbol,
        schema_format="graphql",
        payload=payload,
        origin="source",
    )


def _interpret(facts: list[EmbeddedDescriptorFact]) -> tuple[list[DeclaredShapeFact], list[str]]:
    return interpret_descriptors(facts, _RefusingNaming())


def _module() -> list[EmbeddedDescriptorFact]:
    """Task 1's fixture module: two SDL files, one schema."""
    return [
        _sdl(SCHEMA_SDL),
        _sdl(AUDIT_SDL, symbol="audit.graphqls", document_id="doc:audit"),
    ]


def _shape(shapes: list[DeclaredShapeFact], symbol: str) -> DeclaredShapeFact:
    [found] = [shape for shape in shapes if shape.symbol == symbol]
    return found


def _fields(shape: DeclaredShapeFact) -> dict[str, object]:
    return {field.name: field for field in shape.fields}


def test_object_type_projects_fields():
    """The declaration's own answers, nothing derived: a type name is the
    symbol (SDL compiles to no class), GraphQL renames nothing on the wire,
    and the format has no field numbers."""
    shapes, failed = _interpret(_module())

    assert failed == []
    order = _shape(shapes, "Order")
    assert order.schema_format == "graphql"
    assert order.schema_name == "Order"
    assert order.origin == "source"
    # A repository file is a declaration about what the build ought to serve,
    # never compiler evidence that it does.
    assert order.evidence == "declared"
    fields = _fields(order)
    assert list(fields) == ["id", "lines", "totals", "status", "count", "ratio", "active"]
    assert (fields["id"].wire_type, fields["id"].wire_format) == ("string", None)
    assert fields["id"].wire_name == "id"
    assert fields["id"].field_number is None
    assert (fields["count"].wire_type, fields["count"].wire_format) == ("integer", "int32")
    assert (fields["ratio"].wire_type, fields["ratio"].wire_format) == ("number", "double")
    assert fields["active"].wire_type == "boolean"
    # An enum reaches the wire as `enum` carrying its constants, never as a
    # reference to a record of them (D00 §5b).
    assert fields["status"].wire_type == "enum"
    assert fields["status"].enum_symbols == ["OPEN", "CLOSED"]
    assert fields["status"].shape_ref is None


def test_a_custom_scalar_is_not_guessed_at():
    """`scalar Long` states a name and nothing about the wire: it may arrive
    as a JSON number, a string, or anything else the runtime's coercer
    chooses. `object` with no shape behind it is this vocabulary's
    least-committal answer (the same one the Avro branch gives a value with no
    encoding of its own) — the field stays open and is reported as a gap,
    which is the honest outcome; `string` would be a guess that reads as an
    observation."""
    shapes, failed = _interpret(_module())

    assert failed == []
    totals = _fields(_shape(shapes, "Order"))["totals"]
    assert (totals.wire_type, totals.wire_format) == ("object", None)
    assert totals.shape_ref is None
    # The scalar itself declares no payload, so it is no shape either.
    assert [shape for shape in shapes if shape.symbol == "Long"] == []


def test_bang_and_list_semantics():
    """`!` is the only presence statement SDL makes, and it makes it twice per
    list — once about the list and once about what it holds. A projection
    that lost the inner one would match a caller sending `[null]` against a
    callee that rejects it."""
    shapes, failed = _interpret([_sdl(SCHEMA_SDL), _sdl(AUDIT_SDL, symbol="audit.graphqls")])

    assert failed == []
    fields = _fields(_shape(shapes, "Query"))
    # `[Order!]!` — the list is required and non-null, its items non-null.
    orders = fields["orders"]
    assert (orders.required, orders.nullable) == (True, False)
    assert orders.wire_type == "array"
    assert orders.item == {
        "wire_type": "object",
        "wire_format": None,
        "nullable": False,
        "shape_id": "Order",
    }
    # `[AuditEntry!]` — same items, but the list itself may be absent.
    audit = fields["auditTrail"]
    assert (audit.required, audit.nullable) == (False, True)
    assert audit.item == {
        "wire_type": "object",
        "wire_format": None,
        "nullable": False,
        "shape_id": "AuditEntry",
    }
    # A bare object reference: `shape_ref`, never `item`.
    by_id = fields["orderById"]
    assert (by_id.wire_type, by_id.shape_ref, by_id.item) == ("object", "Order", None)
    assert (by_id.required, by_id.nullable) == (False, True)
    # `[String!]` on Order — a scalar element, non-null inside a nullable list.
    lines = _fields(_shape(shapes, "Order"))["lines"]
    assert (lines.required, lines.nullable) == (False, True)
    assert lines.item == {"wire_type": "string", "wire_format": None, "nullable": False}


def test_the_two_list_spellings_are_distinguished_on_item_versus_field():
    """`[T!]` and `[T]!` differ only in which half the `!` binds to, and a
    projection that collapsed them would report the opposite contract."""
    shapes, failed = _interpret([_sdl("type Holder { a: [String!]\n b: [String]! }\n")])

    assert failed == []
    fields = _fields(_shape(shapes, "Holder"))
    assert (fields["a"].required, fields["a"].nullable) == (False, True)
    assert fields["a"].item == {"wire_type": "string", "wire_format": None, "nullable": False}
    assert (fields["b"].required, fields["b"].nullable) == (True, False)
    assert fields["b"].item == {"wire_type": "string", "wire_format": None, "nullable": True}


def test_multi_file_merge():
    """Spring merges every `.graphqls` under the root into one schema, so
    `Query.auditTrail` naming a type the OTHER file declares must resolve.
    Interpreting one payload at a time would report it as an unknown
    reference — the protobuf pool's own reason for being module-wide."""
    shapes, failed = _interpret(_module())

    assert failed == []
    audit_trail = _fields(_shape(shapes, "Query"))["auditTrail"]
    assert audit_trail.item is not None
    assert audit_trail.item["shape_id"] == "AuditEntry"
    # Each shape stays with the document that declared it: fact files are
    # per-document, and a shape written into the wrong one would move it.
    assert _shape(shapes, "AuditEntry").document_id == "doc:audit"
    assert _shape(shapes, "Query").document_id == "doc:schema"


def test_interface_and_input_and_enum():
    """Every type that names a payload becomes a shape: an interface is what
    a field typed by it will carry, an input is what an operation receives,
    and an enum is a type something can reference by name."""
    shapes, failed = _interpret(_module())

    assert failed == []
    assert {shape.symbol for shape in shapes} == {
        "Query",
        "Mutation",
        "Subscription",
        "Order",
        "Node",
        "OrderStatus",
        "OrderFilter",
        "AuditEntry",
    }
    node = _fields(_shape(shapes, "Node"))
    assert (node["id"].wire_type, node["id"].required) == ("string", True)
    order_filter = _fields(_shape(shapes, "OrderFilter"))
    assert (order_filter["sku"].required, order_filter["sku"].nullable) == (False, True)
    assert (order_filter["open"].required, order_filter["open"].nullable) == (True, False)
    # An enum's constants are not fields — a record of them is a payload
    # nobody sends (D00 §5b). They ride on every field that references it.
    assert _shape(shapes, "OrderStatus").fields == []


def test_an_input_default_is_what_makes_a_non_null_field_omittable():
    """GraphQL's own rule, and the same one Avro states: a default is what
    makes a field optional, so a non-null input field carrying one is not
    required."""
    shapes, failed = _interpret([_sdl('input Filter { sku: String! = "any", open: Boolean! }\n')])

    assert failed == []
    fields = _fields(_shape(shapes, "Filter"))
    assert (fields["sku"].required, fields["sku"].nullable) == (False, False)
    # Verbatim, the SDL's own spelling of the value (D00 §5c).
    assert fields["sku"].default == '"any"'
    assert (fields["open"].required, fields["open"].default) == (True, None)


def test_a_type_extension_merges_into_the_type_it_extends():
    """`extend type Query` in a second file is how a multi-file schema adds
    an operation, and the runtime merges it before serving anything. Dropping
    the extension's fields would omit real operations with no gap to show for
    it (D00 §3)."""
    shapes, failed = _interpret(
        [
            _sdl("type Query { orders: [Order!]! }\ntype Order { id: ID! }\n"),
            _sdl("extend type Query { audits: String }\n", symbol="audit.graphqls"),
        ]
    )

    assert failed == []
    assert list(_fields(_shape(shapes, "Query"))) == ["orders", "audits"]


def test_a_type_extension_from_a_failed_file_does_not_reach_the_type_it_extends():
    """Fix round 1, IMPORTANT: the merge used to be built before the gap list
    was, so a file that publishes NO shape of its own still published fields
    into someone else's type — half a schema, sneaked in through the back
    door the failure boundary exists to close."""
    sound = _sdl("type Query { ok: String }\n", symbol="a.graphqls", document_id="doc:a")
    failing = _sdl(
        "extend type Query { sneaky: String }\ntype Dup { x: String }\n",
        symbol="b.graphqls",
        document_id="doc:b",
    )
    duplicate = _sdl("type Dup { y: String }\n", symbol="c.graphqls", document_id="doc:c")

    shapes, failed = _interpret([sound, failing, duplicate])

    assert failed == ["b.graphqls", "c.graphqls"]
    assert list(_fields(_shape(shapes, "Query"))) == ["ok"]


def test_the_schema_block_says_which_type_answers_which_operation():
    """A `schema` block exists to rename the roots, so the binding cannot be
    recovered from a type's own name — and nothing downstream may parse SDL
    (the confinement rule), so the answer has to ride on the fact itself."""
    shapes, failed = _interpret(
        [
            _sdl(
                "schema { query: MyQuery, mutation: MyMutation }\n"
                "type MyQuery { a: String }\n"
                "type MyMutation { b: String }\n"
                "type Query { c: String }\n"
            )
        ]
    )

    assert failed == []
    assert _shape(shapes, "MyQuery").role == "query"
    assert _shape(shapes, "MyMutation").role == "mutation"
    # Named `Query` but bound to nothing: a schema block that names its roots
    # is the whole answer, exactly as the GraphQL spec says.
    assert _shape(shapes, "Query").role is None


def test_the_default_root_names_carry_their_roles_when_no_schema_block_binds_them():
    shapes, failed = _interpret(_module())

    assert failed == []
    assert [(shape.symbol, shape.role) for shape in shapes if shape.role is not None] == [
        ("Mutation", "mutation"),
        ("Query", "query"),
        ("Subscription", "subscription"),
    ]
    # Every ordinary payload type carries no role at all.
    assert _shape(shapes, "Order").role is None


def test_the_naming_hook_is_never_consulted():
    """SDL compiles into no class, so a source-origin symbol IS the schema's
    own type name. `_RefusingNaming` raising is the assertion."""
    shapes, _ = _interpret(_module())

    assert [shape.symbol for shape in shapes] == [shape.schema_name for shape in shapes]


# --- failure is a gap, never a crash -------------------------------------


def test_malformed_document_is_gap():
    """One unparseable file is one gap: every other file in the module still
    interprets, and the broken one's own partial reads are discarded rather
    than half-published (2G's Avro rule)."""
    broken = _sdl("type Order { id: ID! ", symbol="broken.graphqls", document_id="doc:broken")

    shapes, failed = _interpret([broken, *_module()])

    assert failed == ["broken.graphqls"]
    assert "Order" in {shape.symbol for shape in shapes}
    assert all(shape.document_id != "doc:broken" for shape in shapes)


def test_unknown_reference_is_gap():
    """A field typed by a name nothing in the module declares is a schema the
    runtime would refuse to build. That file's whole projection is dropped —
    half a type universe is a set of shapes nobody declared."""
    dangling = _sdl(
        "type Cart { id: ID! }\ntype Basket { missing: Ghost! }\n",
        symbol="dangling.graphqls",
        document_id="doc:dangling",
    )

    shapes, failed = _interpret([dangling, *_module()])

    assert failed == ["dangling.graphqls"]
    # Not even the sound type beside it: the file is the failure boundary.
    assert {shape.symbol for shape in shapes}.isdisjoint({"Cart", "Basket"})
    assert "Order" in {shape.symbol for shape in shapes}


def test_a_type_declared_twice_fails_every_file_that_declares_it():
    """Two files declaring one type name is a schema Spring itself rejects,
    and there is no way to tell which one the runtime meant. Both are gaps;
    a module that happens not to reference the duplicate still interprets."""
    first = _sdl("type Order { id: ID! }\n", symbol="one.graphqls", document_id="doc:one")
    second = _sdl("type Order { sku: String }\n", symbol="two.graphqls", document_id="doc:two")
    unrelated = _sdl(AUDIT_SDL, symbol="audit.graphqls", document_id="doc:audit")

    shapes, failed = _interpret([first, second, unrelated])

    assert failed == ["one.graphqls", "two.graphqls"]
    assert [shape.symbol for shape in shapes] == ["AuditEntry"]


def test_a_union_is_a_gap_rather_than_an_empty_shape():
    """Fix round 1, SPEC: a union is one of several types, and this vocabulary
    has no word for that — its members are separate shapes and it has no field
    of its own to carry them. Publishing it as a fieldless shape would be an
    omission dressed as success; `extend union` was already a gap, and a plain
    one now gives the same answer for the same reason."""
    with_union = _sdl(
        "type Cart { id: ID! }\nunion Res = Cart | Basket\ntype Basket { sku: String }\n",
        symbol="union.graphqls",
        document_id="doc:union",
    )

    shapes, failed = _interpret([with_union, *_module()])

    assert failed == ["union.graphqls"]
    # Not even the two sound types beside it: the file is the failure boundary.
    assert {shape.symbol for shape in shapes}.isdisjoint({"Res", "Cart", "Basket"})
    assert "Order" in {shape.symbol for shape in shapes}


def test_an_extend_union_is_a_gap_for_the_same_reason_a_plain_union_is():
    extending = _sdl("union Res = Cart\n", symbol="union.graphqls", document_id="doc:union")
    extension = _sdl(
        "extend union Res = Basket\ntype Basket { sku: String }\n",
        symbol="more.graphqls",
        document_id="doc:more",
    )

    shapes, failed = _interpret([extending, extension])

    assert failed == ["more.graphqls", "union.graphqls"]
    assert shapes == []


def test_an_operations_document_is_ignored_rather_than_reported():
    """Fix round 1, MINOR: `.graphql` also spells the queries a CLIENT sends.
    Such a file declares no type because it is not a schema — reporting it
    would be a permanent gap naming a file that is missing nothing."""
    operations = _sdl(
        "query Orders { orders { id } }\nfragment F on Order { id }\n", symbol="query.graphql"
    )

    shapes, failed = _interpret([operations])

    assert (shapes, failed) == ([], [])


def test_a_file_that_mixes_operations_with_types_still_declares_its_types():
    shapes, failed = _interpret([_sdl("query Q { a }\ntype Order { id: ID! }\n")])

    assert failed == []
    assert [shape.symbol for shape in shapes] == ["Order"]


def test_an_unreadable_file_takes_the_types_it_declared_with_it():
    """The cascade, stated: a file whose text does not parse declared nothing
    this module can see, so a sibling naming one of its types is naming a type
    the merged schema does not contain — the state the runtime would refuse to
    start in, and a gap of its own rather than a shape pointing at nothing."""
    broken = _sdl("type Ghost { id: ID! ", symbol="ghost.graphqls", document_id="doc:ghost")
    referring = _sdl(
        "type Haunted { ghost: Ghost }\n", symbol="haunted.graphqls", document_id="doc:haunted"
    )

    shapes, failed = _interpret([broken, referring, *_module()])

    assert failed == ["ghost.graphqls", "haunted.graphqls"]
    assert "Order" in {shape.symbol for shape in shapes}


# --- determinism (NFR-1) -------------------------------------------------


def test_output_deterministic():
    """Descriptor input order is whatever the artifact walk produced, and the
    fact files are content-hashed: two orders that disagree are two answers."""
    descriptors = _module()

    first, first_failed = _interpret(descriptors)
    second, second_failed = _interpret(list(reversed(descriptors)))

    assert [shape.model_dump_json() for shape in first] == [
        shape.model_dump_json() for shape in second
    ]
    assert [shape.symbol for shape in first] == sorted(shape.symbol for shape in first)
    assert first_failed == second_failed == []


@pytest.mark.parametrize("reverse", [False, True])
def test_the_gap_list_does_not_depend_on_input_order(reverse: bool):
    broken = _sdl("type Order { id: ID! ", symbol="broken.graphqls", document_id="doc:broken")
    descriptors = [broken, *_module()]

    _, failed = _interpret(list(reversed(descriptors)) if reverse else descriptors)

    assert failed == ["broken.graphqls"]
