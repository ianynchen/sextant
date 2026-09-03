from sextant.egress.render.diagrams import class_diagram
from sextant.egress.render.viewmodel import ClassEdge, ClassNode


def test_the_emitter_draws_nodes_fields_and_references():
    nodes = [
        ClassNode(
            "com/acme/orders/contracts/OrderRequest#",
            (("customer_id", "string"), ("alternates", "array")),
            False,
        ),
        ClassNode("com/acme/orders/contracts/CustomerRef#", (("id", "string"),), False),
    ]
    edges = [
        ClassEdge(
            "com/acme/orders/contracts/OrderRequest#", "com/acme/orders/contracts/CustomerRef#"
        )
    ]
    text = class_diagram(nodes, edges)
    assert "classDiagram" in text
    assert "class OrderRequest" in text
    assert "customer_id: string" in text
    assert "OrderRequest --> CustomerRef" in text


def test_an_open_shape_is_marked_in_the_diagram():
    text = class_diagram([ClassNode("a/B#", (), True)], [])
    assert "open" in text  # rendered as a stereotype/note — exact form is the emitter's


def test_a_dollar_name_is_backtick_quoted_everywhere_it_appears():
    """A JVM nested-class name (`Outer$Inner`) breaks mermaid's bare
    identifier grammar — `class Outer$Inner {` is a parse error (spec §5a).
    The emitter backtick-quotes it in every production that names a node:
    the declaration, a relationship line, and the `<<open>> Name` stereotype."""
    nodes = [
        ClassNode("com/acme/orders/Outer$Inner#", (), True),
        ClassNode("com/acme/orders/Relay#", (), False),
    ]
    edges = [ClassEdge("com/acme/orders/Outer$Inner#", "com/acme/orders/Relay#")]
    text = class_diagram(nodes, edges)
    assert "class `Outer$Inner` {" in text
    assert "<<open>> `Outer$Inner`" in text
    assert "`Outer$Inner` --> Relay" in text
    assert "Outer$Inner#" not in text  # the raw, unquoted form never appears


def test_a_dotted_name_stays_unquoted():
    """Dotted names are legal bare in mermaid's grammar (spec §5a) — quoting
    them would be needless noise, so a name with dots but no other special
    character is emitted without backticks."""
    nodes = [ClassNode("com/acme/orders/Outer.Inner#", (), False)]
    text = class_diagram(nodes, [])
    assert "class Outer.Inner {" in text
    assert "`Outer.Inner`" not in text
