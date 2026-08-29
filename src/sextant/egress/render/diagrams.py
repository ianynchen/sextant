"""Mermaid `classDiagram` emitter (M07). Pure: no workspace, no facts — tested
against a hand-written view model, so diagram correctness stops depending on
having a repository to analyse (M07 "The testing payoff")."""

from sextant.egress.render.viewmodel import ClassEdge, ClassNode, simple_name


def class_diagram(nodes: list[ClassNode], edges: list[ClassEdge]) -> str:
    """Mermaid text for `nodes` and `edges`, in the order given — the
    projection already decided that order, so the emitter adds none of its
    own (M07 "The renderer adds nothing", NFR-1)."""
    lines = ["classDiagram"]
    for node in nodes:
        name = simple_name(node.name)
        lines.append(f"    class {name} {{")
        for field_name, field_type in node.fields:
            lines.append(f"        {field_name}: {field_type}")
        lines.append("    }")
        if node.open:
            # A stereotype, not a note: an open shape is a property of the
            # class itself — the expansion stopped there — not a comment
            # about it.
            lines.append(f"    <<open>> {name}")
    for edge in edges:
        lines.append(f"    {simple_name(edge.source)} --> {simple_name(edge.target)}")
    return "\n".join(lines) + "\n"
