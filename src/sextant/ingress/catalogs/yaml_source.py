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
                    protocol=_closed_or_absent(raw, "protocol", Protocol, path),
                    direction=_closed_or_absent(raw, "direction", Direction, path),
                    requires=tuple(raw.get("requires", [])),
                    matches=_required(raw, "matches", path),
                    source=path,
                    detect_coordinates=_coordinates(raw, path),
                    # D02 §2a, §2e, §2f, §2g — optional blocks. A catalog that
                    # declares none of them still loads.
                    wrappers=raw.get("wrappers", []),
                    nullability=raw.get("nullability", {}),
                    serialization=raw.get("serialization", {}),
                    known_types=raw.get("known_types", []),
                    # D02 §2i — optional, one per framework family.
                    config_model=raw.get("config_model", {}),
                    # 2G design §7 — optional format vocabulary, carried
                    # through unread here for the same reason `matches` is:
                    # the values are checked against D00's format set where
                    # the ladder reads them (`resolve/format.py`), which is
                    # also where the reserved value is refused.
                    # D02's framework-contract media default, read here for
                    # the first time (2O design §2b). Checked where it is
                    # used — `derived_resource` refuses a catalog of its own
                    # style that declares none — like every other block above.
                    default_produces=tuple(raw.get("default_produces", [])),
                    format_fixed=raw.get("format_fixed", {}),
                    media_formats=raw.get("media_formats", {}),
                    json_default_markers=raw.get("json_default_markers", []),
                    parse_calls=raw.get("parse_calls", {}),
                    # 2H design §6 — optional, checked where the pass reads it
                    # (`resolve/protocol_hint.py`), which is also where the
                    # target protocol is checked against D00's closed set.
                    protocol_hint=raw.get("protocol_hint", {}),
                    # D02 §2c — optional, checked where the engine reads it
                    # (`resolve/engines/annotation_driven.py`), which is also
                    # where the resolved direction is checked against D00's
                    # closed set and the condition against the engine's own
                    # closed vocabulary.
                    resolves=raw.get("resolves", {}),
                )
            )
        return catalogs


def _required(raw: dict[str, Any], key: str, path: Path) -> Any:
    if key not in raw:
        raise CatalogError(
            f"loading catalog {path}: no `{key}` — every catalog declares one (D02 §1)"
        )
    return raw[key]


def _coordinates(raw: dict[str, Any], path: Path) -> tuple[str, ...]:
    """D02 §1's `detect.coordinates`, checked here for the reason every other
    value in this file is: it reaches a comparison against the coordinates a
    module's build declared, and a coordinate written in the wrong shape
    matches nothing while looking exactly like a framework that is absent.

    Optional, and an absent block is an empty tuple — every catalog that
    declares `detect: {coordinates: []}` says the same thing explicitly: the
    evidence for this framework is not a dependency. Only the two styles in
    `resolve/dependencies.py`'s `DEPENDENCY_GATED` read the value
    (`Catalog.detect_coordinates`), so a catalog declaring coordinates it never
    uses is not an error; it was the state of every one of the 41 catalogs
    shipping when this was written, and it is the state of the 51 of today's 55
    that no gate reads. **This function is a SHAPE check, not the gate**: it refuses a
    coordinate written in the wrong form for all 55 and compares none of them,
    so citing it as the consumer of `detect.coordinates` would satisfy
    GUIDELINES §5.3 falsely. The consumer is `dependencies.py:108-137`.
    """
    detect = raw.get("detect", {})
    if not isinstance(detect, dict):
        raise CatalogError(
            f"loading catalog {path}: `detect` must be a mapping with `coordinates` "
            f"— got {detect!r} (D02 §1)"
        )
    declared = detect.get("coordinates", [])
    valid = isinstance(declared, list) and all(
        isinstance(entry, str) and entry.count(":") == 1 for entry in declared
    )
    if not valid:
        raise CatalogError(
            f"loading catalog {path}: `detect.coordinates` must be a list of "
            f"`groupId:artifactId` coordinates — got {declared!r} (D02 §1)"
        )
    return tuple(declared)


def _closed_or_absent(raw: dict[str, Any], key: str, values: type[StrEnum], path: Path) -> str:
    """`protocol`/`direction`: one of D00's closed sets, or the empty string
    where the catalog declares the key at all (2O design §4).

    Absence is a CLAIM — "this catalog derives nothing with a wire identity" —
    and it is checked where the claim can be judged, not here. This layer knows
    which values are legal; it does not know which catalogs need one, because
    that is knowledge of `application/resolve`, which this layer must not
    import. `resolve/endpoints.py` refuses a catalog that MINTS ENDPOINT ROWS
    and declares no protocol, and one that mints none and declares one,
    carrying `Catalog.source` so either error still names the file — exactly
    the split the module docstring above states for `style` itself.

    A key written with a value outside the set is still refused right here: a
    typo is not an absence, and `protocol: htp` must never be read as "no wire
    identity".
    """
    if key not in raw:
        return ""
    return _closed(raw, key, values, path)


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
