"""The M07 view model: nodes, fields and relations, with nothing scope-
specific about them. Internal to the renderer — nothing outside this module
reads it, so it carries no `D` document (M07 "The view model is internal")."""

from dataclasses import dataclass

# Re-exported: document.py and diagrams.py both import `simple_name` from
# here, and the seam (`domain/symbols.py`) is where the definition now lives.
from sextant.domain.symbols import simple_name

__all__ = [
    "ClassEdge",
    "ClassNode",
    "SequenceMessage",
    "SequenceParticipant",
    "simple_name",
]


@dataclass(frozen=True)
class ClassNode:
    name: str
    fields: tuple[tuple[str, str], ...]
    open: bool


@dataclass(frozen=True)
class ClassEdge:
    source: str
    target: str


@dataclass(frozen=True)
class SequenceParticipant:
    """One lifeline of a trace's sequence diagram.

    `id` is what messages address — generated, never the type's own name,
    because a mermaid actor id has a grammar and a JVM descriptor
    (`com/macro/mall/dao/OmsOrderDao#`) is not in it. `label` is what a reader
    sees: the projection has already disambiguated it, so the emitter neither
    shortens nor de-duplicates.
    """

    id: str
    label: str


@dataclass(frozen=True)
class SequenceMessage:
    """One call, from the lifeline that makes it to the lifeline it names.

    `source`/`target` are participant ids. `label` is the whole of what the
    message says, elision markers included — the projection decides what a
    message admits to (a boundary the walk did not enter, a body created
    rather than called), because deciding it here would be the renderer
    forming an opinion about the graph.
    """

    source: str
    target: str
    label: str
