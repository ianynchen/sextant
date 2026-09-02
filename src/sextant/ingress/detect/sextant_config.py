"""The per-module `.sextant.yml` (D04 §2a) — Sextant's OWN input, read by the
detector before anything reads code.

Two keys today. `extract_libraries` names the coordinates of the dependencies
this module asks to have extracted alongside its own output. Naming a library
here is the whole opt-in — a module with no file, or a file naming none,
produces exactly the facts it produced before library extraction existed.

`redact` (2K design §1) widens the built-in redaction set: extra key patterns,
extra value regexes. It is read by the EXITS (render and export), not by
`analyze` — masking happens where data crosses the trust boundary, and the
workspace stays verbatim. **Additive only**: there is no reveal or unmask key,
and `domain/redaction.py` makes that structural rather than merely unwritten.

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

from sextant.domain.redaction import RedactionRules

CONFIG_FILE = ".sextant.yml"

# The only keys this file may carry. A closed set, so a misspelling fails rather
# than being ignored — see the module docstring.
_KEYS = frozenset({"extract_libraries", "redact"})

# And the only keys `redact:` may carry, closed for the same reason: a typo'd
# `value_pattern` that read as "add no value patterns" would look exactly like
# a module that asked for none, which is the failure this whole file exists to
# refuse.
_REDACT_KEYS = frozenset({"key_patterns", "value_patterns"})

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


def _document(module_root: Path) -> tuple[Path, dict[str, object]]:
    """The file's root mapping, with the checks every reader of it shares: it
    parses, its root is a mapping, and it declares no key Sextant reads
    nowhere. An absent or empty file answers with an empty mapping, so each
    reader's own "declared nothing" default is the same code path as "wrote no
    file" — the ordinary case, and the only absence this file treats as an
    answer.

    Extracted when `redact:` gained a second reader, so a mistyped top-level
    key is refused by whichever command reads the file first rather than by
    whichever one happens to look at that section."""
    path = module_root / CONFIG_FILE
    if not path.is_file():
        return path, {}
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as failure:
        raise SextantConfigError(f"{path} is not readable YAML: {failure}") from failure
    # An empty file parses to None. Nothing is declared, which is a legitimate
    # thing to write; it is only unreadable structure that is refused.
    if document is None:
        return path, {}
    if not isinstance(document, dict):
        raise SextantConfigError(f"{path} must be a mapping, not {type(document).__name__}")
    unknown = sorted(set(document) - _KEYS)
    if unknown:
        raise SextantConfigError(
            f"{path} declares {', '.join(repr(key) for key in unknown)}, which Sextant "
            f"reads nowhere — the keys it reads are {', '.join(sorted(_KEYS))}"
        )
    return path, document


def read_redaction_rules(module_root: Path) -> RedactionRules:
    """What this module ADDS to the built-in redaction set (2K design §1).

    Returns empty rules where the module declares no `redact:` section — the
    ordinary case, which still redacts by the built-in set: these are
    additions, and `Redactor.from_rules` is what unions the built-ins in.

    Raises `SextantConfigError` for a `redact:` that is not a mapping, one
    carrying a key nobody reads, a section whose value is not a list, or a
    non-string pattern. Whether a pattern is USABLE — an empty key pattern, a
    value pattern that is not a regular expression — is `Redactor`'s own
    refusal (`RedactionError`), raised on the same path and for the same
    reason.
    """
    path, document = _document(module_root)
    section = document.get("redact", {})
    if not isinstance(section, dict):
        raise SextantConfigError(
            f"{path}: `redact` must be a mapping of pattern lists, not {type(section).__name__}"
        )
    unknown = sorted(set(section) - _REDACT_KEYS)
    if unknown:
        raise SextantConfigError(
            f"{path}: `redact` declares {', '.join(repr(key) for key in unknown)}, which "
            f"Sextant reads nowhere — the keys it reads are {', '.join(sorted(_REDACT_KEYS))}"
        )
    return RedactionRules(
        key_patterns=_patterns(path, section, "key_patterns"),
        value_patterns=_patterns(path, section, "value_patterns"),
    )


def _patterns(path: Path, section: dict[str, object], name: str) -> tuple[str, ...]:
    """One `redact:` list, checked to be a list of strings. Order is kept as
    written for the same NFR-1 reason `extract_libraries` keeps it; the
    redactor sorts the EFFECTIVE set itself, so file order never reaches the
    rule-set hash."""
    declared = section.get(name, [])
    if not isinstance(declared, list):
        raise SextantConfigError(
            f"{path}: `redact.{name}` must be a list of patterns, not {type(declared).__name__}"
        )
    for entry in declared:
        if not isinstance(entry, str):
            raise SextantConfigError(f"{path}: `redact.{name}` entry {entry!r} is not a string")
    return tuple(declared)


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
    path, document = _document(module_root)
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
