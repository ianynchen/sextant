"""The derivation diff (spec 2026-10-22-boundary-vocabulary-and-diff §3, FR-22): two analyses
of one module, joined kind by kind on the vocabulary's identities. It answers "did the
architecture change", never "did the code change" — an endpoint whose controller moved is
the same endpoint, because the wire is the identity and the handler is evidence (§2).

**Refusals come first, on stamps alone (§3c).** Before any row is read: a stamp absent on a
side, a schema or vocabulary version that differs, or two module ids refuse outright; a
Sextant version, catalog hash or redaction rule set that differs refuses unless the caller
allows it, and then the result says `producer_changed` — a fixed dispatch bug or a new
catalog changes rows with no code change, and a diff that mixed the two could not say which
it was reporting (decision 3, §7).

**Both sides are read through the same exit (§3d).** A bundle's `path`/`peer` and
`boundary-property` value were masked at export; a workspace's are verbatim. Each side's
rows pass through the redactor the exporter uses, by the same calls on the same columns, so
a masked bundle and the workspace it came from diff empty, and the diff's own output is
masked. A bundle side passes through unchanged because masking is idempotent. A workspace
records no `redaction_set_hash`; its rows are masked by the redactor given here, so that is
the rule set it is compared under.

Masking can make two identities one — two peers that differ only in userinfo — which is what
the bundle's own grouping already did. Such rows are joined after masking exactly as the
source groups rows: an attribute they disagree on is `{"several": [...]}`, sets are unions,
evidence is the union of both.

**`changed` is attribute-level**: `from`/`to` carry only the attributes that differ. An
endpoint's or dependency's request/response change is labelled by M06 step 3's directional
test read forwards in time: `breaking` where the request gained a required field or the
response lost one, `compatible` otherwise, and `None` where a changed body has no field list
on one side (no body, or `{"several": [...]}`) and nothing else said `breaking`.

One `rows(kind)` per kind per side — fourteen reads — and the join is a dictionary on
identity (§3e).
"""

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Literal, cast

from sextant.application.boundary.source import ROW_KEYS, STAMPS, BoundarySource, _agreed
from sextant.application.boundary.vocabulary import KINDS, Kind
from sextant.domain.redaction import Redactor

Change = Literal["added", "removed", "changed"]
Compatibility = Literal["compatible", "breaking"]

_CHANGES: tuple[Change, ...] = ("added", "removed", "changed")
# A difference here means the two sides do not hold comparable tables: no flag overrides it.
_VERSIONS = ("graph_schema_version", "fact_schema_version", "boundary_vocabulary_version")
# A difference here changes rows with no code change: refused unless allowed, then labelled.
_PRODUCER = ("sextant_version", "catalog_hash", "redaction_set_hash")
# The attributes that are sets, not values: rows joined by masking take their union.
_SETS = ("requirements", "conditions", "headers")
_BODIES = ("request", "response")


class DiffRefused(ValueError):
    """The two sides cannot be compared, and `stamps` names what says so. The facade turns
    it into the api's own error (`api` may name `SextantError`, this layer may not)."""

    def __init__(self, reason: str, stamps: tuple[str, ...]) -> None:
        super().__init__(reason)
        self.stamps = stamps


@dataclass(frozen=True)
class Entry:
    """One identity that is in one side only, or in both with an attribute that differs."""

    kind: str
    change: Change
    identity: dict[str, object]
    from_: dict[str, object] | None
    to: dict[str, object] | None
    evidence: dict[str, object]
    origin: str
    compatibility: Compatibility | None

    def to_json(self) -> dict[str, object]:
        document: dict[str, object] = {
            "kind": self.kind,
            "change": self.change,
            "identity": self.identity,
        }
        if self.from_ is not None:
            document["from"] = self.from_
        if self.to is not None:
            document["to"] = self.to
        document["evidence"] = self.evidence
        document["origin"] = self.origin
        document["compatibility"] = self.compatibility
        return document


@dataclass(frozen=True)
class Diff:
    boundary_vocabulary_version: int
    a: dict[str, object]
    b: dict[str, object]
    producer_changed: bool
    entries: tuple[Entry, ...]
    summary: dict[str, dict[str, int]]

    def to_json(self) -> dict[str, object]:
        """The spec's §3b document, keys in its order."""
        return {
            "boundary_vocabulary_version": self.boundary_vocabulary_version,
            "a": self.a,
            "b": self.b,
            "producer_changed": self.producer_changed,
            "entries": [entry.to_json() for entry in self.entries],
            "summary": self.summary,
        }

    def to_text(self) -> str:
        """The summary table, then one line per entry: a view of `to_json`, never a second
        source."""
        lines = ["| kind | added | removed | changed |", "|---|---|---|---|"]
        for name, counts in self.summary.items():
            lines.append(
                f"| {name} | {counts['added']} | {counts['removed']} | {counts['changed']} |"
            )
        lines.append("")
        for entry in self.entries:
            line = f"- {entry.kind} {entry.change} {json.dumps(entry.identity, sort_keys=True)}"
            if entry.change == "changed" and entry.to is not None:
                line += ": " + ", ".join(entry.to)
            if entry.compatibility is not None:
                line += f" ({entry.compatibility})"
            lines.append(line)
        return "\n".join(lines) + "\n"


def diff_sources(
    a: BoundarySource,
    b: BoundarySource,
    redactor: Redactor,
    *,
    allow_producer_change: bool = False,
) -> Diff:
    """What changed at the boundary from `a` to `b`. `redactor` is the exit's: the module's
    own for a workspace side, the built-ins for two bundles. Raises `DiffRefused`."""
    stamps_a, stamps_b = _stamps(a, redactor), _stamps(b, redactor)
    producer_changed = _refuse_or_allow(a, b, stamps_a, stamps_b, allow_producer_change)
    entries: list[Entry] = []
    for kind in KINDS.values():
        before = _indexed(kind, a.rows(kind), redactor)
        after = _indexed(kind, b.rows(kind), redactor)
        entries.extend(_compared(kind, before, after))
    order = {name: position for position, name in enumerate(KINDS)}
    entries.sort(
        key=lambda e: (
            order[e.kind],
            _CHANGES.index(e.change),
            json.dumps(e.identity, sort_keys=True),
        )
    )
    summary: dict[str, dict[str, int]] = {name: dict.fromkeys(_CHANGES, 0) for name in KINDS}
    for entry in entries:
        summary[entry.kind][entry.change] += 1
    return Diff(
        boundary_vocabulary_version=int(str(stamps_b["boundary_vocabulary_version"])),
        a={"module": a.module_id, "commit": a.commit, "producer": stamps_a},
        b={"module": b.module_id, "commit": b.commit, "producer": stamps_b},
        producer_changed=producer_changed,
        entries=tuple(entries),
        summary=summary,
    )


# --- refusals -----------------------------------------------------------------------------


def _stamps(side: BoundarySource, redactor: Redactor) -> dict[str, object]:
    stamps = dict(side.producer)
    if not side.is_bundle:
        stamps["redaction_set_hash"] = redactor.rule_set_hash
    return stamps


def _refuse_or_allow(
    a: BoundarySource,
    b: BoundarySource,
    stamps_a: dict[str, object],
    stamps_b: dict[str, object],
    allow_producer_change: bool,
) -> bool:
    """Raises for what no flag overrides, then for a producer change unless it is allowed;
    returns whether the producer changed."""
    absent = [
        (name, label)
        for name in STAMPS
        for label, stamps in (("a", stamps_a), ("b", stamps_b))
        if name not in stamps
    ]
    if absent:
        raise DiffRefused(
            "cannot diff: " + "; ".join(f"{name} absent on {label}" for name, label in absent),
            tuple(dict.fromkeys(name for name, _ in absent)),
        )

    def differing(names: tuple[str, ...]) -> list[str]:
        return [name for name in names if stamps_a[name] != stamps_b[name]]

    def described(names: list[str]) -> str:
        return "; ".join(f"{name} {stamps_a[name]} vs {stamps_b[name]}" for name in names)

    if versions := differing(_VERSIONS):
        raise DiffRefused(f"cannot diff: {described(versions)}", tuple(versions))
    if a.module_id != b.module_id:
        raise DiffRefused(
            f"cannot diff two modules: {a.module_id} vs {b.module_id}", ("module_id",)
        )
    producer = differing(_PRODUCER)
    if producer and not allow_producer_change:
        raise DiffRefused(
            f"cannot diff: {described(producer)} — rows can differ with no code change; "
            "allow the producer change to diff anyway, labelled",
            tuple(producer),
        )
    return bool(producer)


# --- masking, and the rows masking joins -------------------------------------------------


def _indexed(
    kind: Kind, rows: Iterable[dict[str, object]], redactor: Redactor
) -> dict[tuple[object, ...], dict[str, object]]:
    index: dict[tuple[object, ...], dict[str, object]] = {}
    for row in rows:
        masked = _masked(kind, row, redactor)
        key = tuple(masked[column] for column in kind.identity)
        index[key] = _joined(kind, index[key], masked) if key in index else masked
    return index


def _attribute_keys(kind: Kind) -> list[str]:
    return [ROW_KEYS.get(token, token) for token in kind.attributes]


def _masked(kind: Kind, row: dict[str, object], redactor: Redactor) -> dict[str, object]:
    """The row as the exporter would have shipped it, cut to identity, attributes and
    evidence: `path`/`peer` through `redact_text`, a property's value through
    `redact_value` — the calls `_EXPORT_QUERIES` makes on the same columns."""
    projected = {
        **{column: row[column] for column in kind.identity},
        **{key: row[key] for key in _attribute_keys(kind)},
        "evidence": row["evidence"],
        "origin": row["origin"],
    }
    for column in ("path", "peer"):
        if column in kind.identity and projected[column] is not None:
            projected[column] = redactor.redact_text(str(projected[column]))
    if kind.name == "boundary-property":
        key = str(row["key"])
        projected["value"] = _each(projected["value"], lambda v: redactor.redact_value(key, v))
    if kind.name == "data-contract":
        projected["fields"] = _by_wire_name(projected["fields"])
    for column in _SETS:
        if column in projected:
            projected[column] = _canonical(projected[column])
    return projected


def _each(value: object, mask: Callable[[str], str]) -> object:
    """`mask` applied to a value, or to each of `{"several": [...]}` — after which two that
    masked alike are one, as they would be in a bundle."""
    if value is None:
        return None
    return _agreed(None if v is None else mask(str(v)) for v in _flat([value]))


def _flat(values: Iterable[object]) -> list[object]:
    flat: list[object] = []
    for value in values:
        if isinstance(value, dict) and set(value) == {"several"}:
            flat.extend(value["several"])
        else:
            flat.append(value)
    return flat


def _canonical(entries: object) -> list[object]:
    """A set's members in one order whatever order they were joined in."""
    members = {json.dumps(entry, sort_keys=True): entry for entry in cast(list[object], entries)}
    return [members[key] for key in sorted(members)]


def _by_wire_name(fields: object) -> dict[str, object]:
    """A contract's field set keyed by wire name (§2: wire name → wire type, format,
    required, nullable), so a `changed` names the field. Two fields with one wire name keep
    both, as `{"several": [...]}`."""
    grouped: dict[str, list[dict[str, object]]] = {}
    for field in cast(list[dict[str, object]], fields):
        rest = {key: value for key, value in field.items() if key != "wire_name"}
        grouped.setdefault(str(field["wire_name"]), []).append(rest)
    return {name: _agreed(values) for name, values in grouped.items()}


def _joined(kind: Kind, kept: dict[str, object], other: dict[str, object]) -> dict[str, object]:
    """Two rows that masking made one identity, joined as the source joins a group."""
    joined = {column: kept[column] for column in kind.identity}
    for key in _attribute_keys(kind):
        if key in _SETS:
            joined[key] = _canonical(
                [*cast(list[object], kept[key]), *cast(list[object], other[key])]
            )
        else:
            joined[key] = _agreed(_flat([kept[key], other[key]]))
    evidence_kept = cast(dict[str, object], kept["evidence"])
    evidence_other = cast(dict[str, object], other["evidence"])
    joined["evidence"] = {
        name: (
            sorted({*cast(list[str], evidence_kept[name]), *cast(list[str], evidence_other[name])})
            if isinstance(evidence_kept[name], list)
            else _agreed(_flat([evidence_kept[name], evidence_other[name]]))
        )
        for name in evidence_kept
    }
    # `dependency` only where every row with a grounding document is one (source `_origin`).
    grounded = [
        row for row in (kept, other) if cast(dict[str, object], row["evidence"])["documents"]
    ]
    joined["origin"] = (
        "dependency"
        if grounded and all(row["origin"] == "dependency" for row in grounded)
        else "module_output"
    )
    return joined


# --- the comparison -----------------------------------------------------------------------


def _compared(
    kind: Kind,
    before: dict[tuple[object, ...], dict[str, object]],
    after: dict[tuple[object, ...], dict[str, object]],
) -> list[Entry]:
    keys = _attribute_keys(kind)

    def entry(
        change: Change,
        row: dict[str, object],
        from_: dict[str, object] | None,
        to: dict[str, object] | None,
        compatibility: Compatibility | None = None,
    ) -> Entry:
        evidence = row["evidence"]
        assert isinstance(evidence, dict)
        return Entry(
            kind=kind.name,
            change=change,
            identity={column: row[column] for column in kind.identity},
            from_=from_,
            to=to,
            evidence=evidence,
            origin=str(row["origin"]),
            compatibility=compatibility,
        )

    found: list[Entry] = []
    for identity, row in after.items():
        if identity not in before:
            found.append(entry("added", row, None, {key: row[key] for key in keys}))
    for identity, row in before.items():
        if identity not in after:
            found.append(entry("removed", row, {key: row[key] for key in keys}, None))
    for identity, old in before.items():
        new = after.get(identity)
        if new is None:
            continue
        differing = [key for key in keys if old[key] != new[key]]
        if differing:
            found.append(
                entry(
                    "changed",
                    new,
                    {key: old[key] for key in differing},
                    {key: new[key] for key in differing},
                    _compatibility(kind, old, new, differing),
                )
            )
    return found


def _compatibility(
    kind: Kind, old: dict[str, object], new: dict[str, object], differing: list[str]
) -> Compatibility | None:
    if kind.name not in ("endpoint", "dependency"):
        return None
    verdicts = [_body_verdict(body, old[body], new[body]) for body in _BODIES if body in differing]
    if "breaking" in verdicts:
        return "breaking"
    if verdicts and all(verdict == "compatible" for verdict in verdicts):
        return "compatible"
    return None


def _body_verdict(body: str, old: object, new: object) -> Compatibility | None:
    """M06 step 3 forwards in time, on field lists keyed by wire name; `None` where a side
    has no field list to compare."""
    if not isinstance(old, list) or not isinstance(new, list):
        return None
    old_names = {field["wire_name"] for field in old}
    new_names = {field["wire_name"] for field in new}
    if body == "request":
        gained_required = any(
            field["required"] is True for field in new if field["wire_name"] not in old_names
        )
        return "breaking" if gained_required else "compatible"
    return "breaking" if old_names - new_names else "compatible"
