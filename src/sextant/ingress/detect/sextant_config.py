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
from dataclasses import dataclass
from pathlib import Path

import yaml

from sextant.domain.redaction import RedactionRules

CONFIG_FILE = ".sextant.yml"

# The only keys this file may carry. A closed set, so a misspelling fails rather
# than being ignored — see the module docstring.
_KEYS = frozenset({"extract_libraries", "redact", "enrich"})

# The keys `docs/components/D04-config-and-exclusion.md` §2 specifies for two
# OTHER files — a repository-root `sextant.yml` and `~/.sextant/config.yml`.
# **Neither file is ever opened by anything** (`A-C9`, principles sweep §3.2):
# nothing in `src/` names either path, the catalog set is hard-wired to the
# package's own directory (`ingress/catalogs/yaml_source.py`), `scanners.pin`
# has no parameter to reach, and `tools.helm` has no reader. So this list is
# not a list of keys that belong somewhere else — it is a list of keys that
# belong nowhere, and it exists purely so the refusal below can say which
# mistake the author made.
#
# It matters because the repository file's documented name is one character
# from this one's, and in a single-module repository the two roots coincide.
# A reader who follows D04 §2 writes these keys HERE, all four commands share
# this reader, and the run is refused — with a message that (before this)
# said only "read nowhere", which is equally true of a typo and points at
# nothing. A user following the documentation is not degraded, they are
# stopped, and the least this can do is tell them why.
#
# It shrinks to nothing the day D04 §2 is retired or built. Retiring is the
# roadmap's standing ruling for the `catalogs:` half (project catalogs are
# deliberately unscheduled: they would make D02's schema a public API), and
# the amendment recording that is in D04 §2 itself.
_DOCUMENTED_ELSEWHERE = frozenset(
    {"catalogs", "first_party", "modules", "output", "redaction", "scanners", "tools", "workspace"}
)

# And the only keys `redact:` may carry, closed for the same reason: a typo'd
# `value_pattern` that read as "add no value patterns" would look exactly like
# a module that asked for none, which is the failure this whole file exists to
# refuse.
_REDACT_KEYS = frozenset({"key_patterns", "value_patterns"})

# `enrich:`'s own keys (2K design §3: "repo defaults in `.sextant.yml` under
# `enrich:`; flags win"), closed for the same reason every other section here
# is: a typo'd `max_turn` would read as "no default", indistinguishable from
# a module that declared none. `auth`/`session_store` join the set for the
# Tradewind adapter (2N design §1): the CLI's own `--auth` flag wins over
# `auth:` the same way every other flag wins over its default here;
# `session_store` has no flag counterpart at all, only this default.
_ENRICH_KEYS = frozenset({"agent", "model", "max_turns", "auth", "session_store"})

# The only two `auth:` values the Tradewind adapter knows (2N design §1) —
# closed the same way `--auth`'s own `click.Choice` is, so a typo here is
# refused loudly rather than read as "no default" (this file's own
# module-docstring rule).
_AUTH_VALUES = frozenset({"subscription", "api-key"})

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
        raise SextantConfigError(_unknown_key_message(path, unknown))
    return path, document


def _unknown_key_message(path: Path, unknown: list[str]) -> str:
    """Why this file cannot be honoured, in the terms the author will
    recognise.

    Two audiences, and one message for each. A misspelling gets the plain
    closed-set refusal. A key `D04` §2 specifies for the repository-root
    `sextant.yml` gets told that the file it belongs to is a DIFFERENT one and
    that Sextant does not read it — which is the answer somebody who just
    followed the documentation needs, and the one the plain refusal cannot
    give (`A-C9`).
    """
    named = ", ".join(repr(key) for key in unknown)
    message = (
        f"{path} declares {named}, which Sextant reads nowhere — "
        f"the keys it reads are {', '.join(sorted(_KEYS))}"
    )
    documented = sorted(set(unknown) & _DOCUMENTED_ELSEWHERE)
    if not documented:
        return message
    return (
        f"{message}. {', '.join(repr(key) for key in documented)} "
        f"belong{'s' if len(documented) == 1 else ''} to the repository-root `sextant.yml` "
        f"docs/components/D04-config-and-exclusion.md §2 specifies — a different file from "
        f"this per-module `{CONFIG_FILE}`, and one Sextant does not read at all. Nothing "
        f"opens it, so moving these keys there will not help either: see D04 §2's own "
        f"amendment for what is supported instead"
    )


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


@dataclass(frozen=True)
class EnrichDefaults:
    """`enrich:`'s own defaults (2K design §3) — each `None` where the module
    declares none, which is the ordinary case: `sextant module enrich`'s own
    `--agent`/`--model`/`--max-turns`/`--auth` flags win over whatever is set
    here, and win over nothing when neither exists. `session_store` has no
    flag counterpart (2N design §1) — this is its only source besides the
    Tradewind adapter's own per-auth default."""

    agent: str | None = None
    model: str | None = None
    max_turns: int | None = None
    auth: str | None = None
    session_store: str | None = None


def read_enrich_defaults(module_root: Path) -> EnrichDefaults:
    """This module's `enrich:` defaults, or every field `None` where it
    declares none — the ordinary module, which supplies every flag itself or
    takes the CLI's own defaults.

    Raises `SextantConfigError` for anything else: unparseable YAML, a root
    that is not a mapping, an unknown top-level or `enrich:` key, `agent`/
    `model`/`session_store` not a string, `max_turns` a negative integer (or
    not an integer at all), or `auth` not `"subscription"`/`"api-key"`.
    """
    path, document = _document(module_root)
    section = document.get("enrich", {})
    if not isinstance(section, dict):
        raise SextantConfigError(
            f"{path}: `enrich` must be a mapping of defaults, not {type(section).__name__}"
        )
    unknown = sorted(set(section) - _ENRICH_KEYS)
    if unknown:
        raise SextantConfigError(
            f"{path}: `enrich` declares {', '.join(repr(key) for key in unknown)}, which "
            f"Sextant reads nowhere — the keys it reads are {', '.join(sorted(_ENRICH_KEYS))}"
        )
    agent = _optional_string(path, section, "agent")
    model = _optional_string(path, section, "model")
    max_turns = section.get("max_turns")
    if max_turns is not None and (
        not isinstance(max_turns, int) or isinstance(max_turns, bool) or max_turns < 0
    ):
        # `0` stays legal (mirrors `agents/tradewind.py`'s own constructor
        # check): an honest single-response run with no tool execution
        # permitted, not a value the run itself would ever reject.
        raise SextantConfigError(f"{path}: `enrich.max_turns` must be a non-negative integer")
    auth = _optional_string(path, section, "auth")
    if auth is not None and auth not in _AUTH_VALUES:
        raise SextantConfigError(
            f"{path}: `enrich.auth` must be one of {', '.join(sorted(_AUTH_VALUES))}, not {auth!r}"
        )
    session_store = _optional_string(path, section, "session_store")
    return EnrichDefaults(
        agent=agent, model=model, max_turns=max_turns, auth=auth, session_store=session_store
    )


def _optional_string(path: Path, section: dict[str, object], name: str) -> str | None:
    value = section.get(name)
    if value is not None and not isinstance(value, str):
        raise SextantConfigError(f"{path}: `enrich.{name}` must be a string")
    return value
