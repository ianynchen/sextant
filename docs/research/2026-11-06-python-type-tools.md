# Python types: our own reader, or a type checker (OI-208, plan 1, task 10)

Date: 2026-11-07. The spec asks for this record (`docs/superpowers/specs/2026-11-06-python-reader-design.md`
§7 item 6). The first-principles review asked why the spec builds its own type reading when a
type checker already does that work (`2026-11-06-python-reader-review-first-principles.md` M1).
This file weighs the options with what is now built and measured.

**How to read the claims.** Each claim is marked:
- **measured:** run on this machine (Apple M4, Python 3.14.10), with the command given;
- **from the tool's documents [n]:** taken from the page numbered in "Sources" at the end,
  fetched 2026-11-07, and not run here;
- **not checked:** a claim no fetched page states. It is kept only where it matters, and is
  marked.

pyright, Pyrefly and ty are not installed on this machine, and this task downloads nothing,
so none of them was run.

## The options

| | A. Our own reader (built) | B. pyright over LSP | C. Pyrefly or ty over LSP | D. mypy in-process |
|---|---|---|---|---|
| What it is | a `Scanner` backend over the standard library's `ast`, with a pinned typeshed copy and the installed environment's own type files | Microsoft's type checker, run as a language server; Sextant asks it per position | two newer type checkers, each with a language server: Meta's Pyrefly [4] and Astral's ty, "written in Rust" [5]; Pyrefly's language is not checked | mypy imported as a library, its internal build and type objects read in Sextant's own process |
| What Sextant must ship or install | nothing new: `ast` is the standard library; typeshed is in the wheel (13.2 MB, Task 7) | a Node.js runtime and the pyright npm package: the PyPI `pyright` package runs it with `node` [3] | one more package each: `pip install pyrefly` [4]; ty as a PyPI package or a standalone binary [6] | nothing new for development: mypy 2.3.1 is already in the dev environment (the gate runs `mypy src`); a run-time dependency for users |
| Runs scanned code | no | no | no | no, unless a mypy plugin is loaded; the plugins a project configures (`pydantic.mypy`, SQLAlchemy's) are code from the scanned environment, so they must not be loaded |
| Downloads | none at run time (R20) | **yes, unless Node is installed:** with no `node` on `PATH`, the PyPI `pyright` package downloads Node at run time and installs the pyright npm package [3] | none once installed (not checked) | none |
| Fits M03 (one file at a time, facts out) | yes: it writes the existing facts per file | no: answers come per position from a server holding the whole program; Sextant would translate hover text or LSP types into facts | no, as B | partly: one build over the whole module, then types read per expression |
| Grammar | the running Python's (3.12 floor in CI, 3.14 in development); a newer file is listed as uncovered with the version it needs | its own parser, independent of the running Python (not checked) | their own parsers (not checked) | the running Python's `ast`, as A (not checked) |
| Stability of the interface | ours | LSP is a published protocol; that pyright has no programmatic API for types is not checked (the earlier essay stated it) | LSP, as B; neither front page states a release status [4][5], and ty's install page shows only `0.0.x` example versions [6] | `mypy.api.run` returns `(normal report, error report, exit status)`, text only [1]; the plugin system "is experimental and prone to change" [2]; the stability of the build and type objects that reading types needs is not stated [1][2] (not checked) |

## What each one answers that the others do not

**A, our reader, measured on Sextant and polar** (`docs/research/2026-11-06-python-performance.md`):
- It writes every call with its receiver, its arguments, its place in the control flow and,
  where the file or a library states one, its owner. The resolver then binds the rest per path
  (spec §3b, ruling M-1). Nothing else in this table gives the per-path facts the value walk
  reads.
- On Sextant, the scanner wrote an owner for 19,429 of 23,482 call sites (82.7%). The resolver
  bound the owner of 126 more; 34 are calls of a function value whose edge enters that
  function's body (ruling R29); the other 3,893 are unresolved, each with a reason from the one
  reason list (104 with several, one per path). No site is outside these groups.
- **What it does not type, which a type checker does** (measured with a five-function probe and
  on Sextant's own unresolved sites):
  - an element taken out of a container (`xs[0].strip()`, `for x in xs: x.strip()`);
  - the result of a library method whose return type is a type variable (`d.get(k)` on a
    `dict[str, str]`);
  - a field declared only by a class-level annotation (dataclass, `NamedTuple`);
  - a value typed `Any` and narrowed by `isinstance`.

  These shapes are most of Sextant's 2,996 `not_readable` sites: 2,541 of them call a `dict`,
  `list`, `str`, `set` or `tuple` method. A `str | None` narrowed by `is not None` is typed.

**B and C** would very likely type all four shapes above, because generic substitution and
narrowing are what a type checker does; this is not checked per tool. They give no flow facts, no value ids and no
per-path answers. Sextant would still need A's scanner for those, and would then hold two
readings of one file, which the spec rules out ("a second pipeline", §4).

**D, mypy, measured here** (compiled mypy 2.3.1, a fresh `--cache-dir` for each cold run):

| Command | Files | Cold | Warm (cache kept) |
|---|---|---|---|
| `.venv/bin/mypy src --cache-dir <new folder>`, run at the repository root, so it reads Sextant's `pyproject.toml` `[tool.mypy]` (`strict = true`, `files = ["src"]`, `exclude = ["^src/sextant/resources/typeshed/"]`, two `ignore_missing_imports` overrides): the gate's own command | 171 | 2.6–2.7 s (three runs) | 0.11 s |
| `.venv/bin/mypy --config-file /dev/null --ignore-missing-imports --cache-dir <new folder> examples/py-polar/server/polar`, run from the scratch folder so polar's own `[tool.mypy]` and its plugins are not loaded | 1,120 (no tests) | 4.8 s | 0.15 s |

Sextant's config is needed: with `--config-file /dev/null`, `mypy src` stops at once on
`src/sextant/resources/typeshed/stubs/mypy-extensions/mypy_extensions.pyi: error: This file
shadows library module "mypy_extensions"`, because the typeshed copy is no longer excluded.

polar has no installed environment here, so every third-party import is `Any`, and mypy reported
840 errors in 171 files. That makes the polar run cheaper than a real one. Neither run reads
types back out: the time to walk mypy's internal objects for every receiver is not measured.

For comparison, our scanner takes 4.8 s on Sextant and 13.8 s on polar's 2,053 files, tests
included, writing every fact (performance file). mypy only checks types, so the two numbers
measure different work.

## Weighing them by the spec's reasons

- **No downloads, nothing run from the scanned project (§3e, §4).** A and D meet both. B meets
  "no downloads" only where Node is installed beside it: otherwise its PyPI wrapper downloads
  Node at run time [3]. C meets both once installed (not checked). B and C each add a package
  or runtime that Sextant must ship.
- **One pipeline, facts in the existing format (§1, §4).** Only A writes facts. B, C and D each
  answer types only, so each could at most fill the owner of a call that A left to the
  resolver. They cannot replace A.
- **Truth (§7 item 5).** A writes a type only where the code, typeshed or an installed library
  states it, and gives a reason otherwise. A checker's `Any` hides a gap rather than naming it
  (the earlier Python essay recorded this for mypy). Any checker answer would have to treat
  `Any` and an unsolved variable as unknown.
- **Speed (§5).** A meets the cold target (27.2 s on polar against 60 s). mypy's own checking
  is fast (4.8 s cold on polar's package without libraries). The cost of reading types out of
  it per receiver, and of an LSP round trip per position for B and C, is not measured.

## Where this leaves the decision

The spec's choice, A, stands for the parts only A can do: facts per file, flow, value ids and
per-path binding. The measured gap is narrower than "types". It is four shapes that a type
checker solves exactly (above). Two ways to close it are open, and neither is built:
1. Extend A's rules: substitute a generic's type variables from the receiver's written type
   arguments, read class-level annotations as field types, and read `isinstance` tests as the
   walk reads `is not None`.
2. Ask mypy in-process (D) for the owner of a call A left `not_readable`, with no plugin, and
   with `Any` read as unknown.

Choosing between them is the user's call. The cost of (2) per receiver needs measuring first.

## Sources

Fetched 2026-11-07. None of these tools was downloaded or run.

1. mypy 2.4.1 documentation, "Extending and integrating mypy", section "Integrating mypy into
   another Python application": https://mypy.readthedocs.io/en/stable/extending_mypy.html
2. The same page, section "Extending mypy using plugins" ("The plugin system is experimental
   and prone to change"; "no guarantees about backwards compatibility").
3. pyright-python README (the PyPI `pyright` package): https://github.com/RobertCraigie/pyright-python
   ("If it is not, then we download node at runtime using nodeenv, then install the pyright
   npm package").
4. Pyrefly home page: https://pyrefly.org/ ("a fast type checker and language server for
   Python"; `pip install pyrefly`).
5. ty documentation home: https://docs.astral.sh/ty/ ("An extremely fast Python type checker
   and language server, written in Rust").
6. ty installation: https://docs.astral.sh/ty/installation/ (standalone installer, GitHub
   Releases binaries, `pip install ty`).
