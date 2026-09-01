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
    # D02 §2i: a new top-level, optional block, one per framework family —
    # the family's base catalog carries it (Spring's ships on spring-web.yml).
    # `resolve/config.py`'s pass 2 collects every catalog's own non-empty
    # block; every other catalog's default `{}` means it contributes none.
    config_model: dict[str, Any] = field(default_factory=dict)
    # 2G design §7's format vocabulary, three optional top-level blocks read
    # only by `resolve/format.py`'s ladder. Each is shipped by the catalog
    # that OWNS the knowledge — a protocol's constant format by the catalog
    # declaring that protocol, the MIME table and the default-converter
    # markers by the family's HTTP catalogs — so no format name is ever an
    # engine's to know. Every catalog that declares none contributes none.
    #
    # `format_fixed`  -- protocol -> format, for a protocol whose wire is
    #                    constant by definition (rung 1).
    # `media_formats` -- MIME string -> format (rung 2).
    # `json_default_markers` -- package prefixes whose presence anywhere in a
    #                    module is evidence that a JSON default converter is
    #                    on the classpath (rung 5).
    format_fixed: dict[str, str] = field(default_factory=dict)
    media_formats: dict[str, str] = field(default_factory=dict)
    json_default_markers: list[str] = field(default_factory=list)
    # 2G design §7's fourth format vocabulary, read only by
    # `resolve/shapes/parse_binding.py`: `{bytes_payloads: [...], calls:
    # [...]}` — which payload parameter types mean "this channel carries the
    # wire's bytes, not a decoded object", and which calls turn those bytes
    # into a typed payload. Carried through unread here, like every block
    # above; the pass that reads it refuses a malformed one.
    parse_calls: dict[str, Any] = field(default_factory=dict)


class CatalogError(ValueError):
    """A catalog that cannot be trusted. An unchecked value does not stay in
    the file: it is bound straight into the derivation and published as
    `protocol` in metadata.json, where a typo is indistinguishable from an
    observation."""


class CatalogSource(Protocol):
    def load(self) -> list[Catalog]:
        """Every catalog this source holds, in a deterministic order."""
