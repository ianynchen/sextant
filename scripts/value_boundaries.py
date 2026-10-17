"""Regenerate COVERAGE.md §3c — which asked positions the value walk cannot answer.

Spec `docs/superpowers/specs/2026-09-22-value-resolution-design.md` §3d: the
`unresolved` vocabulary of §1d "is decoration unless something records it", and
`value_resolutions` is what records it. The same section says COVERAGE's boundary
statements are **generated from that table rather than hand-written**, and this file is
what does it.

## What is generated and what stays prose — stated, because the line matters

A boundary statement in §5 has two halves. One names a FORM a catalog does not read
(`.topic(Function)`, `from(Supplier)`, XML) — framework semantics the table cannot
express, written by whoever measured the framework, and untouched here. The other says
how often a position a catalog DID ask about came back without an answer, and with which
reason. That half is a measurement, it went stale twice in this document's history, and
it is the half this script owns.

So §3c is the generated table the prose must agree with, not a replacement for the prose.

## Why a snapshot rather than a run in `--check`

`--check` runs in `scripts/check.sh`, and the measurement needs the analyser over
eighteen compiled fixtures. So the run and the check are separated the way
`coverage_versions.py` separates reading the catalogs from checking the document:

* `--measure` runs shadow mode over every built fixture and writes the snapshot;
* no flag regenerates the document block from the snapshot;
* `--check` compares the document against the snapshot and fails if they differ.

**The snapshot is therefore only as current as the last `--measure`**, which is why it
records the commit it was taken at and why this module prints that commit into the
document. The alarm for an engine change that MOVES these figures is not here: it is
`tests/application/test_shadow_mode.py`'s `_ASKS_PER_CATALOG`, which fails when any
catalog gains, loses or re-spells a position.

## What the corpus is, and what it is not

Every fixture under `fixtures/` with compiled classes or a committed fact stream —
eighteen of twenty today. The two it skips (`gradle-orders`, `orders-reactor`) are
printed rather than dropped, because a reader comparing one run's catalog list against
another's would otherwise be comparing two different estates without being told.

**The fixtures are not the field.** They are what COVERAGE §5's rows cite, which is why
they are the corpus here, but a reason that never fires on them may fire on real code.
The estate-wide figures live in `docs/research/2026-09-23-value-walk-measurement.md` §4
and this document cites that section rather than keeping a second copy.

Usage:
  python scripts/value_boundaries.py --measure   # re-run the fixtures, refresh the snapshot
  python scripts/value_boundaries.py             # regenerate the block from the snapshot
  python scripts/value_boundaries.py --check     # fail if the block is stale
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "COVERAGE.md"
SNAPSHOT = ROOT / "docs" / "coverage" / "value-boundaries.json"
FIXTURES = ROOT / "fixtures"
SEXTANT = ROOT / ".venv" / "bin" / "sextant"

BEGIN = "<!-- BEGIN GENERATED: value_boundaries -->"
END = "<!-- END GENERATED: value_boundaries -->"

# §1d's closed reason set, in the order §4 of the measurement document ranks them on the
# asked surface. Declared rather than derived from the rows, so a reason that fires
# NOWHERE still gets a column — which is the finding in `cycle`'s case, and a table built
# from the observed keys alone could not show it.
REASONS = ("external", "not_readable", "no_writer", "escapes", "non_enumerable", "cycle")

_CLASSES = "target/classes"
_FACTS = ".sextant/facts"


def corpora() -> tuple[list[Path], list[str]]:
    """The built fixtures, and the buildable ones that are not built.

    The same rule `scripts/measure_value_walk.py::corpora` uses, narrowed to `fixtures/`:
    this table is cited by COVERAGE §5 rows, every one of which names a fixture."""
    found: list[Path] = []
    skipped: list[str] = []
    for root in sorted(FIXTURES.iterdir()):
        if not root.is_dir():
            continue
        if (root / _FACTS).is_dir() or (root / _CLASSES).is_dir():
            found.append(root)
        elif any(root.glob("*.gradle*")) or (root / "pom.xml").is_file():
            skipped.append(root.name)
    return found, skipped


def _rows(fixture: Path) -> list[tuple[str, str, str | None]]:
    """`(catalog, outcome, reason)` for every `value_resolutions` row of one fixture,
    through the CLI the flag is documented on rather than through the stage directly —
    `--shadow`'s own failure mode was a flag that never reached the walk
    (`test_the_shadow_flag_reaches_the_walk_through_the_analyze_stage`), and a harness
    that bypassed the CLI would not have caught it."""
    import duckdb

    with tempfile.TemporaryDirectory() as into:
        workspace = Path(into) / "ws"
        done = subprocess.run(
            [
                str(SEXTANT),
                "module",
                "analyze",
                str(fixture),
                "--workspace",
                str(workspace),
                "--shadow",
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=ROOT,
        )
        if done.returncode != 0:
            raise SystemExit(f"{fixture.name}: analyze failed\n{done.stderr}")
        connection = duckdb.connect(str(workspace / "workspace.duckdb"), read_only=True)
        try:
            return [
                (str(catalog), str(outcome), reason)
                for catalog, outcome, reason in connection.execute(
                    "SELECT catalog, outcome, reason FROM value_resolutions"
                ).fetchall()
            ]
        finally:
            connection.close()


def measure() -> dict[str, object]:
    """Run every built fixture and aggregate per catalog. One fixture's rows are not
    reported on their own: a catalog is read by several fixtures and COVERAGE states its
    boundary once, so the unit here is the CATALOG."""
    found, skipped = corpora()
    answered: Counter[str] = Counter()
    unanswered: dict[str, Counter[str]] = {}
    for fixture in found:
        print(f"{fixture.name:30s} ...", end="", flush=True, file=sys.stderr)
        rows = _rows(fixture)
        print(f" {len(rows):4d} rows", file=sys.stderr)
        for catalog, outcome, reason in rows:
            if outcome == "would_resolve":
                answered[catalog] += 1
            else:
                unanswered.setdefault(catalog, Counter())[str(reason)] += 1
    catalogs = sorted(set(answered) | set(unanswered))
    return {
        "measured_at_commit": subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            cwd=ROOT,
        ).stdout.strip(),
        "fixtures": [fixture.name for fixture in found],
        "not_built": skipped,
        "catalogs": {
            catalog: {
                "would_resolve": answered.get(catalog, 0),
                "unresolved": dict(sorted(unanswered.get(catalog, Counter()).items())),
            }
            for catalog in catalogs
        },
    }


def render(snapshot: dict[str, object]) -> str:
    catalogs: dict[str, dict[str, object]] = snapshot["catalogs"]  # type: ignore[assignment]
    fixtures: list[str] = snapshot["fixtures"]  # type: ignore[assignment]
    not_built: list[str] = snapshot["not_built"]  # type: ignore[assignment]
    totals: Counter[str] = Counter()
    for entry in catalogs.values():
        for reason, count in entry["unresolved"].items():  # type: ignore[union-attr]
            totals[reason] += count
    answered = sum(int(entry["would_resolve"]) for entry in catalogs.values())

    lines = [
        BEGIN,
        "",
        f"Measured over **{len(fixtures)} built fixtures** at `{snapshot['measured_at_commit']}`",
        "by `python scripts/value_boundaries.py --measure`. Not built, so not measured: "
        + (", ".join(f"`{name}`" for name in not_built) if not_built else "none")
        + ".",
        "",
        "| catalog | answered | " + " | ".join(f"`{reason}`" for reason in REASONS) + " |",
        "|---" * (len(REASONS) + 2) + "|",
    ]
    for catalog, entry in catalogs.items():
        unresolved: dict[str, int] = entry["unresolved"]  # type: ignore[assignment]
        cells = [str(unresolved.get(reason, 0)) or "0" for reason in REASONS]
        lines.append(
            f"| `{catalog}` | {entry['would_resolve']} | "
            + " | ".join("—" if cell == "0" else cell for cell in cells)
            + " |"
        )
    lines.append(
        f"| **total** | **{answered}** | "
        + " | ".join(f"**{totals[reason]}**" if totals[reason] else "**—**" for reason in REASONS)
        + " |"
    )
    never = [reason for reason in REASONS if not totals[reason]]
    lines += [
        "",
        "**A dash is a reason that did not fire for that catalog, never a reason that "
        "cannot.** "
        + (
            "Across the whole fixture corpus "
            + ", ".join(f"`{reason}`" for reason in never)
            + (" fires nowhere" if len(never) == 1 else " fire nowhere")
            + " — which is a statement about these fixtures, not about the vocabulary; "
            "`docs/research/2026-09-23-value-walk-measurement.md` §4 has the estate-wide "
            "counts and the six real recursions `cycle` answers."
            if never
            else "Every reason in the set fires somewhere in this corpus."
        ),
        "",
        END,
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--measure",
        action="store_true",
        help="re-run shadow mode over the built fixtures and refresh the snapshot",
    )
    parser.add_argument("--check", action="store_true", help="fail if the document is stale")
    arguments = parser.parse_args()

    if arguments.measure:
        snapshot = measure()
        SNAPSHOT.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {SNAPSHOT.relative_to(ROOT)}", file=sys.stderr)
    if not SNAPSHOT.is_file():
        print(
            f"{SNAPSHOT.relative_to(ROOT)} does not exist — run with --measure first",
            file=sys.stderr,
        )
        return 1
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    current = DOC.read_text(encoding="utf-8")
    if BEGIN not in current or END not in current:
        print(f"{DOC.name} has no {BEGIN} block", file=sys.stderr)
        return 1
    head, rest = current.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    updated = head + render(snapshot) + tail

    if arguments.check:
        if updated != current:
            print(
                f"{DOC.name} §3c is stale — run `python scripts/value_boundaries.py`",
                file=sys.stderr,
            )
            return 1
        print(f"{DOC.name} §3c matches {SNAPSHOT.name}")
        return 0
    DOC.write_text(updated, encoding="utf-8")
    print(f"regenerated {DOC.name} §3c from {SNAPSHOT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
