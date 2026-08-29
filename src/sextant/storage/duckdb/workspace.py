from pathlib import Path

import duckdb

_SQL_DIR = Path(__file__).parent

_NAMED_QUERIES = {
    "documents": "SELECT * FROM documents ORDER BY document_id",
    # `handler` is part of the ordering, not decoration: two mappings may share
    # a wire identity, and an ordering with ties is an ordering that can change
    # between runs (NFR-1).
    "endpoints": "SELECT * FROM endpoints ORDER BY protocol, method, path, handler",
    "shapes": "SELECT * FROM shapes ORDER BY shape_id",
    # `ordinal` alone would tie across shapes; `shape_id` first is what makes
    # the ordering total rather than merely stable within one shape (NFR-1).
    "shape_fields": "SELECT * FROM shape_fields ORDER BY shape_id, ordinal",
    # The field facts the shape pass expands, in declaration order within each
    # defining document — `seq` is what `ordinal` is derived from, so the
    # ordering is part of the answer rather than a convenience (NFR-1).
    #
    # The two modifiers come through because nothing else can say whether a
    # declared field reaches a payload: a constant bound to the type and a
    # field declared not serialized are as public and as typed as any other,
    # and a pass with nothing to filter on turns both into contract terms
    # nobody wrote. False where a scanner reports no modifiers at all — an
    # absent answer is not a claim that the field is off the wire.
    "fields": """
        SELECT symbol, document_id, seq, signature -> 'returns' AS returns,
               coalesce((modifiers ->> 'static')::BOOLEAN, false) AS "static",
               coalesce((modifiers ->> 'transient')::BOOLEAN, false) AS "transient"
        FROM symbols
        WHERE construct_kind = 'field'
        ORDER BY document_id, seq
    """,
    # The declared types the facts call enumerations. A reference to an
    # enumeration is indistinguishable from a reference to a record — only the
    # referenced type's own fact carries the construct kind — so the pass reads
    # them all once rather than looking one up per field.
    "enum_types": """
        SELECT symbol FROM symbols WHERE construct_kind = 'enum' ORDER BY symbol
    """,
    # Annotations on one target. Ordered by name so a target carrying two of
    # them is read the same way twice; which one wins is the caller's rule,
    # never this ordering.
    "annotations_of": """
        SELECT annotation, args, type_path FROM annotations WHERE target = ? ORDER BY annotation
    """,
    # Every annotation in the workspace, regardless of target — what a scope
    # rule (D02 §2e) needs: the class or package it was declared on is not the
    # field it claims, so `annotations_of`'s per-field lookup cannot find it.
    # Ordered so two fields under the same scope read its claim the same way.
    "annotations": """
        SELECT target, annotation, type_path FROM annotations ORDER BY target, annotation
    """,
    "coverage": """
        SELECT count(*) AS documents,
               sum(CASE WHEN partial THEN 1 ELSE 0 END) AS partial_documents
        FROM documents
    """,
    # A cheap read of what `analyze` already loaded — for `render`, which
    # queries the workspace instead of reloading fact files from disk.
    "facts": "SELECT count(*) AS facts FROM raw_facts",
}

_NAMED_DERIVATIONS = {
    "endpoints": "derive_endpoints.sql",
    "endpoints_reset": "reset_endpoints.sql",
    "endpoints_merge": "merge_endpoints.sql",
    "endpoint_contracts": "derive_endpoint_contracts.sql",
    "shapes": "derive_shapes.sql",
    "shape_fields": "derive_shape_fields.sql",
    "shapes_reset": "reset_shapes.sql",
}


class DuckDbWorkspace:
    """The Workspace port over DuckDB. Owns SQL and D01; knows nothing about
    frameworks, languages or protocols (ARCHITECTURE §10)."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = duckdb.connect(str(path))
        self._connection.execute((_SQL_DIR / "schema.sql").read_text(encoding="utf-8"))

    def load_facts(self, fact_root: Path) -> int:
        """One bulk statement over the whole tree. Per-row insertion is a
        defect under NFR-11 — the difference is orders of magnitude."""
        pattern = str(fact_root / "**" / "*.jsonl")
        self._connection.execute("DELETE FROM raw_facts")
        self._connection.execute(
            """
            INSERT INTO raw_facts
            SELECT json ->> 'kind', json ->> 'document_id', json
            FROM read_ndjson_objects(?)
            """,
            [pattern],
        )
        row = self._connection.execute("SELECT count(*) FROM raw_facts").fetchone()
        assert row is not None
        return int(row[0])

    def derive(self, name: str, **params: object) -> None:
        sql = (_SQL_DIR / _NAMED_DERIVATIONS[name]).read_text(encoding="utf-8")
        self._connection.execute(sql, params or None)

    def query(self, name: str, **params: object) -> list[dict[str, object]]:
        sql = _NAMED_QUERIES[name]
        cursor = self._connection.execute(sql, list(params.values()) or None)
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def close(self) -> None:
        self._connection.close()
