# Python types: our own reader, or a type checker (OI-208, plan 1, task 10)

Date: 2026-11-07. The spec asks for this record (`docs/superpowers/specs/2026-11-06-python-reader-design.md`
§7 item 6). The first-principles review asked why the spec builds its own type reading when a
type checker already does that work (`2026-11-06-python-reader-review-first-principles.md` M1).
This file weighs the options with what is now built and measured.

**How to read the claims.** Each claim is marked:
- **measured:** run on this machine (Apple M4, Python 3.14.10), with the command given;
- **from the tool's documents:** taken from the tool's own documents or README, and not run
  here. pyright, Pyrefly and ty are not installed on this machine, and this task downloads
  nothing, so none of them was run.

## The options

| | A. Our own reader (built) | B. pyright over LSP | C. Pyrefly or ty over LSP | D. mypy in-process |
|---|---|---|---|---|
| What it is | a `Scanner` backend over the standard library's `ast`, with a pinned typeshed copy and the installed environment's own type files | Microsoft's type checker, run as a language server; Sextant asks it per position | two newer type checkers written in Rust (Meta's Pyrefly, Astral's ty), each with a language server | mypy imported as a library, its internal build and type objects read in Sextant's own process |
| What Sextant must ship or install | nothing new: `ast` is the standard library; typeshed is in the wheel (13.2 MB, Task 7) | a Node.js runtime and the pyright package | one native binary each, as a wheel | nothing new for development: mypy 2.3.1 is already in the dev environment (the gate runs `mypy src`); a run-time dependency for users |
| Runs scanned code | no | no | no | no, unless a mypy plugin is loaded; the plugins a project configures (`pydantic.mypy`, SQLAlchemy's) are code from the scanned environment, so they must not be loaded |
| Downloads | none at run time (R20) | none at run time once installed; the PyPI `pyright` package is a wrapper that fetches the Node package on first use (from the tool's documents) | none once installed | none |
| Fits M03 (one file at a time, facts out) | yes: it writes the existing facts per file | no: answers come per position from a server holding the whole program; Sextant would translate hover text or LSP types into facts | no, as B | partly: one build over the whole module, then types read per expression |
| Grammar | the running Python's (3.12 floor in CI, 3.14 in development); a newer file is listed as uncovered with the version it needs | its own parser, independent of the running Python (from the tool's documents) | their own parsers (from the tools' documents) | the running Python's `ast`, as A (from the tool's documents) |
| Stability of the interface | ours | LSP is stable; pyright has no programmatic API for types (from the tool's documents) | LSP is stable; ty is a preview release (from the tool's documents) | mypy's documented API (`mypy.api`) returns report text only; the build and type objects are internal and change between releases (from the tool's documents) |

## What each one answers that the others do not

**A, our reader, measured on Sextant and polar** (`docs/research/2026-11-06-python-performance.md`):
- It writes every call with its receiver, its arguments, its place in the control flow and,
  where the file or a library states one, its owner. The resolver then binds the rest per path
  (spec §3b, ruling M-1). Nothing else in this table gives the per-path facts the value walk
  reads.
- On Sextant, the scanner wrote an owner for 19,429 of 23,482 call sites (82.7%). The resolver
  bound 160 more and gave a reason for every other one (0 sites with neither).
- **What it does not type, which a type checker does** (measured with a five-function probe and
  on Sextant's own unresolved sites):
  - an element taken out of a container (`xs[0].strip()`, `for x in xs: x.strip()`);
  - the result of a library method whose return type is a type variable (`d.get(k)` on a
    `dict[str, str]`);
  - a field declared only by a class-level annotation (dataclass, `NamedTuple`);
  - a value typed `Any` and narrowed by `isinstance`.

  These shapes are most of Sextant's 2,996 `not_readable` sites: 2,541 of them call a `dict`,
  `list`, `str`, `set` or `tuple` method. A `str | None` narrowed by `is not None` is typed.

**B and C** would type all four shapes above: generic substitution and narrowing are what a type
checker is for (from the tools' documents). They give no flow facts, no value ids and no
per-path answers. Sextant would still need A's scanner for those, and would then hold two
readings of one file, which the spec rules out ("a second pipeline", §4).

**D, mypy, measured here** (fresh cache folder each cold run, `--config-file /dev/null` so no
project plugin loads, compiled mypy 2.3.1):

| Tree | Files | Cold | Warm (cache kept) |
|---|---|---|---|
| `mypy src` on Sextant | 171 | 2.7 s | 0.11 s |
| `mypy --ignore-missing-imports examples/py-polar/server/polar` | 1,120 (no tests) | 4.8 s | 0.15 s |

polar has no installed environment here, so every third-party import is `Any`, and mypy reported
840 errors in 171 files. That makes the polar run cheaper than a real one. Neither run reads
types back out: the time to walk mypy's internal objects for every receiver is not measured.

For comparison, our scanner takes 4.8 s on Sextant and 13.8 s on polar's 2,053 files, tests
included, writing every fact (performance file). mypy only checks types, so the two numbers
measure different work.

## Weighing them by the spec's reasons

- **No downloads, nothing run from the scanned project (§3e, §4).** A and D meet both. B and C
  meet both once installed, but each adds a native or Node runtime that Sextant must ship.
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
