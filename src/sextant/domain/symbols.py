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


def method_name(descriptor: str) -> str:
    """The method's plain name, with its trailing signature-hash argument
    list stripped (D00 §5a's `sig_...` disambiguator) — the identifier a
    compiler bridge shares with the real, differently-descriptored override
    it stands in for (2E checkpoint item (4)). `member_name` alone cannot
    tell the two apart: both `find(sig_95a78dff)` and `find(sig_4cb6f523)`
    already differ there, by design, since the disambiguator is what makes
    the descriptor form join-safe. This strips one layer further, to the
    name a same-class same-name conflict actually shares. A descriptor with
    no parameter list (a field, a type) returns `member_name` unchanged."""
    name = member_name(descriptor)
    head, paren, _ = name.partition("(")
    return head if paren else name


# D00 §5a: an array's symbol is its ELEMENT's descriptor with this suffix
# appended — `byte#[]`, never `byte[]#`. Written here because this is the seam
# that converts the catalogs' notation, and a catalog naming an array type
# (2G's bytes-shaped payload parameters) has to reach the very string the
# facts carry.
_ARRAY_SUFFIX = "[]"


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

    A trailing `[]` (repeated for a nested array) is carried past the
    descriptor marker rather than into it: the facts spell `byte[]` as
    `byte#[]`, so a catalog writing `byte[]` and a scanned parameter of that
    type must compare equal. Inert for every name without one, which is
    every catalog value written before 2G.
    """
    depth = 0
    while dotted.endswith(_ARRAY_SUFFIX):
        dotted = dotted[: -len(_ARRAY_SUFFIX)]
        depth += 1
    return dotted.replace(".", "/") + "#" + _ARRAY_SUFFIX * depth


def package_path(dotted: str) -> str:
    """Converts a catalog's dotted PACKAGE name to the path form the facts
    use — `type_descriptor`'s prefix-only sibling.

    A package is not a type: it has no descriptor suffix, so a caller
    matching one (2G design §5's `json_default_markers`, which ask whether
    anything from a package family appears at all) cannot use
    `type_descriptor` without also asserting that the prefix names a type.
    Here rather than at the call site for the reason `type_descriptor` is:
    the two notations meet in one seam, never in every pass that compares
    them."""
    return dotted.replace(".", "/")


def simple_name(symbol: str) -> str:
    """The display name for a SCIP symbol (D00 §5a): the last path segment,
    with the trailing `#` a type descriptor always carries stripped."""
    return symbol.rsplit("/", 1)[-1].rstrip("#")
