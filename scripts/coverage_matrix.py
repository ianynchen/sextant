"""Regenerate the COVERAGE.md matrices (section 2) from the checklist (section 5).

Section 5 is the source of truth: one row per (language, library). This derives the
per-cell tier spread so the matrices cannot drift from the checklist they summarise.

Usage: python scripts/coverage_matrix.py [--check]
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

DOC = Path(__file__).resolve().parent.parent / "docs" / "COVERAGE.md"

# Section 5 heading -> (matrix, column label). Order here is column order.
HTTP_COLUMNS = [
    ("REST inbound", "REST in"),
    ("REST outbound", "REST out"),
    ("SOAP", "SOAP"),
    ("GraphQL", "GraphQL"),
    ("WebSocket", "WebSocket"),
    ("Server-Sent Events", "SSE"),
]
MSG_COLUMNS = [
    ("gRPC", "gRPC"),
    ("Kafka", "Kafka"),
    ("JMS and AMQP", "JMS / AMQP"),
    ("AWS SQS", "SQS"),
    ("Google Cloud Pub/Sub", "Pub/Sub"),
    ("Async and internal boundaries", "Async"),
]

# Row label in section 5 -> matrix rows it feeds.
LANGUAGES = ["Java / Kotlin", "Go", "TypeScript", "JavaScript", "Python", "Rust", "Swift"]
ALIASES = {
    "Java": ["Java / Kotlin"],
    "Kotlin": ["Java / Kotlin"],
    "Go": ["Go"],
    "TS": ["TypeScript", "JavaScript"],
    "Python": ["Python"],
    "Rust": ["Rust"],
    "Swift": ["Swift"],
}


def anchor(heading: str, number: str) -> str:
    slug = re.sub(r"[^a-z0-9 -]", "", f"{number} {heading}".lower()).replace(" ", "-")
    return f"#{slug}"


def classify(cell: str) -> str | None:
    """Reduce a tier cell to one of shipped / A / B / C / na / unknown."""
    text = cell.replace("*", "").replace("`", "").strip()
    if text.startswith("✅"):
        return "shipped"
    if text.startswith("◐"):
        return "partial"
    if text.startswith("⚠️"):
        return "unknown"
    if text.startswith("—") or text == "":
        return "na"
    m = re.match(r"([ABC])(?![A-Za-z])", text)
    return m.group(1) if m else None


def parse(md: str) -> tuple[dict, dict]:
    """Return {(language, heading): Counter} and {heading: number}."""
    counts: dict[tuple[str, str], Counter] = {}
    numbers: dict[str, str] = {}
    section = None
    for line in md.splitlines():
        h = re.match(r"### (5\.\d+) (.+)", line)
        if h:
            numbers[h.group(2)] = h.group(1)
            section = h.group(2)
            continue
        if section is None or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or set(cells[0]) <= {"-", ":"}:
            continue
        lang = cells[0].replace("*", "").strip()
        if lang not in ALIASES:
            continue  # header rows, "Any", and prose rows are skipped by construction
        tier = classify(cells[-1])
        if tier is None:
            continue
        for target in ALIASES[lang]:
            counts.setdefault((target, section), Counter())[tier] += 1
    return counts, numbers


def cell(c: Counter | None) -> str:
    """One matrix cell, in a notation a reader can take at face value.

        ✅                        shipped, nothing outstanding
        ◐ (2 limited)             every library catalogued, 2 with stated limits
        ◐ (4A 3B 4C)              4+3+4 libraries not catalogued at all
        ◐ (2 limited, 4A 3B 4C)   both
        4A 3B                     nothing shipped, these outstanding
        —                         not applicable to this language
        ·                         not enumerated in §5 yet

    **`◐` can never appear alone**, and that is a rule rather than an accident of
    the data: a partial cell is one with something missing, so the bracket carries
    whichever kind of incompleteness caused the glyph. A row that is itself
    partial — "shipped, narrower than the framework's rule" — counts as `limited`;
    a library nobody has catalogued counts in its tier.

    **What this replaces, and why it was wrong.** The lead used to be
    `"◐ " if c["partial"] or c["shipped"]`, which collapsed two different states
    into one glyph: a cell with every row shipped rendered `◐ —` exactly like a
    cell with partial rows. Three Java cells — SOAP, GraphQL, WebSocket — are
    7/7, 5/5 and 3/3 shipped with no gaps at any tier, and all three read `◐ —`.
    The file then carried a paragraph telling readers to take `◐ —` as "the
    stronger of the two markings, not the weaker", which is a defect report
    written as a legend: `◐` is a half-filled circle and reads as half-done to
    anyone, and `—` reads as not-applicable to anyone, so the pair read as
    neither of the things it meant.

    The information needed to write `✅` was in the counter the whole time and
    was thrown away one line before it was used.
    """
    if not c:
        return "·"  # no rows in section 5 at all: not yet enumerated, not known-absent
    if not (c - Counter({"na": c["na"], "unknown": c["unknown"]})):
        return "⚠️" if c["unknown"] else "—"
    tail = " ⚠️" if c["unknown"] else ""
    gaps = " ".join(f"{c[t]}{t}" for t in "ABC" if c[t])
    if not (c["partial"] or c["shipped"]):
        # Nothing shipped: the tiers stand alone, unbracketed, because there is
        # no shipped half for them to qualify.
        return f"{gaps}{tail}"
    if not c["partial"] and not gaps:
        return f"✅{tail}"
    missing = [f"{c['partial']} limited"] if c["partial"] else []
    if gaps:
        missing.append(gaps)
    return f"◐ ({', '.join(missing)}){tail}"


def render(counts, numbers, columns, first_col=None) -> str:
    head = ["Language"] + ([first_col] if first_col else [])
    head += [f"[{label}]({anchor(h, numbers[h])})" for h, label in columns]
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for lang in LANGUAGES:
        row = [f"**{lang}**"]
        if first_col:
            row.append("✅ ASM" if lang == "Java / Kotlin" else "none")
        row += [cell(counts.get((lang, h))) for h, _ in columns]
        out.append("| " + " | ".join(row) + " |")
    return "\n".join(out)


def main() -> int:
    md = DOC.read_text()
    counts, numbers = parse(md)
    http = render(counts, numbers, HTTP_COLUMNS, first_col="Scanner")
    msg = render(counts, numbers, MSG_COLUMNS)

    new = md
    for marker, table in (
        ("2a. Application protocols over HTTP", http),
        ("2b. Messaging and RPC", msg),
    ):
        start = new.index(f"### {marker}")
        tbl_start = new.index("| Language", start)
        tbl_end = new.index("\n\n", tbl_start)
        new = new[:tbl_start] + table + new[tbl_end:]

    if "--check" in sys.argv:
        print("matrices are current" if new == md else "STALE — rerun without --check")
        return 0 if new == md else 1
    DOC.write_text(new)
    print(f"regenerated from {sum(sum(c.values()) for c in counts.values())} checklist rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
