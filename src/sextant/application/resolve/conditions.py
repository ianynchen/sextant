"""Shared reads for rules conditional on annotations (spec 2026-09-18 §2, §4):
where an owner's and its type's annotations are, once per load.

Built through `Workspace.once` so the `annotations` decode runs once per load
rather than once per catalog (`annotation_driven._annotation_rows`' reason).
Read by the body rule (`shapes/contracts.py`), the conditional wrapper filter
and the `protocol_hint` pass; written by none of them.
"""

from __future__ import annotations

import json
from typing import Any

from sextant.application.ports.workspace import Workspace
from sextant.domain.symbols import is_type_descriptor, owner_of


def enclosing_type_of(symbol: str) -> str | None:
    """The type a member symbol belongs to, `#` included — the coordinates
    prefix carries no `#`, so this holds for a full symbol and a bare
    descriptor alike (D00 §5a). None for a type or a free function. Read
    through the two `domain.symbols` questions rather than the marker itself:
    the grammar stays behind that seam."""
    return None if is_type_descriptor(symbol) else owner_of(symbol)


def annotation_index(workspace: Workspace) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    """target → [(annotation descriptor, args)], every annotation row once."""
    return workspace.once(_annotation_index)


def member_annotations_by_type(workspace: Workspace) -> dict[str, set[str]]:
    """enclosing type → the annotation descriptors any field or method declared
    in it carries — Quarkus's parameter-container rule reads exactly this
    (CP-19 row 4)."""
    return workspace.once(_member_annotations_by_type)


# The builders are module-level, not closures: `Workspace.once` keys its fold on
# the callable itself, and a function defined inside each call would be a new key
# every time — rebuilt per call and never found again.


def _annotation_index(workspace: Workspace) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    found: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for row in workspace.query("annotations"):
        args = json.loads(str(row["args"])) if row["args"] is not None else {}
        found.setdefault(str(row["target"]), []).append((str(row["annotation"]), args))
    for entries in found.values():
        entries.sort(key=lambda entry: entry[0])
    return found


def _member_annotations_by_type(workspace: Workspace) -> dict[str, set[str]]:
    # `located_symbols`, not `symbols`: the three columns this needs — symbol,
    # kind, enclosing type — over the same view, and a query `once` accepts
    # (`symbols` is not on the workspace's facts-only list, so a fold reading
    # it is refused).
    enclosing = {
        str(row["symbol"]): str(row["enclosing"])
        for row in workspace.query("located_symbols")
        if row.get("enclosing") and str(row["construct_kind"]) in ("field", "method")
    }
    found: dict[str, set[str]] = {}
    for target, entries in annotation_index(workspace).items():
        owner = enclosing.get(target)
        if owner is not None:
            found.setdefault(owner, set()).update(annotation for annotation, _ in entries)
    return found
