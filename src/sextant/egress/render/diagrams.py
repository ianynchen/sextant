"""Mermaid `classDiagram` and `sequenceDiagram` emitters (M07). Pure: no
workspace, no facts — tested against a hand-written view model, so diagram
correctness stops depending on having a repository to analyse (M07 "The
testing payoff")."""

import re

from sextant.egress.render.viewmodel import (
    ClassEdge,
    ClassNode,
    SequenceMessage,
    SequenceParticipant,
    simple_name,
)

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


# Every arrow is the same arrow. A trace step is one thing — a call the
# compiler recorded — and mermaid's other arrows say things this graph does
# not know: `-->>` is a RETURN (the walk records what a callee hands back,
# never when control comes back), `-x` is a failure, `->` a message with no
# activation. Varying the arrow by `invoke_kind` or by stop reason would put
# four claims into a glyph a reader has to be taught; the message LABEL says
# those in words instead.
_CALL_ARROW = "->>"


def sequence_diagram(
    participants: list[SequenceParticipant], messages: list[SequenceMessage]
) -> str:
    """Mermaid text for one trace, in the order given — the projection already
    decided participant order (first appearance in the walk) and message order
    (the walk's own depth-first order over `call_edges`), so the emitter adds
    none of its own (M07 "The renderer adds nothing", NFR-1).

    **Every participant is declared before any message**, rather than left for
    mermaid to infer from first use: an inferred lifeline takes the id as its
    label, and these ids are generated (`a0`, `a1`, …) precisely because a JVM
    descriptor is not a legal one. A message naming an undeclared id would
    therefore draw a lifeline called `a4`.

    `label` is written after the `as`/`:` separator and read to end of line by
    mermaid, so a label is never quoted here — the projection is what
    guarantees it carries no newline, having built it from a symbol and a
    fixed vocabulary."""
    lines = ["sequenceDiagram"]
    for participant in participants:
        lines.append(f"    participant {participant.id} as {participant.label}")
    for message in messages:
        lines.append(f"    {message.source}{_CALL_ARROW}{message.target}: {message.label}")
    return "\n".join(lines) + "\n"
