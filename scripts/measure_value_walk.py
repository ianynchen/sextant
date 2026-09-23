"""What the backward value walk COSTS, measured before anything consumes it
(spec 2026-09-22 §3a, Task 4).

§3a's ruling is **no cap in v1, measure first**, and this file is what makes that safe:
`resolve/values.py` ships with no `fan_out` and no `depth` in its reason vocabulary, and
nothing in `src/` calls it until these numbers exist. A cap added on judgement would settle
by default the question the measurement exists to answer, so the harness lives here, outside
the package, and the walk stays unwired.

## What a "position" is here, and why it is not every slot in the corpus

The walk explores only what is ASKED. §3b's own precedent is the shape to check: on
`orders-quarkus`, eight catalogs declared `metadata_from` and **zero** annotation walks ran,
because no catalog owned a row there. So the denominator is not "every argument of every
call site" — it is **every position a shipped catalog actually asks about**, and finding
those is half the measurement.

The shipped catalogs spell a position in six shapes, **found by auditing all 101 files
rather than derived from a grammar**, which is the standing caveat on every count this
prints: a catalog that invents a seventh spelling is missed until this list is re-audited.
The first version of this harness had three of the six and under-counted by 20 positions,
which is how the caveat came to be written down.

* a `methods`/`entries`/`vocabulary` row carrying `arg` or a `<name>_arg` integer beside a
  method name (`single_call`, `combinator`, `interface_implementation`,
  `supertype_dispatch`, `config_join`);
* a `fluent` root/step/terminal carrying `captures: {name: argN}`;
* a NESTED capture, `captures: {channel_link: {bean_via: arg0}}` — the same position, with
  what to do with it afterwards (eleven rows, the `spring-integration-*` catalogs);
* a SUB-OBJECT of a row, carrying slots while the method name stays on the parent:
  `ktor-routing`'s `request_requirement: {kind: header, name_arg: 1, value_arg: 2}` and
  `spring-kafka-message`'s `when: {arg: 0, equals: "kafka_topic"}` (26 occurrences);
* `arg: all_strings` — EVERY positional argument of the call, a varargs array read as its
  own elements. Thirteen rows, all `List.of`/`Arrays.asList`/`Subscriptions.topics` topic
  lists. It is the one spelling where a single catalog row can ask about an unbounded
  number of positions, and it is also this harness's widest over-match — `_indices_of` has
  the measurement and the reason;
* a `call_wrappers`/`record_wrappers` entry carrying a `<name>_ctor_arg` against a wrapper
  `type` — a position on that type's CONSTRUCTOR call, so the method name is `<init>`.
  `payload_ctor_arg: last` is not an index but a rule, and it is resolved per site against
  that site's own argument count. The `_ctor_arg` key is REQUIRED: a `payload_arg` beside
  a `type` is a generic TYPE-ARGUMENT index rather than a call slot, so matching on the
  shape alone would be a wrong answer and not conservative slack (narrowed 2026-09-23,
  Task 5 review round 2; the four nodes that match, and the five slots this row counts,
  are unchanged).

**The reader itself now lives in `src/sextant/application/resolve/shadow.py`** and this
harness imports it (Task 5): §3d's shadow table is written for exactly the positions
measured here, and two copies of "what does a catalog ask" would be two answers the day a
catalog invents a spelling. Every count in this document was reproduced after the move.

**Two bases, and they differ by about a quarter.** An ASK is a distinct (catalog, position)
pair; a POSITION is a distinct `(site, slot)`, which is what the walk is actually run on —
two catalogs asking about one slot is two asks and one walk. Both are printed, per corpus
and in total, because quoting one against the other is the easy mistake here. Every COST
figure is per position.

A row is matched to real call sites on the keys the engines match on — the owner (where the
row or an enclosing node declares one, converted through the catalogs' own
`catalog_symbols`), the method name, and the JVM `descriptor` or the `arity` where the row
declares either. **What it does NOT model is the engines' REACHABILITY**, and two classes of
row are therefore over-matched:

1. a row declaring NO owner (`fluent`'s owner-free steps, whose real scope is a chain the
   engine has already rooted; `ktor-routing`'s `request_reads`, whose receiver comes through
   a `via` call) is matched by method name alone — 23 of 802 rows;
2. a `channel_via` row, which an engine reaches only by following a `source` link back from
   a site it has already matched, is matched here against every call site in the estate —
   the 13 `all_strings` rows, and `_indices` has the measurement.

Both are WIDER than the engine's own, deliberately, and both are the safe direction: this
measurement sizes a ceiling, so over-counting the asks can only make the answer more
conservative. It also means the asked surface reported here is an upper bound on the one
production will present, not an estimate of it.

## What is measured, and against what

**Against real sites only.** `resolve_site` uses the row it is handed only to NAME the site;
it resolves the PROJECTED row for that `(caller, ordinal)` pair. A synthesised row would be
silently replaced by the workspace's own, so every position here comes from
`effective_call_sites` — the rows the engines see — and nothing is invented.

Per position, from the walk's own return value (a tuple of `(path, answer)` pairs):

* **path count** — how many coherent paths reached it;
* **hop depth** — crossings on the longest of those paths;
* **answer count** — DISTINCT answers, which is not the path count: two callers passing the
  same literal are two paths and one answer;
* **positions visited** — every `(position, path)` the walk computed on the way, which is
  the work a cap would bound;
* **wall time**.

Per SITE, additionally, `resolve_site` itself is timed and its `Binding` count recorded —
because §3b's "potentially unbounded and multiplicative" is about the COMBINATION step, and
a per-position measurement alone would miss it.

**The INDEX FOLD is timed beside both, and printed as a headline rather than a footnote.**
`value_index` folds five queries; `resolve_site` rebuilds it whenever a caller does not
pass one, and there is no cache — `Workspace.once` refuses this fold, because two of the
five are derived. On `mall-admin` the fold costs more than walking every position in the
corpus, so a report that timed only the walk would describe the cheap half.

The walk's memo is per resolve and shared across one site's slots, so the harness builds one
`_Walk` per site and times each slot inside it. That is the production lifetime, not a
friendlier one.

## Reporting

**Distribution, maximum and tail — never the mean** (§3a step 2). A mean hides the
pathological module, which is the only thing this measurement is for. The script prints
percentiles, the worst individual positions BY NAME, the worst SITES by binding count, and
the `unresolved` reason distribution — a reason nothing produces on real code is either
dead vocabulary or a gap in the corpus, and the report has to say which.

**Wall time is printed and is never a maximum.** At these magnitudes one position varies by
more than 10x between runs on identical input (measured: a 128-path position read 33 ms
once and 1 ms the next time). **`visits` — the `(position, path)` pairs computed — is
identical to the row across runs**, and it is the figure to compare, to rank the tail by,
and to bound if anything is ever bounded. Every wall-time column here is labelled noisy.

Run:  `.venv/bin/python scripts/measure_value_walk.py [--json OUT] [--corpus NAME ...]`
"""

from __future__ import annotations

import argparse
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

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.scanner import ScanRequest
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.call_edges import record_call_edges
from sextant.application.resolve.effective_calls import effective_call_sites
from sextant.application.resolve.return_flow import record_return_flows
from sextant.application.resolve.shadow import Position, asks_of, positions_asked
from sextant.application.resolve.values import (
    RECEIVER,
    UNRESOLVED,
    ValueIndex,
    _Walk,
    resolve_site,
    value_index,
)
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource
from sextant.ingress.extract.jvm.scanner import AsmScanner
from sextant.resources import extractor_jar
from sextant.storage.duckdb.workspace import DuckDbWorkspace

CATALOGS = REPO / "src" / "sextant" / "catalogs"

# A corpus is a directory that already holds a full scan (`.sextant/facts`, which includes
# the dependency jars the scan read) or a compiled `target/classes` this harness scans
# itself. The facts directory is preferred wherever one exists: it is the corpus as the
# product actually sees it, and for `mall-admin` it is the 48 MB / 648-document scan §3a
# names as the largest available.
_FACTS = Path(".sextant") / "facts"
_CLASSES = Path("target") / "classes"


def corpora() -> tuple[list[tuple[str, Path]], list[str]]:
    """Every fixture that compiles, plus every example with a scan — `mall-admin` among
    them. Sorted by name so a run's order is stable (NFR-1's habit, in a script).

    **The set depends on what is BUILT, so the skipped ones are returned beside it and
    printed.** A module with no `target/classes` and no `.sextant/facts` is silently not
    measured otherwise, and a reader comparing a later run's corpus count against this
    one's would be comparing two different estates without being told. Priming them is
    `python tests/fixture_build.py` and an analysis run over `examples/`."""
    found: list[tuple[str, Path]] = []
    skipped: list[str] = []
    for parent in (REPO / "fixtures", REPO / "examples", REPO / "examples" / "mall"):
        if not parent.is_dir():
            continue
        for root in sorted(parent.iterdir()):
            if not root.is_dir() or root.name == "mall":
                continue
            if (root / _FACTS).is_dir() or (root / _CLASSES).is_dir():
                found.append((root.name, root))
            elif any(root.glob("*.gradle*")) or (root / "pom.xml").is_file():
                skipped.append(root.name)
    return found, skipped


# ---------------------------------------------------------------------------
# What a catalog asks about
# ---------------------------------------------------------------------------
#
# **Read by `resolve/shadow.py`, not by this file.** It was written here for Task 4,
# when nothing in `src/` was allowed to change — §3a's gate is that the walk ships
# unwired and the measurement happens first. Task 5's shadow mode needs exactly the
# same question answered (§3d: the table is written only for positions a catalog asked
# about), so the reader moved into the package and this harness imports it. Two copies
# of "what does a catalog ask" would be two answers the day a catalog invents a seventh
# spelling, which is the disease §0a records. Behaviour is unchanged: the module there
# carries the same six shapes, the same two over-matches and the same caveat, and this
# script's numbers are what they were.

# ---------------------------------------------------------------------------
# The measurement
# ---------------------------------------------------------------------------


class _Counting(_Walk):
    """The walk, counting the `(position, path)` pairs it computes.

    The count is the work a `fan_out` or `depth` cap would bound, and it is not the path
    count: a position reached twice on two paths is two computations and may still be one
    answer. Subclassed here rather than instrumented in `values.py` — §3a's gate is that
    nothing in `src/` changes for this."""

    def __init__(self, index: ValueIndex) -> None:
        super().__init__(index)
        self.visits = 0

    def _compute(self, position: Any, trail: Any, frames: Any) -> Any:
        self.visits += 1
        return super()._compute(position, trail, frames)


@dataclass
class Measured:
    corpus: str
    call_sites: int
    value_edges: int
    asks: int
    # TWO bases, because they are different numbers and a reader comparing one against the
    # other would be wrong by roughly a factor of two. `pairs` counts distinct (catalog,
    # position): two catalogs asking about one slot are two asks, and it is the number the
    # per-catalog and per-style tables add up to. `positions` counts distinct (site, slot)
    # — the walks that actually run, since the walk is asked once per position whoever
    # asked. Every cost figure is per position; `pairs` answers "how much do catalogs ask"
    # and never "how much does it cost".
    pairs: int
    positions: int
    sites: int
    index_seconds: float
    rows: list[dict[str, Any]] = field(default_factory=list)
    site_rows: list[dict[str, Any]] = field(default_factory=list)
    reasons: Counter[str] = field(default_factory=Counter)
    kinds: Counter[str] = field(default_factory=Counter)


def every_position(sites: list[dict[str, Any]]) -> list[Position]:
    """EVERY slot of every call site — the ceiling if the ask surface were unlimited.

    Not what §3a asks for, and measured beside it rather than instead of it. The asked
    surface is what the walk will really be given, but a ruling on a cap wants to know
    whether the corpus HOLDS a pathological shape at all, or merely fails to ask about
    one. A cap sized on the asked surface alone would be re-litigated by the first
    catalog that asks somewhere new.

    The RECEIVER is a slot here, as it is to the walk (`values._slots_of`): it is where a
    chain of calls on one value lives, so a ceiling that left it out would leave out the
    deepest shape in the corpus."""
    found: list[Position] = []
    for site in sites:
        caller, ordinal = str(site["caller"]), int(str(site["ordinal"]))
        for slot in range(len(site["arguments"] or [])):
            found.append(Position("*", caller, ordinal, slot))
        if site.get("receiver") is not None or site.get("receiver_parameter") is not None:
            found.append(Position("*", caller, ordinal, RECEIVER))
    return found


def measure(
    name: str, workspace: Workspace, catalogs: list[Catalog], all_slots: bool = False
) -> Measured:
    sites = effective_call_sites(workspace)
    asks = [ask for catalog in catalogs for ask in asks_of(catalog)]
    positions = every_position(sites) if all_slots else positions_asked(sites, asks)
    started = time.perf_counter()
    index = value_index(workspace)
    index_seconds = time.perf_counter() - started

    by_site: dict[tuple[str, int], list[Position]] = {}
    for position in positions:
        by_site.setdefault((position.caller, position.ordinal), []).append(position)

    result = Measured(
        corpus=name,
        call_sites=len(sites),
        value_edges=len(workspace.query("value_edges")),
        asks=len(asks),
        pairs=len(set(positions)),
        positions=len({(p.caller, p.ordinal, p.slot) for p in positions}),
        sites=len(by_site),
        index_seconds=index_seconds,
    )
    for (caller, ordinal), asked in by_site.items():
        site = index.sites.get((caller, ordinal))
        if site is None:
            continue
        walk = _Counting(index)
        for slot in dict.fromkeys(position.slot for position in asked):
            before = walk.visits
            started = time.perf_counter()
            reached = walk.at(site, slot)
            seconds = time.perf_counter() - started
            answers = {
                (answer.kind, str(answer.value), answer.literal_kind, answer.reason)
                for _, answer in reached
            }
            for _, answer in reached:
                result.kinds[answer.kind] += 1
                if answer.kind == UNRESOLVED and answer.reason is not None:
                    result.reasons[answer.reason] += 1
            result.rows.append(
                {
                    "catalogs": sorted({p.catalog for p in asked if p.slot == slot}),
                    "caller": caller,
                    "ordinal": ordinal,
                    "slot": slot,
                    "paths": len(reached),
                    "depth": max((len(trail) for trail, _ in reached), default=0),
                    "answers": len(answers),
                    "visits": walk.visits - before,
                    "seconds": seconds,
                }
            )
        started = time.perf_counter()
        bindings = resolve_site(workspace, site, index)
        result.site_rows.append(
            {
                "caller": caller,
                "ordinal": ordinal,
                "slots": len(dict.fromkeys(position.slot for position in asked)),
                "bindings": len(bindings),
                "seconds": time.perf_counter() - started,
            }
        )
    return result


def _workspace(root: Path, into: Path, catalogs: list[Catalog]) -> DuckDbWorkspace:
    """A FRESH workspace for one corpus: facts in, then the two passes `value_edges` is
    normalised out of. Nothing else in the pipeline is run — the edge query reads
    `call_sites`, `return_flows` and `call_edges`, and the walk reads `method_returns`
    beside them, so an endpoint derivation would only add time to the measurement."""
    facts = root / _FACTS
    if not facts.is_dir():
        facts = into / "facts"
        AsmScanner(extractor_jar()).scan(
            ScanRequest(
                module_id=f"measure:{root.name}",
                coordinates=f"measure/{root.name}",
                version="0",
                classes_dir=root / _CLASSES,
                out_dir=facts,
            )
        )
    workspace = DuckDbWorkspace(into / "workspace.duckdb")
    workspace.load_facts(facts)
    record_return_flows(workspace)
    record_call_edges(workspace, catalogs)
    return workspace


# ---------------------------------------------------------------------------
# Reporting: distribution, maximum and tail — never the mean
# ---------------------------------------------------------------------------


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round(fraction * (len(ordered) - 1)))
    return ordered[index]


def _distribution(values: list[float]) -> dict[str, float]:
    return {
        "p50": percentile(values, 0.50),
        "p90": percentile(values, 0.90),
        "p99": percentile(values, 0.99),
        "max": max(values) if values else 0.0,
    }


def report(measured: list[Measured]) -> str:
    """The per-corpus tables.

    **`index s` is a headline column and not a footnote.** `value_index` folds five
    queries, and `resolve_site` rebuilds it whenever a caller does not pass one — there is
    no cache anywhere, and `Workspace.once` refuses this fold because two of the five are
    derived. On `mall-admin` it costs more than every walk in the corpus put together, so
    a report that showed only the walking would describe the cheap half.

    **Wall time is printed but never called a maximum.** At these magnitudes a single
    position varies by more than 10x between runs on identical input; `visits` — the
    `(position, path)` pairs computed — is the same to the row every time, and is the
    figure to compare or to bound."""
    lines: list[str] = []
    lines.append(
        "| corpus | call sites | value edges | asks | positions | sites | "
        "index fold s | walk s | resolve_site s |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for one in measured:
        total = sum(row["seconds"] for row in one.rows)
        resolved = sum(row["seconds"] for row in one.site_rows)
        lines.append(
            f"| `{one.corpus}` | {one.call_sites:,} | {one.value_edges:,} | {one.pairs:,} | "
            f"{one.positions:,} | {one.sites:,} | {one.index_seconds:.3f} | "
            f"{total:.3f} | {resolved:.3f} |"
        )
    lines.append("")
    lines.append(
        "| corpus | paths p50/p90/p99/max | depth p50/p90/p99/max | "
        "answers p99/max | visits p99/max | bindings max | slowest position s (noisy) |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for one in measured:
        if not one.rows:
            lines.append(f"| `{one.corpus}` | — | — | — | — | — | — |")
            continue
        paths = _distribution([row["paths"] for row in one.rows])
        depth = _distribution([row["depth"] for row in one.rows])
        answers = _distribution([row["answers"] for row in one.rows])
        visits = _distribution([row["visits"] for row in one.rows])
        seconds = _distribution([row["seconds"] for row in one.rows])
        bindings = max((row["bindings"] for row in one.site_rows), default=0)
        lines.append(
            f"| `{one.corpus}` | {paths['p50']:.0f}/{paths['p90']:.0f}/"
            f"{paths['p99']:.0f}/{paths['max']:.0f} | "
            f"{depth['p50']:.0f}/{depth['p90']:.0f}/{depth['p99']:.0f}/{depth['max']:.0f} | "
            f"{answers['p99']:.0f}/{answers['max']:.0f} | "
            f"{visits['p99']:.0f}/{visits['max']:.0f} | {bindings} | {seconds['max']:.4f} |"
        )
    return "\n".join(lines)


def worst(measured: list[Measured], key: str, count: int = 12) -> str:
    rows = [(one.corpus, row) for one in measured for row in one.rows]
    rows.sort(key=lambda entry: entry[1][key], reverse=True)
    lines = [
        "| corpus | position | catalogs | paths | depth | answers | visits | seconds |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for corpus, row in rows[:count]:
        caller = str(row["caller"]).rsplit(" ", 1)[-1]
        lines.append(
            f"| `{corpus}` | `{caller}`@{row['ordinal']} slot {row['slot']} | "
            f"{', '.join(row['catalogs'])} | {row['paths']} | {row['depth']} | "
            f"{row['answers']} | {row['visits']} | {row['seconds']:.4f} |"
        )
    return "\n".join(lines)


def worst_sites(measured: list[Measured], count: int = 8) -> str:
    """The sites `resolve_site` returns the most bindings for — the number an engine
    actually receives, and the one the combination can inflate."""
    rows = [(one.corpus, row) for one in measured for row in one.site_rows]
    rows.sort(key=lambda entry: entry[1]["bindings"], reverse=True)
    lines = [
        "| corpus | site | slots | bindings | seconds (noisy) |",
        "|---|---|---|---|---|",
    ]
    for corpus, row in rows[:count]:
        caller = str(row["caller"]).rsplit(" ", 1)[-1]
        lines.append(
            f"| `{corpus}` | `{caller}`@{row['ordinal']} | {row['slots']} | "
            f"{row['bindings']} | {row['seconds']:.4f} |"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=None, help="write every row here")
    parser.add_argument("--corpus", action="append", default=None, help="limit to these")
    parser.add_argument(
        "--all-slots",
        action="store_true",
        help="every slot of every call site, not only what a catalog asks about",
    )
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
            one = measure(name, workspace, catalogs, arguments.all_slots)
            workspace.close()
        measured.append(one)
        print(
            f"{name:34s} sites={one.call_sites:6,d} positions={one.positions:6,d} "
            f"fold={one.index_seconds:6.3f}s "
            f"walk={sum(row['seconds'] for row in one.rows):7.3f}s "
            f"total={time.perf_counter() - started:6.1f}s",
            file=sys.stderr,
            flush=True,
        )

    print(report(measured))
    print()
    asked = sum(one.pairs for one in measured)
    positions = sum(one.positions for one in measured)
    print(
        "**Totals.** index fold "
        f"{sum(one.index_seconds for one in measured):.2f}s, "
        f"walk {sum(row['seconds'] for one in measured for row in one.rows):.2f}s, "
        f"`resolve_site` {sum(row['seconds'] for one in measured for row in one.site_rows):.2f}s "
        f"over {positions:,} distinct positions"
        + (f" ({asked:,} catalog-to-position asks)" if asked != positions else "")
        + f" at {sum(one.sites for one in measured):,} sites."
    )
    print()
    print("### Worst positions by path count\n")
    print(worst(measured, "paths"))
    print()
    print("### Worst positions by positions visited (the deterministic work figure)\n")
    print(worst(measured, "visits"))
    print()
    print("### Worst sites by binding count — the combination, which is what an engine pays\n")
    print(worst_sites(measured))
    print()
    print("### `unresolved` reasons\n")
    reasons: Counter[str] = Counter()
    kinds: Counter[str] = Counter()
    for one in measured:
        reasons.update(one.reasons)
        kinds.update(one.kinds)
    for reason, count in reasons.most_common():
        print(f"- `{reason}`: {count:,}")
    print()
    for kind, count in kinds.most_common():
        print(f"- answer `{kind}`: {count:,}")

    if arguments.json is not None:
        arguments.json.write_text(
            json.dumps(
                [
                    {
                        "corpus": one.corpus,
                        "call_sites": one.call_sites,
                        "value_edges": one.value_edges,
                        "asks": one.asks,
                        "pairs": one.pairs,
                        "positions": one.positions,
                        "sites": one.sites,
                        "index_seconds": one.index_seconds,
                        "reasons": dict(one.reasons),
                        "kinds": dict(one.kinds),
                        "rows": one.rows,
                        "site_rows": one.site_rows,
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
