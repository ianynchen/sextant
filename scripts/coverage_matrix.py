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
    if not c:
        return "·"  # no rows in section 5 at all: not yet enumerated, not known-absent
    if not (c - Counter({"na": c["na"], "unknown": c["unknown"]})):
        return "⚠️" if c["unknown"] else "—"
    lead = "◐ " if c["partial"] or c["shipped"] else ""
    gaps = " ".join(f"{c[t]}{t}" for t in "ABC" if c[t])
    tail = " ⚠️" if c["unknown"] else ""
    return f"{lead}{gaps or '—'}{tail}"


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
