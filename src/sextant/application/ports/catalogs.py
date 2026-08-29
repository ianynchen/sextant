"""The CatalogSource port (ARCHITECTURE §7). Catalogs are Sextant's own
framework knowledge (D02) — not the analysed module's configuration, which is
read as facts by an ArtifactReader.

A port rather than a directory argument because D02 §6 loads two sets together
and privileges neither: the catalogs shipped with Sextant, and a repository's
own. Both arrive as one list, and the layer that interprets them never learns
where they came from."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class Catalog:
    id: str
    style: str
    protocol: str
    direction: str
    requires: tuple[str, ...]
    matches: dict[str, Any]
    # Where this came from. Carried so a defect found after loading — a style
    # no engine implements — can still name the file, which is the only place
    # it is cheap to fix.
    source: Path
    # D02 §2a, §2e, §2f, §2g. Default to empty so a catalog that declares none
    # of them — every catalog before Task 8, and the invented catalogs tests
    # construct by hand — still loads; only Task 9's wrapper unwrapping reads
    # `wrappers` today, the rest wait on Tasks 10 and 11.
    wrappers: list[dict[str, Any]] = field(default_factory=list)
    nullability: dict[str, Any] = field(default_factory=dict)
    serialization: dict[str, Any] = field(default_factory=dict)
    known_types: list[dict[str, Any]] = field(default_factory=list)


class CatalogError(ValueError):
    """A catalog that cannot be trusted. An unchecked value does not stay in
    the file: it is bound straight into the derivation and published as
    `protocol` in metadata.json, where a typo is indistinguishable from an
    observation."""


class CatalogSource(Protocol):
    def load(self) -> list[Catalog]:
        """Every catalog this source holds, in a deterministic order."""
