"""Every `identified_by` entry `value-models/` ships carries its probe row
(spec 2026-09-22 §7b; D02 §1f; GUIDELINES §5.4).

## The defect this closes before it happens

§7b names the second risk of the value-resolution design in as many words:
`value-models/` becomes a dumping ground — entries accumulate because adding one
is easy, and nobody measures whether the framework really identifies that value
that way. An entry here is a standing claim that *this argument of this call is
the value its result stands for*, made once and read by every catalog at once,
which is exactly the property that makes an unmeasured one expensive: it is not
one framework's mistake, it is the estate's.

So this file is `test_catalog_measurement_coverage.py` applied one directory
along, and deliberately not a second mechanism. A `measured:` row cites a
committed probe in `by:` and that probe states the `**Version scope…**`
paragraph §5.4 makes every verdict in it bounded by; an `identified_by` entry
cites a committed probe in `by:` and the same paragraph bounds it.

## Why `by:` alone, where a catalog writes a whole `measured:` row

A `measured:` row also carries `artifact` (a `groupId:artifactId`), `versions`
and `identity`. The first shipped entry here cannot: `java.net.URI` lives in
`java.base`, which is not a Maven coordinate at all, and the probe that measured
it records the JDK the way a JDK states itself — `$JAVA_HOME/release` and
`javap -version`. Writing a coordinate for it would be a plausible-looking value
nobody can check, which is `A-Mi8`'s own defect wearing a different field name.
What CAN be checked is the same thing `test_every_cited_probe_states_a_version_scope_at_all`
checks: the cited document exists in this repository and bounds itself.

## The split with the loader, and why there is one

The loader refuses an entry that declares no `by:` at all
(`yaml_source._identities`) — a shape check at the edge, where every other shape
check in that file lives, and the one that has to hold for a REPOSITORY'S OWN
catalog set too ([D02](../../docs/components/D02-catalog-schema.md) §6), whose
probes are not in this tree. What this file adds is the half a loader cannot
make: that the path a SHIPPED entry cites is a committed probe here, and that the
probe says what it measured against.

It is OFFLINE and deterministic (NFR-1): it reads committed files and runs
nothing.
"""

import re
from pathlib import Path

import yaml

REPO = Path(__file__).parents[2]
VALUE_MODELS = REPO / "src" / "sextant" / "catalogs" / "value-models"


def declared_identities() -> dict[str, list[dict[str, object]]]:
    """`value model id -> its `identified_by` entries`, read off the directory.

    Enumerated, never listed, for `declared_measurements`' reason: a
    hand-maintained roster drifts, and the one thing this rule must not do is
    stop seeing a file.
    """
    found: dict[str, list[dict[str, object]]] = {}
    for path in sorted(VALUE_MODELS.glob("*.yml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        found[path.stem] = document.get("identified_by") or []
    return found


def _version_scope(document: Path) -> str:
    """The `**Version scope…**` paragraph §5.4 requires a probe to state, read
    exactly as `test_catalog_measurement_coverage._version_scope` reads it."""
    text = document.read_text(encoding="utf-8")
    match = re.search(r"\*\*Version scope[^*]*\*\*(.*?)(?=\n\n)", text, re.DOTALL)
    return match.group(0) if match else ""


def test_an_identity_entry_without_a_probe_row_is_refused():
    """§7b, the shipped half. An entry citing nothing is an entry nobody
    measured, and the directory is one file away from being the dumping ground
    the design named."""
    unsupported: list[str] = []
    for model_id, entries in sorted(declared_identities().items()):
        for index, entry in enumerate(entries):
            by = entry.get("by") if isinstance(entry, dict) else None
            if not isinstance(by, str) or not (REPO / by).is_file():
                unsupported.append(f"{model_id}[{index}]: `by` names no committed file — {by!r}")
    assert unsupported == [], (
        "these `identified_by` entries cite no committed probe (spec §7b):\n"
        + "\n".join(f"  - {line}" for line in unsupported)
        + "\n\nRun a probe against the archive the producing call lives in and cite the "
        "document it wrote. An entry without one is a claim about a framework that nobody "
        "measured, read by every catalog at once."
    )


def test_every_cited_probe_states_a_version_scope_at_all():
    """A citation is only as good as the paragraph it points at — the rule
    `measured:` rows already take. A probe with no version scope bounds nothing,
    so an entry citing it would read as measured while resting on the silence the
    block exists to end."""
    scopeless = sorted(
        {
            str(entry["by"])
            for entries in declared_identities().values()
            for entry in entries
            if isinstance(entry, dict)
            and isinstance(entry.get("by"), str)
            and (REPO / str(entry["by"])).is_file()
            and not _version_scope(REPO / str(entry["by"]))
        }
    )
    assert scopeless == [], (
        f"these cited probes state no `**Version scope…**` paragraph (§5.4): {scopeless}"
    )


def test_the_scan_finds_the_entries_that_ship():
    """A coverage check that discovers nothing passes for the wrong reason: both
    rules above agree with an empty scan, and a renamed directory or a changed
    block name would retire them silently rather than loudly."""
    declared = declared_identities()
    assert declared, "the `identified_by` scan found no file in `catalogs/value-models/`"
    assert any(entries for entries in declared.values()), (
        "every shipped value model declares an empty `identified_by` — the scan sees the "
        "files and not the block it governs"
    )
