"""The interpreter's fourth schema format (2I design §3): WSDL/XSD in,
`declared_shape` facts out.

The XML here mirrors `fixtures/orders-service/src/main/resources/wsdl`,
duplicated on purpose for the same reason the `.proto` copies in
`test_descriptors.py` and the SDL copies in `test_graphql_descriptors.py` are:
the interpreter is a pure function over payloads, and a unit test of it must
not depend on a fixture build having run.

Three things separate this format from the other three, and most of the tests
below exist for them. A WSDL is not a schema on its own — its `<types>` holds
an `xsd:import` and the types live next door, so the module's files are ONE
universe and a cross-file reference must resolve. A contract file compiles
into no class at all, so the `GeneratedNaming` hook every non-SDL format needs
is never consulted. And a WSDL says something no other format here says: which
of its declared elements ARE operations, which is the `role` mark Task 4
derives endpoints from.
"""

from sextant.domain.facts import DeclaredShapeFact, EmbeddedDescriptorFact
from sextant.ingress.interpret.descriptors import SchemaLocation, interpret_descriptors

# Task 1's fixture, verbatim in structure: the `xs:` prefix here and the
# `xsd:` prefix in the WSDL below are deliberately different, so nothing can
# pass by assuming one spelling of the XML Schema namespace.
TYPES_XSD = """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:tns="http://orders.example.com/ws"
           targetNamespace="http://orders.example.com/ws"
           elementFormDefault="qualified">
  <xs:simpleType name="status">
    <xs:restriction base="xs:string">
      <xs:enumeration value="NEW"/>
      <xs:enumeration value="CONFIRMED"/>
      <xs:enumeration value="SHIPPED"/>
      <xs:enumeration value="CANCELLED"/>
    </xs:restriction>
  </xs:simpleType>
  <xs:element name="placeOrderRequest">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="sku" type="xs:string"/>
        <xs:element name="count" type="xs:int"/>
        <xs:element name="note" type="xs:string" minOccurs="0"/>
        <xs:element name="tags" type="xs:string" maxOccurs="unbounded"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
  <xs:element name="quoteOrderRequest">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="sku" type="xs:string"/>
        <xs:element name="count" type="xs:int"/>
        <xs:element name="status" type="tns:status"/>
        <xs:element name="cancelledAt" type="xs:dateTime" nillable="true"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
"""

ORDERS_WSDL = """<?xml version="1.0" encoding="UTF-8"?>
<wsdl:definitions name="OrdersService"
    targetNamespace="http://orders.example.com/ws"
    xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
    xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
    xmlns:tns="http://orders.example.com/ws"
    xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <wsdl:types>
    <xsd:schema>
      <xsd:import namespace="http://orders.example.com/ws"
                  schemaLocation="orders-types.xsd"/>
    </xsd:schema>
  </wsdl:types>
  <wsdl:message name="placeOrderRequestMessage">
    <wsdl:part name="parameters" element="tns:placeOrderRequest"/>
  </wsdl:message>
  <wsdl:message name="quoteOrderRequestMessage">
    <wsdl:part name="parameters" element="tns:quoteOrderRequest"/>
  </wsdl:message>
  <wsdl:portType name="OrdersPort">
    <wsdl:operation name="placeOrder">
      <wsdl:input message="tns:placeOrderRequestMessage"/>
    </wsdl:operation>
    <wsdl:operation name="quoteOrder">
      <wsdl:input message="tns:quoteOrderRequestMessage"/>
    </wsdl:operation>
  </wsdl:portType>
</wsdl:definitions>
"""

NS = "http://orders.example.com/ws"


class _RefusingNaming:
    """A contract file compiles into no class, so nothing may ask this what a
    generated one would be called. A double that raises is the only way to
    prove the hook is not consulted — a recording double would pass whether
    the production code called it with a plausible location or not."""

    def class_symbol(self, location: SchemaLocation) -> str:
        raise AssertionError(f"the naming hook must not be consulted for WSDL: {location}")


def _contract(payload: str, symbol: str, document_id: str | None = None):
    return EmbeddedDescriptorFact(
        document_id=document_id or f"doc:{symbol}",
        symbol=symbol,
        schema_format="wsdl",
        payload=payload,
        origin="source",
    )


def _interpret(facts: list[EmbeddedDescriptorFact]) -> tuple[list[DeclaredShapeFact], list[str]]:
    return interpret_descriptors(facts, _RefusingNaming())


def _module() -> list[EmbeddedDescriptorFact]:
    """Task 1's fixture module: one WSDL, one XSD, one type universe."""
    return [
        _contract(ORDERS_WSDL, "orders.wsdl"),
        _contract(TYPES_XSD, "orders-types.xsd"),
    ]


def _shape(shapes: list[DeclaredShapeFact], symbol: str) -> DeclaredShapeFact:
    [found] = [shape for shape in shapes if shape.symbol == symbol]
    return found


def _fields(shape: DeclaredShapeFact) -> dict[str, object]:
    return {field.name: field for field in shape.fields}


def test_a_global_element_projects_the_payload_it_declares():
    """The declaration's own answers, nothing derived: an element's QName is
    both symbol and schema_name (a contract compiles to no class), XSD renames
    nothing on the wire, and the format has no field numbers."""
    shapes, failed = _interpret(_module())

    assert failed == []
    request = _shape(shapes, f"{{{NS}}}placeOrderRequest")
    assert request.schema_format == "wsdl"
    assert request.schema_name == f"{{{NS}}}placeOrderRequest"
    assert request.origin == "source"
    # A repository file is a declaration about what the build ought to serve,
    # never compiler evidence that it does.
    assert request.evidence == "declared"
    # The XSD's document, not the WSDL's: a shape belongs to the file that
    # declared it, even though the operation marking came from the other one.
    assert request.document_id == "doc:orders-types.xsd"
    fields = _fields(request)
    assert list(fields) == ["sku", "count", "note", "tags"]
    assert (fields["sku"].wire_type, fields["sku"].wire_format) == ("string", None)
    # Verbatim: an XSD element's declared name IS its element name on the
    # wire, so there is no second spelling for a wire name to disagree with.
    assert fields["sku"].wire_name == "sku"
    assert fields["sku"].field_number is None
    assert (fields["count"].wire_type, fields["count"].wire_format) == ("integer", "int32")


def test_min_occurs_zero_is_the_only_thing_that_makes_a_field_optional():
    """XSD states presence outright, and `minOccurs` defaults to 1 — so every
    element without one is required, and nothing here is inferred from a
    type's nullability (D00 §5b's trap)."""
    shapes, _ = _interpret(_module())

    fields = _fields(_shape(shapes, f"{{{NS}}}placeOrderRequest"))
    assert fields["sku"].required is True
    assert fields["count"].required is True
    assert fields["note"].required is False
    # Absence and nil-ness are different claims: an omittable element is not
    # thereby a nillable one.
    assert fields["note"].nullable is False


def test_nillable_is_the_only_thing_that_makes_a_field_nullable():
    """`xsi:nil` is XSD's own way of sending a present-but-null element, and
    it is declared per element — the mirror image of the presence rule above."""
    shapes, _ = _interpret(_module())

    fields = _fields(_shape(shapes, f"{{{NS}}}quoteOrderRequest"))
    assert fields["cancelledAt"].nullable is True
    # Still required: nillable says the value may be nil, never that the
    # element may be absent.
    assert fields["cancelledAt"].required is True
    assert (fields["cancelledAt"].wire_type, fields["cancelledAt"].wire_format) == (
        "string",
        "date-time",
    )
    assert fields["sku"].nullable is False


def test_max_occurs_unbounded_is_an_array_carrying_what_it_repeats():
    """A repeated element is one element declaration, not one field per
    occurrence — the array's `item` is D01 §5's descriptor for what it holds."""
    shapes, _ = _interpret(_module())

    tags = _fields(_shape(shapes, f"{{{NS}}}placeOrderRequest"))["tags"]
    assert tags.wire_type == "array"
    assert tags.wire_format is None
    assert tags.item == {"wire_type": "string", "wire_format": None, "nullable": False}
    # The array's own shape_ref is None: what it holds is in `item`.
    assert tags.shape_ref is None


def test_a_bounded_repeat_greater_than_one_is_equally_an_array():
    """`maxOccurs="5"` repeats exactly as `unbounded` does — a cardinality
    bound is not a different wire form, and reading only the word `unbounded`
    would report a list as a scalar."""
    schema = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
                   targetNamespace="urn:a" elementFormDefault="qualified">
      <xs:element name="batch">
        <xs:complexType>
          <xs:sequence>
            <xs:element name="line" type="xs:string" maxOccurs="5"/>
            <xs:element name="only" type="xs:string" maxOccurs="1"/>
          </xs:sequence>
        </xs:complexType>
      </xs:element>
    </xs:schema>"""
    shapes, failed = _interpret([_contract(schema, "batch.xsd")])

    assert failed == []
    fields = _fields(_shape(shapes, "{urn:a}batch"))
    assert fields["line"].wire_type == "array"
    assert fields["only"].wire_type == "string"


def test_an_enumeration_facet_reaches_the_wire_as_enum_carrying_its_constants():
    """D00 §5b: an enumeration reaches the wire as `enum`, never as a record
    of its constants — which is why a `simpleType` earns no shape of its own
    and its constants ride on every field that references it."""
    shapes, _ = _interpret(_module())

    status = _fields(_shape(shapes, f"{{{NS}}}quoteOrderRequest"))["status"]
    assert status.wire_type == "enum"
    assert status.enum_symbols == ["NEW", "CONFIRMED", "SHIPPED", "CANCELLED"]
    assert status.shape_ref is None
    # A restricted scalar is not a payload anybody sends, so there is no
    # `{ns}status` shape to point at.
    assert [shape.symbol for shape in shapes if shape.symbol.endswith("}status")] == []


def test_a_named_complex_type_is_its_own_shape_and_a_reference_reaches_it():
    """Unlike a simpleType, a complexType IS a payload — something sends one —
    so it earns a shape, and a field typed by it carries an ordinary
    `shape_ref` to that shape's QName."""
    schema = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
                   xmlns:tns="urn:a" targetNamespace="urn:a">
      <xs:complexType name="Line">
        <xs:sequence><xs:element name="sku" type="xs:string"/></xs:sequence>
      </xs:complexType>
      <xs:element name="order">
        <xs:complexType>
          <xs:sequence><xs:element name="line" type="tns:Line"/></xs:sequence>
        </xs:complexType>
      </xs:element>
    </xs:schema>"""
    shapes, failed = _interpret([_contract(schema, "order.xsd")])

    assert failed == []
    assert _shape(shapes, "{urn:a}Line").schema_name == "{urn:a}Line"
    line = _fields(_shape(shapes, "{urn:a}order"))["line"]
    assert line.wire_type == "object"
    assert line.shape_ref == "{urn:a}Line"


def test_an_element_typed_by_a_named_complex_type_carries_that_types_fields():
    """The element is what goes on the wire, so its shape has to describe what
    the payload actually contains. This vocabulary has no way to say "this
    shape IS that one", so the fields are carried on both — never left off the
    element, which would publish an empty payload nobody sends."""
    schema = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
                   xmlns:tns="urn:a" targetNamespace="urn:a">
      <xs:complexType name="Ping">
        <xs:sequence><xs:element name="at" type="xs:dateTime"/></xs:sequence>
      </xs:complexType>
      <xs:element name="ping" type="tns:Ping"/>
    </xs:schema>"""
    shapes, failed = _interpret([_contract(schema, "ping.xsd")])

    assert failed == []
    assert list(_fields(_shape(shapes, "{urn:a}ping"))) == ["at"]
    assert list(_fields(_shape(shapes, "{urn:a}Ping"))) == ["at"]


def test_an_element_ref_borrows_the_referenced_elements_name_and_type():
    """`ref` is how XSD reuses a global element declaration, and the referenced
    declaration is what the wire carries — reading the local `ref` attribute as
    a name would put a prefixed QName where an element name belongs."""
    schema = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
                   xmlns:tns="urn:a" targetNamespace="urn:a">
      <xs:element name="sku" type="xs:string"/>
      <xs:element name="order">
        <xs:complexType>
          <xs:sequence><xs:element ref="tns:sku" minOccurs="0"/></xs:sequence>
        </xs:complexType>
      </xs:element>
    </xs:schema>"""
    shapes, failed = _interpret([_contract(schema, "ref.xsd")])

    assert failed == []
    sku = _fields(_shape(shapes, "{urn:a}order"))["sku"]
    assert sku.wire_name == "sku"
    assert sku.wire_type == "string"
    # The local `minOccurs` still governs: a ref borrows the declaration, not
    # the occurrence.
    assert sku.required is False


def test_an_anonymous_nested_complex_type_is_named_by_the_path_that_reaches_it():
    """XSD gives an inline complexType no name, and this vocabulary needs one
    to point a `shape_ref` at. The containing shape's QName plus the element
    name is the only identity the schema itself states — `/` cannot appear in
    an NCName, so a synthesized name can never collide with a real QName."""
    schema = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
                   targetNamespace="urn:a">
      <xs:element name="order">
        <xs:complexType>
          <xs:sequence>
            <xs:element name="line">
              <xs:complexType>
                <xs:sequence><xs:element name="sku" type="xs:string"/></xs:sequence>
              </xs:complexType>
            </xs:element>
          </xs:sequence>
        </xs:complexType>
      </xs:element>
    </xs:schema>"""
    shapes, failed = _interpret([_contract(schema, "nested.xsd")])

    assert failed == []
    line = _fields(_shape(shapes, "{urn:a}order"))["line"]
    assert line.shape_ref == "{urn:a}order/line"
    assert list(_fields(_shape(shapes, "{urn:a}order/line"))) == ["sku"]


def test_a_wsdl_types_block_and_a_standalone_xsd_are_one_universe():
    """A WSDL embeds XSD in `<types>` and imports the rest from beside it, so
    a type one file declares is routinely referenced by the next — a per-file
    interpretation would report the reference as dangling, which is why the
    merge is module-wide (2G design §3)."""
    wsdl = """<wsdl:definitions targetNamespace="urn:a"
        xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
        xmlns:tns="urn:a" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
      <wsdl:types>
        <xsd:schema targetNamespace="urn:a">
          <xsd:import namespace="urn:a" schemaLocation="lines.xsd"/>
          <xsd:element name="order">
            <xsd:complexType>
              <xsd:sequence><xsd:element name="line" type="tns:Line"/></xsd:sequence>
            </xsd:complexType>
          </xsd:element>
        </xsd:schema>
      </wsdl:types>
    </wsdl:definitions>"""
    lines = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:a">
      <xs:complexType name="Line">
        <xs:sequence><xs:element name="sku" type="xs:string"/></xs:sequence>
      </xs:complexType>
    </xs:schema>"""
    shapes, failed = _interpret([_contract(wsdl, "a.wsdl"), _contract(lines, "lines.xsd")])

    assert failed == []
    # The element declared inside the WSDL's own `<types>` is a shape like any
    # other, and it reaches a type the sibling file declared.
    assert _fields(_shape(shapes, "{urn:a}order"))["line"].shape_ref == "{urn:a}Line"
    assert _shape(shapes, "{urn:a}Line").document_id == "doc:lines.xsd"


def test_an_import_naming_a_file_the_module_does_not_carry_fails_that_file_alone():
    """The 2H boundary verbatim: a file whose import never arrives is one
    file's gap and no reason to lose the others. It has to be checked
    explicitly — the fixture's WSDL declares nothing of its own, so a silently
    dropped import would leave it publishing no shape AND no gap, which is an
    omission dressed as success (D00 §3)."""
    other = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:b">
      <xs:element name="ping" type="xs:string"/>
    </xs:schema>"""
    shapes, failed = _interpret([_contract(ORDERS_WSDL, "orders.wsdl"), _contract(other, "b.xsd")])

    assert failed == ["orders.wsdl"]
    # The sibling still interprets: a gap is one file's, never the module's.
    assert [shape.symbol for shape in shapes] == ["{urn:b}ping"]


def test_a_file_that_fails_publishes_nothing_at_all_rather_than_the_part_that_read():
    """Half a schema is a shape nobody declared (2G's Avro rule): the types
    read before the trouble are discarded, not published."""
    broken = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:a">
      <xs:element name="fine">
        <xs:complexType><xs:sequence><xs:element name="a" type="xs:string"/></xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="broken">
        <xs:complexType><xs:sequence><xs:element name="b" type="xs:string"/></xs:sequence></xs:complexType>
      </xs:element>
      <xs:import schemaLocation="nowhere.xsd"/>
    </xs:schema>"""
    shapes, failed = _interpret([_contract(broken, "broken.xsd")])

    assert failed == ["broken.xsd"]
    assert shapes == []


def test_a_type_name_two_files_declare_makes_gaps_of_both():
    """A duplicate declaration is a schema the runtime itself would refuse to
    build, and nothing here can pick a winner — so every file declaring it is
    a gap, never a fold whose result depends on arrival order (NFR-1)."""
    first = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:a">
      <xs:complexType name="Line">
        <xs:sequence><xs:element name="sku" type="xs:string"/></xs:sequence>
      </xs:complexType>
    </xs:schema>"""
    second = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:a">
      <xs:complexType name="Line">
        <xs:sequence><xs:element name="code" type="xs:string"/></xs:sequence>
      </xs:complexType>
      <xs:element name="ping" type="xs:string"/>
    </xs:schema>"""
    innocent = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:c">
      <xs:element name="other" type="xs:string"/>
    </xs:schema>"""
    shapes, failed = _interpret(
        [
            _contract(first, "one.xsd"),
            _contract(second, "two.xsd"),
            _contract(innocent, "three.xsd"),
        ]
    )

    assert failed == ["one.xsd", "two.xsd"]
    assert [shape.symbol for shape in shapes] == ["{urn:c}other"]


def test_a_gapped_files_declarations_reach_nobody_elses_shape():
    """The failure boundary is only a boundary if it holds in BOTH directions.
    A file that publishes nothing must not publish a DECLARATION into a
    sibling's fields either — otherwise a shape read out of a file `failed`
    reports as unpublishable is exactly the half-schema the boundary exists to
    prevent, crossing it under another file's name.

    The sibling gaps instead, as a dangling reference, which is what it now is:
    this run published no such shape for its `shape_ref` to reach."""
    # Duplicated across two files, so both of them gap and `Line` leaves the
    # universe with them.
    duplicate = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:a">
      <xs:complexType name="Line">
        <xs:sequence><xs:element name="sku" type="xs:string"/></xs:sequence>
      </xs:complexType>
    </xs:schema>"""
    sibling = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
                   xmlns:tns="urn:a" targetNamespace="urn:a">
      <xs:element name="order">
        <xs:complexType>
          <xs:sequence><xs:element name="line" type="tns:Line"/></xs:sequence>
        </xs:complexType>
      </xs:element>
    </xs:schema>"""
    shapes, failed = _interpret(
        [
            _contract(duplicate, "one.xsd"),
            _contract(duplicate, "two.xsd"),
            _contract(sibling, "sibling.xsd"),
        ]
    )

    assert failed == ["one.xsd", "sibling.xsd", "two.xsd"]
    # Not a shape whose `line` field points at a `{urn:a}Line` nothing
    # published.
    assert shapes == []


def test_a_global_element_never_inlines_the_fields_of_a_gapped_complex_type():
    """The same leak by the other route, and the worse one: an element typed
    by a named complex type carries that type's FIELDS, so a gapped file's
    declarations would be copied wholesale into a surviving shape rather than
    merely referenced."""
    duplicate = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:a">
      <xs:complexType name="Hidden">
        <xs:sequence><xs:element name="secret" type="xs:string"/></xs:sequence>
      </xs:complexType>
    </xs:schema>"""
    sibling = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
                   xmlns:tns="urn:a" targetNamespace="urn:a">
      <xs:element name="order" type="tns:Hidden"/>
    </xs:schema>"""
    shapes, failed = _interpret(
        [
            _contract(duplicate, "one.xsd"),
            _contract(duplicate, "two.xsd"),
            _contract(sibling, "sibling.xsd"),
        ]
    )

    assert failed == ["one.xsd", "sibling.xsd", "two.xsd"]
    assert shapes == []
    assert "secret" not in repr(shapes)


def test_an_input_message_carrying_several_parts_is_that_wsdls_gap():
    """Document/literal WRAPPED is exactly one part, and the wrapper element
    it names IS the operation. A multi-part message is legal and a different
    wire shape — marking each of its elements would silently turn ONE
    operation into two endpoints, which is a wrong answer rather than a
    partial one."""
    wsdl = """<wsdl:definitions targetNamespace="urn:a"
        xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/" xmlns:tns="urn:a">
      <wsdl:message name="m">
        <wsdl:part name="head" element="tns:first"/>
        <wsdl:part name="body" element="tns:second"/>
      </wsdl:message>
      <wsdl:portType name="P">
        <wsdl:operation name="go"><wsdl:input message="tns:m"/></wsdl:operation>
      </wsdl:portType>
    </wsdl:definitions>"""
    schema = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:a">
      <xs:element name="first" type="xs:string"/>
      <xs:element name="second" type="xs:string"/>
    </xs:schema>"""
    shapes, failed = _interpret([_contract(wsdl, "multi.wsdl"), _contract(schema, "multi.xsd")])

    assert failed == ["multi.wsdl"]
    # The schema still interprets, and NEITHER element is marked: one
    # operation must never become two.
    assert [shape.role for shape in shapes] == [None, None]


def test_a_redefine_is_that_files_gap():
    """`xsd:redefine` REPLACES a declaration in the file it names, and this
    branch reads that file on its own terms — so the pre-redefine definition
    is what would reach the fact stream. Publishing the definition the
    contract explicitly replaced is a wrong answer, not a partial one."""
    base = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:a">
      <xs:complexType name="Line">
        <xs:sequence><xs:element name="sku" type="xs:string"/></xs:sequence>
      </xs:complexType>
    </xs:schema>"""
    redefining = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:a">
      <xs:redefine schemaLocation="base.xsd">
        <xs:complexType name="Line">
          <xs:complexContent>
            <xs:extension base="Line">
              <xs:sequence><xs:element name="extra" type="xs:string"/></xs:sequence>
            </xs:extension>
          </xs:complexContent>
        </xs:complexType>
      </xs:redefine>
    </xs:schema>"""
    shapes, failed = _interpret(
        [_contract(base, "base.xsd"), _contract(redefining, "redefine.xsd")]
    )

    assert failed == ["redefine.xsd"]
    # The redefined `extra` reaches nothing. The base file still publishes its
    # own `Line` under its own name, which is true of that file; what is
    # reported missing is the redefinition that rewrites it.
    assert "extra" not in repr(shapes)


def test_an_override_is_that_files_gap():
    """XSD 1.1's `xsd:override` replaces a declaration outright — the same lie
    `redefine` would tell, by a newer spelling, and previously not a known
    construct at all."""
    base = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:a">
      <xs:complexType name="Line">
        <xs:sequence><xs:element name="sku" type="xs:string"/></xs:sequence>
      </xs:complexType>
    </xs:schema>"""
    overriding = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:a">
      <xs:override schemaLocation="base.xsd">
        <xs:complexType name="Line">
          <xs:sequence><xs:element name="extra" type="xs:string"/></xs:sequence>
        </xs:complexType>
      </xs:override>
    </xs:schema>"""
    shapes, failed = _interpret(
        [_contract(base, "base.xsd"), _contract(overriding, "override.xsd")]
    )

    assert failed == ["override.xsd"]
    assert "extra" not in repr(shapes)


def test_a_same_namespace_include_resolves_like_an_import():
    """The ordinary `xsd:include`: one namespace split across two files, and
    the included file's declarations join the universe under their own QNames
    exactly as an import's do."""
    including = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
                      xmlns:tns="urn:a" targetNamespace="urn:a">
      <xs:include schemaLocation="lines.xsd"/>
      <xs:element name="order">
        <xs:complexType>
          <xs:sequence><xs:element name="line" type="tns:Line"/></xs:sequence>
        </xs:complexType>
      </xs:element>
    </xs:schema>"""
    lines = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:a">
      <xs:complexType name="Line">
        <xs:sequence><xs:element name="sku" type="xs:string"/></xs:sequence>
      </xs:complexType>
    </xs:schema>"""
    shapes, failed = _interpret([_contract(including, "order.xsd"), _contract(lines, "lines.xsd")])

    assert failed == []
    assert _fields(_shape(shapes, "{urn:a}order"))["line"].shape_ref == "{urn:a}Line"


def test_a_chameleon_include_is_the_including_files_gap():
    """A namespaced schema including one that declares NO `targetNamespace`:
    XSD says the included components take on the includer's namespace. This
    branch reads the included file on its own terms, so its declarations carry
    the bare names it wrote and no QName the contract actually states — a
    stated boundary, reported rather than published under a name nothing
    declared.

    The including schema deliberately does NOT reference `Line`: a schema that
    did would gap anyway, on the dangling reference, and would leave the real
    hole open — an includer that merely PUBLISHES alongside a chameleon
    include would otherwise report a complete contract while the module is
    missing every type the include was supposed to supply under the includer's
    namespace."""
    including = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
                      targetNamespace="urn:a">
      <xs:include schemaLocation="bare.xsd"/>
      <xs:element name="order">
        <xs:complexType>
          <xs:sequence><xs:element name="sku" type="xs:string"/></xs:sequence>
        </xs:complexType>
      </xs:element>
    </xs:schema>"""
    bare = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
      <xs:complexType name="Line">
        <xs:sequence><xs:element name="sku" type="xs:string"/></xs:sequence>
      </xs:complexType>
    </xs:schema>"""
    shapes, failed = _interpret([_contract(including, "order.xsd"), _contract(bare, "bare.xsd")])

    assert failed == ["order.xsd"]
    # The included file itself is fine on its own terms and still publishes —
    # under the bare name it actually wrote, which is the honest one.
    assert [shape.symbol for shape in shapes] == ["Line"]


def test_an_attribute_is_that_files_gap():
    """An `xsd:attribute` is part of the payload and this vocabulary has no
    field for one, so projecting the elements around it would report a payload
    missing what the contract says it carries. A ruled boundary (Task 3
    report §4.1) — reported, never dropped."""
    schema = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:a">
      <xs:element name="order">
        <xs:complexType>
          <xs:sequence><xs:element name="sku" type="xs:string"/></xs:sequence>
          <xs:attribute name="id" type="xs:string" use="required"/>
        </xs:complexType>
      </xs:element>
    </xs:schema>"""
    shapes, failed = _interpret([_contract(schema, "attribute.xsd")])

    assert failed == ["attribute.xsd"]
    assert shapes == []


def test_a_complex_content_model_is_that_files_gap():
    """`complexContent` derives one type from another by extension or
    restriction, and this branch resolves neither — the same ruled boundary,
    and the one a `redefine` would otherwise smuggle in."""
    schema = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
                   xmlns:tns="urn:a" targetNamespace="urn:a">
      <xs:complexType name="Base">
        <xs:sequence><xs:element name="sku" type="xs:string"/></xs:sequence>
      </xs:complexType>
      <xs:complexType name="Derived">
        <xs:complexContent>
          <xs:extension base="tns:Base">
            <xs:sequence><xs:element name="extra" type="xs:string"/></xs:sequence>
          </xs:extension>
        </xs:complexContent>
      </xs:complexType>
    </xs:schema>"""
    shapes, failed = _interpret([_contract(schema, "derived.xsd")])

    assert failed == ["derived.xsd"]
    assert shapes == []


def test_an_element_and_a_complex_type_sharing_a_qname_is_that_files_gap():
    """VALID XSD — the format has two symbol spaces where
    `DeclaredShapeFact.symbol` has one — and it is our representation that
    cannot hold both, not the contract that is wrong. Two facts under one
    symbol would read downstream as one shape declared twice, so the gap is
    the safer answer and it is REPORTED, unlike a silent drop."""
    schema = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
                   xmlns:tns="urn:a" targetNamespace="urn:a">
      <xs:complexType name="ping">
        <xs:sequence><xs:element name="at" type="xs:dateTime"/></xs:sequence>
      </xs:complexType>
      <xs:element name="ping" type="tns:ping"/>
    </xs:schema>"""
    shapes, failed = _interpret([_contract(schema, "collision.xsd")])

    assert failed == ["collision.xsd"]
    assert shapes == []


def test_a_schema_in_no_namespace_resolves_its_own_unprefixed_type_references():
    """XML's own rule: an unprefixed name is in the default namespace, and in
    NO namespace when none is declared. A schema without a `targetNamespace`
    writes every one of its own references that way, so reading an unprefixed
    name as unresolvable would gap the commonest schema there is."""
    schema = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
      <xs:complexType name="Line">
        <xs:sequence><xs:element name="sku" type="xs:string"/></xs:sequence>
      </xs:complexType>
      <xs:element name="order">
        <xs:complexType>
          <xs:sequence><xs:element name="line" type="Line"/></xs:sequence>
        </xs:complexType>
      </xs:element>
    </xs:schema>"""
    shapes, failed = _interpret([_contract(schema, "bare.xsd")])

    assert failed == []
    # No target namespace, so the QName IS the local name — W3C notation's own
    # rule, and the spelling an annotation-derived row would meet it on.
    assert _shape(shapes, "order").schema_name == "order"
    assert _fields(_shape(shapes, "order"))["line"].shape_ref == "Line"


def test_element_qualification_form_changes_no_recorded_name():
    """`elementFormDefault` and a local `form` decide whether a local element
    is namespace-QUALIFIED in the instance document. `wire_name` is the local
    name in every format this vocabulary carries, so qualification changes how
    a name is spelled in an XML document and never which name the field has —
    deliberately unread, and pinned here so a later reading of it is a
    decision rather than a drift."""
    body = """<xs:element name="order">
        <xs:complexType>
          <xs:sequence><xs:element name="sku" type="xs:string"/></xs:sequence>
        </xs:complexType>
      </xs:element>"""
    qualified = f"""<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
                       targetNamespace="urn:a" elementFormDefault="qualified">{body}</xs:schema>"""
    unqualified = f"""<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
                         targetNamespace="urn:a"
                         elementFormDefault="unqualified">{body}</xs:schema>"""
    first, _ = _interpret([_contract(qualified, "q.xsd")])
    second, _ = _interpret([_contract(unqualified, "u.xsd")])

    [sku] = first[0].fields
    assert (sku.name, sku.wire_name) == ("sku", "sku")
    assert [field.model_dump() for field in first[0].fields] == [
        field.model_dump() for field in second[0].fields
    ]


def test_a_choice_group_is_that_files_gap():
    """A choice is one of several elements, and this vocabulary has no word
    for that — the same answer a GraphQL union gets, for the same reason. A
    guessed projection would report fields the payload may not carry."""
    schema = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:a">
      <xs:element name="order">
        <xs:complexType>
          <xs:choice>
            <xs:element name="sku" type="xs:string"/>
            <xs:element name="code" type="xs:string"/>
          </xs:choice>
        </xs:complexType>
      </xs:element>
    </xs:schema>"""
    shapes, failed = _interpret([_contract(schema, "choice.xsd")])

    assert failed == ["choice.xsd"]
    assert shapes == []


def test_an_any_wildcard_is_that_files_gap():
    """`xsd:any` declares that anything at all may appear here. Projecting the
    fields around it would report a closed payload that is open."""
    schema = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:a">
      <xs:element name="order">
        <xs:complexType>
          <xs:sequence>
            <xs:element name="sku" type="xs:string"/>
            <xs:any namespace="##other"/>
          </xs:sequence>
        </xs:complexType>
      </xs:element>
    </xs:schema>"""
    shapes, failed = _interpret([_contract(schema, "any.xsd")])

    assert failed == ["any.xsd"]
    assert shapes == []


def test_a_substitution_group_is_that_files_gap():
    """A substitution group means the element on the wire may be any member of
    the group, so the declared element's own type is not what arrives."""
    schema = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
                   xmlns:tns="urn:a" targetNamespace="urn:a">
      <xs:element name="base" type="xs:string"/>
      <xs:element name="special" type="xs:string" substitutionGroup="tns:base"/>
    </xs:schema>"""
    shapes, failed = _interpret([_contract(schema, "substitution.xsd")])

    assert failed == ["substitution.xsd"]
    assert shapes == []


def test_a_type_nothing_in_the_module_declares_is_that_files_gap():
    """The dangling-reference rule the GraphQL branch already keeps: a field
    typed by a name the merged universe does not carry is a schema the runtime
    would refuse, and so a gap rather than a shape_ref pointing at nothing."""
    schema = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
                   xmlns:tns="urn:a" targetNamespace="urn:a">
      <xs:element name="order">
        <xs:complexType>
          <xs:sequence><xs:element name="line" type="tns:Missing"/></xs:sequence>
        </xs:complexType>
      </xs:element>
    </xs:schema>"""
    shapes, failed = _interpret([_contract(schema, "dangling.xsd")])

    assert failed == ["dangling.xsd"]
    assert shapes == []


def test_a_global_element_typed_by_a_name_nothing_declares_is_that_files_gap():
    """The dangling reference the empty-shape path would otherwise hide: this
    element carries no fields of its own, so a missing type would leave it
    publishing an EMPTY shape and no gap — which reads downstream as a payload
    that genuinely carries nothing (D00 §3)."""
    schema = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
                   xmlns:tns="urn:a" targetNamespace="urn:a">
      <xs:element name="order" type="tns:Missing"/>
    </xs:schema>"""
    shapes, failed = _interpret([_contract(schema, "missing-type.xsd")])

    assert failed == ["missing-type.xsd"]
    assert shapes == []


def test_a_global_element_typed_by_a_scalar_is_a_shape_with_no_fields():
    """The payload is a single value, and this vocabulary describes records —
    so no fields is the honest answer, and it must still be told apart from
    the dangling-type case above."""
    schema = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:a">
      <xs:element name="ping" type="xs:string"/>
    </xs:schema>"""
    shapes, failed = _interpret([_contract(schema, "scalar.xsd")])

    assert failed == []
    assert _shape(shapes, "{urn:a}ping").fields == []


def test_xml_that_does_not_parse_is_that_files_gap():
    """Failure is a gap, never a crash — and the reader deliberately left this
    question here, because only the interpreter may parse the format."""
    shapes, failed = _interpret(
        [_contract("<wsdl:definitions>", "truncated.wsdl"), _contract(TYPES_XSD, "types.xsd")]
    )

    assert failed == ["truncated.wsdl"]
    assert [shape.symbol for shape in shapes] == [
        f"{{{NS}}}placeOrderRequest",
        f"{{{NS}}}quoteOrderRequest",
    ]


def test_a_root_that_is_neither_a_schema_nor_a_definitions_is_that_files_gap():
    """Something harvested this as a contract. A file that declares nothing
    and reports nothing would be an omission dressed as success (D00 §3)."""
    _, failed = _interpret([_contract("<html><body/></html>", "page.xsd")])

    assert failed == ["page.xsd"]


def test_each_port_type_operations_input_element_carries_the_operation_role():
    """Document/literal's own rule: an operation's identity IS its input
    element's QName — the thing `@PayloadRoot` matches — so the mark lands on
    the element declaration's shape and Task 4 derives one endpoint from the
    shape itself."""
    shapes, failed = _interpret(_module())

    assert failed == []
    assert _shape(shapes, f"{{{NS}}}placeOrderRequest").role == "operation"
    assert _shape(shapes, f"{{{NS}}}quoteOrderRequest").role == "operation"


def test_an_element_no_operation_references_carries_no_role():
    """NULL is the answer for an ordinary payload type, which is nearly all of
    them — a role marked on everything would make Task 4 derive an endpoint
    per declared type."""
    schema = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:a">
      <xs:element name="unused" type="xs:string"/>
    </xs:schema>"""
    shapes, failed = _interpret([_contract(schema, "unused.xsd")])

    assert failed == []
    assert _shape(shapes, "{urn:a}unused").role is None


def test_a_named_complex_type_never_carries_the_role_its_element_does():
    """The wrapper element is the wire-true request shape (2I design §3): the
    type behind it is a payload, not an operation, and marking it too would
    derive the same endpoint twice under two identities."""
    wsdl = """<wsdl:definitions targetNamespace="urn:a"
        xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/" xmlns:tns="urn:a">
      <wsdl:message name="m"><wsdl:part name="p" element="tns:ping"/></wsdl:message>
      <wsdl:portType name="P">
        <wsdl:operation name="ping"><wsdl:input message="tns:m"/></wsdl:operation>
      </wsdl:portType>
    </wsdl:definitions>"""
    schema = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
                   xmlns:tns="urn:a" targetNamespace="urn:a">
      <xs:complexType name="Ping">
        <xs:sequence><xs:element name="at" type="xs:dateTime"/></xs:sequence>
      </xs:complexType>
      <xs:element name="ping" type="tns:Ping"/>
    </xs:schema>"""
    shapes, failed = _interpret([_contract(wsdl, "p.wsdl"), _contract(schema, "p.xsd")])

    assert failed == []
    assert _shape(shapes, "{urn:a}ping").role == "operation"
    assert _shape(shapes, "{urn:a}Ping").role is None


def test_an_operation_whose_input_element_no_file_declares_fails_that_wsdl():
    """A portType naming an element the universe does not carry is the same
    dangling reference a field's type would be — reported, never dropped, or
    the operation would vanish without a word."""
    wsdl = """<wsdl:definitions targetNamespace="urn:a"
        xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/" xmlns:tns="urn:a">
      <wsdl:message name="m"><wsdl:part name="p" element="tns:missing"/></wsdl:message>
      <wsdl:portType name="P">
        <wsdl:operation name="go"><wsdl:input message="tns:m"/></wsdl:operation>
      </wsdl:portType>
    </wsdl:definitions>"""
    other = """<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:a">
      <xs:element name="ping" type="xs:string"/>
    </xs:schema>"""
    shapes, failed = _interpret([_contract(wsdl, "p.wsdl"), _contract(other, "p.xsd")])

    assert failed == ["p.wsdl"]
    assert [shape.symbol for shape in shapes] == ["{urn:a}ping"]
    # And the surviving file's element is NOT marked: the marks of a file that
    # publishes nothing must not reach anybody else's shape either.
    assert _shape(shapes, "{urn:a}ping").role is None


def test_an_rpc_style_message_part_is_that_wsdls_gap():
    """`rpc`/`encoded` is a stated boundary (2I design §3): a part typed
    rather than element'd gives the operation no element QName to be
    identified by, and inventing one would be a guess about the wire."""
    wsdl = """<wsdl:definitions targetNamespace="urn:a"
        xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/" xmlns:tns="urn:a"
        xmlns:xsd="http://www.w3.org/2001/XMLSchema">
      <wsdl:message name="m"><wsdl:part name="p" type="xsd:string"/></wsdl:message>
      <wsdl:portType name="P">
        <wsdl:operation name="go"><wsdl:input message="tns:m"/></wsdl:operation>
      </wsdl:portType>
    </wsdl:definitions>"""
    _, failed = _interpret([_contract(wsdl, "rpc.wsdl")])

    assert failed == ["rpc.wsdl"]


def test_a_wsdl_that_declares_no_types_and_no_operations_is_neither_shape_nor_gap():
    """The binding-and-service half of a split WSDL declares nothing and
    references nothing, so nothing is missing from it. A gap would report a
    file that is not missing anything, permanently — the same answer a GraphQL
    operations document gets."""
    wsdl = """<wsdl:definitions targetNamespace="urn:a"
        xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/" xmlns:tns="urn:a"
        xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/">
      <wsdl:service name="S">
        <wsdl:port name="P" binding="tns:B">
          <soap:address location="http://example.com/ws"/>
        </wsdl:port>
      </wsdl:service>
    </wsdl:definitions>"""
    shapes, failed = _interpret([_contract(wsdl, "service.wsdl")])

    assert failed == []
    assert shapes == []


def test_the_other_formats_are_untouched_by_a_module_that_also_carries_contracts():
    """Four branches, one entry point: a module carrying an SDL file and a
    contract file interprets both, and neither reaches the other's universe."""
    sdl = EmbeddedDescriptorFact(
        document_id="doc:schema.graphqls",
        symbol="schema.graphqls",
        schema_format="graphql",
        payload="type Order { id: ID! }\n",
        origin="source",
    )
    shapes, failed = _interpret([sdl, _contract(TYPES_XSD, "orders-types.xsd")])

    assert failed == []
    assert {shape.symbol for shape in shapes} == {
        "Order",
        f"{{{NS}}}placeOrderRequest",
        f"{{{NS}}}quoteOrderRequest",
    }


def test_interpretation_does_not_depend_on_the_order_the_payloads_arrived_in():
    """NFR-1: descriptor input order is whatever an artifact walk happened to
    produce, and the fact files are content-hashed."""
    descriptors = _module()
    first, first_failed = _interpret(descriptors)
    second, second_failed = _interpret(list(reversed(descriptors)))

    assert [shape.model_dump() for shape in first] == [shape.model_dump() for shape in second]
    assert first_failed == second_failed


def test_a_second_run_over_the_same_payloads_is_byte_identical():
    """The determinism double-run: nothing in the branch may depend on set or
    dict iteration order."""
    descriptors = _module()
    first, first_failed = _interpret(descriptors)
    second, second_failed = _interpret(descriptors)

    assert [shape.model_dump_json() for shape in first] == [
        shape.model_dump_json() for shape in second
    ]
    assert first_failed == second_failed
