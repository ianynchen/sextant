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
