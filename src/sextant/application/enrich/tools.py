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
through these tools. One residual, accepted rather than closed (2K final
review, F1): the jailed RENDER root still serves `architecture.md`, which
after an `enrich` is the ENRICHED document, so a re-run's `read_file` can
reach the prior run's claims by that route. Accepted because the two
things that made it a loop are gone — the BRIEF is composed from an
in-memory MACHINE-ONLY assembly (`cli/app.py`), never the on-disk file, so
nothing feeds prior claims back unprompted; and every claim in that file
is visibly labelled as model output, so a model that goes looking finds
text marked as such rather than machine findings it might mistake for its
own evidence. A derived-output directory (`DERIVED_OUTPUT_DIRS` —
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
root's walk into a SET, keyed by real path, before sorting.

**One anchor, one spelling** (2K Task 5 fix round 4, the ruled
replacement for three rounds of per-file naming). EVERY citation EVERY
tool prints is the file's path relative to ONE directory: the repository
root `ignore` was loaded for, which `__init__` already proves contains
every jailed root. Distinct real paths therefore get distinct citations
BY CONSTRUCTION — no collision logic, no fallback, no cache, and
`_visible_files`' sort key (the citation itself) is injective, so the
order is fully determined. Three separate defects died with the scheme
this replaces, all of them shapes of "the name depends on which root a
file is measured against": two same-named files under SIBLING roots
collided and left one unreachable; a file the naming cache had never seen
fell through to an absolute HOST path in a model-visible `grep` result;
and a cached name disagreed with a live `read_file` about what exists.
The price, accepted and ruled: a fact file cites as
`.sextant/facts/com/acme/Order.jsonl`, not `com/acme/Order.jsonl` — the
ancestor's spelling, longer, and the same for every file. RESOLUTION
stays permissive: a caller-given path is walked case-exact from the
ANCHOR first (`_resolve_from_anchor` — the canonical reading, since that
is the spelling citations are minted in, and the one that makes a
citation resolve at all when the roots are SIBLINGS) and then from each
jailed root as the convenience spelling. That order matters, not just the
set of spellings accepted (fix round 5, A2): reading a root first let a
decoy at `mod/mod/notes.md` answer to the citation `mod/notes.md` minted
for the real `mod/notes.md`. So the round-trip contract holds both ways
and unambiguously: every citation `find`/`grep` prints, `read_file` and a
scoped `grep` accept unchanged, and return the file it named.

**Redaction on read, three ways.** A config-bearing file's content — the
extensions the config-reading `ArtifactReader`s claim, see
`CONFIG_BEARING_EXTENSIONS` below for precisely where that rule comes from
— is masked key-by-key before `read_file` or `grep` exposes it. The SAME
value, one derivation earlier, reaches the wire a second way: the fact
root is one of the three jailed roots by design (2K design §4), and its
`.jsonl` files carry that same `config_entry.value` verbatim — spec §1
names "config-entry facts served by tools" as its own redaction target,
distinct from the config file itself, and `_mask_fact_lines`/
`domain.factfile.redact_config_entry_line` is what closes it (2K Task 7
fix round 2). Between the two, a model cannot recover a value through
`grep` — over the config file OR over the fact file that describes it —
that `read_file` would have masked from either. The third way is
`redactor.redact_text` (URL userinfo stripped, plus any repo-added value
patterns), which covers the file kinds neither line-masker claims — an
ORDINARY source file with a credentialled URL in it — and runs inside
`_content_of` for exactly the reason the other two do: `grep` searches
what `read_file` returns, so match/no-match can never answer a question
the mask refuses (2K final review, F2). Every result, from every tool
(including a refusal), additionally passes `redact_text` AND an
anchor-prefix rewrite (the display anchor's own absolute path, stripped
wherever served CONTENT happens to carry it — a fact document's
`origin_entry`, chiefly — never only the citations this class prints
itself) on their way out of `execute`, BEFORE the byte cap — cheap, safe,
and the one pass nothing here is allowed to skip, in the one order that
keeps a secret from surviving half-truncated (see `execute`).
"""

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path

from sextant.application.ports.artifacts import file_kind
from sextant.domain.enrichment import ENRICHMENT_FILE
from sextant.domain.factfile import redact_config_entry_line
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

# A fact file's own extension (D00 §7) — root-agnostic on purpose (2K Task 7
# fix round 2, CRITICAL): rather than asking "is this path under the fact
# root" (which `ToolExecutor` would have to start tracking root ROLES to
# answer — a distinction nothing else here needs), any served `.jsonl` file
# is offered to `_mask_fact_lines`, which only ever touches a line that
# actually parses as a `config_entry` fact and leaves every other line,
# valid JSON or not, byte-identical. A `.jsonl` file that is not one of
# Sextant's own fact files pays one no-op parse attempt per line and
# nothing else — safe by construction, not merely by the ordinary layout.
FACT_LINE_EXTENSION = "jsonl"

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
                    "A directory, spelled the way find/grep print a path "
                    "(a path relative to one of the jailed roots, or an "
                    "absolute path already inside one, also works)."
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
        "Returns one path per line, each relative to the single "
        "repository root the jail is anchored to — so two different "
        "files never print the same path — sorted, each file listed once "
        "even if two roots nest inside each other. A symlinked file or "
        "directory is never followed or listed."
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
                    "Optional: a file or directory to scope the search to — "
                    "spelled the way find/grep print a path, or relative to a "
                    "jailed root; omitted searches every jailed root."
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
                "description": (
                    "A file, spelled the way find/grep print a path (a path "
                    "relative to one of the jailed roots also works)."
                ),
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

    **A root that does not exist is refused the same way, for the same
    reason (2K Task 7 fix round 1, CRITICAL C1b).** Before this, a missing
    root (an unrendered workspace's absent `.sextant/render`, say) degraded
    silently: every call still "worked", but `list_directory` raised
    inside `_walk_visible` on the first walk that reached it, caught by
    `execute`'s own catch-all, and every `find`/`grep` came back an opaque
    `"refused: ... could not be completed"` — indistinguishable, from
    inside the jail, from a genuine unexpected failure, and observed
    against exactly this fixture (2K Task 7's own golden-overlay
    regeneration). A caller wiring a workspace that has not reached the
    stage a root implies (analysed but not yet rendered, say) needs to know
    that AT CONSTRUCTION, loudly, not discover it one degraded tool call at
    a time.
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
            if not root.is_dir():
                # Names the absolute path, unlike the mismatch message above
                # (2K Task 7 fix round 2, minor) — deliberately, not an
                # inconsistency: BOTH exceptions are raised here, at
                # construction, before a single tool call exists to answer
                # — neither is ever wrapped into an `execute()` result the
                # model reads, only ever into a caller's own message (a
                # ClickException, in `cli/app.py`) meant for the operator
                # wiring this jail up. Naming the specific root is exactly
                # what that operator needs to fix the wiring; the mismatch
                # message stays generic because it names an ignore/root
                # PAIRING, several roots deep, that no one path identifies.
                raise ValueError(
                    f"ToolExecutor: jailed root {root} does not exist — construction "
                    "refused rather than building a jail whose calls degrade to opaque "
                    "refusals the moment a walk reaches it"
                )
        self._roots = resolved_roots
        self._redactor = redactor
        self._ignore = ignore
        # THE display anchor (2K Task 5 fix round 4): the loop just above
        # proves every jailed root sits under `ignore`'s own repository
        # root, so that ONE directory can name every file every tool
        # cites — see `_display_path` and the module docstring's "One
        # anchor, one spelling".
        self._anchor = ignore.repo_root
        # The user's home directory (2K Task 7 fix round 3, IMPORTANT
        # remainder): a LIBRARY fact document's `origin_entry` names the
        # extracted jar's own absolute path — legitimate local provenance
        # for analysis, written verbatim by design, and never under the
        # anchor (`~/.m2/repository/...`, ordinarily) — so `_anchor_relative`
        # alone cannot touch it. Cached once, like `_anchor`, rather than
        # recomputed per call.
        self._home = Path.home()
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
            # The anchor and home-directory rewrites run the same way, for
            # the same reason, ahead of both (2K Task 7 fix rounds 2-3): a
            # host path split by the byte cap is still a host path leaked
            # in part. Anchor before home, as `_content_of` explains.
            result = _cap(
                self._redactor.redact_text(self._home_relative(self._anchor_relative(result)))
            )
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
        # existing order): `_content_of` masks the FULL text — key by key,
        # and now `redact_text` over the whole of it too (2K final review,
        # F2) — and only then is the requested window cut out of it.
        # Cutting first would risk a config file's masking rule looking at
        # a value with its own line missing the context (a continuation, a
        # nearby key) a future, less line-local masking rule might need,
        # and would let a `redact:` pattern spanning the window boundary
        # go unmatched on the half this call happens to return.
        lines = content.splitlines()
        last = start + DEFAULT_READ_LINES - 1 if end is None else end
        return "\n".join(lines[start - 1 : last])

    def _resolve_in_jail(self, raw_path: str) -> Path:
        """`raw_path`'s real location under one of the jailed roots, found
        by `_walk_segments` — the naming route's half of the module
        docstring's one symlink-and-case policy. The DISPLAY ANCHOR is
        walked FIRST (`_resolve_from_anchor`, fix round 4: what makes an
        anchor-relative citation resolve when the roots are SIBLINGS), and
        only if that finds nothing is each jailed root tried in turn as the
        convenience spelling. That ORDER is the fix for 2K Task 5 fix round
        5, A2: citations are minted anchor-relative, so the anchor's own
        reading of a path is the canonical one, and trying a root first let
        a decoy shadow a real citation — with an anchor of `/repo` and a
        root of `/repo/mod`, the citation `mod/notes.md` (minted for
        `/repo/mod/notes.md`) resolved through the ROOT walk to
        `/repo/mod/mod/notes.md` instead, silently returning a different
        file than the citation named and leaving the named one unreachable.
        In the ordinary wiring the anchor IS `roots[0]`, so the two walks
        are the same walk and the order changes nothing. Exactly two
        refusals, and the caller can tell them apart no further than this:

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
        anchored = self._resolve_from_anchor(raw_path)
        if anchored is not None:
            return anchored
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

    def _resolve_from_anchor(self, raw_path: str) -> Path | None:
        """`raw_path` walked from the DISPLAY ANCHOR rather than from a
        jailed root — the CANONICAL reading of a path (fix round 5, A2:
        tried before any root, because this is the spelling every citation
        is minted in), and the other half of fix round 4's round-trip
        contract. Citations are anchor-relative now, and with SIBLING roots
        (`repo/mod` and `repo/ws/render` under an anchor of `repo`) an
        anchor-relative citation (`mod/notes.md`) names nothing under
        EITHER root's own walk, so a path `find` printed would otherwise be
        a path `read_file` refuses.

        Widens NAMING only, never the jail: the walk is the same case-exact,
        never-through-a-symlink `_walk_segments`, and the target must still
        land inside a jailed root and survive `_is_excluded` — so a file
        outside every root stays unreadable under this spelling exactly as
        it is under any other, and `None` here leaves the caller's own two
        refusals (and their deliberate indistinguishability) untouched."""
        parts = _relative_parts(self._anchor, raw_path)
        if parts is None:
            return None
        target = _walk_segments(self._anchor, parts)
        if target is None or not any(target.is_relative_to(root) for root in self._roots):
            return None
        return None if self._is_excluded(target) else target

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
        `path`'s own ancestry is judged against for the derived-output
        exclusion (`_is_excluded`, its one caller since display stopped
        depending on which root a file is measured against): 2K Task 5 fix
        round 2 ruling (N2). With the ordinary nested layout, a fact-root
        file is contained by BOTH the module root (its ancestor) and the
        fact root itself — the module root is never the answer once a more
        specific root also contains it, because a nested root's own files
        must not be judged excluded by ancestry that belongs to an
        ancestor root rather than to them. `None` only for a
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
        """Every visible file under every jailed root, deduplicated by real
        path and sorted by its own citation (2K Task 5 fix round 2, N1; the
        sort key is `_display_path`, injective since fix round 4, so the
        order is fully determined rather than settled among ties by
        `set`-iteration order). The ordinary layout nests the fact/render
        roots INSIDE the module root, so walking the module root already
        reaches every fact and render file, and walking each of THOSE roots
        separately reaches them again — a real fixture (module root plus
        its own `.sextant/facts`) walked 279 entries for 180 unique files
        before the dedup.

        Walked LIVE on every call, never cached (fix round 4): a cached
        snapshot made `find`/`grep` disagree with `read_file`/`list_dir`
        about what exists the moment anything wrote inside a root
        mid-run, and told the model a file it could read did not exist."""
        files: set[Path] = set()
        for root in self._roots:
            files.update(self._walk_visible(root))
        return sorted(files, key=self._display_path)

    def _display_path(self, path: Path) -> str:
        """`path`'s citation: its path relative to THE anchor, the one and
        only spelling any tool prints (module docstring, "One anchor, one
        spelling"). Total by construction — `__init__` proved every jailed
        root sits under the anchor, and every path that reaches here came
        out of a walk from one of those roots — so there is deliberately NO
        fallback branch: a path outside the anchor is a programming error
        raised as one, never a model-visible string. The `path.as_posix()`
        fallback this replaces is exactly how an absolute HOST path reached
        a scoped `grep`'s result (2K Task 5 fix round 4, S2), and the
        per-file, per-root naming it replaces is what collided (S1)."""
        if not path.is_relative_to(self._anchor):
            raise AssertionError(f"ToolExecutor: {path} is outside the display anchor")
        return path.relative_to(self._anchor).as_posix()

    def _anchor_relative(self, text: str) -> str:
        """`text` with every occurrence of the display anchor's own absolute
        path rewritten to its relative spelling (2K Task 7 fix round 2,
        IMPORTANT). `_display_path` already keeps every CITATION this class
        prints anchor-relative, but a served FILE's own bytes can carry the
        anchor as an absolute host path too — a fact document's
        `origin_entry` (`ingress/read/__init__.py`, the JVM extractor's own
        classpath entry) chiefly — and that is CONTENT, not a citation the
        anchor contract covers.

        Called from TWO places, deliberately: `_content_of` (so `grep`'s own
        pattern search runs against already-relativized text — a caller
        searching for the anchor's raw host path must find NOTHING, not
        merely see a cleaned-up report of a match it should never have been
        able to make) and `execute`'s own final pass, alongside
        `redact_text` (so every OTHER result — `list_dir`/`find`'s own
        names are already anchor-relative by construction, but nothing stops
        a later tool from returning content `_content_of` never touched —
        gets the same treatment). Idempotent: a text already relativized by
        the first call is unchanged by the second.

        `anchor/tail` becomes `tail`; a bare, standalone `anchor` (nothing
        after it) becomes `.` — the same "root itself" spelling
        `list_dir(path=".")` already accepts. See `_rewrite_prefix` for the
        boundary discipline that keeps this from touching `<anchor>.bak` or
        `/mnt/backup<anchor>/...` (2K Task 7 fix round 3, minor 1).
        """
        return _rewrite_prefix(text, self._anchor.as_posix(), slash="", bare=".")

    def _home_relative(self, text: str) -> str:
        """`text` with every occurrence of the user's home directory
        rewritten to `~` (2K Task 7 fix round 3, IMPORTANT remainder): a
        LIBRARY fact document's `origin_entry` names the extracted jar's own
        absolute path (`ingress/detect/maven.py`'s local-repository
        resolution, ordinarily under `~/.m2/repository`) — legitimate local
        provenance for `analyze`, written verbatim by design, and never
        under the ANCHOR the way a module's own resource root is, so
        `_anchor_relative` alone cannot touch it. The leak this closes is at
        the SERVING exit, not the write site: the absolute path stays real
        and useful on the analyst's own disk, and only the username is
        stripped on its way to a model. `home/tail` becomes `~/tail`
        (keeping the path usable, unlike the anchor's own "strip and lose
        the root" rewrite — home is not this jail's root, so there is no
        "the module itself" spelling to collapse to); a bare `home` becomes
        `~` alone. Same boundary discipline as `_anchor_relative`
        (`_rewrite_prefix`), and applied at the same two call sites.
        """
        return _rewrite_prefix(text, self._home.as_posix(), slash="~/", bare="~")

    def _content_of(self, path: Path) -> str | None:
        """`path`'s text, masked first when it is config-bearing OR a fact
        file (2K design §4's "redaction-on-read"; the fact-file half is 2K
        Task 7 fix round 2) — BEFORE either `read_file` or `grep` exposes
        it, so a `grep` for the very value `read_file` would have masked
        cannot recover it through EITHER route a value reaches the jail by.
        The anchor and home-directory rewrites (2K Task 7 fix rounds 2-3)
        run here too, unconditionally, for the same reason and not only at
        `execute`'s own final pass: `grep`'s OWN pattern search runs against
        what this method returns, so a caller searching for a host path —
        the anchor's own, or the analyst's home directory — has to find
        NOTHING, not merely see a cleaned-up report of a match it should
        never have been able to make. The anchor rewrite runs FIRST: the
        anchor is ordinarily a subdirectory of home, so content that is the
        anchor's own path must be claimed by the (root-collapsing) anchor
        rule before the (username-hiding, root-preserving) home rule would
        otherwise partially rewrite it into something that reads as merely
        "somewhere under home" rather than "the module itself".

        `redact_text` runs LAST, here and not only at `execute`'s exit (2K
        final review, F2), for the identical reason and against a proven
        leak: a `redact:`-pattern value or a URL's userinfo sitting in an
        ORDINARY source file — neither config-bearing nor `.jsonl`, so
        neither line-masker touches it — reached the exit pass masked, but
        `grep` had already searched the RAW text, so match/no-match answered
        the question the mask exists to refuse. `grep "svc:h"` matching
        while `grep "svc:x"` did not extracted `amqp://svc:hunter2@…` out of
        an ordinary source file one character at a time. Searching the bytes
        `read_file` returns is what closes it; `execute` keeps its own pass
        as belt-and-braces for results this method never saw. The exit pass
        therefore re-applies the patterns to already-masked text, which is
        safe by construction: userinfo stripping leaves no `user@` for a
        second pass to find, and a value pattern's own replacement is the
        `«redacted»` marker, chosen (D04) so no config value, URL or topic
        name could legitimately carry it. `None` for a file that cannot be
        decoded as UTF-8 text or cannot be read at all: both tools skip it
        rather than raising, the same silent-skip a real `grep` gives a
        binary file."""
        try:
            text = read_file_text(path)
        except (UnicodeDecodeError, OSError):
            return None
        kind = file_kind(path)
        if kind in CONFIG_BEARING_EXTENSIONS:
            text = _mask_config_lines(text, self._redactor)
        elif kind == FACT_LINE_EXTENSION:
            text = _mask_fact_lines(text, self._redactor)
        return self._redactor.redact_text(self._home_relative(self._anchor_relative(text)))


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


def _rewrite_prefix(text: str, prefix: str, slash: str, bare: str) -> str:
    """`text` with every occurrence of `prefix` — matched only as a whole
    path segment, never a substring on EITHER side — rewritten: `prefix/
    tail` becomes `slash + tail` (so `slash=""` strips the segment and its
    separator entirely, `slash="~/"` keeps a shortened root), and a bare,
    standalone `prefix` (nothing following it at all) becomes `bare` alone.
    Shared by `ToolExecutor._anchor_relative` and `._home_relative` (2K Task
    7 fix rounds 2-3): a text or JSON value the anchor's own absolute path
    can appear in is exactly the shape the home directory's can appear in
    too, so this is the one place the boundary rule is written.

    **Bounded on both sides (2K Task 7 fix round 3, minor 1 — a fix round 2
    regex admitted two false positives, reproduced and fixed here).** The
    lookbehind `(?<![\\w./-])` refuses a match where `prefix` is merely the
    TAIL of a longer segment — `/mnt/backup` immediately followed by
    `prefix` with no separator between them must never have `prefix` (or
    `prefix/...`) read out of the middle of `/mnt/backup<prefix>/...` and
    rewritten, leaving `/mnt/backup...` behind. The lookahead
    `(?![\\w.-])` (note the `.`, absent from fix round 2's version) refuses
    a match where `prefix` is merely the HEAD of a longer name —
    `<prefix>.bak` must never be read as "the bare prefix, then `.bak`" and
    rewritten into `<bare>.bak`; a `.` right after `prefix` means `prefix`
    was not the whole segment, the same way a `-` already excluded a
    sibling directory (`<prefix>-2`) from fix round 2 on.

    **Two residuals, stated rather than chased (2K Task 7 fix round 3, minor
    3).** A case-VARIANT spelling of `prefix` in served content (an
    uppercased drive-style prefix, say) survives this rewrite unrecognized:
    every writer that puts a host path into a fact or a source file emits
    the REAL spelling, so this has no known live case to reach from. A
    `prefix` containing a `"` or a `\\` would be JSON-escaped as written to
    disk and so never match `prefix`'s own un-escaped spelling here either
    — a miss, not a corruption: the path is not rewritten, but it is not
    mangled either, and nothing about that shape is plausible for a real
    filesystem path in the first place.
    """
    pattern = re.compile(r"(?<![\w./-])" + re.escape(prefix) + r"(/|(?![\w.-]))")
    return pattern.sub(lambda m: slash if m.group(1) == "/" else bare, text)


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


def _mask_fact_lines(text: str, redactor: Redactor) -> str:
    """`text` (a `.jsonl` fact file's content, or a window of it) with every
    line passed through `domain.factfile.redact_config_entry_line` (2K Task
    7 fix round 2, CRITICAL) — the SAME function the bundle export path
    calls, reused rather than reimplemented: a line that is not a
    `config_entry` fact (a symbol, a call site, the document header, or
    simply a line that does not parse as JSON at all — `read_file`'s own
    windowing can cut a line in half) passes through byte-identical, and a
    `config_entry` line's `value` is masked exactly as `read_file`/`grep`
    already mask that same value from the config file it was read out of.

    `compact=True` (2K Task 7 fix round 3, minor 2): a masked line
    re-serializes in `_line`'s OWN compact spelling, matching the style of
    the unmasked neighbours around it in the same served file — the export
    path's own default spelling is a byte-compatibility promise to 2K Task
    1's pins and belongs there alone."""
    return "\n".join(
        redact_config_entry_line(line, redactor, compact=True) for line in text.splitlines()
    )


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
