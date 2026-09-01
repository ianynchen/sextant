"""`schema_operations` engine for endpoint derivation (D02 §2's
`schema_operations` style, 2H design §3).

The ninth style, and the first whose evidence is neither a call site, an
annotation nor a configuration key: **a schema file states the operations
outright**. A schema-first service — a hand-built runtime wiring, no mapping
annotation anywhere — derives nothing at all without it, and the schema is
the contract that service publishes.

**What it reads** is the module's `declared_shape` universe, the facts the one
descriptor interpreter emits (2G design §3). One field of one of those facts
answers the whole root question: `DeclaredShapeFact.role` names the operation
root a type serves, set upstream from the schema's own bindings — a `schema {
query: MyQuery }` block, an `extend schema`, or the format's default root
names where nothing binds at all, with a conflicting binding already failing
into a gap before any fact is written. **This engine therefore parses no
schema and re-derives no root name.** Which type is the query root is a FACT
because it is renameable, and no pass outside that one interpreter may learn a
schema format (2H design §2).

**What it derives** is one row per field of a root type, at the wire identity
D01 states for a root operation — `(graphql, query|mutation|subscription,
<field>)`, the operation-kind column value coming from the catalog.
`direction` and `protocol` are the catalog's own; `evidence` is `declared`
(2H design §2: the schema is a file in the repository, and the format whose
roots are operations has no compiled origin); `resolution` is `resolved`,
because the schema states the operation outright and nothing about the
address was left unread. `handler` and `caller` are both NULL: the schema
names no code, and the wiring that would is explicitly not read (2H design
§3, recorded as a COVERAGE boundary). `request_shape` is NULL for the same
kind of reason — a root field's ARGUMENTS are what the operation takes, and
the interpreter deliberately does not project them, so there is nothing here
to carry.

**Agreement with the annotation catalogs rides two existing mechanics** (2H
design §3), neither of them new:

* the INSERT goes through the same insert-if-absent guard every call-site
  style uses (`derive_call_endpoints.sql`), and this style runs after every
  annotation engine (`resolve/endpoints.py`'s `_RUNS_LAST`) — so an operation
  an annotation already derived keeps THAT row, with the handler symbol only
  the annotation knows;
* the STAMP then fills `response_shape` on every matching identity that still
  has none (`stamp_declared_response.sql`, whose header states exactly which
  rows that reaches and which of them keep it).

The schema format's name, the operation-kind column values and the protocol
are catalog data. No format name and no framework name appears in this
module.
"""

import json
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.domain.closed_sets import Evidence, Resolution

_OPERATIONS = "schema_operations"


def run(workspace: Workspace, catalog: Catalog) -> None:
    """Derives this catalog's root operations, then stamps their declared
    response shapes.

    Both halves walk the same rows, in one pass over the declared universe:
    the identity a row is inserted at and the identity the stamp selects on
    are the same four columns, so building them apart would be two things to
    keep in step.
    """
    _validate_matches(catalog)
    declared = catalog.matches[_OPERATIONS]
    schema_format = str(declared["schema_format"])
    operations = declared["operations"]

    rows: list[dict[str, Any]] = []
    stamps: list[dict[str, Any]] = []
    # Deduplicated on the wire identity by the pass, because
    # `derive_call_endpoints.sql` cannot do it within a single batch (its own
    # header says so: the guard is evaluated against the table as it stood
    # before the statement began). Two facts CAN name one identity — a type
    # legitimately arrives twice when a shared name is declared per document —
    # and two rows for one operation would be the same operation counted
    # twice.
    seen: set[tuple[str, str]] = set()
    for shape in workspace.query("declared_shapes"):
        # The format gate is what makes this catalog's declared `protocol`
        # true of the rows below: `role` is a neutral field on every declared
        # shape (D00 §5), and only the schema format this catalog names states
        # operations THIS protocol serves. Without it, a second format that
        # one day carries roots would mint rows under a protocol nobody
        # declared for it.
        if str(shape["schema_format"]) != schema_format:
            continue
        role = shape["role"]
        if role is None:
            continue
        # A role the catalog does not name derives nothing — the `config_join`
        # rule for an unmapped binder name or serializer class, for the same
        # reason: an unmapped value is a gap to grow the catalog from, never a
        # column value to invent.
        method = operations.get(str(role))
        if method is None:
            continue
        for field in json.loads(str(shape["fields"])):
            # GraphQL renames nothing and the interpreter says so by writing
            # the declared name into `wire_name` too; `wire_name` is the
            # column D01 §5 makes the identity, so it is the one read here.
            path = str(field["wire_name"])
            if (str(method), path) in seen:
                continue
            seen.add((str(method), path))
            rows.append(_row(catalog, str(method), path))
            stamps.append(
                {
                    "protocol": catalog.protocol,
                    "direction": catalog.direction,
                    "method": str(method),
                    "path": path,
                    "response_shape": _declared_response(field),
                }
            )

    workspace.derive("call_endpoints", rows=rows)
    workspace.derive("stamp_declared_response", rows=stamps)


def _row(catalog: Catalog, method: str, path: str) -> dict[str, Any]:
    """One root operation's row. Every column this style cannot speak for is
    NULL rather than filled with a plausible value — the schema declares an
    operation and its type, and says nothing whatever about the code that
    serves it, the media it negotiates, or the arguments' own shapes.

    `response_shape` is NULL HERE and filled by the stamp, not set on the row:
    the schema's answer must reach the annotation twin that blocked this row
    just as much as it reaches this one, and a single statement doing both is
    one rule rather than two that can drift.
    """
    return {
        "protocol": catalog.protocol,
        "direction": catalog.direction,
        "method": method,
        "path": path,
        "handler": None,
        "caller": None,
        "peer": None,
        "handler_signature": None,
        "resolution": str(Resolution.RESOLVED),
        "evidence": str(Evidence.DECLARED),
        "catalog_id": catalog.id,
        "request_shape": None,
        "response_shape": None,
        "consumes": None,
        "produces": None,
    }


def _declared_response(field: dict[str, Any]) -> str:
    """A root field's declared type as D01 §5's
    `{wire_type, wire_format, nullable, shape_id?, item?}` descriptor.

    Reshaped, never re-derived: the interpreter that understands the schema
    format already answered every one of these in D00 §5b's wire vocabulary
    (`shapes/expansion.py`'s `_declared_rows_of` reshapes the same fields the
    same way for a shape's own field rows). The reference it produces is a
    SCHEMA-NAME identity — a shape id within the declared universe — and no
    join to a bytecode-derived class is attempted anywhere on this path: two
    shape universes describe one service, and matching them by simple name is
    a guess (2H design §4).

    Serialised with the same `sort_keys`/compact separators every other writer
    of these two columns uses, so two runs produce the same bytes (NFR-1) and
    `stamp_format.sql`'s column-equality match still finds the row.
    """
    described: dict[str, Any] = {
        "wire_type": field["wire_type"],
        "wire_format": field.get("wire_format"),
        "nullable": field["nullable"],
    }
    if field.get("shape_ref") is not None:
        described["shape_id"] = field["shape_ref"]
    if field.get("item") is not None:
        described["item"] = field["item"]
    return json.dumps(described, sort_keys=True, separators=(",", ":"))


def _validate_matches(catalog: Catalog) -> None:
    """Refuses a broken catalog before anything is read (the
    `config_join._validate_matches` precedent): `schema_format` selects which
    facts this catalog speaks for and every `operations` value is written
    straight into the `method` column, where a typo is indistinguishable from
    an observation.

    The `operations` KEYS are deliberately unchecked against a closed set: a
    role no fact ever carries simply matches nothing, which is the same
    "unmapped value is a gap, not a guess" answer `config_join` gives an
    unknown binder name — and D00's role vocabulary lives on the fact model,
    not in a set this layer could compare against without duplicating it.
    """
    block = catalog.matches.get(_OPERATIONS)
    if not isinstance(block, dict):
        raise CatalogError(
            f"loading catalog {catalog.source}: `matches` declares no `{_OPERATIONS}` "
            f"block — a `{_OPERATIONS}` catalog declares D02 §2's one vocabulary"
        )
    if not isinstance(block.get("schema_format"), str) or not block["schema_format"]:
        raise CatalogError(
            f"loading catalog {catalog.source}: `{_OPERATIONS}.schema_format` must name "
            f"the schema format whose roots this catalog's protocol serves (2H design §3)"
        )
    operations = block.get("operations")
    valid = (
        isinstance(operations, dict)
        and bool(operations)
        and all(isinstance(value, str) and value for value in operations.values())
    )
    if not valid:
        raise CatalogError(
            f"loading catalog {catalog.source}: `{_OPERATIONS}.operations` must be a "
            f"non-empty mapping of operation root to the `method` column value it "
            f"derives (D01's root-operation identity), got {operations!r}"
        )
