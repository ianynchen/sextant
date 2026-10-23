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
`boundary-property` value were masked at export; a workspace's are verbatim. Each side comes
with its OWN redactor — a workspace's is its module's `.sextant.yml` widening the built-ins,
exactly as `export` would mask it; a bundle's is the built-ins, its own rules having been
applied already — and its rule set is what it is compared under: a workspace records no
`redaction_set_hash`, so its hash is its redactor's; a bundle's is the one its exporter
recorded. Two that differ refuse with the other producer stamps. Where they agree, or the
caller allowed the change, every row of both sides passes through the UNION of the two
redactors, by the calls the exporter makes on the same columns, so a masked bundle and the
workspace it came from diff empty, nothing either side's rules hide is printed, and the
diff's own output is masked. A bundle side passes through unchanged because masking is
idempotent.

A stated limit: a bundle's own `redact:` additions are not in its manifest, only their
hash, so under `allow_producer_change` a workspace value only the BUNDLE's extra rules would
mask is masked by the workspace's rules and the built-ins alone.

Masking can make two identities one — two peers that differ only in userinfo — which is what
the bundle's own grouping already did. Such rows are joined after masking exactly as the
source groups rows: an attribute they disagree on is `{"several": [...]}`, sets are unions,
evidence is the union of both.

**A body is compared twice**: as its field set by wire name (`request`/`response`), and as
its descriptor's STRUCTURE (`request_shape`/`response_shape`) with every type symbol erased
to `"<type>"` — wire type, format, nullability and nesting kept. So `OrderView` becoming
`List<OrderView>` is a change, and a DTO renamed with the same structure is not (decision 1:
implementation never matters). The stored descriptor names its type under `shape_id`.

**`changed` is attribute-level**: `from`/`to` carry only the attributes that differ. An
endpoint's or dependency's body change is labelled by M06 step 3's directional test read
forwards in time: `breaking` where the request gained a required field or an existing
request field became required, where the response lost a field, where an existing field's
wire type changed in either body, or where either body's structure changed; `compatible`
otherwise; and `None` where a changed body has nothing to compare on one side (no body, or
`{"several": [...]}`) and nothing else said `breaking`. The requirement set (an endpoint's
`requirements`, a dependency's `headers`) is labelled by the same test, because M06 step 3
counts `requirement: required` metadata as part of what the server requires: an entry that
GAINS `required` (a header, query parameter or cookie an old client never sent) is
`breaking`; one lost, added optional or relaxed to optional is `compatible`. A change only
to `conditions`, `consumes`, `produces`, `format` or `resolution` is not labelled.

One `rows(kind)` per kind per side — six named kind reads per side (`module` is read off
the metadata, no query), plus the shared reads a side makes once on first use and every kind
then shares: `shape_fields`, `endpoint_metadata`, `endpoint_conditions` and the two
document joins, five more, so at most eleven reads a side and twenty-two in all — and the
join is a dictionary on identity (§3e).
"""

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Literal, cast

from sextant.application.boundary.source import ROW_KEYS, STAMPS, BoundarySource, _agreed
from sextant.application.boundary.vocabulary import KINDS, Kind
from sextant.domain.redaction import REDACTED, Redactor
from sextant.domain.version import GRAPH_SCHEMA_VERSION

Change = Literal["added", "removed", "changed"]
Compatibility = Literal["compatible", "breaking"]

_CHANGES: tuple[Change, ...] = ("added", "removed", "changed")
# A difference here means the two sides do not hold comparable tables: no flag overrides it.
_VERSIONS = ("graph_schema_version", "fact_schema_version", "boundary_vocabulary_version")
# A difference here changes rows with no code change: refused unless allowed, then labelled.
_PRODUCER = ("sextant_version", "catalog_hash", "redaction_set_hash")
# The attributes that are sets, not values: rows joined by masking take their union.
_SETS = ("requirements", "conditions", "headers")
# The sets whose change is labelled: what the server requires of a request (M06 step 3).
_REQUIREMENT_SETS = ("requirements", "headers")
_BODIES = ("request", "response")
_DESCRIPTORS = ("request_shape", "response_shape")
# What a type symbol becomes in a descriptor's structure, and the keys that hold one.
_ERASED = "<type>"
_SYMBOL_KEYS = ("shape_id", "symbol")


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
        """The spec's §3b document, keys in its order. Each side's `producer` carries
        `redaction_recorded` beside `redaction_set_hash`: `true` for a bundle, whose hash
        the exporter recorded, `false` for a workspace, whose hash is its own module's rule
        set as the diff computed it — nothing recorded one at `analyze`."""
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
        lines = []
        if self.producer_changed:
            # The JSON's `producer_changed`, said where a reader of the text will see it: rows
            # can differ with no code change, and a stale side's peers print masked.
            lines += ["**Producer changed** — see `producer` in the JSON output.", ""]
        lines += ["| kind | added | removed | changed |", "|---|---|---|---|"]
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
    redactor_a: Redactor,
    redactor_b: Redactor,
    *,
    allow_producer_change: bool = False,
) -> Diff:
    """What changed at the boundary from `a` to `b`. `redactor_a`/`redactor_b` are each
    side's exit: its module's own rules for a workspace side, the built-ins for a bundle.
    Raises `DiffRefused`."""
    stamps_a, stamps_b = _stamps(a, redactor_a), _stamps(b, redactor_b)
    producer_changed = _refuse_or_allow(a, b, stamps_a, stamps_b, allow_producer_change)
    # Equal rule sets make this either side's own; differing ones (allowed) make it both.
    redactor = redactor_a.union(redactor_b)
    # Both sides share one graph schema by now (`_VERSIONS`), so one answer covers both.
    stale = stamps_a["graph_schema_version"] != GRAPH_SCHEMA_VERSION
    entries: list[Entry] = []
    for kind in KINDS.values():
        before = _indexed(kind, a.rows(kind), redactor, stale)
        after = _indexed(kind, b.rows(kind), redactor, stale)
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
        a={"module": a.module_id, "commit": a.commit, "producer": _described(a, stamps_a)},
        b={"module": b.module_id, "commit": b.commit, "producer": _described(b, stamps_b)},
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


def _described(side: BoundarySource, stamps: dict[str, object]) -> dict[str, object]:
    return {**stamps, "redaction_recorded": side.is_bundle}


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
    # A side older than this build may hold what the build no longer writes — before graph
    # schema 5, a peer carrying a URL's password with its scheme gone — and every other
    # reader refuses such a workspace (user ruling, 2026-10-23). The diff alone can be told
    # to read one anyway, because a kept bundle is history the user asked to compare; it is
    # then labelled, and such a peer is masked whole (`_masked`).
    stale = stamps_a["graph_schema_version"] != GRAPH_SCHEMA_VERSION
    if stale and not allow_producer_change:
        raise DiffRefused(
            f"cannot diff: both sides are graph_schema_version "
            f"{stamps_a['graph_schema_version']} and this build is {GRAPH_SCHEMA_VERSION} — "
            "re-analyse BOTH (a bundle by re-exporting a fresh analysis of its commit; one "
            "side alone is then refused as a version mismatch), or allow the producer change "
            "to diff them as they are, labelled",
            ("graph_schema_version",),
        )
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
    return bool(producer) or stale


# --- masking, and the rows masking joins -------------------------------------------------


def _indexed(
    kind: Kind, rows: Iterable[dict[str, object]], redactor: Redactor, stale: bool
) -> dict[tuple[object, ...], dict[str, object]]:
    index: dict[tuple[object, ...], dict[str, object]] = {}
    for row in rows:
        masked = _masked(kind, row, redactor, stale)
        key = tuple(masked[column] for column in kind.identity)
        index[key] = _joined(kind, index[key], masked) if key in index else masked
    return index


def _attribute_keys(kind: Kind) -> list[str]:
    return [ROW_KEYS.get(token, token) for token in kind.attributes]


def _masked(
    kind: Kind, row: dict[str, object], redactor: Redactor, stale: bool
) -> dict[str, object]:
    """The row as the exporter would have shipped it, cut to identity, attributes and
    evidence: `path`/`peer` through `redact_text`, a property's value through
    `redact_value`, each condition's `expression` through `redact_json` — the calls
    `_EXPORT_QUERIES` makes on the same columns. A condition entry is replaced, never
    edited: the source shares one entry between the kinds that carry it.

    From an analysis older than graph schema 5 (`stale`, allowed by the caller), a peer
    with an `@` and no `scheme://` is masked WHOLE: it may be a split URL's authority with
    its password kept, and in text that cannot be told from a `mailto:ops@billing` peer, so
    it is hidden rather than rewritten into a host either way."""
    projected = {
        **{column: row[column] for column in kind.identity},
        **{key: row[key] for key in _attribute_keys(kind)},
        "evidence": row["evidence"],
        "origin": row["origin"],
    }
    for column in ("path", "peer"):
        if column in kind.identity and projected[column] is not None:
            projected[column] = redactor.redact_text(str(projected[column]))
    peer = projected.get("peer")
    if stale and isinstance(peer, str) and "@" in peer and "://" not in peer:
        projected["peer"] = REDACTED
    if kind.name == "boundary-property":
        key = str(row["key"])
        projected["value"] = _each(projected["value"], lambda v: redactor.redact_value(key, v))
    if kind.name == "data-contract":
        projected["fields"] = _by_wire_name(projected["fields"])
    if kind.name in ("endpoint", "dependency"):
        # Not `error-handler.response_shape`: that column is a shape id, not a descriptor.
        for column in _DESCRIPTORS:
            projected[column] = _each(projected[column], _structure)
    if "conditions" in projected:
        projected["conditions"] = [
            {**entry, "expression": _redacted_json(entry["expression"], redactor)}
            for entry in cast(list[dict[str, object]], projected["conditions"])
        ]
    for column in _SETS:
        if column in projected:
            projected[column] = _canonical(projected[column])
    return projected


def _redacted_json(expression: object, redactor: Redactor) -> object:
    return None if expression is None else redactor.redact_json(str(expression))


def _each(value: object, mask: Callable[[str], object]) -> object:
    """`mask` applied to a value, or to each of `{"several": [...]}` — after which two that
    masked alike are one, as they would be in a bundle."""
    if value is None:
        return None
    return _agreed(None if v is None else mask(str(v)) for v in _flat([value]))


def _structure(descriptor: str) -> object:
    """A payload descriptor with every type symbol erased, at every level of nesting."""

    def erased(node: object) -> object:
        if isinstance(node, dict):
            return {
                key: _ERASED if key in _SYMBOL_KEYS else erased(value)
                for key, value in node.items()
            }
        if isinstance(node, list):
            return [erased(value) for value in node]
        return node

    return erased(json.loads(descriptor))


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
    verdicts += [
        _structure_verdict(old[column], new[column])
        for column in _DESCRIPTORS
        if column in differing
    ]
    verdicts += [
        _requirement_verdict(old[column], new[column])
        for column in _REQUIREMENT_SETS
        if column in differing
    ]
    if "breaking" in verdicts:
        return "breaking"
    if verdicts and all(verdict == "compatible" for verdict in verdicts):
        return "compatible"
    return None


def _body_verdict(body: str, old: object, new: object) -> Compatibility | None:
    """M06 step 3 forwards in time, on field lists keyed by wire name; `None` where a side
    has no field list to compare. A request field is required if any field of its name is."""
    if not isinstance(old, list) or not isinstance(new, list):
        return None
    old_by, new_by = _by_name(old), _by_name(new)
    shared = old_by.keys() & new_by.keys()
    if any(_wire_types(old_by[name]) != _wire_types(new_by[name]) for name in shared):
        return "breaking"
    if body == "request":
        # A new required field, or an existing one that became required: an old client
        # never sent it.
        newly_required = any(
            _required(fields) and not _required(old_by.get(name, []))
            for name, fields in new_by.items()
        )
        return "breaking" if newly_required else "compatible"
    return "breaking" if old_by.keys() - new_by.keys() else "compatible"


def _requirement_verdict(old: object, new: object) -> Compatibility:
    """M06 step 3 counts a `requirement: required` metadata row as part of what the server
    REQUIRES, beside a body's required fields: an entry, by `(kind, name)`, that is
    `required` on the new side and was not on the old is one an old client never sent, so
    `breaking`; an entry lost, added optional or relaxed from required is `compatible`. An
    entry carrying no `requirement` (every outbound header — a call SENDS it, it enforces
    nothing) is never required."""

    def required(entries: object) -> set[tuple[object, object]]:
        return {
            (entry.get("kind"), entry.get("name"))
            for entry in cast(list[dict[str, object]], entries)
            if entry.get("requirement") == "required"
        }

    gained = required(new) - required(old)
    return "breaking" if gained else "compatible"


def _structure_verdict(old: object, new: object) -> Compatibility | None:
    """A container or scalar change of a body breaks a client either way it points; `None`
    where a side has no single structure (no body, or several)."""
    if not isinstance(old, dict) or not isinstance(new, dict):
        return None
    if set(old) == {"several"} or set(new) == {"several"}:
        return None
    return "breaking"


def _by_name(fields: list[dict[str, object]]) -> dict[object, list[dict[str, object]]]:
    grouped: dict[object, list[dict[str, object]]] = {}
    for field in fields:
        grouped.setdefault(field["wire_name"], []).append(field)
    return grouped


def _wire_types(fields: list[dict[str, object]]) -> set[object]:
    return {field["wire_type"] for field in fields}


def _required(fields: list[dict[str, object]]) -> bool:
    return any(field["required"] is True for field in fields)
