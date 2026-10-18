"""CP-37 — how large the operand PRODUCT actually gets (spec 2026-10-18 §4).

§4 declares no cap and says why: the product is over HOLES — the recipe's hole count,
which is small — while the answers per hole are what can be large. It also says the
decision waits on a measurement "over all corpora PLUS Apollo", and this is that
measurement. Per `_joined` call it counts two things:

* **combinations** — the exact number of candidate strings the product enumerates,
  before coherence filtering;
* **answers** — what `_joined` returns, after `_combine` dropped the incoherent
  combinations and `dict.fromkeys` deduplicated the rest.

Counted by replacing `values.product` and wrapping `values._Walk._joined`, so every
number is the shipped code's own rather than a re-implementation of it.

**Why the 685-path position is not by itself an alarm.** `apollo-portal` reaches 685 paths
at one position (`measure_value_walk.py`, 2026-10-18), 18x the previous estate-wide max of
11. Paths are not candidates: a hole contributes one candidate per path on which it reached
a `string` LITERAL, and a position with 685 paths that resolves to a literal on none of them
contributes exactly one — the hole itself. Measuring that distinction is the point.

Run: `.venv/bin/python scripts/probes/cp37_join_product/product_sizes.py [corpus ...]`
"""

import sys
import tempfile
from importlib.metadata import version
from itertools import product as _itertools_product
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src"))

from measure_value_walk import CATALOGS, _workspace, corpora

from sextant.application.resolve import values as V
from sextant.application.resolve.effective_calls import effective_call_sites
from sextant.application.resolve.shadow import asks_of, positions_asked
from sextant.ingress.catalogs.yaml_source import YamlCatalogSource

COMBINATIONS: list[tuple[str, int]] = []
ANSWERS: list[tuple[str, int]] = []
_template = [""]


def _counting_product(*lists):  # type: ignore[no-untyped-def]
    size = 1
    for one in lists:
        size *= len(one)
    COMBINATIONS.append((_template[0], size))
    return _itertools_product(*lists)


_joined = V._Walk._joined


def _counting_joined(self, template, argument, method, origin, trail, frames):  # type: ignore[no-untyped-def]
    _template[0] = template
    answered = _joined(self, template, argument, method, origin, trail, frames)
    ANSWERS.append((template, 0 if answered is None else len(answered)))
    return answered


V.product = _counting_product  # type: ignore[attr-defined]
V._Walk._joined = _counting_joined  # type: ignore[method-assign]


def main(argv: list[str]) -> int:
    # **The identity comes from the run, never from a parameter** (GUIDELINES §5.4, the
    # CP-5 failure). What this probe measures is Sextant's OWN join arm, so the
    # configuration a cell is attributed to is the Sextant distribution this interpreter
    # actually imported — read out of its installed metadata here, before anything is
    # measured, and printed as the table's column header.
    measured_version = version("sextant")
    print(f"sextant {measured_version} — as the installed distribution reports itself")
    catalogs = YamlCatalogSource(CATALOGS).load()
    available, _ = corpora()
    chosen = [(n, r) for n, r in available if not argv or n in argv]
    print(f"{'corpus':24s} {'joins':>6s} {'combos max':>11s} {'answers max':>12s}  worst template")
    for name, root in chosen:
        COMBINATIONS.clear()
        ANSWERS.clear()
        with tempfile.TemporaryDirectory() as into:
            try:
                workspace = _workspace(root, Path(into), catalogs)
            except (OSError, RuntimeError, duckdb.Error) as problem:
                print(f"{name:24s} {'—':>6s} {'—':>11s} {'—':>12s}  {problem.__class__.__name__}")
                continue
            sites = effective_call_sites(workspace)
            asks = [ask for catalog in catalogs for ask in asks_of(catalog)]
            index = V.value_index(workspace)
            for position in set(positions_asked(sites, asks)):
                site = index.sites.get((position.caller, position.ordinal))
                if site is not None:
                    V._Walk(index, ()).at(site, position.slot)
            workspace.close()
        if not ANSWERS:
            continue
        worst = max(COMBINATIONS, key=lambda row: row[1], default=("—", 0))
        print(
            f"{name:24s} {len(ANSWERS):6d} {worst[1]:11d} "
            f"{max(size for _, size in ANSWERS):12d}  {worst[0]!r}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
