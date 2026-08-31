"""The M07 view model: nodes, fields and relations, with nothing scope-
specific about them. Internal to the renderer — nothing outside this module
reads it, so it carries no `D` document (M07 "The view model is internal")."""

from dataclasses import dataclass

# Re-exported: document.py and diagrams.py both import `simple_name` from
# here, and the seam (`domain/symbols.py`) is where the definition now lives.
from sextant.domain.symbols import simple_name

__all__ = ["ClassEdge", "ClassNode", "simple_name"]


@dataclass(frozen=True)
class ClassNode:
    name: str
    fields: tuple[tuple[str, str], ...]
    open: bool


@dataclass(frozen=True)
class ClassEdge:
    source: str
    target: str
