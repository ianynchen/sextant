"""Reads Sextant's own catalog files from a directory (D02 §1, §6).

Structural validation lives here, at the edge, because the values reach the
derivation as bound parameters. What this cannot check is whether an engine
implements the declared `style`: that is knowledge of `application/resolve`,
which this layer must not import, so the style is checked where the engines
are — carrying `Catalog.source` so the error still names the file."""

from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.domain.closed_sets import Direction, Protocol


class YamlCatalogSource:
    """The CatalogSource port over a directory of `*.yml` files."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def load(self) -> list[Catalog]:
        """Reads every catalog in the directory, sorted by filename.

        Raises `CatalogError` naming the file and the offending value when a
        catalog omits a required field or declares a `protocol` or `direction`
        outside D00's closed sets.
        """
        catalogs = []
        for path in sorted(self._directory.glob("*.yml")):
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise CatalogError(f"loading catalog {path}: not a YAML mapping")
            catalogs.append(
                Catalog(
                    id=_required(raw, "id", path),
                    style=_required(raw, "style", path),
                    protocol=_closed(raw, "protocol", Protocol, path),
                    direction=_closed(raw, "direction", Direction, path),
                    requires=tuple(raw.get("requires", [])),
                    matches=_required(raw, "matches", path),
                    source=path,
                )
            )
        return catalogs


def _required(raw: dict[str, Any], key: str, path: Path) -> Any:
    if key not in raw:
        raise CatalogError(
            f"loading catalog {path}: no `{key}` — every catalog declares one (D02 §1)"
        )
    return raw[key]


def _closed(raw: dict[str, Any], key: str, values: type[StrEnum], path: Path) -> str:
    """Checks one field against a closed set of D00 (`domain/closed_sets.py`).

    The sets are closed on purpose: adding a value is a schema change, never
    an implementation choice (NFR-5). So a value outside one is not a new
    kind of endpoint, it is a mistake, and the only place it is still cheap
    to name is the file it came from.
    """
    value = _required(raw, key, path)
    allowed = sorted(member.value for member in values)
    if value not in allowed:
        raise CatalogError(
            f"loading catalog {path}: `{key}: {value}` is not one of "
            f"{', '.join(allowed)} — D00's closed sets are closed (NFR-5)"
        )
    return str(value)
