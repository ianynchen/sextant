"""`.sextantignore` (2K design §2) — file-level exclusion, gitignore semantics,
two layers.

Clean split with `redaction.py`: that module masks a VALUE within a file
Sextant reads; this one decides whether a file is read AT ALL. "Sextant does
not read this, anywhere" is a stronger claim than any value pattern can make
— a redactor sees a value only after something already decided to read it.

**`pathspec`'s `gitwildmatch` pattern class, not a hand-rolled matcher.**
Negation, dir-only patterns (`build/`), anchoring (`/build` vs `build`), and
`**` all have corners where a naive translation to `fnmatch` or a single
regex disagrees with git — that drift is exactly what DR-6 names, and the
fix is mirroring git's own implementation rather than re-deriving it.

**Two layers, one safety rule.** `BUILTIN_PATTERNS` sits BENEATH whatever a
repository writes and is non-negatable: a repo `.sextantignore` carrying
`!.env` re-admits nothing, because the built-in layer is never given that
line to begin with — it is compiled from its own fixed tuple, once, and a
match against it short-circuits before the repo's own spec (negation and
all) is even consulted. Within the repo's own patterns, full gitignore
semantics apply, negation included: a repo can re-admit a file ITS OWN
earlier pattern excluded, just never one the built-in layer excludes.
"""

from pathlib import Path

import pathspec

IGNORE_FILE = ".sextantignore"

# Non-negatable (module docstring above). Fixed shapes for the credential
# material a repository is least likely to remember to list itself —
# `.sextant.yml`'s `redact:` widens VALUE masking the same way, but a file
# this set names is never opened at all, additions or not.
BUILTIN_PATTERNS = (
    ".env",
    ".env.*",
    "*.pem",
    "*.p12",
    "*.jks",
    "id_rsa*",
    "id_ed25519*",
    "secrets/**",
    "*.keystore",
)

# Compiled once, at import time, from the fixed tuple above and nothing
# else — no repository input ever reaches this spec, which is what makes it
# the non-negatable layer rather than merely the first lines of one.
_BUILTIN_SPEC = pathspec.PathSpec.from_lines("gitwildmatch", BUILTIN_PATTERNS)


class IgnoreRules:
    """The effective ignore decision for one repository root: the built-in
    layer, plus whatever `.sextantignore` (if any) adds.

    Construct through `load`. `matches` is the only question this class
    answers, and it answers it the same way for every walk site (config
    reads, schema reads, resource walks, and 2K Task 5's enrichment jail) —
    one utility, applied wherever a file enumeration decides what to open.
    """

    def __init__(
        self, repo_root: Path, repo_spec: "pathspec.PathSpec[pathspec.pattern.Pattern]"
    ) -> None:
        self._repo_root = repo_root
        self._repo_spec = repo_spec

    @classmethod
    def load(cls, repo_root: Path) -> "IgnoreRules":
        """`repo_root`'s own `.sextantignore`, root-level only (2K design §2:
        nested per-directory files are a stated fast-follow, not read here).

        A missing file is not an error — it is the ordinary case, and it
        leaves the repo layer empty so `matches` falls back to the built-ins
        alone. Lines are handed to `pathspec` exactly as git would read
        them: comments, blank lines, and any pattern `gitwildmatch` accepts
        behave the way git behaves, and this function invents no stricter
        reading of a malformed line than git's own would give it.
        """
        path = repo_root / IGNORE_FILE
        lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
        return cls(repo_root, pathspec.PathSpec.from_lines("gitwildmatch", lines))

    def matches(self, path: Path) -> bool:
        """Whether `path` is ignored — an absolute path (made relative to
        the repo root this instance was loaded for) or a path already
        relative to it.

        **Repo-root-relative, always** (2K Task 2 binding): a file under a
        nested root — `src/main/resources/x.yml`, three levels under the
        repo root a Maven module's `resource_roots` point at — is matched
        against `src/main/resources/x.yml`, never against `x.yml` relative
        to the resource root it happened to be enumerated from. A pattern
        written against the repo root (what a `.sextantignore` author sees
        when they open the file) would silently never match otherwise.

        The built-in layer is checked first and short-circuits: a match
        there is ignored regardless of what the repo's own spec — negation
        included — says about the same path.
        """
        relative = path.relative_to(self._repo_root) if path.is_absolute() else path
        candidate = relative.as_posix()
        return _BUILTIN_SPEC.match_file(candidate) or self._repo_spec.match_file(candidate)
