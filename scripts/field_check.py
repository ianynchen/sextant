"""Field check: validate Sextant's own output against real, live upstream repositories.

**Opt-in, network-using by nature — never part of the test suite or `scripts/check.sh`**
(2M design §3). It checks out a pinned commit and, when the module is not already built at
it, runs `mvn compile` — which reaches the network for anything not already cached. §5's
beyond-fixture claims are verified only when someone runs this; the fixture pins are the
always-on net.

Each expectation file under `scripts/field-expectations/*.json` PINS the upstream commit
it was recorded against. This script checks out that exact commit before validating, so
upstream drift can never masquerade as a Sextant regression — refreshing a pin (a new
`commit`, and the counts/routes re-recorded against it) is a deliberate, reviewed act, not
something this script does on its own.

Checks, per expectation:

- **Endpoint counts** — `metadata.json`'s own `endpoints` object, compared whole.
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


def _checkout(repo: Path, commit: str) -> None:
    """Pin the upstream working tree to exactly `commit` — the whole point of pinning
    (upstream drift never masquerades as a Sextant regression). A dirty tree or a commit
    this clone does not have is a loud failure, never a silent checkout of whatever is
    closest."""
    head = _run(["git", "rev-parse", "HEAD"], cwd=repo)
    if head.returncode != 0:
        raise FieldCheckFailure(f"{repo} is not a git repository: {head.stderr.strip()}")
    if head.stdout.strip() == commit:
        return
    status = _run(["git", "status", "--porcelain"], cwd=repo)
    if status.stdout.strip():
        raise FieldCheckFailure(
            f"{repo} has uncommitted changes; refusing to check out the pinned "
            f"commit {commit} over them"
        )
    checkout = _run(["git", "checkout", "--quiet", commit], cwd=repo)
    if checkout.returncode != 0:
        raise FieldCheckFailure(
            f"could not check out {repo}'s pinned commit {commit}: {checkout.stderr.strip()}"
        )


def _ensure_compiled(repo: Path) -> None:
    """`target/classes` populated at the checked-out commit — the compiled-first reading
    `MavenDetector` requires (it never runs Maven itself). Skipped when `target/classes`
    already exists: `_checkout` already proved the tree is at the pinned commit, and a
    field run against an already-built checkout (the ordinary case between two runs of
    this script) should not pay a full rebuild every time. Delete `target/` to force one.
    Offline first (`-o`), the same posture the detectors themselves default to; only
    retried without it — reaching the network — when the offline attempt fails, since this
    script is explicitly allowed to (network-using by nature, see the module docstring)."""
    if (repo / "target" / "classes").is_dir():
        return
    offline = _run(["./mvnw", "-q", "-o", "compile"], cwd=repo)
    if offline.returncode == 0:
        return
    online = _run(["./mvnw", "-q", "compile"], cwd=repo)
    if online.returncode != 0:
        raise FieldCheckFailure(
            f"`mvn compile` failed in {repo} even with the network allowed:\n"
            f"{online.stdout}\n{online.stderr}"
        )


def _analyze_and_render(repo: Path) -> None:
    sextant = _sextant_bin()
    analyze = _run([sextant, "module", "analyze", str(repo)], cwd=REPO_ROOT)
    if analyze.returncode != 0:
        raise FieldCheckFailure(
            f"`sextant module analyze {repo}` failed:\n{analyze.stdout}\n{analyze.stderr}"
        )
    render = _run([sextant, "module", "render", str(repo)], cwd=REPO_ROOT)
    if render.returncode != 0:
        raise FieldCheckFailure(
            f"`sextant module render {repo}` failed:\n{render.stdout}\n{render.stderr}"
        )


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
    there was nothing to check."""
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
    problems: list[str] = []

    _checkout(repo, expectation["commit"])
    _ensure_compiled(repo)
    _analyze_and_render(repo)

    metadata = json.loads((repo / ".sextant" / "metadata.json").read_text(encoding="utf-8"))
    if metadata["endpoints"] != expectation["endpoints"]:
        problems.append(
            f"endpoint counts: expected {expectation['endpoints']!r}, got {metadata['endpoints']!r}"
        )

    markdown = (repo / ".sextant" / "render" / "architecture.md").read_text(encoding="utf-8")
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

    html_text = (repo / ".sextant" / "render" / "architecture.html").read_text(encoding="utf-8")
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
