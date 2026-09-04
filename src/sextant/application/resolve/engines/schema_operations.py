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
`direction` and `protocol` are the catalog's own; `evidence` is the
DECLARING SHAPE'S OWN tier, so a row never claims one the schema did not earn
(a schema file in the repository is `declared`, one the compiler embedded is
`compiler` — D00 §3, and the shape's fact already decided which); `resolution`
is `resolved`, because the schema states the operation outright and nothing
about the address was left unread. `handler` and `caller` are both NULL: the
schema names no code, and the wiring that would is explicitly not read (2H
design §3, recorded as a COVERAGE boundary). `request_shape` is NULL for the
same kind of reason — a root field's ARGUMENTS are what the operation takes, and
the interpreter deliberately does not project them, so there is nothing here
to carry.

**A `role` of the literal word `"operation"` (2I, this task) derives
differently — one row per SHAPE, never per field, and the one case where this
engine hardcodes a role name rather than reading it off catalog data.** A WSDL
input element's shape IS the operation (2I Task 3): the wrapper element is the
whole request payload, not a type some root field merely returns, so there is
no "field of a root type" here to iterate — deriving one row per FIELD would
mint an endpoint per element of the request body, the same defect a per-field
pass over an ordinary payload type would commit. `path` is the shape's own
schema name; `method` is NULL, because SOAP is verbless like every other
non-HTTP protocol (D02 §2, amended) — never the catalog's mapped value, which
this branch does not read. `request_shape` is NOT NULL here, unlike the
per-field case above: the wrapper is wire-true (2I design §4), so the
operation's request shape is the very shape this row derives from, carried as
a self-referencing descriptor. `response_shape` stays NULL and gets no stamp
at all — 2I Task 3 marks INPUT elements only, so no fact links an operation to
an output message, and inventing that join is explicitly out of this task's
scope (a later task's to read, honestly absent until then). Every other
column — `handler`, `caller`, `evidence`, `resolution` — reads exactly as the
per-field case above.

**gRPC (2O design §1a, Task 4) is the same per-shape branch, over a shape that
answers the output side WSDL's own boundary leaves NULL.** A descriptor
`service` method's own shape carries `DeclaredShapeFact.operation` — the
`{input_ref, output_ref, client_streaming, server_streaming}` sub-record the
2G interpreter's protobuf branch now fills — so the branch below reads it
straight off the fact rather than self-referencing the shape the way the WSDL
case does: `request_shape`/`response_shape` are two DIFFERENT descriptors,
each an intra-descriptor join to the SAME descriptor's message shapes
(`input_ref`/`output_ref`, never a guess across universes). Streaming carries
alongside `response_shape`'s own `shape_id`, under a `streaming` key no other
format's descriptor ever writes — `unary`, `server-streaming`,
`client-streaming` or `bidi` — read by the module document's detail block
(2M design §5b) and nowhere else: it joins on nothing, so it is not a new
`endpoints` column, the explicit ruling 2O design §1a states. `path` is the
shape's own `schema_name` (`<protoPackage>.<Service>/<Method>`, D01's gRPC
identity table) exactly as the WSDL case's `path` is; `method` stays NULL for
the same reason — gRPC is as verbless as SOAP (D02 §2, amended).

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
from sextant.domain.closed_sets import Resolution

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
    #
    # `method` is `None` for a per-SHAPE identity (below) — SOAP is verbless,
    # same as every other non-HTTP protocol (D02 §2, amended) — so the set
    # widens to hold it rather than gaining a second seen-set for one style.
    seen: set[tuple[str | None, str]] = set()
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
        # column value to invent. `operations.get` still GATES `"operation"`
        # (2I design, this task): a catalog must name the role to be read at
        # all, the same as `query`/`mutation`/`subscription`. Its MAPPED VALUE
        # is not, though — the branch below never reads `method` — because
        # unlike a GraphQL root kind, WSDL's `role="operation"` names no verb
        # for the catalog to spell; the mapping entry exists to be present,
        # not to be read.
        method = operations.get(str(role))
        if method is None:
            continue
        # `role == "operation"` (2I design §3, this task's own ruling): a WSDL
        # input element's shape IS the operation — 2I Task 3 marks the shape
        # itself, not one of its fields, with the role — so this branch
        # derives exactly one row from the SHAPE, never from its fields. The
        # graphql `query`/`mutation`/`subscription` branch below is
        # untouched: those roles name a ROOT TYPE whose FIELDS are the
        # operations, a different shape of fact entirely, and this new branch
        # runs before it ever sees one of that role's shapes reach the loop
        # (`continue`, not `elif`, so nothing after it can also fire for the
        # same shape).
        if str(role) == "operation":
            # `symbol` is what `declared_shapes` selects — `schema_name`
            # itself is deliberately unselected there (DR-4 precedence's own
            # concern, settled upstream) — but for a schema-only fact the two
            # are the identical value: `wsdl_xsd.py`'s own `_add_shape` writes
            # `symbol=qualified, schema_name=qualified` because a contract
            # file compiles to no class, so there is no second naming for
            # `schema_name` to bridge; `protobuf.py`'s `_service_shapes`
            # (2O design §1a) gives an RPC method's shape the identical
            # treatment for the identical reason — it travels as no class of
            # its own either. Reading `symbol` here is reading `schema_name`
            # under the one name this query carries.
            path = str(shape["symbol"])
            if (None, path) in seen:
                continue
            seen.add((None, path))
            # `payload -> 'operation'` (the JSON, not text, extractor —
            # `workspace.py`'s own choice, kept so `json.loads` below can read
            # a nested object): a JSON `null` value comes back as the STRING
            # `"null"`, not SQL NULL, because pydantic always writes the key
            # (`OperationRecord | None = None` still dumps `"operation":
            # null` for every message-typed shape) — so parsing FIRST and
            # checking the parsed result, rather than the raw column, is what
            # tells a WSDL shape's absent record apart from a gRPC shape's
            # real one either way a duckdb version happens to hand it back.
            raw_operation = shape["operation"]
            operation = None if raw_operation is None else json.loads(str(raw_operation))
            if operation is None:
                rows.append(_operation_row(catalog, path, str(shape["evidence"])))
            else:
                # gRPC's own shape of this branch (2O design §1a): the
                # sub-record names BOTH sides, so there is a real response to
                # derive here, not merely a request self-reference.
                rows.append(_grpc_operation_row(catalog, path, str(shape["evidence"]), operation))
            # No stamp: `stamps` fills a row's `response_shape` from the
            # OUTPUT side of an operation, coalescing what a pre-existing
            # annotation twin left NULL — and gRPC's row above already CARRIES
            # its own `response_shape`, so stamping it would only ever find a
            # row that has nothing to coalesce. 2I Task 3 marks WSDL's INPUT
            # elements only — no `declared_shape` fact links a WSDL operation
            # to what its output message names, so there is nothing here to
            # coalesce a response from either. Inventing one by, say, guessing
            # at an output element's name would be exactly the guess D00 §3
            # rules out; the WSDL row's `response_shape` stays NULL, honestly,
            # until a later task reads the output side.
            continue
        for field in json.loads(str(shape["fields"])):
            # GraphQL renames nothing and the interpreter says so by writing
            # the declared name into `wire_name` too; `wire_name` is the
            # column D01 §5 makes the identity, so it is the one read here.
            path = str(field["wire_name"])
            if (str(method), path) in seen:
                continue
            seen.add((str(method), path))
            rows.append(_row(catalog, str(method), path, str(shape["evidence"])))
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


def _row(catalog: Catalog, method: str | None, path: str, evidence: str) -> dict[str, Any]:
    """One root operation's row. Every column this style cannot speak for is
    NULL rather than filled with a plausible value — the schema declares an
    operation and its type, and says nothing whatever about the code that
    serves it, the media it negotiates, or the arguments' own shapes.

    `evidence` is the DECLARING SHAPE's own, carried rather than restated: the
    interpreter already decided which tier a schema earned (D00 §3 —
    `declared` for a repository file, `compiler` for one the build embedded),
    and a literal here would be this engine claiming a tier on the schema's
    behalf, wrong the first time a format arrives with a compiled origin.

    `response_shape` is NULL HERE and filled by the stamp, not set on the row:
    the schema's answer must reach the annotation twin that blocked this row
    just as much as it reaches this one, and a single statement doing both is
    one rule rather than two that can drift. (The per-shape `"operation"`
    branch appends no stamp at all — this task's own stated boundary, in
    `run`'s comment beside its `continue` — so `response_shape` simply stays
    NULL on those rows.)

    `method` is `None` for a per-shape `"operation"` row: SOAP is verbless,
    like every other non-HTTP protocol (D02 §2, amended), and `_operation_row`
    below is the one caller that passes it.
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
        "evidence": evidence,
        "catalog_id": catalog.id,
        "request_shape": None,
        "response_shape": None,
        "consumes": None,
        "produces": None,
    }


def _operation_row(catalog: Catalog, path: str, evidence: str) -> dict[str, Any]:
    """The `role == "operation"` row `_row` cannot fully state on its own:
    every column but one reads exactly as `_row` already writes it (`method`
    NULL, `handler`/`caller` NULL, `response_shape` NULL — this task's stated
    boundary), so this wraps `_row` rather than repeating its fields.

    `request_shape` is the one column that differs, and it is NOT NULL here —
    the one place this style's `request_shape` is ever set. 2I design §4's
    ruling is that the wrapper element is wire-true: unlike a GraphQL root
    field, whose ARGUMENTS the interpreter does not project (`_row`'s own
    docstring, the per-field branch above), a WSDL operation's request payload
    IS the shape this row was derived from — the input element wraps the
    whole request body, so the operation and its request shape are one
    schema-universe fact, not two. The descriptor self-references `path` by
    `shape_id`, in the exact `{wire_type, wire_format, nullable, shape_id}`
    grammar `wsdl_xsd.py` already writes for an element-typed-by-a-named-type
    reference (D01 §5) — reused rather than invented, and serialised the same
    deterministic way (`sort_keys`, compact separators — NFR-1) `_declared_
    response` below already does for the sibling column.
    """
    row = _row(catalog, None, path, evidence)
    row["request_shape"] = json.dumps(
        {"wire_type": "object", "wire_format": None, "nullable": False, "shape_id": path},
        sort_keys=True,
        separators=(",", ":"),
    )
    return row


def _grpc_operation_row(
    catalog: Catalog, path: str, evidence: str, operation: dict[str, Any]
) -> dict[str, Any]:
    """gRPC's own shape of the per-shape `"operation"` row (2O design §1a,
    Task 4) — everything but the two payload columns reads exactly as
    `_operation_row` above (`method` NULL, `handler`/`caller` NULL), so this
    wraps `_row` the identical way rather than repeating its fields.

    Both `request_shape` AND `response_shape` are set here, unlike the WSDL
    case: a gRPC method names TWO independent message types, never one shape
    wrapping the other, so there is no self-reference to make — `operation`'s
    own `input_ref`/`output_ref` are the descriptor's fully-qualified names
    for the SAME descriptor's message shapes, read straight off the fact
    (an intra-descriptor join `protobuf.py`'s `_service_shapes` already made,
    never a guess across universes here).

    Streaming rides beside `response_shape`'s own `shape_id` rather than
    becoming a new `endpoints` column — the explicit ruling 2O design §1a
    states. It could as easily sit on `request_shape` (client streaming is a
    property of the REQUEST side); it sits on the response side instead
    because gRPC's four-way vocabulary (`unary`/`server-streaming`/
    `client-streaming`/`bidi`) is a property of the OPERATION as a whole, and
    one column needs to carry the combined word rather than each side stating
    its own half. `_shape_descriptor`'s `streaming` key is written under a
    name no other schema format's descriptor ever uses — every existing
    reader of `request_shape`/`response_shape` (`document.py`'s detail block,
    `shapes/contracts.py`'s expansion) either ignores an unknown key or reads
    only `shape_id`/`item`, so this costs nothing beside the columns that
    already exist."""
    row = _row(catalog, None, path, evidence)
    row["request_shape"] = _shape_descriptor(str(operation["input_ref"]))
    row["response_shape"] = _shape_descriptor(
        str(operation["output_ref"]), streaming=_streaming_word(operation)
    )
    return row


def _streaming_word(operation: dict[str, Any]) -> str:
    """The four-way vocabulary 2O design §1a states verbatim, derived from
    the two flags the descriptor itself carries — never a guess, since a
    protobuf `service` method states both independently and every one of the
    four combinations is a real, legal RPC shape."""
    client = bool(operation["client_streaming"])
    server = bool(operation["server_streaming"])
    if client and server:
        return "bidi"
    if server:
        return "server-streaming"
    if client:
        return "client-streaming"
    return "unary"


def _shape_descriptor(shape_id: str, streaming: str | None = None) -> str:
    """D01 §5's `{wire_type, wire_format, nullable, shape_id}` descriptor for
    a gRPC operation's own request or response — always `object`, never
    nullable (a gRPC message field is always present, protobuf's own
    proto3 rule `protobuf.py`'s `_protobuf_element` already applies to every
    message-typed field) — with `streaming` appended only where the caller
    passes one, the one column-pair use of that key (this module's own,
    `_grpc_operation_row`'s docstring). Serialised the same deterministic way
    (`sort_keys`, compact separators — NFR-1) every other writer of these two
    columns uses."""
    described: dict[str, Any] = {
        "wire_type": "object",
        "wire_format": None,
        "nullable": False,
        "shape_id": shape_id,
    }
    if streaming is not None:
        described["streaming"] = streaming
    return json.dumps(described, sort_keys=True, separators=(",", ":"))


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
    facts this catalog speaks for, and every `operations` value except
    `"operation"`'s own (`run`'s comment beside its `operations.get` call) is
    written straight into the `method` column, where a typo is
    indistinguishable from an observation. `"operation"`'s value is still
    required to be a non-empty string — nothing here excuses it from the rule
    below — it is simply never read past that check.

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
