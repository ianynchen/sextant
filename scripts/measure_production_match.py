"""How many of the shadow reader's asked sites a CONSUMING matcher would really accept
(spec 2026-09-22 §7a, folded into Task 7 by controller ruling).

## Why this exists, and what it costs to not have it

`resolve/shadow.py` over-matches **on purpose**: it models the keys a catalog spells a
position with — owner where declared, method name, descriptor or arity where the row
declares either — and deliberately not the engines' REACHABILITY. Its own docstring says
why: *"a review that sees more candidates than will ever be published is a review with
slack in it; one that sees fewer is a review with a hole."*

The cost of that slack is that **a shadow figure quoted as a production figure is wrong**,
and Task 5 paid it: it published a protobuf `parseFrom` position as the estate's headline
maximum and then discovered that production's matcher refuses all twelve sites of that
corpus. Tasks 8 and 9 begin the same way Task 7 did — by reading the shadow table — and
will ask the same question about their own engines.

So this script asks the question, and asks it of **production**. Every verdict below comes
from a function `src/` already uses to decide the same thing; nothing here re-states a
matching rule in its own words, because a second statement of a rule is a second answer the
day the first one changes (spec §0a's disease, one level up).

## What is answered, and what is honestly not

A matcher is *reachable* when a production function answers "is this call site the one this
catalog describes" without the engine that owns it being run. Two are, today:

* **`interface_implementation`** — `engines/interface_implementation.accepts_registration`,
  exposed for exactly this (Task 7 migrated that engine, so its matcher is the one whose
  answer can be checked against rows that now exist).
* **`parse_calls`** — `shapes/parse_binding._matches`, over the same `_vocabulary` and
  `_facts` the pass builds. This is the arm Task 5 got wrong, and the arm whose `owner_hierarchy`
  resolution is the reason a key-shaped read cannot stand in for it.

Every other style's matcher is **inline in its engine's own loop** and cannot be called
without running it. Those catalogs are reported as `unanswered` — named, counted, and never
guessed at. A row this script cannot answer is a row a later migration has to answer by
exposing its engine's matcher the way Task 7 exposed one, and the `unanswered` total is the
size of that remaining job.

**`unanswered` is not `refused`.** Reading one as the other is the same mistake in the other
direction, so they are separate columns and no total merges them.

## Reading the output

`asked sites` is the distinct `(caller, ordinal)` pairs the shadow reader matched for that
catalog — sites, not positions: a matcher accepts or refuses a SITE, and one site may carry
several asked slots. A corpus total adds those per catalog, so it counts (catalog, site)
PAIRS and two catalogs asking about one site count twice; the per-row figure is the one to
quote.

`accepted` is what the NAMED matcher takes. **`refused` is not "the engine will never see
this"**, and reading it that way is the mistake this script exists to prevent in the other
direction: a row can be refused by the matcher named and still be consumed by the same
engine through a different route. The three `google-pubsub-subscriber` refusals on
`orders-service` are exactly that — they are the `ProjectSubscriptionName.of` sites, which
the shadow reader matches through the catalog's hop entry and which the engine reaches
through the walk's identity hop rather than through `accepts_registration`. What `refused`
answers is one question only: **would THIS matcher accept this site.** A correction factor
for a quoted shadow figure needs that answer per matcher, not a single estate ratio.

**A catalog with both a `matches` block and a `parse_calls` block is split in two rows**,
because the two blocks are matched by different code. The split is made by asking `asks_of`
twice — once for the catalog as loaded, once for a copy with `parse_calls` emptied — rather
than by re-deciding which key came from where.

Corpus discovery, the workspace build and the `--json` habit are `measure_value_walk.py`'s,
imported rather than copied.

Run:  `.venv/bin/python scripts/measure_production_match.py [--json OUT] [--corpus NAME ...]`
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

from measure_value_walk import CATALOGS, _workspace, corpora

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.effective_calls import effective_call_sites
from sextant.application.resolve.engines.interface_implementation import (
    accepts_registration,
    registration_owners,
)
from sextant.application.resolve.shadow import asks_of, positions_asked
from sextant.application.resolve.shapes.parse_binding import _facts, _matches, _vocabulary
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource

# What a row's verdict came from, printed so a reader can go and read the function. The
# empty string is the honest answer for a style whose matcher lives inside its engine's
# own loop — see the docstring: unanswered is not refused.
_REGISTRATION = "interface_implementation.accepts_registration"
_PARSE = "parse_binding._matches"
_NONE = ""


@dataclass(frozen=True)
class Row:
    corpus: str
    catalog: str
    style: str
    block: str
    matcher: str
    sites: int
    accepted: int

    @property
    def refused(self) -> int:
        return self.sites - self.accepted if self.matcher else 0

    @property
    def unanswered(self) -> int:
        return self.sites if not self.matcher else 0


@dataclass
class Measured:
    corpus: str
    call_sites: int
    rows: list[Row] = field(default_factory=list)


def _sites_asked(catalog: Catalog, sites: list[dict[str, Any]]) -> set[tuple[str, int]]:
    """The distinct `(caller, ordinal)` pairs the SHADOW reader matches for one catalog —
    the production reader, called exactly as `record_value_resolutions` calls it."""
    asks = asks_of(catalog)
    return {(position.caller, position.ordinal) for position in positions_asked(sites, asks)}


def _without_parse_calls(catalog: Catalog) -> Catalog:
    """The same catalog with its `parse_calls` block emptied.

    The split between the two blocks is made by asking `asks_of` twice and subtracting,
    never by re-deciding which key came from where: `asks_of` is the one place that knows,
    and a second opinion here would be a second answer the day it learns a seventh shape.
    """
    return dataclasses.replace(catalog, parse_calls={})


def measure(name: str, workspace: Workspace, catalogs: list[Catalog]) -> Measured:
    sites = [dict(row) for row in effective_call_sites(workspace)]
    by_site = {(str(row["caller"]), int(str(row["ordinal"]))): row for row in sites}
    result = Measured(corpus=name, call_sites=len(sites))
    parse_facts = _facts(workspace)
    parse_calls = _vocabulary(catalogs).calls
    for catalog in catalogs:
        asked = _sites_asked(catalog, sites)
        if not asked:
            continue
        from_matches = _sites_asked(_without_parse_calls(catalog), sites)
        from_parse = asked - from_matches
        if from_matches:
            result.rows.append(_matches_row(name, catalog, sorted(from_matches), by_site))
        if from_parse:
            # Against the WHOLE vocabulary, not this catalog's slice, because that is
            # what production does: `_vocabulary` unions every catalog's block on the
            # stated ground that "a parse means the same thing whoever wrote it down",
            # and `_ParseCall` carries no catalog of its own as a result.
            accepted = sum(
                1
                for key in from_parse
                if any(_matches(by_site[key], entry, parse_facts) for entry in parse_calls)
            )
            result.rows.append(
                Row(
                    corpus=name,
                    catalog=catalog.id,
                    style=catalog.style,
                    block="parse_calls",
                    matcher=_PARSE,
                    sites=len(from_parse),
                    accepted=accepted,
                )
            )
    result.rows.sort(key=lambda row: (row.catalog, row.block))
    return result


def _matches_row(
    corpus: str,
    catalog: Catalog,
    asked: list[tuple[str, int]],
    by_site: dict[tuple[str, int], dict[str, Any]],
) -> Row:
    """One catalog's `matches` asks, against its style's production matcher where one is
    reachable."""
    if catalog.style != "interface_implementation":
        return Row(
            corpus=corpus,
            catalog=catalog.id,
            style=catalog.style,
            block="matches",
            matcher=_NONE,
            sites=len(asked),
            accepted=0,
        )
    owners = registration_owners(catalog)
    method = catalog.matches["registration"]["method"]
    accepted = sum(1 for key in asked if accepts_registration(by_site[key], owners, method))
    return Row(
        corpus=corpus,
        catalog=catalog.id,
        style=catalog.style,
        block="matches",
        matcher=_REGISTRATION,
        sites=len(asked),
        accepted=accepted,
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def report(measured: list[Measured]) -> str:
    lines = [
        "| corpus | call sites | asked sites | answered | accepted | refused | unanswered |",
        "|---|---|---|---|---|---|---|",
    ]
    for one in measured:
        asked = sum(row.sites for row in one.rows)
        answered = sum(row.sites for row in one.rows if row.matcher)
        accepted = sum(row.accepted for row in one.rows)
        refused = sum(row.refused for row in one.rows)
        lines.append(
            f"| `{one.corpus}` | {one.call_sites:,} | {asked:,} | {answered:,} | "
            f"{accepted:,} | {refused:,} | {asked - answered:,} |"
        )
    return "\n".join(lines)


def answered_rows(measured: list[Measured]) -> str:
    """Every row a production matcher answered — the correction factor, per catalog."""
    lines = [
        "| corpus | catalog | block | matcher | asked sites | accepted | refused |",
        "|---|---|---|---|---|---|---|",
    ]
    for one in measured:
        for row in one.rows:
            if not row.matcher:
                continue
            lines.append(
                f"| `{row.corpus}` | `{row.catalog}` | {row.block} | `{row.matcher}` | "
                f"{row.sites} | {row.accepted} | {row.refused} |"
            )
    if len(lines) == 2:
        lines.append("| — | — | — | — | — | — | — |")
    return "\n".join(lines)


def unanswered_styles(measured: list[Measured]) -> str:
    """**The size of what this script cannot answer yet**, by style — a matcher living
    inside its engine's own loop cannot be called without running the engine, and saying so
    is the deliverable's own rule. Each of these closes when the migration that owns the
    engine exposes its matcher, as Task 7 did for `interface_implementation`."""
    per_style: Counter[str] = Counter()
    catalogs: dict[str, set[str]] = {}
    for one in measured:
        for row in one.rows:
            if row.matcher:
                continue
            per_style[row.style] += row.sites
            catalogs.setdefault(row.style, set()).add(row.catalog)
    lines = ["| style | catalogs | asked sites with no reachable matcher |", "|---|---|---|"]
    for style, count in per_style.most_common():
        lines.append(f"| `{style}` | {len(catalogs[style])} | {count:,} |")
    if len(lines) == 2:
        lines.append("| — | — | — |")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=None, help="write every row here")
    parser.add_argument("--corpus", action="append", default=None, help="limit to these")
    arguments = parser.parse_args()

    catalogs = YamlCatalogSource(CATALOGS).load()
    available, skipped = corpora()
    chosen = [
        (name, root)
        for name, root in available
        if arguments.corpus is None or name in arguments.corpus
    ]
    if skipped:
        print(
            f"NOT MEASURED — {len(skipped)} module(s) with no built classes and no scan: "
            + ", ".join(skipped),
            file=sys.stderr,
        )
    measured: list[Measured] = []
    for name, root in chosen:
        started = time.perf_counter()
        with tempfile.TemporaryDirectory() as into:
            workspace = _workspace(root, Path(into), catalogs)
            one = measure(name, workspace, catalogs)
            workspace.close()
        measured.append(one)
        print(
            f"{name:34s} sites={one.call_sites:6,d} "
            f"asked={sum(row.sites for row in one.rows):5,d} "
            f"total={time.perf_counter() - started:6.1f}s",
            file=sys.stderr,
            flush=True,
        )

    print(report(measured))
    print()
    asked = sum(row.sites for one in measured for row in one.rows)
    answered = sum(row.sites for one in measured for row in one.rows if row.matcher)
    accepted = sum(row.accepted for one in measured for row in one.rows)
    print(
        f"**Totals.** {asked:,} (catalog, asked site) PAIRS across {len(measured)} corpora "
        f"— a site two catalogs ask about counts twice, because a verdict is per matcher "
        f"and the two may disagree. {answered:,} were put to a production matcher and "
        f"{accepted:,} accepted ({answered - accepted:,} refused BY THAT MATCHER, which is "
        f"not the same as unconsumed); {asked - answered:,} have no reachable matcher and "
        f"are UNANSWERED, never counted as either."
    )
    print()
    print("### Answered by a production matcher\n")
    print(answered_rows(measured))
    print()
    print("### No reachable matcher — what a later migration has to expose\n")
    print(unanswered_styles(measured))

    if arguments.json is not None:
        arguments.json.write_text(
            json.dumps(
                [
                    {
                        "corpus": one.corpus,
                        "call_sites": one.call_sites,
                        "rows": [
                            {
                                **dataclasses.asdict(row),
                                "refused": row.refused,
                                "unanswered": row.unanswered,
                            }
                            for row in one.rows
                        ],
                    }
                    for one in measured
                ],
                indent=1,
            ),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
