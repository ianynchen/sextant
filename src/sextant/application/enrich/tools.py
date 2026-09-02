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
jail violation, an excluded file, or a filesystem surprise all become a
`"refused: ..."` string the model reads like any other tool result, worded
generically (never the raw exception text — see `execute`). A crashed loop
is a worse outcome than a puzzled model.

**One policy, two routes, checked the same way (2K Task 5 fix round 1).** A
caller reaches a file two ways — naming it (`read_file`, `list_dir`, the
scoped `path` on `grep`) or discovering it (`find`, an unscoped `grep`) —
and both routes enforce the identical rule: a path is visible only if it is
the EXACT — case included — name of a REAL directory entry, reached without
crossing a single symlink. `_walk_segments` is the naming route's walk (one
caller-given string, verified segment by segment against `list_directory`);
`_walk_visible`/`_visible` is the discovery route's walk (real directory
entries only, so the case question never arises — only the symlink one
does). Neither ever calls `Path.resolve()`: a build that trusted resolution
would follow a symlink to see where it leads and could only refuse it
AFTERWARD, by re-checking the target — which is exactly the shape of the
first version of this file, and exactly what a symlink chained through two
hops, or a lexically-innocent name aliasing an excluded one, got past. Not
resolving at all — refusing the instant a symlink is MET, never mind where
it points — removes the class of bug rather than patching one instance of
it. A symlink is never followed even when it points somewhere INSIDE the
jail: the tool descriptions below say so, because a repository with a
symlinked source directory otherwise goes quietly invisible with nothing
telling the model why (2K Task 5 fix round 2, N5).

**Two invisibility layers, checked together at every walk site, against
the MOST SPECIFIC containing root.** `ignore` (T2's `IgnoreRules`, already
loaded for the repository the jailed roots live under) hides
`.sextantignore` matches and the built-in credential patterns.
`domain.enrichment.ENRICHMENT_FILE` (`.sextant-enrichment.json`) is
excluded here as a JAIL-SPECIFIC rule, not a `.sextantignore` builtin (2K
Task 3 ruling): the model must never read its own prior run's claims
through these tools. A derived-output directory (`DERIVED_OUTPUT_DIRS` —
`target/`, `build/`, `out/`, `node_modules/`, `.git/`) is excluded the same
jail-specific way (2K Task 5 fix round 1 ruling): the jail describes
human-authored source, never its compiled shadow, and `BUILTIN_PATTERNS`
stays the short, non-negatable credential layer it was designed as. All
three are PATH-SHAPED and content-blind — a copy of an excluded file
sitting somewhere `_is_excluded` does not name is not caught by it (2K
design §11, which a fix round 2 sentence extends to a hardlink: readable
outside content, but not an escape, since planting one needs write access
inside the root already). The derived-output check judges a path's
ancestry against its own MOST SPECIFIC jailed root (`_most_specific_root`),
never an ancestor root that merely happens to contain it too — otherwise a
module whose OWN root sits under a directory literally named `target`
would blank its nested fact and render roots outright (2K Task 5 fix round
2, N2 — a real, reviewer-reproduced bug, not a hypothetical one).

**Nested roots, deduplicated.** The ordinary wiring nests the fact and
render roots INSIDE the module root (`module_root/.sextant/facts`,
`module_root/.sextant/render`), so a `find`/unscoped `grep` walking every
root separately would otherwise see every fact and render file TWICE —
once as part of the module root's own walk, once as that nested root's
own — inflating `MAX_GREP_MATCHES` and breaking the "sorted, deterministic"
contract (2K Task 5 fix round 2, N1). `_visible_files` collects every
root's walk into a SET before sorting, and `_display_path` (what `find`/
`grep` print, and what `_is_excluded` judges ancestry against) always
picks the most specific containing root, so a nested root's own file reads
and sorts by ITS OWN namespace, never its ancestor's.

**Redaction on read, twice over.** A config-bearing file's content — the
extensions the config-reading `ArtifactReader`s claim, see
`CONFIG_BEARING_EXTENSIONS` below for precisely where that rule comes from
— is masked key-by-key before `read_file` or `grep` exposes it, so a model
cannot recover a value through `grep` that `read_file` would have masked.
Every result, from every tool (including a refusal), additionally passes
`redactor.redact_text` (URL userinfo stripped, plus any repo-added value
patterns) on its way out of `execute`, BEFORE the byte cap — cheap, safe,
and the one pass nothing here is allowed to skip, in the one order that
keeps a secret from surviving half-truncated (see `execute`).
"""

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path

from sextant.application.ports.artifacts import file_kind
from sextant.domain.enrichment import ENRICHMENT_FILE
from sextant.domain.file_reads import list_directory, read_file_text
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
# `ArtifactReader`s in `sextant.ingress.read.READERS` (the registry
# `cli/app.py` hands `analyze`) that read ordinary configuration rather than
# a schema source — as opposed to `AvscReader`, `GraphqlSdlReader`,
# `ProtoSourceReader` and `WsdlXsdReader`, all `reads_schema_sources = True`,
# which read shapes, not settings, and carry no credentials to mask.
#
# This module cannot import that registry to ask it directly: the import
# contracts (`.importlinter`) place `ingress` ABOVE `application` in the
# layering (`cli -> ingress|storage|egress -> application -> domain`), so an
# `application` module reaching into `ingress` is exactly the direction the
# contract forbids. What follows is therefore a STATED MIRROR of the
# registry's own split, not a fresh guess at which extensions carry
# configuration — `tests/application/test_enrich_tools.py` pins both
# directions against the real `READERS` tuple, so a reader's own
# `accepts`/`reads_schema_sources` changing without this constant changing
# with it fails a test rather than drifting silently.
CONFIG_BEARING_EXTENSIONS = frozenset({"yml", "yaml", "properties"})

# Derived-output directories (2K Task 5 fix round 1 ruling): invisible and
# unreadable everywhere in the jail, ancestry included, but NOT part of
# `ignorefile.BUILTIN_PATTERNS` — that set stays the short, non-negatable
# CREDENTIAL layer; this is a separate, jail-specific exclusion for a
# module's COMPILED SHADOW, joining `ENRICHMENT_FILE`'s own precedent.
# Deliberately does not touch `.sextantignore`, `resource_files.list_files`,
# or any analysis walk — a build directory is fair game for `analyze`
# (D00 §2's origin tiering already answers whether ITS classes count), only
# the enrichment jail refuses to describe it as source.
DERIVED_OUTPUT_DIRS = frozenset({"target", "build", "out", "node_modules", ".git"})

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
        ".sextantignore or a built-in credential pattern excludes, "
        "Sextant's own prior enrichment overlay, and any build/dependency "
        "directory (e.g. target/, node_modules/) never appears. A SYMLINK "
        "is never followed and never listed, even one pointing back inside "
        "the jail at a file you could otherwise read directly — use this "
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
        "found under, sorted, each file listed once even if two roots "
        "nest inside each other. A symlinked file or directory is never "
        "followed or listed."
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
        f"{MAX_GREP_MATCHES} matches, each file searched once even if two "
        "roots nest inside each other. Omit 'path' to search every jailed "
        "root; give a file or a directory to scope the search. Config "
        "files (.yml/.yaml/.properties) have credential-shaped values "
        "masked before matching, so grep cannot recover a value "
        "read_file would have masked. A symlinked file or directory is "
        "never followed, so its content is never searched."
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
        "you can tell the setting exists. A symlinked path is never "
        "followed — it reads as not available, even if it points "
        "somewhere else inside the jail you could read directly by its "
        "real name."
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

    **Wiring assumption, enforced at construction, not merely stated:**
    `ignore` must be loaded (`IgnoreRules.load`) against a repository root
    that contains every entry in `roots` — true of the module root together
    with its own `.sextant/facts` and `.sextant/render` (the layout
    `_workspace_dir_of` builds), which is the only wiring Task 6 is
    expected to construct this with. `__init__` checks this for every root
    and raises rather than build a jail that silently refuses every call
    (2K Task 5 fix round 1, I4): a mismatch here previously surfaced as an
    ordinary-looking refusal on every single tool call, indistinguishable
    from the jail actually working, with the raw mismatch — an absolute
    host path — landing in the MODEL-visible refusal text.
    """

    def __init__(self, roots: tuple[Path, ...], redactor: Redactor, ignore: IgnoreRules) -> None:
        resolved_roots = tuple(root.resolve() for root in roots)
        for root in resolved_roots:
            try:
                ignore.matches(root)
            except ValueError as mismatch:
                raise ValueError(
                    "ToolExecutor: `ignore` was not loaded (IgnoreRules.load) for a "
                    "repository root that contains every jailed root — construction "
                    "refused rather than building a jail that refuses every call"
                ) from mismatch
        self._roots = resolved_roots
        self._redactor = redactor
        self._ignore = ignore
        # Every call and its result, in call order — persisted by the
        # caller (2K design §3: "a full session transcript logged locally
        # for audit"). This class only ever appends to it; `args` is
        # stored as a COPY (2K Task 5 fix round 1, minor) so a caller that
        # mutates the dict it passed in afterward cannot rewrite history.
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
        exceptions. An UNEXPECTED failure's own text never reaches the
        model (2K Task 5 fix round 1, I4): it can carry an absolute host
        path or other diagnostic detail that is fine for a transcript a
        human reads and wrong for a tool result the model reads back as if
        it described the repository; the real text goes to `transcript`
        alone, under `error`."""
        error_detail: str | None = None
        try:
            # The inner `try` handles the EXPECTED outcome (a refusal);
            # `redact_text`/`_cap` run inside the OUTER `try` too — not
            # after it — because a redactor or the cap themselves raising
            # (a caller-supplied `redactor` misbehaving, say) must land on
            # the identical generic-message path as a dispatch failure,
            # never escape past this method (2K Task 5 fix round 1, I4).
            try:
                result = self._dispatch(name, args)
            except _ToolRefusal as refusal:
                result = str(refusal)
            # Redaction BEFORE the byte cap, always (2K Task 5 fix round
            # 1, minor, pinning the existing order): `_cap` truncates at a
            # raw byte offset, so if it ran first, a secret straddling
            # that offset would come back with its tail sliced off rather
            # than replaced by the marker — `redact_text` has to see the
            # WHOLE result at least once before any of it is thrown away.
            result = _cap(self._redactor.redact_text(result))
        except Exception as unexpected:  # noqa: BLE001 — deliberate, see below
            # The one hard guarantee this class makes is that NOTHING
            # escapes `execute` (2K Task 5 brief) — a permissions error, a
            # symlink cycle, a misbehaving redactor, or any other
            # surprise becomes a refusal the model can read rather than a
            # crash of the whole enrichment run.
            error_detail = str(unexpected)
            result = f"refused: {name} could not be completed"
        entry: dict[str, object] = {
            "name": name,
            "args": dict(args) if isinstance(args, dict) else args,
            "result": result,
        }
        if error_detail is not None:
            entry["error"] = error_detail
        self.transcript.append(entry)
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
            if self._visible(child)
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
        # Mask BEFORE slicing (2K Task 5 fix round 1, minor, pinning the
        # existing order): `_content_of` key-masks the FULL text, and only
        # then is the requested window cut out of it — cutting first would
        # risk a config file's masking rule looking at a value with its
        # own line missing the context (a continuation, a nearby key) a
        # future, less line-local masking rule might need.
        lines = content.splitlines()
        last = start + DEFAULT_READ_LINES - 1 if end is None else end
        return "\n".join(lines[start - 1 : last])

    def _resolve_in_jail(self, raw_path: str) -> Path:
        """`raw_path`'s real location under one of the jailed roots, found
        by `_walk_segments` — the naming route's half of the module
        docstring's one symlink-and-case policy. Exactly two refusals, and
        the caller can tell them apart no further than this:

        * "outside the allowed roots" — `raw_path` cannot possibly land
          under ANY root, decided from its own spelling alone (a `..`
          segment, or an absolute path lexically outside every root)
          before the filesystem is even touched. A pure SHAPE question,
          answered without ever listing a directory.
        * "{raw_path} is not available" — every other reason a target does
          not come back: it does not exist, it exists under a different
          case, a symlink stood in the way, or it exists but is excluded
          (`.sextantignore`, the overlay, a derived-output directory). ONE
          message for all four (2K Task 5 fix round 1, I3; extended fix
          round 2, N4): "excluded" and "does not exist" used to be two
          different strings, an EXISTENCE ORACLE for exactly the names an
          attacker would probe (`.env`, `*.pem`, the overlay's own name);
          a symlink used to get its own THIRD string ("outside the
          allowed roots"), which was also simply FALSE for a symlink that
          resolves back inside the jail to a file the model could read
          directly under its real name — so this jail now gives the model
          no way to tell any of the four apart.
        """
        if _has_traversal(raw_path):
            raise _ToolRefusal("refused: outside the allowed roots")
        reachable = False
        for root in self._roots:
            parts = _relative_parts(root, raw_path)
            if parts is None:
                continue
            reachable = True
            target = _walk_segments(root, parts)
            if target is not None and not self._is_excluded(target):
                return target
        if reachable:
            raise _ToolRefusal(f"refused: {raw_path} is not available")
        raise _ToolRefusal("refused: outside the allowed roots")

    def _is_excluded(self, path: Path) -> bool:
        """Whether `path` — already confirmed real and inside a jailed
        root — is invisible to every tool: `.sextantignore` plus the
        built-in credential patterns (`ignore`); the enrichment overlay
        itself (the Task 3 ruling); or a derived-output directory
        (`DERIVED_OUTPUT_DIRS`) anywhere in `path`'s ancestry RELATIVE TO
        ITS OWN MOST SPECIFIC ROOT (`_most_specific_root` — 2K Task 5 fix
        round 2, N2). Judging ancestry against the wrong root is a real
        bug, not a theoretical one: with the ordinary nested layout
        (module root, its `.sextant/facts`, its `.sextant/render`), a
        module whose OWN root happens to sit under a directory literally
        named `target` (`--workspace target/ws`, say) previously blanked
        every fact and render row, because their ancestry was checked
        against the OUTER module root — which genuinely does have
        `target` in it — rather than against the fact/render root itself,
        which does not. Path-shaped and content-blind, like every check
        here: a copy of an excluded file sitting somewhere this does not
        name is not caught by it."""
        if path.name == ENRICHMENT_FILE:
            return True
        if self._ignore.matches(path):
            return True
        root = self._most_specific_root(path)
        if root is None:
            return False
        return any(part in DERIVED_OUTPUT_DIRS for part in path.relative_to(root).parts)

    def _most_specific_root(self, path: Path) -> Path | None:
        """The NARROWEST jailed root that contains `path` — the root
        `path`'s own ancestry is judged against, whether for the
        derived-output exclusion (`_is_excluded`) or for display
        (`_display_path`): 2K Task 5 fix round 2 ruling (N1 + N2). With
        the ordinary nested layout, a fact-root file is contained by BOTH
        the module root (its ancestor) and the fact root itself — the
        module root is never the answer once a more specific root also
        contains it, because a nested root's own files must never inherit
        an ancestor root's path segments as their own. `None` only for a
        path outside every root, which no caller of this method ever
        passes (unreachable in practice)."""
        containing = [root for root in self._roots if path.is_relative_to(root)]
        return max(containing, key=lambda root: len(root.parts), default=None)

    def _visible(self, entry: Path) -> bool:
        """The one per-entry check both `_list_dir`'s children and
        `_walk_visible`'s walk apply: real (not a symlink) and not
        `_is_excluded`. The naming route (`_walk_segments`) enforces the
        identical symlink rule its own way, one segment at a time, because
        it resolves a caller's STRING rather than filtering entries
        `list_directory` already handed it."""
        return not entry.is_symlink() and not self._is_excluded(entry)

    def _walk_visible(self, directory: Path) -> list[Path]:
        """The discovery route's half of the module docstring's policy:
        every visible file under `directory`, recursively, in whatever
        order `list_directory` gives its entries (the caller sorts).
        Every name here already comes from a REAL directory entry, so
        case is never in question on this route — `_visible`'s symlink
        check is what stops `find`/`grep` from walking through
        `innocent.txt -> .env` or a symlink chain that leaves every root
        (2K Task 5 fix round 1, C1): an excluded or symlinked entry is
        skipped, and a directory that is either is never even descended
        into. Deliberately unaware of `self._roots`' own nesting — a
        fact/render root sitting inside the module root means THIS
        method, called once per root by `_visible_files`, walks the same
        nested files more than once; `_visible_files` is where that gets
        deduplicated, not here, so this method stays a plain "everything
        visible under one starting point" primitive."""
        visible: list[Path] = []
        for entry in list_directory(directory):
            if not self._visible(entry):
                continue
            if entry.is_dir():
                visible.extend(self._walk_visible(entry))
            elif entry.is_file():
                visible.append(entry)
        return visible

    def _visible_files(self) -> list[Path]:
        """Every visible file under every jailed root, deduplicated and
        sorted by its own `_display_path` (2K Task 5 fix round 2, N1): the
        ordinary layout nests the fact/render roots INSIDE the module
        root, so walking the module root already reaches every fact and
        render file, and walking each of THOSE roots separately reaches
        them again — a real fixture (module root plus its own
        `.sextant/facts`) walks 279 entries for 180 unique files without
        this. Collected into a SET first (Path equality — every entry here
        is already real and resolved, no symlink involved, so identity is
        unambiguous) precisely so `find`/`grep`'s downstream counts and
        match caps see each file once, then sorted by the DISPLAY string
        — the form relative to the file's own most specific root — rather
        than by which root's pass happened to walk it first."""
        files: set[Path] = set()
        for root in self._roots:
            files.update(self._walk_visible(root))
        return sorted(files, key=self._display_path)

    def _display_path(self, path: Path) -> str:
        """`path`, relative to whichever jailed root MOST SPECIFICALLY
        contains it (`_most_specific_root` — 2K Task 5 fix round 2, N1) —
        the form `find`/`grep` show and `read_file`/`grep`'s own `path`
        scoping accepts back, so a citation this tool prints is a
        citation the model can hand to another tool call unchanged. A
        fact-root file displays relative to the fact root (`foo.jsonl`),
        never relative to the module root that happens to be its
        ancestor too (`.sextant/facts/foo.jsonl`) — the same specificity
        rule `_is_excluded` uses, for the identical reason: a nested
        root's own files belong to IT, not to whatever contains it."""
        root = self._most_specific_root(path)
        if root is None:
            return path.as_posix()  # unreachable: every caller only passes jailed paths
        return path.relative_to(root).as_posix()

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


def _has_traversal(raw_path: str) -> bool:
    """Whether `raw_path` names a `..` segment anywhere — checked on the
    STRING alone, before any root is even tried, because `..` means the
    same thing (a bid to leave the jail) regardless of which root it is
    weighed against. A bare `.` never reaches this check: `pathlib` drops
    it while parsing, so `Path(".").parts` is already empty — which is
    what lets `list_dir(path=".")` mean "the root itself"."""
    return ".." in Path(raw_path).parts


def _relative_parts(root: Path, raw_path: str) -> tuple[str, ...] | None:
    """The segments to walk from `root` for `raw_path` — a STRING
    computation only (`PurePath.relative_to`; no filesystem access, no
    `Path.resolve()`, so this alone decides nothing about whether the
    target exists, is real, or is visible — `_walk_segments` decides all
    of that). An absolute `raw_path` not lexically prefixed by `root`'s own
    resolved spelling cannot land under it: `None`, and the caller tries
    the next root. A relative `raw_path` applies to every root alike —
    `parts` is returned exactly as given, unresolved, for `_walk_segments`
    to verify against real directory entries one segment at a time."""
    candidate = Path(raw_path)
    if candidate.is_absolute():
        try:
            return candidate.relative_to(root).parts
        except ValueError:
            return None
    return candidate.parts


def _walk_segments(root: Path, parts: tuple[str, ...]) -> Path | None:
    """The naming route's half of the module docstring's one
    symlink-and-case policy (2K Task 5 fix round 1, C1+C2): descend from
    `root` one segment at a time, requiring each to be the EXACT — case
    included — name of a REAL directory entry (`list_directory`, never the
    filesystem's own case-insensitive lookup, which a case-preserving-but-
    insensitive filesystem such as macOS's default satisfies for `.ENV`
    against a real `.env` and hands back a spelling `.sextantignore` never
    matches).

    A segment that is a SYMLINK — `root` itself, an intermediate
    directory, or the final target — stops the walk (`None`), the SAME
    outcome as not found or found under a different case: this jail never
    follows one, in or out, and a chain of several symlinks is refused at
    the FIRST hop rather than followed to see where it ends up. Folded
    into `_resolve_in_jail`'s single "is not available" message rather
    than its "outside the allowed roots" one (2K Task 5 fix round 2, N4):
    a symlink pointing back INSIDE the jail at a file the model could
    read directly is not "outside" — that word would be false — and a
    separate wording would tell a model it is specifically a symlink,
    which is one bit more than "not available" the model has no use for.

    Returns the real path once every segment is confirmed; `None`
    otherwise — not found, found under a different case, or a symlink are
    the SAME outcome here, on purpose (I3, extended by N4: distinguishing
    any of them would let a caller learn more about what actually sits at
    a name than "you cannot have this")."""
    current = root
    if current.is_symlink():
        return None
    for part in parts:
        try:
            real_names = {entry.name for entry in list_directory(current)}
        except OSError:
            return None
        if part not in real_names:
            return None
        current = current / part
        if current.is_symlink():
            return None
    return current


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
    sequence rather than raising or emitting invalid UTF-8). Callers only
    ever hand this the ALREADY-`redact_text`-ed result (see `execute`) —
    the ordering that keeps a secret from surviving with its tail cut off
    instead of replaced by the marker."""
    encoded = text.encode("utf-8")
    if len(encoded) <= MAX_RESULT_BYTES:
        return text
    note = f"\n... [truncated: result exceeds the {MAX_RESULT_BYTES}-byte cap]"
    budget = MAX_RESULT_BYTES - len(note.encode("utf-8"))
    return encoded[:budget].decode("utf-8", errors="ignore") + note
