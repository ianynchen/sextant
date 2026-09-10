"""Field check: validate Sextant's own output against real, live upstream repositories.

**Opt-in, network-using by nature — never part of the test suite or `scripts/check.sh`**
(2M design §3). It checks out a pinned commit and, when the module is not already built at
it, runs `mvn compile` — which reaches the network for anything not already cached. §5's
beyond-fixture claims are verified only when someone runs this; the fixture pins are the
always-on net.

Each expectation file under `scripts/field-expectations/*.json` PINS the upstream commit
it was recorded against, and the upstream's own `remote` URL — `examples/` is gitignored,
so nothing survives outside these expectation files to say which repository a `repo` name
even refers to. Reproducing a check on a machine that does not already have the clone is
therefore `git clone <remote> examples/<repo>` (at any commit — this script checks out the
pinned one itself) before running this script. It then checks the working tree out to
exactly that commit before validating, so upstream drift can never masquerade as a Sextant
regression — refreshing a pin (a new `commit`, and the counts/routes re-recorded against
it) is a deliberate, reviewed act, not something this script does on its own.

Three optional keys carry an upstream whose build is not one wrapper-script invocation at
the repository root (`mall-admin.json` is the first to need any of them):

- **`module`** — the path under the clone that `analyze`/`render` run against, and whose
  `target/classes` decides whether a build is needed. Absent, the repository root is both,
  which is every single-module pin.
- **`maven`** — the Maven launcher, defaulting to the wrapper `./mvnw`. `macrozheng/mall`
  ships no wrapper, so its pin names the system `mvn`; naming it here rather than falling
  back silently keeps "which Maven built this" a property of the recorded pin.
- **`jdk`** — the MAJOR Java version the upstream's build requires, checked against the one
  Maven will actually use (its own `-v` banner) and REFUSED on a mismatch rather than left
  to fail somewhere inside the build. `macrozheng/mall` is why: on a JDK newer than 21 its
  Lombok annotation processor throws and the build dies several screens deep in a stack
  trace with nothing pointing at the toolchain. Recording the identity from the run's own
  output rather than from an environment variable is GUIDELINES §5.4.

Checks, per expectation:

- **Endpoint counts** — `metadata.json`'s own `endpoints` object, compared whole.
- **`resolvable_superclass_calls`**, where the pin declares one (F3 §4.2, W21) — how many
  calls the upstream makes onto a method declared on an ancestor it also scans. A property
  of the upstream's SOURCE rather than of Sextant's output, checked because it is the
  number that made adding `spring-petclinic-rest` worth doing: a drop means the shape has
  left the corpus and the resolution work is measured against nothing, a rise means
  upstream drift the pinned commit was supposed to prevent.
- **`terminal_kinds`**, where the pin declares one (F7 §8.2, W30) — what the shipped
  `terminals` rules classified on this corpus, per `kind/target`, compared whole. It is
  the ONLY check anywhere on those twelve rules: the unit tests invent their own type
  names on purpose, so a typo in a real one is inert rather than invalid and nothing else
  would notice. One corpus per route — `mall-admin` for scanned packages and the `cache`
  rule, `jhipster-sample-app` for supertypes, `spring-petclinic-rest` for owners.
- **`narrowed_sites`**, where the pin declares one (F7 §8.3, W32) — call sites whose
  dispatch narrowed to several bodies, as `{in_graph, reached_by_a_trace}`. Two numbers
  because they are two claims: only the second can appear in the document. Pinned because
  W32's plan row claimed this shape never occurred on real code and it occurs 34 times on
  `spring-petclinic-rest`.
- **Route sets** — the wire-identity column of the rendered document's "Inbound endpoints"
  and "Outbound endpoints" tables, each sorted.
- **Zero `<pre>`-outside-code-blocks** (2M design §5b) — every `<pre>` in
  `architecture.html` is either a diagram (`<pre class="mermaid">`) or a fenced code block
  immediately wrapping a `<code>` (`<pre><code>`, machine or claim alike); the
  `MachineSection` escape hatch (`<pre class="machine">`) reaching real output at all is
  the failure this exists to catch.
- **The first diagram parses** (2M design §5a) — defined HERE, conservatively and without
  a browser or a real mermaid grammar: no unquoted `$` survives outside a backtick-quoted
  span in the first `<pre class="mermaid">` block's source. A JVM nested class's `$`
  breaking mermaid's bare-identifier grammar is the one real failure this phase fixed
  (`egress/render/diagrams.py`'s own quoting rule); this check proves that failure mode
  stays fixed against a live diagram, not that mermaid's full grammar is satisfied.

Usage:

    python scripts/field_check.py                  # every *.json under field-expectations/
    python scripts/field_check.py jhipster-sample-app
"""

from __future__ import annotations

import html
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"
EXPECTATIONS_DIR = REPO_ROOT / "scripts" / "field-expectations"

_TABLE_ROW = re.compile(r"^\| `([^`]+)` \|", re.MULTILINE)
_PRE_OPEN = re.compile(r"<pre(?P<attrs>[^>]*)>")
_BACKTICK_SPAN = re.compile(r"`[^`]*`")
# Maven's own `-v` banner line: `Java version: 21.0.12.1, vendor: Homebrew, runtime: ...`.
# The MAJOR component alone is captured — a pin declaring `21` is a statement about the
# language level the upstream's build needs, never about a patch release.
_MVN_JAVA_VERSION = re.compile(r"^Java version: (\d+)", re.MULTILINE)

# The Maven launcher a pin gets when it names none: the wrapper every pin before
# `mall-admin` had, run from the repository root.
_DEFAULT_MAVEN = "./mvnw"


class FieldCheckFailure(Exception):
    """One expectation did not hold against the live run — carries the reader-facing
    reason, never a bare traceback (DR-6's own discipline, extended to this script)."""


def _sextant_bin() -> str:
    """The installed `sextant` command — the project virtualenv's own copy when one
    exists, mirroring `scripts/check.sh`'s own `BIN` resolution, so this script and the
    pre-commit/CI gate resolve the same binary rather than whatever happens to be on
    `PATH` first."""
    venv_bin = REPO_ROOT / ".venv" / "bin" / "sextant"
    return str(venv_bin) if venv_bin.is_file() else "sextant"


def _run(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)


def _ensure_repo_present(repo: Path, remote: str) -> None:
    """The pinned repository has to already be cloned locally — this script deliberately
    never clones it for you (§3's opt-in, deliberate-network posture governs a `mvn
    compile` this script DOES run, not fetching a whole upstream history unasked). `remote`
    is `git clone`-able straight from the expectation file (see the module docstring)."""
    if not repo.is_dir():
        raise FieldCheckFailure(
            f"{repo} does not exist — clone the pinned upstream first: git clone {remote} {repo}"
        )


def _checkout(repo: Path, commit: str) -> bool:
    """Pin the upstream working tree to exactly `commit` — the whole point of pinning
    (upstream drift never masquerades as a Sextant regression). A dirty tree or a commit
    this clone does not have is a loud failure, never a silent checkout of whatever is
    closest.

    Returns whether this call actually MOVED HEAD (`False` when the tree was already at
    `commit`). `_ensure_compiled` uses this to decide whether its own "`target/classes`
    already exists" shortcut is still trustworthy (2M final review wave, I1):
    `target/` is untracked and survives a real `git checkout` untouched, so a moved HEAD
    leaves the OLD commit's bytecode sitting there under NEW sources until something
    forces a rebuild.

    The dirty-tree check runs BEFORE the already-at-`commit` early return (2M Task 7 fix
    round 1, field-check gap a): a dirty tree sitting AT the pinned commit is not "already
    correct" — validating against it means validating against whatever local edits are
    sitting on top, which is exactly the drift this whole script exists to rule out. Left
    after the early return, it also compounds with `_ensure_compiled`'s own "skip if
    `target/classes` already exists" shortcut into a fully unpinned `ok`: a stale, edited
    tree that still happens to report `HEAD == commit` would never be checked at all.

    `--untracked-files=no`: TRACKED content only, deliberately. `sextant module
    analyze`/`render` write `.sextant/` (and `.sextant-enrichment.json`) straight into
    the module root by design (ARCHITECTURE §8) — this script's own prior run, or an
    earlier `enrich`, leaves exactly that behind as untracked cruft the upstream's own
    `.gitignore` never names. That is expected output, not drift: what this check exists
    to catch is a TRACKED file — a `pom.xml`, a Java source — edited out from under the
    pin, which `--untracked-files=no` still reports (`M path`) every time."""
    head = _run(["git", "rev-parse", "HEAD"], cwd=repo)
    if head.returncode != 0:
        raise FieldCheckFailure(f"{repo} is not a git repository: {head.stderr.strip()}")
    status = _run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=repo)
    if status.stdout.strip():
        raise FieldCheckFailure(
            f"{repo} has uncommitted changes; refusing to validate against a tree that "
            f"may not match the pinned commit {commit}"
        )
    if head.stdout.strip() == commit:
        return False
    checkout = _run(["git", "checkout", "--quiet", commit], cwd=repo)
    if checkout.returncode != 0:
        raise FieldCheckFailure(
            f"could not check out {repo}'s pinned commit {commit}: {checkout.stderr.strip()}"
        )
    return True


def _refused_if_wrong_jdk(repo: Path, maven: str, required_major: str) -> None:
    """Refuse before building unless the JDK **Maven itself** reports is `required_major`.

    Read from Maven's own `-v` banner rather than from `JAVA_HOME` or from whichever
    `java` happens to be first on `PATH`, because those are what the runner INTENDED and
    the banner is what will run (GUIDELINES §5.4: *"record identity from the run's own
    output, never from the parameter you passed in"*). Maven resolves its JDK through
    `JAVA_HOME`, so the two disagree exactly when it matters.

    **Fatal rather than advisory**, for the same reason §5.4 gives: the failure this
    prevents is not a missing JDK but a WRONG one, and a wrong one fails deep inside the
    build — `macrozheng/mall` on a JDK newer than 21 dies in Lombok's annotation
    processor, with nothing in the output naming the toolchain as the cause.

    Called only for a pin that declares `jdk`, and only when a BUILD is actually about to
    run — from inside `_ensure_compiled`, past its already-built shortcut. It was called
    before that decision, which made it refuse a pin whose `target/classes` was already
    compiled, at the pinned commit, by the right JDK: nothing was going to invoke Maven,
    so there was no wrong toolchain to prevent, and the check reported a machine's missing
    JDK as though the pin could not be validated. A pin that declares no `jdk` is
    unchanged and runs on whatever the machine has."""
    banner = _run([maven, "-v"], cwd=repo)
    if banner.returncode != 0:
        raise FieldCheckFailure(
            f"could not read {repo}'s Maven toolchain (`{maven} -v`):\n"
            f"{banner.stdout}\n{banner.stderr}"
        )
    found = _MVN_JAVA_VERSION.search(banner.stdout)
    if found is None:
        raise FieldCheckFailure(
            f"`{maven} -v` in {repo} printed no `Java version:` line, so the JDK this pin "
            f"requires ({required_major}) cannot be verified:\n{banner.stdout}"
        )
    if found.group(1) != required_major:
        raise FieldCheckFailure(
            f"{repo} pins JDK {required_major} and Maven will use {found.group(1)}; "
            f"set JAVA_HOME to a {required_major} JDK and re-run"
        )


def _ensure_compiled(
    repo: Path,
    force: bool,
    module: Path | None = None,
    maven: str = _DEFAULT_MAVEN,
    jdk: str | None = None,
) -> None:
    """`target/classes` populated at the checked-out commit — the compiled-first reading
    `MavenDetector` requires (it never runs Maven itself). Skipped when `target/classes`
    already exists AND `force` is `False`: `_checkout` proves the tree's SOURCES are at
    the pinned commit, never that `target/classes` was compiled from them — `target/` is
    untracked and survives `git checkout` untouched (2M final review wave, I1), so
    skipping unconditionally on "already exists" validates a PIN REFRESH's new sources
    against the OLD commit's leftover bytecode. `force=True` — `_checkout` just moved
    HEAD — rebuilds unconditionally regardless of what is already in `target/classes`;
    the ordinary case between two runs of this script (HEAD unmoved) still skips, so a
    field run against an already-built checkout does not pay a full rebuild every time.
    Delete `target/` to force one by hand. Offline first (`-o`), the same posture the
    detectors themselves default to; only retried without it — reaching the network —
    when the offline attempt fails, since this script is explicitly allowed to
    (network-using by nature, see the module docstring).

    `module` is the ANALYSED module's directory on a multi-module pin, and only the
    already-built check reads it: `target/classes` belongs to the module, while the Maven
    launcher is the reactor's and runs from the repository root — building the whole
    reactor rather than one module because a module's own compile needs its siblings
    installed, which a root build gives for free. Defaults to `repo`, which is every
    single-module pin.

    `jdk`, when the pin declares one, is verified HERE rather than before the shortcut
    above. The check exists to stop a build running on the wrong toolchain, so it belongs
    on the path that runs one: a module already compiled at the pinned commit needs no
    JDK at all, and refusing it there turned "this machine cannot BUILD this pin" into
    "this pin cannot be validated", which is a different and untrue statement."""
    if not force and ((module or repo) / "target" / "classes").is_dir():
        return
    if jdk is not None:
        _refused_if_wrong_jdk(repo, maven, jdk)
    offline = _run([maven, "-q", "-o", "compile"], cwd=repo)
    if offline.returncode == 0:
        return
    online = _run([maven, "-q", "compile"], cwd=repo)
    if online.returncode != 0:
        raise FieldCheckFailure(
            f"`mvn compile` failed in {repo} even with the network allowed:\n"
            f"{online.stdout}\n{online.stderr}"
        )


def _analyze_and_render(module: Path) -> None:
    """`render` takes no display flags, so the pin validates the only document there is,
    which is the complete one (GUIDELINES §8.4)."""
    sextant = _sextant_bin()
    analyze = _run([sextant, "module", "analyze", str(module)], cwd=REPO_ROOT)
    if analyze.returncode != 0:
        raise FieldCheckFailure(
            f"`sextant module analyze {module}` failed:\n{analyze.stdout}\n{analyze.stderr}"
        )
    render = _run([sextant, "module", "render", str(module)], cwd=REPO_ROOT)
    if render.returncode != 0:
        raise FieldCheckFailure(
            f"`sextant module render {module}` failed:\n{render.stdout}\n{render.stderr}"
        )


def _narrowed_sites(module: Path) -> dict[str, int]:
    """`{"in_graph": N, "reached_by_a_trace": M}` — call sites whose dispatch narrowed to
    several bodies, and how many of them a walk reaches.

    Two numbers because they are two claims and W32's own docstring welded them together:
    34 sites are in `spring-petclinic-rest`'s `call_edges` and 31 of them are in a trace,
    so only 31 can appear in the document. A single number would let either drift under
    the other's name.
    """
    from sextant.application.query.trace import traces_of
    from sextant.domain.closed_sets import Resolution
    from sextant.storage.duckdb.workspace import DuckDbWorkspace

    workspace = DuckDbWorkspace(module / ".sextant" / "workspace.duckdb")
    try:
        in_graph = {
            (str(row["caller"]), int(str(row["ordinal"])))
            for row in workspace.query("call_edges")
            if str(row["resolution"]) == Resolution.NARROWED
        }
        reached: set[tuple[str, int]] = set()
        for trace in traces_of(workspace):
            counted: dict[tuple[str, int], int] = {}
            for step in trace.steps:
                if step.resolution != Resolution.NARROWED:
                    continue
                key = (step.caller, step.ordinal)
                counted[key] = counted.get(key, 0) + 1
                if counted[key] > 1:
                    reached.add(key)
    finally:
        workspace.close()
    return {"in_graph": len(in_graph), "reached_by_a_trace": len(reached)}


def _terminal_kinds(module: Path) -> dict[str, int]:
    """`call_edges`' classification, counted per `kind/target`, from the workspace
    `analyze` has just written.

    Reads the workspace rather than re-deriving, unlike `resolvable_superclass_calls`
    beside it: this is a property of Sextant's OUTPUT, not of the upstream's source, so
    the run that produced it is the thing to measure. `unresolved` is counted too — it is
    the denominator, and a rule that stopped matching would move a classified count down
    and this one up by the same amount, which reads very differently from a corpus that
    simply grew.
    """
    import duckdb

    connection = duckdb.connect(str(module / ".sextant" / "workspace.duckdb"), read_only=True)
    try:
        rows = connection.execute(
            "SELECT terminal_kind, coalesce(target_kind, ''), count(*) FROM call_edges "
            "WHERE terminal_kind IS NOT NULL GROUP BY 1, 2 ORDER BY 1, 2"
        ).fetchall()
    finally:
        connection.close()
    return {f"{kind}/{target}" if target else str(kind): int(count) for kind, target, count in rows}


def _routes_in_section(markdown: str, heading: str) -> list[str]:
    """Every row's wire identity (the first, backtick-quoted column) under `## {heading}`,
    sorted — the section runs from that heading to the next `## `, or the document's end
    when `heading` is the last one."""
    marker = f"\n## {heading}\n"
    start = markdown.find(marker)
    if start == -1:
        return []
    start += len(marker)
    end = markdown.find("\n## ", start)
    section = markdown[start:] if end == -1 else markdown[start:end]
    return sorted(_TABLE_ROW.findall(section))


def _zero_pre_outside_code_blocks(html_text: str) -> bool:
    """2M design §5b: every `<pre>` in the rendered BODY is either a diagram
    (`<pre class="mermaid">`) or immediately wraps a `<code>` (a fenced block, machine or
    claim). Anything else — the `MachineSection` escape hatch chief among them — fails
    this.

    Scanned only up to the first `<script>` tag: `html_document` appends the vendored
    mermaid/panzoom assets verbatim after the rendered body (`html.py`'s own template),
    and mermaid's own bundled source contains the literal substring `<pre` in its error-
    rendering strings — a real `<pre>` in a `<script>` block's TEXT, not a tag in the
    page's markup, and not this check's business."""
    body, _, _ = html_text.partition("<script>")
    for match in _PRE_OPEN.finditer(body):
        if 'class="mermaid"' in match.group("attrs"):
            continue
        if body[match.end() :].startswith("<code>"):
            continue
        return False
    return True


def _first_diagram_parses(html_text: str) -> bool:
    """See the module docstring's own definition of "parses". `None` (no diagram found at
    all) is itself a failure — every rendered document carries a `## Structure` diagram
    unconditionally, so its absence from the HTML means something upstream broke, not that
    there was nothing to check.

    `_BACKTICK_SPAN` (`` `[^`]*` ``) matches across newlines — mermaid identifiers are
    single-line, so this is deliberately loose, not tight, and the conservatism this check
    was documented with (module docstring) runs in the OPPOSITE direction here: a stray,
    unpaired backtick earlier in the source can make this regex treat everything up to the
    NEXT backtick — real `$`s included — as one big quoted span and strip it along with
    them, hiding a genuinely unquoted `$` rather than flagging it. This check still proves
    what it claims for well-formed, single-line quoted spans (2M design §5a's own emitted
    shape); it is not a mermaid tokenizer and does not defend against adversarially
    malformed diagram source."""
    match = re.search(r'<pre class="mermaid">(.*?)</pre>', html_text, re.DOTALL)
    if match is None:
        return False
    source = html.unescape(match.group(1))
    without_quoted_spans = _BACKTICK_SPAN.sub("", source)
    return "$" not in without_quoted_spans


def _check_one(name: str) -> list[str]:
    """Every problem found validating one expectation file — empty means it held."""
    expectation_path = EXPECTATIONS_DIR / f"{name}.json"
    expectation = json.loads(expectation_path.read_text(encoding="utf-8"))
    repo = EXAMPLES_DIR / expectation["repo"]
    # The analysed module, which is the repository root on every single-module pin. `repo
    # / "."` would be `repo` here too, but the conditional says out loud that the key is
    # optional rather than relying on a pathlib normalisation a reader has to know.
    module = repo / expectation["module"] if "module" in expectation else repo
    problems: list[str] = []

    _ensure_repo_present(repo, expectation["remote"])
    maven = expectation.get("maven", _DEFAULT_MAVEN)
    moved_head = _checkout(repo, expectation["commit"])
    _ensure_compiled(repo, force=moved_head, module=module, maven=maven, jdk=expectation.get("jdk"))
    _analyze_and_render(module)

    metadata = json.loads((module / ".sextant" / "metadata.json").read_text(encoding="utf-8"))
    if metadata["endpoints"] != expectation["endpoints"]:
        problems.append(
            f"endpoint counts: expected {expectation['endpoints']!r}, got {metadata['endpoints']!r}"
        )

    markdown = (module / ".sextant" / "render" / "architecture.md").read_text(encoding="utf-8")
    inbound = _routes_in_section(markdown, "Inbound endpoints")
    outbound = _routes_in_section(markdown, "Outbound endpoints")
    if inbound != expectation["routes"]["inbound"]:
        problems.append(
            f"inbound routes: expected {expectation['routes']['inbound']!r}, got {inbound!r}"
        )
    if outbound != expectation["routes"]["outbound"]:
        problems.append(
            f"outbound routes: expected {expectation['routes']['outbound']!r}, got {outbound!r}"
        )

    # F7 §8.2 (W30). What the shipped `terminals` rules actually classified, as
    # `{"<kind>/<target>": count}` plus the corpus's own total, compared whole.
    #
    # **This is the only thing that checks a shipped terminal rule at all**, which is
    # what W30's review found: `grep -rn terminals tests/` reaches not one of
    # `spring-web.yml`'s twelve rows. Every unit test invents its own annotation and its
    # own base type, deliberately — a rule read from catalog data is only proved to be
    # read from catalog data if the data is not the real spellings — and the cost of that
    # is exactly this gap. A typo in `org.mybatis.spring.annotation.MapperScan` or in
    # `org.springframework.data.jpa.repository.JpaRepository` is not INVALID, so nothing
    # refuses it; it is simply inert, with no error, no COVERAGE row and every test green.
    # GUIDELINES §10 names that shape: "could a change to it be WRONG without being
    # INVALID?"
    #
    # Here it moves a number. `mall-admin` is the pin that covers the scanned-package
    # route and the one `cache` rule, `jhipster-sample-app` the supertype route, and
    # `spring-petclinic-rest` the owner route — one corpus per route, which is how the
    # routes were chosen in the first place.
    expected_terminals = expectation.get("terminal_kinds")
    if expected_terminals is not None:
        counted = _terminal_kinds(module)
        if counted != expected_terminals:
            problems.append(
                f"terminal kinds: expected {expected_terminals!r}, got {counted!r} — this "
                f"is what the shipped `terminals` rules classify, and nothing else checks "
                f"that they name types the frameworks really declare"
            )

    # F7 §8.3 (W32). How many call sites dispatch to SEVERAL bodies with none picked, and
    # how many of them a trace actually reaches — the second being what appears in the
    # rendered document as an `alt` block.
    #
    # **Pinned because the claim that was NOT pinned turned out to be wrong.** W32's plan
    # row said this shape "has never fired on real code (four corpora, zero occurrences)";
    # it fires 34 times on `spring-petclinic-rest`, every one a repository interface
    # narrowing to a JDBC implementation and a JPA one, and the diagram drew them as a
    # sequence. An unpinned corpus number in a document is a number that rots.
    expected_narrowed = expectation.get("narrowed_sites")
    if expected_narrowed is not None:
        counted = _narrowed_sites(module)
        if counted != expected_narrowed:
            problems.append(
                f"narrowed sites: expected {expected_narrowed!r}, got {counted!r} — this "
                f"is the shape F7 §8.3's `alt` blocks are drawn for, and the last time it "
                f"went unpinned a plan row claimed it never occurred"
            )

    # F3 §4.2 (W21). OPTIONAL, because it is a property of the upstream's own source
    # rather than of Sextant's output, and only the pin that motivated Wave 3 records
    # one. It is checked here because it is the number that made the corpus worth
    # adding: `spring-petclinic-rest` makes 131 calls whose OWNER it scans, naming a
    # method that owner does not declare but a scanned ancestor does. The always-on
    # fixture scored ZERO of them before W21, which is why the suite could pass while
    # neither of Wave 3's Criticals had anywhere to appear.
    #
    # It re-scans the module rather than reading the workspace `analyze` just wrote,
    # which is a real cost and a real caveat: a pin using `.sextant.yml` ignore rules or
    # multi-release selection would count documents the pipeline excludes. No pinned
    # corpus does today — `spring-petclinic-rest` ships no `.sextant.yml` — and this
    # note is the condition under which that stops being true.
    #
    # A DROP here means the shape has left the corpus and the resolution work is being
    # measured against nothing; a RISE means upstream drift the pinned commit was
    # supposed to prevent. Either is worth stopping for.
    expected_shape = expectation.get("resolvable_superclass_calls")
    if expected_shape is not None:
        # Imported HERE, not at module scope. `_sextant_bin` exists so this script
        # shells out to the venv rather than importing the package, and the Usage line
        # says `python scripts/field_check.py` — a top-level `import sextant` would kill
        # that invocation outside the venv, for a check only one pin asks for.
        from corpus_shapes import resolvable_superclass_calls

        counted = len(resolvable_superclass_calls(module / "target" / "classes"))
        if counted != expected_shape:
            problems.append(
                f"resolvable superclass calls: expected {expected_shape}, got {counted} "
                f"— this is the shape F3 §4.2's resolution work is measured against"
            )

    html_text = (module / ".sextant" / "render" / "architecture.html").read_text(encoding="utf-8")
    if not _zero_pre_outside_code_blocks(html_text):
        problems.append("a <pre> outside a code block or a diagram survived in architecture.html")
    if not _first_diagram_parses(html_text):
        problems.append("the first diagram carries an unquoted `$` outside any backtick span")

    return problems


def main(argv: list[str]) -> int:
    names = argv or sorted(path.stem for path in EXPECTATIONS_DIR.glob("*.json"))
    if not names:
        print(f"no expectation files under {EXPECTATIONS_DIR}", file=sys.stderr)
        return 1
    failed = False
    for name in names:
        print(f"== {name} ==")
        try:
            problems = _check_one(name)
        except FieldCheckFailure as failure:
            print(f"  FAILED: {failure}")
            failed = True
            continue
        if problems:
            failed = True
            for problem in problems:
                print(f"  FAILED: {problem}")
        else:
            print("  ok")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
