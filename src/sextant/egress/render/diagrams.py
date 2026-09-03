"""Mermaid `classDiagram` emitter (M07). Pure: no workspace, no facts — tested
against a hand-written view model, so diagram correctness stops depending on
having a repository to analyse (M07 "The testing payoff")."""

import re

from sextant.egress.render.viewmodel import ClassEdge, ClassNode, simple_name

# spec §5a: mermaid's bare-identifier grammar refuses a JVM `$` name — `class
# AuthenticateController$JWTToken {` is a parse error — while a dotted name
# is legal bare. Backtick-quoting is verified (against the vendored mermaid
# 11.17.2 build, in a live browser session) to parse and keep the true name
# as the node id, so every identifier outside this set gets quoted rather
# than emitted bare.
_BARE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


def _quoted(identifier: str) -> str:
    """`identifier`, backtick-quoted when it is not a bare mermaid
    identifier — unchanged otherwise, so the common case emits no noise."""
    return identifier if _BARE_IDENTIFIER.match(identifier) else f"`{identifier}`"


def class_diagram(nodes: list[ClassNode], edges: list[ClassEdge]) -> str:
    """Mermaid text for `nodes` and `edges`, in the order given — the
    projection already decided that order, so the emitter adds none of its
    own (M07 "The renderer adds nothing", NFR-1)."""
    lines = ["classDiagram"]
    for node in nodes:
        name = _quoted(simple_name(node.name))
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
        source = _quoted(simple_name(edge.source))
        target = _quoted(simple_name(edge.target))
        lines.append(f"    {source} --> {target}")
    return "\n".join(lines) + "\n"
