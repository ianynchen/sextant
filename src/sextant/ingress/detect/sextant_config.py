"""The per-module `.sextant.yml` (D04 §2a) — Sextant's OWN input, read by the
detector before anything reads code.

One key today: `extract_libraries`, the coordinates of the dependencies this
module asks to have extracted alongside its own output. Naming a library here
is the whole opt-in — a module with no file, or a file naming none, produces
exactly the facts it produced before library extraction existed.

A coordinate is `groupId:artifactId`, or `groupId:artifactId:version`. The two-part
form defers to the build for the version, which is where it belongs when the build
states it. The three-part form is the author's OWN assertion of which release to
read, and it is the escape hatch for the case the two-part form cannot reach: a
version managed by a parent POM or a BOM, which the detector does not resolve.

**Every malformed shape is refused, loudly.** This is the DR-6 exemption: DR-6's
refusal-to-guess is about evidence read from a codebase Sextant does not own,
where a silent absence is the honest answer. A `.sextant.yml` is not evidence —
it is an instruction someone wrote FOR Sextant, so a key nobody reads or a
coordinate nothing can parse is a mistake to report, never a line to skip. A
typo'd `extract_libaries` that read as "extract nothing" would be indexed as an
empty answer and look exactly like an unconfigured module.
"""

import re
from pathlib import Path

import yaml

CONFIG_FILE = ".sextant.yml"

# The only key this file may carry. A closed set, so a misspelling fails rather
# than being ignored — see the module docstring.
_KEYS = frozenset({"extract_libraries"})

# `groupId:artifactId`, optionally `:version`, over Maven's own identifier
# charset. Each segment becomes a directory — under `facts/lib/`, or in the
# local repository's own layout — so the grammar is what makes those mappings
# both injective (no segment may carry the `:` they are joined by, nor a path
# separator) and safe (no segment may be `.` or `..` — a leading dot is refused
# outright, which no real Maven identifier has).
_SEGMENT = r"[A-Za-z0-9_-][A-Za-z0-9_.-]*"
_COORDINATE = re.compile(rf"{_SEGMENT}:{_SEGMENT}(:{_SEGMENT})?")


class SextantConfigError(ValueError):
    """A `.sextant.yml` that cannot be honoured as written."""


def read_extract_libraries(module_root: Path) -> tuple[str, ...]:
    """The library coordinates this module opts into extracting, in the order
    the file names them (NFR-1: a file order is a stated order, and re-sorting
    it would hide a duplicate rather than carry it).

    Returns the empty tuple where the module has no `.sextant.yml` at all —
    the ordinary case, and the only absence this function treats as an answer.
    Raises `SextantConfigError` for anything else: unparseable YAML, a root
    that is not a mapping, an unknown key, a non-list value, a non-string
    entry, or an entry that is not a `groupId:artifactId[:version]` coordinate.
    """
    path = module_root / CONFIG_FILE
    if not path.is_file():
        return ()
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as failure:
        raise SextantConfigError(f"{path} is not readable YAML: {failure}") from failure
    # An empty file parses to None. Nothing is declared, which is a legitimate
    # thing to write; it is only unreadable structure that is refused.
    if document is None:
        return ()
    if not isinstance(document, dict):
        raise SextantConfigError(f"{path} must be a mapping, not {type(document).__name__}")
    unknown = sorted(set(document) - _KEYS)
    if unknown:
        raise SextantConfigError(
            f"{path} declares {', '.join(repr(key) for key in unknown)}, which Sextant "
            f"reads nowhere — the keys it reads are {', '.join(sorted(_KEYS))}"
        )
    declared = document.get("extract_libraries", [])
    if not isinstance(declared, list):
        raise SextantConfigError(
            f"{path}: `extract_libraries` must be a list of coordinates, "
            f"not {type(declared).__name__}"
        )
    for entry in declared:
        if not isinstance(entry, str) or not _COORDINATE.fullmatch(entry):
            raise SextantConfigError(
                f"{path}: {entry!r} is not a `groupId:artifactId` or "
                f"`groupId:artifactId:version` coordinate"
            )
    return tuple(declared)
