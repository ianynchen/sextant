"""Format inference — the six-rung ladder (2G design §5).

The last pass of a resolve, owning exactly one job: stamp
`(format, format_resolution)` on every endpoint row. It runs after media
stamping and after parse binding because its rungs read their outputs, and
it answers EVERY row — a row nothing could be said about carries NULL and
`unresolved`, which is an answer rather than an omission.

**Two rules bind the whole ladder** (2G design's thesis):

1. *An assumed format must never look observed.* A framework default is
   recorded, but at `narrowed`, never at the resolved tier.
2. *A payload's TYPE does not determine the wire.* Declared channel evidence
   — a media type, a configured serializer — always outranks payload-type
   evidence, because a schema-typed payload has a JSON encoding too. That is
   why rung 2 sits above rung 4 rather than beside it.

The rungs, first answer wins:

1. **Fixed by protocol** — a protocol whose wire is constant by definition;
   `resolved`.
2. **Declared media** — the row's own `consumes`/`produces` MIME strings
   through the catalogs' MIME table; `resolved`.
3. **Serializer config** — the class a module's configuration names for the
   rows a rule covers, through the catalogs' serializer table; `resolved`,
   because a configured serializer states the wire outright.
4. **Payload hierarchy** — the bound shape was described by a schema rather
   than by a class's fields, so its own schema format is suggestive;
   `narrowed`, never more: negotiation this pass cannot see may still put
   the JSON encoding on the wire.
5. **Framework default** — an ordinary declared payload plus a default
   converter whose package family is present in the module; `narrowed`.
6. **Nothing** — NULL and `unresolved`.

**A rung that answers with more than one format answers with none.** Two
MIME types that mean different formats, a configured serializer disagreeing
with itself across the directions of a merged row, a request described by
one schema format and a response by another: the row records `unresolved`
and the impasse goes to `open_questions` (2G design §6) for 2K, rather than
this pass picking the side that happens to sort first. The ladder does NOT
continue past a conflict — a weaker rung cannot break a tie a stronger one
could not.

**Resolution vocabulary.** The design's prose calls the strongest tier
"exact"; the value written is `resolved`, because 2G design §4 states that
`format_resolution` *reuses the existing resolution set* and D00 §4's set is
closed at `resolved`/`narrowed`/`partial`/`unresolved` (NFR-5 — widening it
is a schema change, never an implementation choice). One word, one meaning:
the same tier `endpoints.resolution` already spells this way.

Every framework, protocol, MIME, package and class name this pass compares
against is catalog data (2G design §7) or a column on the row. No such name
appears below.
"""

import json
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.engines.config_join import _agreed, _config_values
from sextant.application.resolve.open_questions import record_open_questions
from sextant.application.resolve.shapes.contracts import _shape_roots_of
from sextant.domain.closed_sets import RESERVED_FORMATS, Direction, Evidence, Format, Resolution
from sextant.domain.symbols import bare_descriptor, package_path

# The `config_join` block rung 3's vocabulary extends (D02 §2d). `format_from`
# rides beside that block's `values` (class -> MIME) rather than in a block of
# its own because the rules that say WHICH configuration key holds a
# serializer, and which rows it covers, already live there: a second copy of
# that machinery keyed on the same configuration would be two things to keep
# in step. `values` and `format_from` answer different questions about the
# same declared class — what MIME it implies, and what is actually on the
# wire — and a class may legitimately appear in one and not the other.
_MEDIA_BLOCK = "media_from_config"
_FORMAT_FROM = "format_from"

# The two evidence tiers a schema-described shape may carry (2G design §3):
# `compiler` for a schema compiled into the artifact, `declared` for one read
# off a repository file. Every `declared_shape` fact carries one of them
# today, so this never excludes a live shape — it is the rung's rule stated
# where the rung reads it, so that a weaker tier arriving later (a schema
# recovered by name match, or supplied by 2K) does not silently become the
# payload evidence rung 4 treats as describing the wire.
_DESCRIBED_BY = (Evidence.COMPILER, Evidence.DECLARED)

# The two payload columns, and the two media columns, in the order a
# candidate list is built from them — fixed so two runs order an
# `open_questions` candidate array the same way (NFR-1).
_PAYLOAD_COLUMNS = ("request_shape", "response_shape")
_MEDIA_COLUMNS = ("consumes", "produces")

# What `stamp_format.sql` matches a stamped answer back onto: the row's
# identity, plus every column a rung above read. The four carried columns are
# there because they are INPUTS — two rows agreeing on all eight were handed
# the same answer, which is what lets an UPDATE with no unique key stay
# idempotent rather than ambiguous.
_MATCH_COLUMNS = (
    "protocol",
    "direction",
    "method",
    "path",
    "handler",
    "caller",
    *_MEDIA_COLUMNS,
    *_PAYLOAD_COLUMNS,
)


def resolve_format(workspace: Workspace, catalogs: list[Catalog]) -> None:
    """Stamps `(format, format_resolution)` on every endpoint row.

    Runs unconditionally and last (`resolve/pipeline.py`). Reads only catalog
    vocabulary, the row's own columns, `resolved_config`, and the shape
    evidence Task 5's declared shapes carry; writes only the two endpoint
    columns and the `format_conflict` half of `open_questions`.
    """
    # Every catalog's format vocabulary is checked BEFORE anything is
    # stamped, the same "broken file, not a half-answered table" discipline
    # `resolve_config` keeps for its own model.
    for catalog in catalogs:
        _validate(catalog)
    fixed = _merged(catalogs, "format_fixed")
    media = _merged(catalogs, "media_formats")
    serializers = _serializer_candidates(workspace, catalogs)
    described = _described_shapes(workspace)
    default_marker = _present_default_marker(workspace, catalogs)

    rows: list[dict[str, Any]] = []
    questions: list[dict[str, Any]] = []
    for endpoint in workspace.query("endpoints"):
        answer = _answer(endpoint, fixed, media, serializers, described, default_marker)
        # The row is matched back by its identity AND by every column the
        # answer above was read from (`stamp_format.sql`) — which is what
        # makes a duplicate match idempotent in a table with no unique key.
        rows.append(
            {column: endpoint.get(column) for column in _MATCH_COLUMNS}
            | {"format": answer.format, "format_resolution": answer.resolution}
        )
        if answer.candidates is not None:
            questions.append(_question(endpoint, answer))
    workspace.derive("stamp_format", rows=rows)
    record_open_questions(workspace, questions)


class _Answer:
    """One row's finished answer: the two stamped columns, plus the candidate
    list and evidence trail a CONFLICT carries (both `None` otherwise — a row
    that reached a rung cleanly asks nothing)."""

    __slots__ = ("candidates", "format", "resolution", "trail")

    def __init__(
        self,
        format: str | None,
        resolution: str,
        candidates: list[dict[str, str]] | None = None,
        trail: str = "",
    ) -> None:
        self.format = format
        self.resolution = resolution
        self.candidates = candidates
        self.trail = trail


def _answer(
    endpoint: dict[str, Any],
    fixed: dict[str, str],
    media: dict[str, str],
    serializers: dict[tuple[str, str], list[dict[str, str]]],
    described: dict[str, dict[str, str]],
    default_marker: str | None,
) -> _Answer:
    """Walks the rungs in order. The first rung that produces candidates
    decides the row — cleanly if every candidate names the same format, as a
    conflict otherwise."""
    rungs = (
        (Resolution.RESOLVED, "rung 1 (fixed by protocol)", _fixed_candidates(endpoint, fixed)),
        (Resolution.RESOLVED, "rung 2 (declared media)", _media_candidates(endpoint, media)),
        (
            Resolution.RESOLVED,
            "rung 3 (serializer config)",
            _config_candidates(endpoint, serializers),
        ),
        (
            Resolution.NARROWED,
            "rung 4 (payload hierarchy)",
            _payload_candidates(endpoint, described),
        ),
        (
            Resolution.NARROWED,
            "rung 5 (framework default)",
            _default_candidates(endpoint, described, default_marker),
        ),
    )
    for resolution, label, candidates in rungs:
        if not candidates:
            continue
        formats = {candidate["format"] for candidate in candidates}
        if len(formats) == 1:
            return _Answer(formats.pop(), str(resolution))
        # A rung that saw several answers saw none it can defend. The row is
        # `unresolved` and the impasse is handed on — the ladder stops here
        # rather than falling through, because a rung BELOW a disagreement
        # would be breaking a tie that stronger evidence could not.
        ordered = sorted(candidates, key=lambda c: (c["format"], c["seen_in"], c["why"]))
        named = ", ".join(f"{c['format']} from {c['seen_in']} ({c['why']})" for c in ordered)
        return _Answer(None, str(Resolution.UNRESOLVED), ordered, f"{label}: {named}")
    return _Answer(None, str(Resolution.UNRESOLVED))


# --- the rungs ------------------------------------------------------------


def _fixed_candidates(endpoint: dict[str, Any], fixed: dict[str, str]) -> list[dict[str, str]]:
    """Rung 1. A protocol whose wire format is constant by definition — the
    catalog that owns the protocol says so, and nothing about the row can
    change it."""
    declared = fixed.get(str(endpoint["protocol"]))
    if declared is None:
        return []
    return [{"format": declared, "seen_in": "protocol", "why": str(endpoint["protocol"])}]


def _media_candidates(endpoint: dict[str, Any], media: dict[str, str]) -> list[dict[str, str]]:
    """Rung 2. The row's own declared MIME strings, mapped by catalog
    vocabulary — the rung that outranks the payload's type by design.

    Both media columns feed one candidate list: `format` describes the wire
    identity, singular, so a row consuming one format and producing another
    is a disagreement to record, not two answers to keep. A MIME string with
    no mapping contributes nothing — an unmapped type is a gap to grow the
    catalog from, never a guess."""
    candidates = []
    for column in _MEDIA_COLUMNS:
        for mime in _mime_list(endpoint.get(column)):
            declared = media.get(mime)
            if declared is not None:
                candidates.append({"format": declared, "seen_in": column, "why": mime})
    return candidates


def _config_candidates(
    endpoint: dict[str, Any], serializers: dict[tuple[str, str], list[dict[str, str]]]
) -> list[dict[str, str]]:
    """Rung 3. What the module's own configuration says it serializes with.

    A rule covers a row when the protocols match and the directions do. A
    merged `both` row is covered by rules for EITHER direction: it is one
    identity the module exposes and calls, so both halves' configuration
    genuinely applies to it — and where the two halves' configured classes
    mean different formats, that is a real disagreement about one wire, which
    the caller records rather than resolves."""
    protocol, direction = str(endpoint["protocol"]), str(endpoint["direction"])
    covered = [
        rule_direction
        for rule_direction in (Direction.INBOUND, Direction.OUTBOUND)
        if direction in (str(rule_direction), Direction.BOTH)
    ]
    return [
        candidate
        for rule_direction in covered
        for candidate in serializers.get((protocol, str(rule_direction)), [])
    ]


def _payload_candidates(
    endpoint: dict[str, Any], described: dict[str, dict[str, str]]
) -> list[dict[str, str]]:
    """Rung 4. The bound shape was described by a schema, and the schema
    names its own format.

    Only ever `narrowed` (the caller's table says so): proto3 defines a JSON
    encoding, so a schema-described payload is evidence about the payload's
    type, not a statement about the bytes. Rungs 1-3 have already had their
    say by the time this runs, which is exactly the precedence the design
    asks for."""
    return [
        {"format": described[root]["schema_format"], "seen_in": column, "why": root}
        for column in _PAYLOAD_COLUMNS
        for root in _shape_roots_of(endpoint.get(column))
        if root in described
    ]


def _default_candidates(
    endpoint: dict[str, Any], described: dict[str, dict[str, str]], default_marker: str | None
) -> list[dict[str, str]]:
    """Rung 5. An ordinary declared payload, and a default converter's
    package family present somewhere in the module.

    Two conditions, both narrow on purpose. The marker is module-wide
    PRESENCE evidence — the converter is on the classpath, which is why it is
    the framework default at all — and it says nothing about this row, so the
    answer is `narrowed`.

    A row qualifies only if it carries a declared payload TYPE: a row with no
    payload at all, and a row whose payload is a bare scalar, are both left to
    rung 6. A converter's presence is not evidence that a channel carrying
    nothing carries it in JSON, and a `String` payload is exactly the case
    where content negotiation decides something this pass cannot see."""
    if default_marker is None:
        return []
    roots = [root for column in _PAYLOAD_COLUMNS for root in _shape_roots_of(endpoint.get(column))]
    # A schema-described payload never reaches here — rung 4 answered it —
    # unless it reached this rung past a rung-4 conflict, which cannot
    # happen: a conflict stops the ladder. The filter is what keeps this
    # rung's claim honest anyway: it is about ORDINARY declared payloads.
    ordinary = [root for root in roots if root not in described]
    if not ordinary:
        return []
    # `seen_in` names the MODULE, not a column: this rung's evidence is not
    # on the row at all — it is the converter's package family being present
    # in the module's world, which is what makes it the default for every
    # payload the module carries.
    return [
        {"format": str(Format.JSON), "seen_in": "module", "why": default_marker},
    ]


# --- catalog vocabulary ---------------------------------------------------


def _merged(catalogs: list[Catalog], block: str) -> dict[str, str]:
    """One vocabulary block, unioned across every catalog that declares it.

    Unioned rather than scoped per catalog because these tables are about the
    world, not about one framework: a MIME string means the same format
    whoever wrote it down, and the row being mapped carries no catalog of its
    own once several engines have contributed to it.

    Two catalogs disagreeing about one key is refused rather than resolved.
    The design deliberately ships the same table on more than one catalog of
    a family (each owns its own protocol), so the collision is a real,
    reachable editing mistake — and picking either side silently would make
    the answer depend on filename order."""
    merged: dict[str, str] = {}
    origin: dict[str, Catalog] = {}
    for catalog in catalogs:
        for key, value in _block_of(catalog, block).items():
            if key in merged and merged[key] != str(value):
                raise CatalogError(
                    f"loading catalog {catalog.source}: `{block}.{key}: {value}` contradicts "
                    f"`{merged[key]}`, declared for the same key in {origin[key].source} — "
                    f"one key, one format (2G design §7)"
                )
            merged[key] = str(value)
            origin.setdefault(key, catalog)
    return merged


def _block_of(catalog: Catalog, block: str) -> dict[str, Any]:
    declared = getattr(catalog, block)
    return declared if isinstance(declared, dict) else {}


def _media_block(catalog: Catalog) -> dict[str, Any]:
    """The `media_from_config` block a catalog declares, or an empty one.

    Reached through `matches`, which the loader carries through unread, so
    every level of it is `Any` and each is checked rather than assumed — the
    same reason `config_join` validates the block it owns before reading it.
    """
    matches = catalog.matches if isinstance(catalog.matches, dict) else {}
    block = matches.get(_MEDIA_BLOCK)
    return block if isinstance(block, dict) else {}


def _serializer_candidates(
    workspace: Workspace, catalogs: list[Catalog]
) -> dict[tuple[str, str], list[dict[str, str]]]:
    """Rung 3's vocabulary, resolved once: `(protocol, direction)` -> the
    candidates the module's configuration actually produced.

    Read from the `media_from_config` rules a catalog already declares, which
    is where the configuration key and the rows it covers are stated; only
    the class-to-format table beside them is this pass's own. Agreement across
    environments is required exactly as the media stamp requires it
    (`_agreed`): a key that resolved differently per environment, or in no
    environment, said nothing one column can carry.

    A class absent from `format_from` contributes nothing — the same "a gap
    to grow the catalog from, not a guess" the media table keeps. Rules are
    read defensively (`.get`): a malformed `media_from_config` block is
    refused by the engine that owns that vocabulary, at derivation time, and
    a second copy of that check here would be a second thing to keep in step.
    """
    config = _config_values(workspace)
    found: dict[tuple[str, str], list[dict[str, str]]] = {}
    for catalog in catalogs:
        block = _media_block(catalog)
        formats = block.get(_FORMAT_FROM)
        if not isinstance(formats, dict) or not formats:
            continue
        for rule in block.get("rules") or []:
            key, on = rule.get("key"), rule.get("on")
            if not isinstance(key, str) or not isinstance(on, dict):
                continue
            declared = _agreed(config, key)
            if declared is None or declared not in formats:
                continue
            identity = (str(on["protocol"]), str(on["direction"]))
            found.setdefault(identity, []).append(
                {"format": str(formats[declared]), "seen_in": key, "why": declared}
            )
    return found


def _present_default_marker(workspace: Workspace, catalogs: list[Catalog]) -> str | None:
    """Rung 5's presence test: the first declared marker package that any
    annotation in the module comes from, or `None`.

    Presence, not usage. The question is whether the default converter is on
    the classpath at all — that is what makes it the framework's default for
    every payload, including the ones that carry none of its annotations —
    and an annotation from its package family is proof that it is, since the
    package could not have been resolved at compile time otherwise.

    **Determinism comes from the ANNOTATION ordering, not from the markers.**
    This walks annotations in the `annotations` named query's own total order
    (`target, annotation`) and returns on the first hit, so a module carrying
    two marker families names the same one on every run because the
    annotations are ordered — sorting the markers only makes the tie-break
    within a single annotation stable, which is a much smaller claim. Either
    way the choice changes nothing but the recorded trail: every marker in
    this list means the same format.
    """
    markers = sorted(
        {str(marker) for catalog in catalogs for marker in catalog.json_default_markers}
    )
    if not markers:
        return None
    prefixes = [(marker, package_path(marker) + "/") for marker in markers]
    for row in workspace.query("annotations"):
        annotation = str(row["annotation"])
        for marker, prefix in prefixes:
            if annotation.startswith(prefix):
                return marker
    return None


def _described_shapes(workspace: Workspace) -> dict[str, dict[str, str]]:
    """Every shape a SCHEMA described, keyed by the symbol an endpoint's
    payload descriptor names it by (2G design §3).

    `bare_descriptor` normalizes the key the way `shapes/expansion.py`'s own
    `_declared_shapes` does, and for the same reason: a payload column's
    `shape_id` never carries module coordinates, and a declared shape's
    `symbol` is only bare because that is what today's naming emits.

    Filtered on the shape's evidence tier: rung 4 treats a schema description
    as evidence about the wire, and only a schema the compiler embedded or a
    schema file the repository declares earns that.
    """
    return {
        bare_descriptor(str(row["symbol"])): {"schema_format": str(row["schema_format"])}
        for row in workspace.query("declared_shapes")
        if row["evidence"] in _DESCRIBED_BY and row["schema_format"] is not None
    }


def _validate(catalog: Catalog) -> None:
    """Refuses a catalog whose format vocabulary names something outside
    D00's format set, or the value the design RESERVES.

    Every value below is stamped into a published column, where a typo is
    indistinguishable from an observation — the same reason the loader checks
    `protocol`/`direction` at the edge (NFR-5). The reserved value is refused
    separately and by name, the 2F `from_key_prefix` precedent: a catalog
    declaring something the design names but nothing implements must fail
    loudly rather than be silently read as something adjacent.
    """
    blocks = {
        "format_fixed": catalog.format_fixed,
        "media_formats": catalog.media_formats,
    }
    declared_from = _media_block(catalog).get(_FORMAT_FROM)
    if isinstance(declared_from, dict):
        blocks[f"{_MEDIA_BLOCK}.{_FORMAT_FROM}"] = declared_from
    allowed = sorted(member.value for member in Format)
    for name, declared in blocks.items():
        for key, value in declared.items():
            if value in RESERVED_FORMATS:
                raise CatalogError(
                    f"loading catalog {catalog.source}: `{name}.{key}: {value}` is RESERVED — "
                    f"the design names it and nothing implements it (2G design §4, §11), so a "
                    f"catalog writing it is refused rather than read as something adjacent"
                )
            if value not in allowed:
                raise CatalogError(
                    f"loading catalog {catalog.source}: `{name}.{key}: {value}` is not one of "
                    f"{', '.join(allowed)} — D00's closed sets are closed (NFR-5)"
                )


# --- the hand-off ---------------------------------------------------------


def _question(endpoint: dict[str, Any], answer: _Answer) -> dict[str, Any]:
    """One `format_conflict` row for the 2K ledger (2G design §6): the wire
    identity, the candidates that were on the table, and the trail that
    reached the impasse. `candidates` is serialized here — the pass that
    builds a candidate is the one that knows its shape."""
    return {
        "protocol": endpoint.get("protocol"),
        "method": endpoint.get("method"),
        "path": endpoint.get("path"),
        "question": "format_conflict",
        "candidates": json.dumps(answer.candidates, sort_keys=True, separators=(",", ":")),
        "evidence": answer.trail,
    }


def _mime_list(column: object) -> list[str]:
    """The MIME strings one media column holds.

    The column is a JSON array of strings, or NULL (D01 §3): every writer of
    it goes through `to_json`/`json.dumps`, so the array is a contract rather
    than a hope. NULL is the only absence this reads — a column holding text
    that is not JSON raises `JSONDecodeError` out of this pass, and a column
    holding a JSON scalar returns no MIME strings. Neither is handled,
    deliberately: both mean a writer broke the column's contract, which is a
    defect to see rather than an emptiness to absorb."""
    if column is None:
        return []
    parsed = json.loads(str(column))
    return [str(entry) for entry in parsed] if isinstance(parsed, list) else []
