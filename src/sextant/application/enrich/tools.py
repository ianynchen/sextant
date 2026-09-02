"""The four enrichment tools and the jail (2K design §4).

`list_dir`, `find`, `grep`, `read_file` — read-only, in-process, and jailed:
the only bytes an enrichment agent ever sees are what these four methods
choose to return, so this module IS the security boundary the rest of 2K's
agentic loop is built behind. Task 6's `EnrichmentAgent` drives a model
through `ToolExecutor.definitions()`/`execute()`; nothing here talks to a
model, a shell, or the network, and nothing here writes.

**Every refusal is a RESULT, never an exception.** `execute` is the one
public entry point a caller (Task 6's loop) uses, and its contract is that
it always returns a string — an unknown tool name, malformed arguments, a
jail violation, an excluded file, or a filesystem surprise `resolve` cannot
unwind all become a `"refused: ..."` string the model reads like any other
tool result. A crashed loop is a worse outcome than a puzzled model.

**Containment is checked AFTER resolution.** `Path.resolve()` follows every
symlink it encounters, so a path is accepted only once its fully-resolved,
symlink-free form sits under one of the jailed roots' own resolved form —
`..` segments, an absolute path elsewhere, and a symlink planted inside a
root that points outside all fail the identical check and get the identical
refusal, so the model learns the shape of the wall rather than which
specific trick failed.

**Two invisibility layers, checked together at every walk site.**
`ignore` (T2's `IgnoreRules`, already loaded for the repository the jailed
roots live under) hides `.sextantignore` matches and the built-in
credential patterns. Independently, `domain.enrichment.ENRICHMENT_FILE`
(`.sextant-enrichment.json`) is excluded here as a JAIL-SPECIFIC rule, not a
`.sextantignore` builtin (2K Task 3 ruling, carried to Task 5 at dispatch):
the model must never read its own prior run's claims through these tools,
or a later run would be grounding its answers in what it already said
rather than in the module — exactly the feedback/anchor-gaming loop the
overlay's `evidence: llm` marker exists to keep out of the machine
document.

**Redaction on read, twice over.** A config-bearing file's content — the
extensions the config-reading `ArtifactReader`s claim, see
`CONFIG_BEARING_EXTENSIONS` below for precisely where that rule comes from
— is masked key-by-key before `read_file` or `grep` exposes it, so a model
cannot recover a value through `grep` that `read_file` would have masked.
Every result, from every tool (including a refusal), additionally passes
`redactor.redact_text` (URL userinfo stripped, plus any repo-added value
patterns) on its way out of `execute` — cheap, safe, and the one pass
nothing here is allowed to skip.
"""

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path

from sextant.application.ports.artifacts import file_kind
from sextant.domain.enrichment import ENRICHMENT_FILE
from sextant.domain.file_reads import list_directory, read_file_text, walk_files
from sextant.domain.ignorefile import IgnoreRules
from sextant.domain.redaction import Redactor

# Determinism + size caps (2K design §4 / Task 5 brief), pinned to exact
# numbers so a transcript replays identically regardless of machine or
# model:
#   * the ceiling on any ONE tool result, applied AFTER redaction and
#     AFTER any tool's own cap below — large enough for a real config file
#     or a source file's default read window, small enough that one call
#     cannot flood the model's context.
MAX_RESULT_BYTES = 64 * 1024
#   * `read_file`'s DEFAULT window when the model gives no `end` — most
#     source files fit whole; a model that wants more asks for more with
#     an explicit range.
DEFAULT_READ_LINES = 400
#   * `grep`'s match cap — a runaway pattern (`.` against every file) stops
#     producing lines rather than exhausting the byte cap one truncated
#     match at a time.
MAX_GREP_MATCHES = 200

# The extensions a config-bearing file carries — the rule this constant
# states is NOT invented here: it mirrors `reads_schema_sources = False` on
# `sextant.ingress.read.yaml_config.YamlConfigReader` (`yml`, `yaml`) and
# `sextant.ingress.read.properties.PropertiesReader` (`properties`), the two
# `ArtifactReader`s `cli/app.py` registers that read ordinary configuration
# rather than a schema source — as opposed to `AvscReader`, `GraphqlSdlReader`,
# `ProtoSourceReader` and `WsdlXsdReader`, all `reads_schema_sources = True`,
# which read shapes, not settings, and carry no credentials to mask.
#
# This module cannot import those readers to ask them directly: the import
# contracts (`.importlinter`) place `ingress` ABOVE `application` in the
# layering (`cli -> ingress|storage|egress -> application -> domain`), so an
# `application` module reaching into `ingress` is exactly the direction the
# contract forbids. What follows is therefore a STATED MIRROR of that
# registry's own split, not a fresh guess at which extensions carry
# configuration — if a reader's own `accepts`/`reads_schema_sources` ever
# changes, this constant has to change with it, by hand, because nothing
# enforces the two agreeing.
CONFIG_BEARING_EXTENSIONS = frozenset({"yml", "yaml", "properties"})

# A config-bearing file's `key: value` / `key = value` assignment lines
# (YAML block style, and the `.properties` format), matched so ONLY an
# actual assignment is ever handed to `Redactor.redact_value` — a comment or prose
# line never starts with a bare identifier directly followed by `:`/`=`, so
# this leaves commentary untouched (even commentary that mentions
# `password` in prose) and only ever reaches a real value.
#
# Stated limitation, deliberately not chased further (GUIDELINES §2): this
# is a LINE-oriented heuristic, not a YAML/properties parser. Flow-style
# mappings (`db: {password: x}`), block scalars (`|`, `>`) and multi-line
# values are invisible to it and pass through unmasked by this rule (the
# blanket `redact_text` pass every result still gets is the only net under
# those). Neither this module's own fixture nor a real Spring config
# ordinarily writes secrets that way, and the alternative — a hand-rolled
# YAML parser reconstructing byte-for-byte output — is exactly the kind of
# drift DR-6 warns about for a problem `pathspec`-style vendoring cannot
# solve here (round-tripping comments and formatting is not what any YAML
# library promises).
_CONFIG_LINE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<key>[A-Za-z][\w.\-]*)(?P<sep>[ \t]*[:=][ \t]*)(?P<value>\S.*)$"
)


class _ToolRefusal(Exception):
    """Internal control flow only. Every raise of this is caught by
    `ToolExecutor.execute` and turned into the refusal string the model
    reads — it never escapes a public method."""


@dataclass(frozen=True)
class ToolDefinition:
    """One tool's name, description and JSON Schema for its arguments — the
    shape Task 6's Messages-API loop hands the model verbatim. The
    description is authored carefully once (2K design §4: "the model's
    search strategy is only as good as they are"), not left to whatever the
    schema's own field descriptions happen to imply."""

    name: str
    description: str
    schema: dict[str, object]


_LIST_DIR = ToolDefinition(
    name="list_dir",
    description=(
        "List the immediate entries of a directory inside the jailed roots "
        "(the module's source root, its fact root, and its rendered "
        "outputs). Directories are suffixed with '/'. Anything "
        ".sextantignore or a built-in credential pattern excludes, and "
        "Sextant's own prior enrichment overlay, never appears — use this "
        "to orient yourself before find/read_file, not to enumerate every "
        "file on disk."
    ),
    schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "A directory, relative to one of the jailed roots "
                    "(or an absolute path already inside one)."
                ),
            }
        },
        "required": ["path"],
        "additionalProperties": False,
    },
)

_FIND = ToolDefinition(
    name="find",
    description=(
        "Search every jailed root for files whose BASE NAME matches a "
        "glob (e.g. '*.yml', 'Order*') — case-sensitive, recursive. "
        "Returns one path per line, relative to whichever root it was "
        "found under, sorted."
    ),
    schema={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "A filename glob matched against each file's base name.",
            }
        },
        "required": ["pattern"],
        "additionalProperties": False,
    },
)

_GREP = ToolDefinition(
    name="grep",
    description=(
        "Search file CONTENT for a regular expression. One match per "
        "line of output, formatted 'path:line:text', sorted, capped at "
        f"{MAX_GREP_MATCHES} matches. Omit 'path' to search every jailed "
        "root; give a file or a directory to scope the search. Config "
        "files (.yml/.yaml/.properties) have credential-shaped values "
        "masked before matching, so grep cannot recover a value "
        "read_file would have masked."
    ),
    schema={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "A regular expression matched against each line's text.",
            },
            "path": {
                "type": "string",
                "description": (
                    "Optional: a file or directory (relative to a jailed root) "
                    "to scope the search to; omitted searches every jailed root."
                ),
            },
        },
        "required": ["pattern"],
        "additionalProperties": False,
    },
)

_READ_FILE = ToolDefinition(
    name="read_file",
    description=(
        "Read one file, 1-indexed lines 'start' through 'end' inclusive — "
        f"defaults to line 1 through a {DEFAULT_READ_LINES}-line window "
        "when 'start'/'end' are omitted. Config files (.yml/.yaml/"
        ".properties) have their credential-shaped values masked before "
        "you see them; the value is still `«redacted»`, never removed, so "
        "you can tell the setting exists."
    ),
    schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "A file, relative to one of the jailed roots.",
            },
            "start": {
                "type": "integer",
                "description": "1-indexed first line to return (default 1).",
            },
            "end": {
                "type": "integer",
                "description": (
                    "1-indexed last line to return, inclusive "
                    f"(default start + {DEFAULT_READ_LINES - 1})."
                ),
            },
        },
        "required": ["path"],
        "additionalProperties": False,
    },
)


class ToolExecutor:
    """The jail: constructed once per enrichment run with an explicit
    allowlist of roots, the redactor both the render and export exits use
    (2K design §1), and the ignore rules T2 loaded for the repository those
    roots live under.

    **Wiring assumption this class does not re-check:** `ignore` was
    loaded (`IgnoreRules.load`) against a repository root that contains
    every entry in `roots` — true of the module root together with its own
    `.sextant/facts` and `.sextant/render` (the layout `_workspace_dir_of`
    builds), which is the only wiring Task 6 is expected to construct this
    with. `IgnoreRules.matches` resolves a path against the root it was
    loaded for regardless of which jailed root the file happens to sit
    under, which is what lets one `ignore` cover all three.
    """

    def __init__(self, roots: tuple[Path, ...], redactor: Redactor, ignore: IgnoreRules) -> None:
        self._roots = tuple(root.resolve() for root in roots)
        self._redactor = redactor
        self._ignore = ignore
        # Every call and its result, in call order — persisted by the
        # caller (2K design §3: "a full session transcript logged locally
        # for audit"). This class only ever appends to it.
        self.transcript: list[dict[str, object]] = []

    def definitions(self) -> list[ToolDefinition]:
        """The four tools, in the order a transcript reads most
        naturally: orientation, then two ways to search, then content."""
        return [_LIST_DIR, _FIND, _GREP, _READ_FILE]

    def execute(self, name: str, args: dict[str, object]) -> str:
        """Run one tool call and append it to `transcript`. Never raises:
        an unknown tool name, malformed arguments, a jail refusal, or any
        unexpected filesystem error all become the same kind of thing — a
        refusal string in `result` — because the model reads results, not
        exceptions."""
        try:
            result = self._dispatch(name, args)
        except _ToolRefusal as refusal:
            result = str(refusal)
        except Exception as unexpected:  # noqa: BLE001 — deliberate, see below
            # The one hard guarantee this class makes is that NOTHING
            # escapes `execute` (2K Task 5 brief) — a permissions error, a
            # symlink cycle `resolve` cannot unwind, or any other
            # filesystem surprise becomes a refusal the model can read
            # rather than a crash of the whole enrichment run.
            result = f"refused: {name} failed: {unexpected}"
        result = _cap(self._redactor.redact_text(result))
        self.transcript.append({"name": name, "args": args, "result": result})
        return result

    def _dispatch(self, name: str, args: dict[str, object]) -> str:
        if not isinstance(args, dict):
            raise _ToolRefusal("refused: arguments must be a JSON object")
        if name == "list_dir":
            return self._list_dir(args)
        if name == "find":
            return self._find(args)
        if name == "grep":
            return self._grep(args)
        if name == "read_file":
            return self._read_file(args)
        raise _ToolRefusal(f"refused: unknown tool {name!r}")

    def _list_dir(self, args: dict[str, object]) -> str:
        path = _require_str(args, "path")
        resolved = self._resolve_in_jail(path)
        if not resolved.is_dir():
            raise _ToolRefusal(f"refused: {path} is not a directory")
        entries = sorted(
            child.name + "/" if child.is_dir() else child.name
            for child in list_directory(resolved)
            if not self._is_excluded(child)
        )
        return "\n".join(entries)

    def _find(self, args: dict[str, object]) -> str:
        pattern = _require_str(args, "pattern")
        matches = sorted(
            self._display_path(path)
            for path in self._visible_files()
            if fnmatch.fnmatchcase(path.name, pattern)
        )
        return "\n".join(matches)

    def _grep(self, args: dict[str, object]) -> str:
        pattern = _require_str(args, "pattern")
        try:
            compiled = re.compile(pattern)
        except re.error as bad_pattern:
            raise _ToolRefusal(
                f"refused: {pattern!r} is not a valid regular expression: {bad_pattern}"
            ) from bad_pattern
        path_arg = _optional_str(args, "path")
        if path_arg is None:
            candidates = self._visible_files()
        else:
            resolved = self._resolve_in_jail(path_arg)
            candidates = (
                [path for path in self._visible_files() if path.is_relative_to(resolved)]
                if resolved.is_dir()
                else [resolved]
            )
        matches: list[tuple[str, int, str]] = []
        for path in candidates:
            content = self._content_of(path)
            if content is None:
                continue
            display = self._display_path(path)
            for line_number, line in enumerate(content.splitlines(), start=1):
                if compiled.search(line):
                    matches.append((display, line_number, line))
        matches.sort()
        if len(matches) > MAX_GREP_MATCHES:
            shown = matches[:MAX_GREP_MATCHES]
            body = "\n".join(f"{p}:{n}:{t}" for p, n, t in shown)
            return (
                f"{body}\n... [truncated: {len(matches)} matches found, "
                f"showing the first {MAX_GREP_MATCHES}]"
            )
        return "\n".join(f"{p}:{n}:{t}" for p, n, t in matches)

    def _read_file(self, args: dict[str, object]) -> str:
        path = _require_str(args, "path")
        start = _optional_int(args, "start", minimum=1)
        start = 1 if start is None else start
        end = _optional_int(args, "end", minimum=start)
        resolved = self._resolve_in_jail(path)
        if not resolved.is_file():
            raise _ToolRefusal(f"refused: {path} is not a file")
        content = self._content_of(resolved)
        if content is None:
            raise _ToolRefusal(f"refused: {path} is not a text file")
        lines = content.splitlines()
        last = start + DEFAULT_READ_LINES - 1 if end is None else end
        return "\n".join(lines[start - 1 : last])

    def _resolve_in_jail(self, raw_path: str) -> Path:
        """`raw_path`'s real, EXISTING location under one of the jailed
        roots — resolved after symlinks, tried against each root in turn,
        first existing match wins.

        A path that resolves inside a root but does not exist there is a
        plain miss, reported as "does not exist"; a path that resolves
        inside NO root at all — `..` escaping every one, an absolute path
        elsewhere, or a symlink whose target lands outside — is the jail's
        one security refusal, always the identical words regardless of
        which of those three shapes triggered it."""
        missing: str | None = None
        for root in self._roots:
            resolved = (root / raw_path).resolve()
            if not resolved.is_relative_to(root):
                continue
            if not resolved.exists():
                if missing is None:
                    missing = raw_path
                continue
            if self._is_excluded(resolved):
                raise _ToolRefusal(f"refused: {raw_path} is excluded from the enrichment jail")
            return resolved
        if missing is not None:
            raise _ToolRefusal(f"refused: {missing} does not exist")
        raise _ToolRefusal("refused: outside the allowed roots")

    def _is_excluded(self, path: Path) -> bool:
        """Whether `path` (already jail-contained) is invisible to every
        tool: `.sextantignore` plus the built-in credential patterns
        (`ignore`), OR the enrichment overlay itself — the jail-specific
        exclusion the module docstring explains."""
        return path.name == ENRICHMENT_FILE or self._ignore.matches(path)

    def _visible_files(self) -> list[Path]:
        """Every file under every jailed root that `_is_excluded` does not
        hide, in deterministic order: sorted by path-relative-to-its-own-root
        within each root, roots walked in the order `roots` was constructed
        with (2K design §4: "sorted outputs everywhere"). Hand-rolled
        rather than `domain.resource_files.list_files`: that helper takes
        an explicit `repo_root` and relativizes against it BEFORE calling
        `ignore.matches`, which is only correct when the root being walked
        IS the ignore's own repo root — true for the module source root
        here, not for the fact/render roots nested under it. Calling
        `ignore.matches` directly with each file's own resolved absolute
        path lets `IgnoreRules` do that relativizing itself, correctly,
        against whichever repo root it was actually loaded for."""
        files: list[Path] = []
        for root in self._roots:
            for path in sorted(
                walk_files(root), key=lambda candidate: candidate.relative_to(root).as_posix()
            ):
                if not self._is_excluded(path):
                    files.append(path)
        return files

    def _display_path(self, path: Path) -> str:
        """`path`, relative to whichever jailed root contains it — the
        form `find`/`grep` show and `read_file`/`grep`'s own `path` scoping
        accepts back, so a citation this tool prints is a citation the
        model can hand to another tool call unchanged."""
        for root in self._roots:
            if path.is_relative_to(root):
                return path.relative_to(root).as_posix()
        return path.as_posix()  # unreachable: every caller only passes jailed paths

    def _content_of(self, path: Path) -> str | None:
        """`path`'s text, key-masked first when it is config-bearing (2K
        design §4's "redaction-on-read") — BEFORE either `read_file` or
        `grep` exposes it, so a `grep` for the very value `read_file` would
        have masked cannot recover it. `None` for a file that cannot be
        decoded as UTF-8 text or cannot be read at all: both tools skip it
        rather than raising, the same silent-skip a real `grep` gives a
        binary file."""
        try:
            text = read_file_text(path)
        except (UnicodeDecodeError, OSError):
            return None
        if file_kind(path) in CONFIG_BEARING_EXTENSIONS:
            return _mask_config_lines(text, self._redactor)
        return text


def _require_str(args: dict[str, object], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value:
        raise _ToolRefusal(f"refused: {key!r} is required and must be a non-empty string")
    return value


def _optional_str(args: dict[str, object], key: str) -> str | None:
    value = args.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise _ToolRefusal(f"refused: {key!r} must be a non-empty string when given")
    return value


def _optional_int(args: dict[str, object], key: str, minimum: int) -> int | None:
    value = args.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise _ToolRefusal(f"refused: {key!r} must be an integer when given")
    if value < minimum:
        raise _ToolRefusal(f"refused: {key!r} must be >= {minimum}")
    return value


def _mask_config_lines(text: str, redactor: Redactor) -> str:
    """`text` (a config-bearing file's content, or a window of it) with
    every `key: value` / `key = value` assignment line passed through
    `redactor.redact_value` — the same key-then-value shape
    `resolved_config`'s own masking already expects (`storage/duckdb/
    workspace.py`), reached here one line at a time because `read_file`
    hands out raw text rather than a parsed document. A line that is not
    an assignment (a comment, a bare mapping header, a list item) is
    returned unchanged."""
    masked_lines = []
    for line in text.splitlines():
        match = _CONFIG_LINE.match(line)
        if match is None:
            masked_lines.append(line)
            continue
        key, value = match.group("key"), match.group("value")
        masked_value = redactor.redact_value(key, value)
        if masked_value == value:
            masked_lines.append(line)
        else:
            masked_lines.append(f"{match.group('indent')}{key}{match.group('sep')}{masked_value}")
    return "\n".join(masked_lines)


def _cap(text: str) -> str:
    """`text`, or its first `MAX_RESULT_BYTES` UTF-8 bytes with a note, so
    no single tool result can flood the model's context regardless of what
    the repository holds. Byte-safe: truncation never lands inside a
    multi-byte character (`errors="ignore"` drops a partial trailing byte
    sequence rather than raising or emitting invalid UTF-8)."""
    encoded = text.encode("utf-8")
    if len(encoded) <= MAX_RESULT_BYTES:
        return text
    note = f"\n... [truncated: result exceeds the {MAX_RESULT_BYTES}-byte cap]"
    budget = MAX_RESULT_BYTES - len(note.encode("utf-8"))
    return encoded[:budget].decode("utf-8", errors="ignore") + note
