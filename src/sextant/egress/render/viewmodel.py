"""The M07 view model: nodes, fields and relations, with nothing scope-
specific about them. Internal to the renderer — nothing outside this module
reads it, so it carries no `D` document (M07 "The view model is internal")."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ClassNode:
    name: str
    fields: tuple[tuple[str, str], ...]
    open: bool


@dataclass(frozen=True)
class ClassEdge:
    source: str
    target: str


def simple_name(symbol: str) -> str:
    """The display name for a SCIP symbol (D00 §5a): the last path segment,
    with the trailing `#` a type descriptor always carries stripped."""
    return symbol.rsplit("/", 1)[-1].rstrip("#")
