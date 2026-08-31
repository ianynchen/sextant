"""The SCIP symbol grammar as a string format (D00 §1). No indexer involved."""

import hashlib
from dataclasses import dataclass

NOT_APPLICABLE = "."


@dataclass(frozen=True)
class Symbol:
    scheme: str
    package_manager: str
    package: str
    version: str
    descriptor: str

    def __str__(self) -> str:
        return (
            f"{self.scheme} {self.package_manager} {self.package} {self.version} {self.descriptor}"
        )

    @property
    def short_id(self) -> str:
        """A prefixed, content-derived handle. Never bare hexadecimal: these
        get pasted into YAML and spreadsheets, which coerce types."""
        digest = hashlib.sha256(str(self).encode("utf-8")).hexdigest()[:8]
        return f"sym_{digest}"


def bare_descriptor(symbol: str) -> str:
    """The descriptor half of a symbol (D00 §5a): a symbol is module
    coordinates then a descriptor, space-separated, and only the descriptor is
    ever compared. A bare descriptor carries no coordinates, so it is
    returned unchanged."""
    return symbol.rsplit(" ", 1)[-1]


def owner_of(descriptor: str) -> str | None:
    """The owning type's descriptor, trailing `#` included, or `None` for a
    free-function descriptor — SCIP spells those with no `#` at all, and an
    ownerless symbol is an answer here, never an exception (D00 §5a)."""
    index = descriptor.find("#")
    return None if index == -1 else descriptor[: index + 1]


def member_name(descriptor: str) -> str:
    """The segment after the last `#`, trailing `.` stripped — a descriptor
    with no `#` returns itself minus any trailing `.` (D00 §5a)."""
    return descriptor.rpartition("#")[2].removesuffix(".")


def type_descriptor(dotted: str) -> str:
    """Converts a catalog's dotted type name to the SCIP symbol form the facts
    use.

    Two forms exist for the same type on purpose: D02's catalogs write a
    dotted name (`reactor.core.publisher.Mono`) because that is how the spec
    and every catalog author spells a fully qualified type; the scanner emits
    SCIP symbols (`reactor/core/publisher/Mono#`, D00 §5a) because that is the
    grammar the rest of the fact stream is keyed on. Neither side should
    change to suit the other — the catalog stays readable in its source
    notation, the facts stay one grammar — so the conversion happens once,
    here, at the point of comparison.
    """
    return dotted.replace(".", "/") + "#"


def simple_name(symbol: str) -> str:
    """The display name for a SCIP symbol (D00 §5a): the last path segment,
    with the trailing `#` a type descriptor always carries stripped."""
    return symbol.rsplit("/", 1)[-1].rstrip("#")
