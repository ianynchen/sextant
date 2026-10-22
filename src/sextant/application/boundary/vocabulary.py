"""The boundary vocabulary (spec 2026-10-22-boundary-vocabulary-and-diff §2, FR-21): a
closed, versioned set of KINDS — the words a diff and an observability map use for what a
module exposes, calls, declares and configures — each naming the table its rows derive
from and splitting that table's columns three ways.

IDENTITY columns say which entry this is; two bundles' entries with equal identity are the
same entry. ATTRIBUTES are what a `changed` entry's `from`/`to` range over. EVIDENCE is
carried on every entry and compared by nothing. The split is the whole point: an endpoint
that moved controller is the same endpoint (the wire is the identity, the symbol is
evidence), while a data contract's content hash is an attribute, never its identity,
because the hash is what changes when a field is added — which is the `changed` entry the
drift scenario exists for.

It is DATA, one registry, read by the diff, the observability map and the exporter, so no
reader keeps its own list of kinds and the lists cannot drift. Adding a kind, or moving a
column between the three sets, changes what a comparison means without changing a table;
`BOUNDARY_VOCABULARY_VERSION` (in `domain/version.py` beside the other stamps) is what says
so, and it moves with any such edit here.

The tokens in `attributes` are the spec's terms, not always column names: "request_body"
is the field set a `request_shape` expands to, and "requirements" the set
`endpoint_metadata` holds. The query that reads each kind (`boundary_<kind>`, in the
workspace's query registry) is what turns a token into rows; this module only names them.

Enrichment never enters: components, prose and overlays are judgements, not facts.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Kind:
    """One row of the spec's §2 table.

    `table` is the workspace table the kind's rows come from, `None` for a kind read off
    `metadata.json`; `where` narrows that table to this kind's rows (two kinds share
    `endpoints`). `grounded_in_code` is True where a catalog writes the rows, which is the
    only case the observability map can call `not-observable` — a module's own metadata or
    a resolved config value is read off a file, not derived by a catalog that can be
    skipped."""

    name: str
    table: str | None
    where: str | None
    identity: tuple[str, ...]
    attributes: tuple[str, ...]
    evidence: tuple[str, ...]
    grounded_in_code: bool


_KIND_LIST = (
    Kind(
        name="module",
        table=None,
        where=None,
        identity=("module_id",),
        attributes=("kind", "languages", "dependency_source"),
        evidence=(),
        grounded_in_code=False,
    ),
    Kind(
        name="endpoint",
        table="endpoints",
        where="direction = 'inbound'",
        # The exposed address, per protocol: a topic for a broker, the operation name for
        # GraphQL, the operation's QName for SOAP. The handler is evidence, not identity.
        identity=("protocol", "method", "path"),
        attributes=(
            "request_body",
            "response_body",
            "consumes",
            "produces",
            "format",
            "requirements",
            "conditions",
            "resolution",
        ),
        evidence=("handler", "documents"),
        grounded_in_code=True,
    ),
    Kind(
        name="dependency",
        table="endpoints",
        where="direction = 'outbound'",
        # `peer` stays: `POST /v1/orders` on `billing` and on `ledger` are two dependencies.
        identity=("protocol", "method", "path", "peer"),
        attributes=("request_body", "response_body", "format", "headers", "resolution"),
        evidence=("caller", "documents"),
        grounded_in_code=True,
    ),
    Kind(
        name="data-contract",
        table="shapes",
        where=None,
        # The shape symbol, never `content_hash`: the hash is what CHANGES.
        identity=("shape_id",),
        attributes=("content_hash", "fields"),
        evidence=("document", "origin_tier"),
        grounded_in_code=True,
    ),
    Kind(
        name="boundary-property",
        table="resolved_config",
        where=None,
        identity=("key", "environment"),
        attributes=("value", "unresolved_reason"),
        evidence=("source",),
        grounded_in_code=False,
    ),
    Kind(
        name="schedule",
        table="scheduled_work",
        where=None,
        identity=("handler", "trigger"),
        attributes=("expression", "resolution"),
        evidence=("catalog",),
        grounded_in_code=True,
    ),
    Kind(
        name="error-handler",
        table="error_handlers",
        where=None,
        identity=("handler", "exception"),
        attributes=("advice", "scope", "status", "response_shape"),
        evidence=("catalog",),
        grounded_in_code=True,
    ),
)

KINDS: dict[str, Kind] = {kind.name: kind for kind in _KIND_LIST}


def kinds_fed_by(style: str, direction: str | None, has_shape_model: bool) -> tuple[str, ...]:
    """Which kinds a catalog's rows can feed (spec §4b), from fields every catalog already
    carries — a function, not a new catalog key.

    `scheduled_work` writes `scheduled_work` and `error_advice` writes `error_handlers`, so
    each feeds exactly its own kind. Every other style writes `endpoints`: `inbound` feeds
    `endpoint`, `outbound` feeds `dependency`, `both` feeds both. A declared `shape_model`
    additionally feeds `data-contract`. The result follows registry order."""
    if style == "scheduled_work":
        return ("schedule",)
    if style == "error_advice":
        return ("error-handler",)
    fed = set[str]()
    if direction in ("inbound", "both"):
        fed.add("endpoint")
    if direction in ("outbound", "both"):
        fed.add("dependency")
    if has_shape_model:
        fed.add("data-contract")
    return tuple(name for name in KINDS if name in fed)
