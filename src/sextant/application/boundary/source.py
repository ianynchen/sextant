"""A read-only source of boundary rows over a module's workspace or an exported bundle
(spec 2026-10-22-boundary-vocabulary-and-diff §3a): the one reader the diff and nothing else
will use, so a comparison sees a workspace and a bundle through the same rows.

It returns each side VERBATIM. Masking is the diff's job (§3d) and is done to both sides
alike — a bundle's addresses and values are masked at export and a workspace's are not, so
a source that masked would hide exactly the difference the diff must account for.

**Rows are grouped on identity.** The query for a kind returns one row per table row; here
the rows sharing the kind's identity columns become ONE row carrying the set of symbols that
ground it, because the wire is the identity and the symbol is evidence (§2): four handlers
behind `GET /**` are one endpoint with four pieces of evidence. NULL equals NULL for this
purpose — two `sendDefault` calls to one peer, whose method and path could not be read, are
one dependency — so the grouping is done on Python tuples, never with SQL equality.

**No silent choice among candidates.** Where the rows grouped under one identity DISAGREE
about an attribute (one method with two `@Scheduled(cron=...)` is one `(handler, trigger)`
with two expressions; handlers behind `GET /**` with different request shapes), the
attribute's value is `{"several": [the distinct values, sorted]}` — sorted by their JSON
serialisation with `sort_keys=True`, which is how lists and dicts order — and where they
agree it is the single value.
This holds for every attribute of every kind, including the field sets and the evidence
columns `origin_tier` and `source`. A reader comparing two rows meets the dict and sees the
disagreement itself, not whichever row the query happened to order first. `requirements`,
`conditions` and `headers` are sets and stay unions.

A stated limit: `dependency.headers` cannot be told apart across two dependencies that share
a caller and an unread address, because `endpoint_metadata` carries no `peer`; both read
the same metadata rows.

A row is a dict keyed by the kind's identity columns, then its attributes under the names
`ROW_KEYS` gives (`request`/`response` are what the vocabulary calls `request_body`/
`response_body`), then `evidence` — `symbols` and `documents`, both sorted, and
whichever of `catalogs`, `source` or `origin_tier` the kind's evidence columns name — and
`origin`.
"""

import json
from collections.abc import Callable, Iterable
from pathlib import Path

from sextant.application.boundary.vocabulary import Kind
from sextant.application.ports.workspace import GraphReader

# The vocabulary's attribute tokens that are not the row's key for them (the vocabulary
# says "request_body"; the row says `request`).
ROW_KEYS = {"request_body": "request", "response_body": "response"}

# The stamps a side is compared on (§3c), under the names the bundle manifest's `producer`
# gives them. `redaction_set_hash` is a bundle's alone: `analyze` applies no rule set, so a
# workspace has none until the diff computes it from the module's own `.sextant.yml`.
STAMPS = (
    "sextant_version",
    "fact_schema_version",
    "graph_schema_version",
    "boundary_vocabulary_version",
    "catalog_hash",
    "redaction_set_hash",
)

_QUERY_OF = {
    "endpoint": "boundary_endpoint",
    "dependency": "boundary_dependency",
    "data-contract": "boundary_contract",
    "boundary-property": "boundary_property",
    "schedule": "boundary_schedule",
    "error-handler": "boundary_error_handler",
}

# What ties an `endpoint_metadata` / `endpoint_conditions` row to the `endpoints` row it
# belongs to: the wire identity with the direction, then the symbol that distinguishes two
# rows at one address. `endpoint_metadata` names that symbol in its `caller` column for
# every row, and the writers put different things there: an INBOUND row's is the handler
# (`request_requirements._entry`, `endpoint_attributes._entry`, `single_call`'s inbound
# rows), whose `endpoints` row has a NULL `caller`; an outbound row's is the calling method,
# which the `endpoints` row carries as `caller`. So an `endpoint` is matched on its
# `handler` and a `dependency` on its `caller`, against the metadata's one column.
_METADATA_KEY = ("protocol", "direction", "method", "path", "caller")
_ENDPOINT_METADATA_KEY = ("protocol", "direction", "method", "path", "handler")
_DEPENDENCY_METADATA_KEY = _METADATA_KEY
_CONDITION_KEY = ("protocol", "direction", "method", "path", "handler")
_FIELD_KEYS = ("wire_name", "wire_type", "wire_format", "required", "nullable")


class NotABoundarySource(ValueError):
    """The path is neither a workspace nor a bundle this source can read. Carries the path
    and what was looked for; the facade turns it into the refusal `render` and `export`
    already raise (`api` may name `NotAnalyzedError`, this layer may not)."""

    def __init__(self, path: Path, looked_for: str) -> None:
        super().__init__(f"{path} is not a boundary source: {looked_for}")
        self.path = path
        self.looked_for = looked_for


def _present_first(value: object) -> tuple[bool, str]:
    return (value is not None, "" if value is None else str(value))


def _agreed(values: Iterable[object]) -> object:
    """The one value the rows agree on, or `{"several": [...]}` naming every distinct value
    where they do not (see the module docstring)."""
    distinct = {json.dumps(value, sort_keys=True, default=str): value for value in values}
    if len(distinct) == 1:
        return next(iter(distinct.values()))
    return {"several": [distinct[key] for key in sorted(distinct)]}


def _attributes(members: list[dict[str, object]], *columns: str) -> dict[str, object]:
    return {column: _agreed(row[column] for row in members) for column in columns}


def _by(*columns: str) -> Callable[[dict[str, object]], tuple[tuple[bool, str], ...]]:
    """A sort key over the named columns that tolerates NULL, which Python will not order
    against text. Deterministic, which is all it has to be."""

    def key(row: dict[str, object]) -> tuple[tuple[bool, str], ...]:
        return tuple(_present_first(row.get(column)) for column in columns)

    return key


class BoundarySource:
    """One side of a comparison. `open` it, ask for `rows` per kind, `close` it."""

    def __init__(self, graph: GraphReader) -> None:
        self._graph = graph
        # Each read below is made once, on first use, and shared by every kind that wants it.
        self._field_sets: dict[str, list[dict[str, object]]] | None = None
        self._requirements: dict[tuple[object, ...], list[dict[str, object]]] | None = None
        self._headers: dict[tuple[object, ...], list[dict[str, object]]] | None = None
        self._conditions: dict[tuple[object, ...], list[dict[str, object]]] | None = None
        self._symbol_documents: dict[str, list[tuple[str, str | None]]] | None = None
        self._shape_documents: dict[str, list[tuple[str, str | None]]] | None = None

    @classmethod
    def open(cls, path: Path, open_graph: Callable[[Path], GraphReader]) -> "BoundarySource":
        """`path` is `<module>/.sextant`, `<module>` (whose `.sextant` is used) or a bundle
        directory. `open_graph` opens it read-only and describes it (`storage` provides it;
        this layer reads no files and cannot import `storage`). Raises `NotABoundarySource`."""
        return cls(open_graph(path))

    @property
    def module_id(self) -> str:
        return str(self._graph.module["id"])

    @property
    def commit(self) -> str:
        return self._graph.commit

    @property
    def producer(self) -> dict[str, object]:
        """The stamps this side carries, under `STAMPS`' names; one it lacks is absent."""
        return self._graph.producer

    @property
    def environments(self) -> list[str]:
        return self._graph.environments

    @property
    def is_bundle(self) -> bool:
        return self._graph.is_bundle

    @property
    def module_root(self) -> Path | None:
        """The directory above the workspace — the module, for the usual `<module>/.sextant`
        layout — where `.sextant.yml` lives; `None` for a bundle, which has none."""
        return self._graph.module_root

    def close(self) -> None:
        self._graph.close()

    # --- rows -------------------------------------------------------------------------

    def rows(self, kind: Kind) -> list[dict[str, object]]:
        """Every entry of `kind`, one per identity, sorted by identity."""
        if kind.name == "module":
            return [self._module_row(kind)]
        found = self._graph.query(_QUERY_OF[kind.name])
        groups: dict[tuple[object, ...], list[dict[str, object]]] = {}
        for row in found:
            groups.setdefault(tuple(row[column] for column in kind.identity), []).append(row)
        build = {
            "endpoint": self._endpoint,
            "dependency": self._dependency,
            "data-contract": self._contract,
            "boundary-property": self._property,
            "schedule": self._schedule,
            "error-handler": self._error_handler,
        }[kind.name]
        built = [build(kind, members) for members in groups.values()]
        return sorted(built, key=_by(*kind.identity))

    def _module_row(self, kind: Kind) -> dict[str, object]:
        return {
            "module_id": self.module_id,
            **{name: self._graph.module.get(name) for name in kind.attributes},
            "evidence": {"symbols": [], "documents": []},
            "origin": "module_output",
        }

    def _endpoint(self, kind: Kind, members: list[dict[str, object]]) -> dict[str, object]:
        return {
            **{column: members[0][column] for column in kind.identity},
            **self._payloads(members),
            **_attributes(members, "consumes", "produces", "format"),
            "requirements": self._merged(
                self._requirements_by_row(), members, _ENDPOINT_METADATA_KEY, ("kind", "name")
            ),
            "conditions": self._merged(
                self._conditions_by_row(),
                members,
                _CONDITION_KEY,
                ("kind", "expression", "environment"),
            ),
            **_attributes(members, "resolution"),
            **self._wire_evidence(members, "handler"),
        }

    def _dependency(self, kind: Kind, members: list[dict[str, object]]) -> dict[str, object]:
        return {
            **{column: members[0][column] for column in kind.identity},
            **self._payloads(members),
            **_attributes(members, "format"),
            "headers": self._merged(
                self._headers_by_row(), members, _DEPENDENCY_METADATA_KEY, ("name", "value")
            ),
            **_attributes(members, "resolution"),
            **self._wire_evidence(members, "caller"),
        }

    def _contract(self, kind: Kind, members: list[dict[str, object]]) -> dict[str, object]:
        shape_id = str(members[0]["shape_id"])
        documents = self._documents_of_shape(shape_id)
        return {
            "shape_id": shape_id,
            **_attributes(members, "content_hash"),
            "fields": list(self._fields_by_shape().get(shape_id, [])),
            "evidence": {
                "symbols": [],
                "documents": _paths(documents),
                **_attributes(members, "origin_tier"),
            },
            "origin": _origin(documents),
        }

    def _property(self, kind: Kind, members: list[dict[str, object]]) -> dict[str, object]:
        return {
            "key": members[0]["key"],
            "environment": members[0]["environment"],
            **_attributes(members, "value", "unresolved_reason"),
            "evidence": {"symbols": [], "documents": [], **_attributes(members, "source")},
            "origin": "module_output",
        }

    def _schedule(self, kind: Kind, members: list[dict[str, object]]) -> dict[str, object]:
        return {
            "handler": members[0]["handler"],
            "trigger": members[0]["trigger"],
            **_attributes(members, "expression", "resolution"),
            **self._handler_evidence(members),
        }

    def _error_handler(self, kind: Kind, members: list[dict[str, object]]) -> dict[str, object]:
        return {
            "handler": members[0]["handler"],
            "exception": members[0]["exception"],
            **_attributes(members, "advice", "scope", "status", "response_shape"),
            **self._handler_evidence(members),
        }

    # --- evidence ---------------------------------------------------------------------

    def _wire_evidence(
        self, members: list[dict[str, object]], symbol_column: str
    ) -> dict[str, object]:
        symbols = {str(row[symbol_column]) for row in members if row[symbol_column] is not None}
        documents = [pair for symbol in symbols for pair in self._documents_of_symbol(symbol)]
        return {
            "evidence": {"symbols": sorted(symbols), "documents": _paths(documents)},
            "origin": _origin(documents),
        }

    def _handler_evidence(self, members: list[dict[str, object]]) -> dict[str, object]:
        handler = str(members[0]["handler"])
        documents = self._documents_of_symbol(handler)
        catalogs = sorted({str(row["catalog_id"]) for row in members if row["catalog_id"]})
        return {
            "evidence": {
                "symbols": [handler],
                "documents": _paths(documents),
                "catalogs": catalogs,
            },
            "origin": _origin(documents),
        }

    def _documents_of_symbol(self, symbol: str) -> list[tuple[str, str | None]]:
        if self._symbol_documents is None:
            self._symbol_documents = _pairs_by(
                self._graph.query("boundary_symbol_documents"), "symbol"
            )
        return self._symbol_documents.get(symbol, [])

    def _documents_of_shape(self, shape_id: str) -> list[tuple[str, str | None]]:
        if self._shape_documents is None:
            self._shape_documents = _pairs_by(
                self._graph.query("boundary_shape_documents"), "shape_id"
            )
        return self._shape_documents.get(shape_id, [])

    # --- bodies, requirements, headers, conditions -------------------------------------

    def _fields_by_shape(self) -> dict[str, list[dict[str, object]]]:
        if self._field_sets is None:
            by_shape: dict[str, list[dict[str, object]]] = {}
            for row in self._graph.query("shape_fields"):
                by_shape.setdefault(str(row["shape_id"]), []).append(
                    {key: row[key] for key in _FIELD_KEYS}
                )
            self._field_sets = {
                shape: sorted(fields, key=_by("wire_name")) for shape, fields in by_shape.items()
            }
        return self._field_sets

    def _payloads(self, members: list[dict[str, object]]) -> dict[str, object]:
        """`request`/`response`: the field set of the shape the descriptor names, or `None`
        where the row declares no payload. The raw descriptors ride along under their column
        names, because the field set alone cannot tell an `OrderView` from a list of them or a
        shapeless string from nothing."""
        return {
            "request": _agreed(self._field_set(row["request_shape"]) for row in members),
            "response": _agreed(self._field_set(row["response_shape"]) for row in members),
            **_attributes(members, "request_shape", "response_shape"),
        }

    def _field_set(self, descriptor: object) -> list[dict[str, object]] | None:
        if descriptor is None:
            return None
        node: object = json.loads(str(descriptor))
        # A collection's shape sits in its `item`: the same shape, one level down.
        while isinstance(node, dict):
            shape_id = node.get("shape_id")
            if shape_id is not None:
                return list(self._fields_by_shape().get(str(shape_id), []))
            node = node.get("item")
        return []

    def _requirements_by_row(self) -> dict[tuple[object, ...], list[dict[str, object]]]:
        if self._requirements is None:
            self._read_metadata()
        assert self._requirements is not None
        return self._requirements

    def _headers_by_row(self) -> dict[tuple[object, ...], list[dict[str, object]]]:
        if self._headers is None:
            self._read_metadata()
        assert self._headers is not None
        return self._headers

    def _read_metadata(self) -> None:
        self._requirements, self._headers = {}, {}
        for row in self._graph.query("endpoint_metadata"):
            key = _row_key(row, _METADATA_KEY)
            self._requirements.setdefault(key, []).append(
                {"kind": row["kind"], "name": row["name"], "requirement": row["requirement"]}
            )
            if row["kind"] == "header":
                self._headers.setdefault(key, []).append(
                    {"name": row["name"], "value": row["value"]}
                )

    def _conditions_by_row(self) -> dict[tuple[object, ...], list[dict[str, object]]]:
        if self._conditions is None:
            self._conditions = {}
            for row in self._graph.query("endpoint_conditions"):
                key = _row_key(row, _CONDITION_KEY)
                self._conditions.setdefault(key, []).append(
                    {
                        "kind": row["kind"],
                        "expression": row["expression"],
                        "environment": row["environment"],
                        "holds": row["holds"],
                    }
                )
        return self._conditions

    @staticmethod
    def _merged(
        by_row: dict[tuple[object, ...], list[dict[str, object]]],
        members: list[dict[str, object]],
        columns: tuple[str, ...],
        order: tuple[str, ...],
    ) -> list[dict[str, object]]:
        """What the table holds for any of the group's rows, once each, sorted: a set,
        whose order the table never promised (a `name` may be NULL: a Kafka key has none)."""
        seen: dict[str, dict[str, object]] = {}
        for member in members:
            for entry in by_row.get(_row_key(member, columns), []):
                seen[json.dumps(entry, sort_keys=True)] = entry
        return sorted(seen.values(), key=_by(*order))


def _row_key(row: dict[str, object], columns: Iterable[str]) -> tuple[object, ...]:
    return tuple(row[column] for column in columns)


def _pairs_by(rows: list[dict[str, object]], key: str) -> dict[str, list[tuple[str, str | None]]]:
    found: dict[str, list[tuple[str, str | None]]] = {}
    for row in rows:
        tier = row["origin_tier"]
        found.setdefault(str(row[key]), []).append(
            (str(row["relative_path"]), None if tier is None else str(tier))
        )
    return found


def _paths(documents: Iterable[tuple[str, str | None]]) -> list[str]:
    return sorted({path for path, _ in documents})


def _origin(documents: Iterable[tuple[str, str | None]]) -> str:
    """`dependency` only where every document that grounds the row is one — a boundary that
    any of the module's own output declares is the module's. A row with no document
    (a schema-declared operation) is the module's too."""
    tiers = {tier for _, tier in documents}
    return "dependency" if tiers and tiers == {"dependency"} else "module_output"
