"""Regenerate COVERAGE.md §3a — what we support, and at which versions.

The catalogs are the source of truth: each carries a `measured:` block naming
the artifact and the exact versions its rules were read from. This derives the
table so the document cannot claim a version nobody opened.

**Measured points, not ranges** (ruled 2026-09-07). A version between two
measured ones is UNVERIFIED, not supported: asserting a range is a prediction
about bytecode nobody read, which is what GUIDELINES §8.1 forbids and what
produced several of the defects this plan exists to fix.

Usage: python scripts/coverage_versions.py [--check]
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "COVERAGE.md"
CATALOGS = ROOT / "src" / "sextant" / "catalogs"

BEGIN = "<!-- BEGIN GENERATED: coverage_versions -->"
END = "<!-- END GENERATED: coverage_versions -->"


def _measured() -> tuple[list[tuple[str, str, str]], list[str]]:
    """(catalog, artifact, versions) rows, and the catalogs measuring nothing."""
    rows: list[tuple[str, str, str]] = []
    unmeasured: list[str] = []
    for path in sorted(CATALOGS.glob("*.yml")):
        catalog = yaml.safe_load(path.read_text(encoding="utf-8"))
        entries = (catalog or {}).get("measured") or []
        artifacts: dict[str, set[str]] = {}
        for entry in entries:
            if isinstance(entry, dict) and entry.get("artifact"):
                artifacts.setdefault(entry["artifact"], set()).update(
                    str(version) for version in (entry.get("versions") or [])
                )
        if not artifacts:
            unmeasured.append(path.stem)
            continue
        for artifact, versions in sorted(artifacts.items()):
            rows.append((path.stem, artifact, ", ".join(sorted(versions))))
    return rows, unmeasured


def render() -> str:
    rows, unmeasured = _measured()
    total = len(list(CATALOGS.glob("*.yml")))
    measured_catalogs = total - len(unmeasured)
    out = [
        BEGIN,
        "",
        (
            f"**{measured_catalogs} of {total} catalogs name the artifact and versions their "
            f"rules were read from. {len(unmeasured)} record none.** The second number is a "
            "statement about our RECORD, not about the knowledge: a bound usually exists and "
            "is findable, it has simply never been written down here."
        ),
        "",
        "| Catalog | Artifact | Versions read |",
        "|---|---|---|",
    ]
    previous = None
    for catalog, artifact, versions in rows:
        shown = "" if catalog == previous else f"`{catalog}`"
        previous = catalog
        out.append(f"| {shown} | `{artifact}` | {versions} |")
    out += [
        "",
        (
            "**No `measured:` block.** Not the same as unbounded, and not a claim that these "
            "do not work. Some are bounded by a library SEXTANT ITSELF ships — `grpc-schema` "
            "and `grpc-java` by `grpcio-tools>=1.83.1` and `protobuf>=7.36.1`, "
            "`graphql-schema` by `graphql-core>=3.2.6`, all declared in `pyproject.toml` — so "
            "their version bound is already determinable and merely unrecorded. Others rest "
            "on framework knowledge taken from documentation or source. **Telling those two "
            "apart per catalog is deferred, not impossible**: there is always a way to find "
            "the real version if we want it."
        ),
        "",
        "| Catalog |",
        "|---|",
    ]
    out += [f"| `{name}` |" for name in unmeasured]
    out += ["", END]
    return "\n".join(out)


def main(argv: list[str]) -> int:
    current = DOC.read_text(encoding="utf-8")
    if BEGIN not in current or END not in current:
        print(f"{DOC} has no generated block; add {BEGIN} / {END}", file=sys.stderr)
        return 1
    head, _, tail = current.partition(BEGIN)
    _, _, tail = tail.partition(END)
    updated = head + render() + tail
    if "--check" in argv:
        if updated != current:
            print("COVERAGE.md §3a is stale — run: python scripts/coverage_versions.py")
            return 1
        print("COVERAGE.md §3a matches the catalogs")
        return 0
    DOC.write_text(updated, encoding="utf-8")
    print(f"regenerated §3a from {len(list(CATALOGS.glob('*.yml')))} catalogs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
