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
    "SequenceAlternatives",
    "SequenceBranch",
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


@dataclass(frozen=True)
class SequenceAlternatives:
    """One call site whose dispatch NARROWED to several bodies, none picked — and
    everything each of them leads to (F7 §8.3, W32).

    A trace records one step per candidate, so a `narrowed` site arrives as several
    messages, each followed by its own subtree. Drawn flat they read as a SEQUENCE:
    `spring-petclinic-rest`'s `ClinicServiceImpl#saveOwner` draws `save` to the JDBC
    repository and, eight arrows later, `save` to the JPA one — two saves, apparently
    both, when at most one repository answers any given call. That is the over-report
    NFR-2 rates worst, and it is live in rendered output rather than hypothetical.

    **At most one branch runs per invocation** — not "exactly one, always". Two in-module
    implementations of an interface can both be live and both run at different times; this
    repo's own `TraceProbe#describe` narrows to two splitters passed as a parameter, with
    nothing making them exclusive. All 34 of petclinic-rest's sites happen to be
    profile-switched repository pairs, so no rendered instance is wrong today, but the
    block says "one of these per call", never "one of these ever".

    `branches` is one entry per candidate, in the walk's own order, each holding that
    candidate's own message and everything below it. The emitter draws them as mermaid's
    `alt`/`else`, which is the notation for exactly this and the only one mermaid has.

    Nothing is dropped and nothing is reordered: the same messages appear, in the same
    order, inside a block that says what they are.
    """

    branches: tuple["SequenceBranch", ...]


@dataclass(frozen=True)
class SequenceBranch:
    """One alternative of a `SequenceAlternatives`: the label naming which body this
    branch is, and the messages that follow if it is the one that runs."""

    label: str
    messages: tuple["SequenceMessage | SequenceAlternatives", ...]
