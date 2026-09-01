from pathlib import Path

import duckdb

_SQL_DIR = Path(__file__).parent

_NAMED_QUERIES = {
    "documents": "SELECT * FROM documents ORDER BY document_id",
    # `handler` is part of the ordering, not decoration: two mappings may share
    # a wire identity, and an ordering with ties is an ordering that can change
    # between runs (NFR-1). `caller` closes the last tie: an outbound row has
    # no handler at all, so a messaging row whose destination could not be read
    # (`method`/`path`/`handler` all NULL — `sendDefault`, and a reply whose
    # `@SendTo` names nothing) ties with every other such row on the first four
    # columns, leaving their order the insert order rather than an ordering.
    "endpoints": "SELECT * FROM endpoints ORDER BY protocol, method, path, handler, caller",
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
    # `args` rides along for Task 6's effective-annotations pre-pass
    # (`resolve/effective_annotations.py`), which needs a composing type's
    # own declared attributes and not just which annotation it carries.
    # Ordered so two fields under the same scope read its claim the same way.
    "annotations": """
        SELECT target, annotation, args, type_path FROM annotations ORDER BY target, annotation
    """,
    # `ordinal` alone would tie across callers; `caller` first is what makes
    # the ordering total, the same reason `shape_fields` orders by
    # `shape_id, ordinal` rather than `ordinal` alone (NFR-1).
    "call_sites": "SELECT * FROM call_sites ORDER BY caller, ordinal",
    # D00 §5's field_write: constructors only, direct traces only — the field
    # resolution ladder's (2F) second rung, joining a `field`-kind argument's
    # symbol back to the parameter it was assigned from. Ordered by `field`
    # so a field written by more than one constructor overload reads its
    # candidates together, `from_parameter` breaking the tie (NFR-1).
    "field_writes": "SELECT field, from_parameter FROM field_writes ORDER BY field, from_parameter",
    # D00 §5a's PTR carrier: every declared type's own generic supertype
    # reference, keyed by the type's own (module-prefixed) symbol — the
    # `single_call` engine strips the prefix itself, the same way
    # `_enum_symbols` does, so this stays a plain projection like every other
    # named query. `json_type(...) NOT IN ('NULL')` is deliberate, not
    # `IS NOT NULL`: DuckDB's `->` returns the JSON scalar `'null'` (a string,
    # not SQL NULL) for a fact that explicitly recorded no supertype, and only
    # a genuinely absent key evaluates to SQL NULL — `IS NOT NULL` alone would
    # keep the explicit-null rows too and hand the engine a supertype to
    # follow that no fact ever carried.
    "supertypes": """
        SELECT payload ->> 'symbol' AS symbol, payload -> 'supertype' AS supertype
        FROM raw_facts
        WHERE kind = 'symbol' AND json_type(payload -> 'supertype') NOT IN ('NULL')
        ORDER BY symbol
    """,
    # `implemented_interfaces`: every class symbol's own declared interfaces,
    # keyed by the type's own (module-prefixed) symbol — Task 10 consumes this
    # the way `single_call` consumes `supertypes` above. Unlike `supertype`,
    # whose Python default is `None` (dumped as the JSON scalar `null`),
    # `interfaces`' default is an empty list — a hand-built or Python-written
    # fact always carries the key, empty or not, so `json_type(...) <> 'NULL'`
    # would keep every symbol. `json_array_length(...) > 0` excludes both a
    # genuinely absent key (SQL NULL propagates through the comparison) and an
    # explicit empty array the same way, which is what "a class implementing
    # none" must mean regardless of which writer produced the fact.
    "implementations": """
        SELECT payload ->> 'symbol' AS symbol, payload -> 'interfaces' AS interfaces
        FROM raw_facts
        WHERE kind = 'symbol' AND json_array_length(payload -> 'interfaces') > 0
        ORDER BY symbol
    """,
    # Every `declared_shape` fact (2G design §3), keyed by its own `symbol` —
    # the generated class a compiled schema type travels as, or the schema's
    # own full name for a source-origin one — with its `fields` JSON array
    # carried through verbatim for the expansion pass to project. Only the
    # columns expansion actually reads: `schema_name`/`schema_format`/`origin`
    # are DR-4 precedence's own concern, already settled upstream (`analyze`'s
    # `_prefer_compiled`) before a fact ever reaches this table — reselecting
    # `origin` here would read as if precedence lived in this query too.
    # Ordered by `(symbol, document_id)`, the same tiebreak the interpreter's
    # own sort uses for a symbol that legitimately arrives twice (a shared
    # nested type inlined into more than one schema payload), so which
    # occurrence wins a dict keyed on `symbol` never depends on read order
    # (NFR-1).
    # `schema_format` is the format ladder's rung 4 (2G design §5): the
    # schema that described this shape is the only thing that can say which
    # wire format the payload's own TYPE suggests. `role` is 2H's
    # `schema_operations` engine (D02 §2, 2H design §3): the operation root a
    # type serves, where its schema names one — re-added here WITH a consumer,
    # which is the rule the 2G trim enforced, and read by nothing else.
    # `schema_name`/`origin` stay unselected — DR-4 precedence is settled
    # upstream, in `analyze`'s `_prefer_compiled`, before a fact reaches this
    # table.
    "declared_shapes": """
        SELECT payload ->> 'symbol'        AS symbol,
               payload ->> 'evidence'      AS evidence,
               payload ->> 'schema_format' AS schema_format,
               payload ->> 'role'          AS role,
               payload ->  'fields'        AS fields
        FROM raw_facts WHERE kind = 'declared_shape'
        ORDER BY symbol, document_id
    """,
    # Every declared method symbol, module-prefixed exactly as the fact wrote
    # it — what `interface_implementation` joins a receiver back to (D02 §2's
    # handler rule). A registration's own receiver argument carries only the
    # BARE descriptor (D00 §5a: a call argument never repeats the module
    # coordinates), so a handler built by concatenating that descriptor with
    # the catalog's method name would name no symbol any fact ever emitted;
    # the engine matches against these instead and writes the row it found,
    # verbatim. Ordered by symbol so a type declaring two overloads of the
    # handler method is read the same way twice (NFR-1).
    #
    # A handler may be a method OR a free function (D00 §4) — the same
    # widening `derive_endpoints.sql` already carries; the JVM extractor
    # emits no `function`, so today's behavior is unchanged.
    "method_symbols": """
        SELECT symbol FROM symbols WHERE construct_kind IN ('method', 'function') ORDER BY symbol
    """,
    # Annotation TYPE symbols — checkpoint item (2): an annotation type
    # compiles to `construct_kind: "interface"` (there is no dedicated
    # `annotation` kind), so this is the cheapest correct source for Task
    # 6's "module-local" test (`resolve/effective_annotations.py`): a
    # composed annotation's own type symbol must appear here before its
    # meta-annotations are followed at all — the jar half (D02 §7) never
    # does. `method_symbols` above cannot serve this; a composing type is
    # never a method.
    "interface_symbols": """
        SELECT symbol FROM symbols WHERE construct_kind = 'interface' ORDER BY symbol
    """,
    # Every declared method's own enclosing type and signature JSON,
    # module-prefixed exactly as the fact wrote them (D00 §5a) — checkpoint
    # item (4)'s inheritance join needs both, and `method_symbols` above
    # cannot serve it: `enclosing` places a candidate within its declaring
    # type at all (interface, implementer, or a scanned ancestor further up
    # the chain), and `signature` is what the structural bridge rule
    # (`resolve/effective_annotations.py`'s `inherited_rows`) compares a
    # same-name sibling's parameter/return types against. Ordered by symbol
    # for the same reason `method_symbols` is.
    #
    # `construct_kind = 'method'`, deliberately not `'function'` too (unlike
    # `method_symbols` above, which is a plain call-registration lookup a
    # free function could equally satisfy): inheritance needs `enclosing` to
    # place a candidate within a declaring type at all, and a free function
    # has none — there is no hierarchy for it to inherit through, so
    # widening this query to `IN ('method', 'function')` would only ever add
    # rows this pass's own `enclosing IS NULL` guard immediately drops.
    "method_declarations": """
        SELECT symbol, enclosing, signature FROM symbols
        WHERE construct_kind = 'method' ORDER BY symbol
    """,
    # Every declared constructor's own enclosing type and signature JSON —
    # the field ladder's rung 2 (2F design §4). A `field_write` fact names
    # the parameter INDEX a field was assigned from and nothing else, and a
    # constructor PARAMETER's own annotations live only inside this
    # signature: they are never emitted as their own `annotation` fact (Task
    # 6 checkpoint item (3)), so the `annotations` view cannot serve this and
    # `method_declarations` above never sees a constructor at all. Ordered by
    # symbol so a type declaring two overloads reads its candidates in the
    # same order twice (NFR-1).
    "constructor_declarations": """
        SELECT symbol, enclosing, signature FROM symbols
        WHERE construct_kind = 'constructor' ORDER BY symbol
    """,
    "coverage": """
        SELECT count(*) AS documents,
               sum(CASE WHEN partial THEN 1 ELSE 0 END) AS partial_documents
        FROM documents
    """,
    # `resolve/config.py`'s own input: every config_entry, in declaration
    # order within its document (`config_entries.seq`, D00 §5c) and its
    # document ahead of that (`document_id`) so a multi-document file's own
    # documents are read together, `doc_index` breaking the tie between them
    # — the same NFR-1 ordering role `call_sites`'s `caller, ordinal` plays.
    "config_entries": "SELECT * FROM config_entries ORDER BY document_id, doc_index, seq",
    # `resolved_config`'s own export/read shape (D01): ordered by
    # `environment, key` so "unresolved for prod, resolved for dev" reads as
    # two adjacent rows rather than an arbitrary interleaving (NFR-1).
    "resolved_config": """
        SELECT key, value, source, environment, unresolved_reason
        FROM resolved_config ORDER BY environment, key
    """,
    # The per-environment answer for every address expression a client-side
    # row carries — a JOIN, never a write (2F design §3, job 3): endpoint
    # rows keep their expressions, `resolved_config` keeps the values, and
    # nothing rewrites a row per environment. One row per (client-side
    # endpoint, environment).
    #
    # `direction <> 'inbound'` rather than `= 'outbound'`: a `both` row is a
    # path the module both exposes and CALLS (D02 §3's merge), so it carries
    # a caller's address expression exactly as an outbound row does — an
    # equality test would silently drop every merged one.
    #
    # A placeholder count, not a regex alternation, decides the three cases:
    # `${` occurs zero times (a literal, which passes straight through with
    # its own value), once (substituted from `resolved_config` for this
    # environment), or more (`multi_placeholder` — D01's own reason for an
    # expression that is substitutable only piecewise, the one reason M04's
    # pass 2 never emits because it belongs to this join alone). `length`
    # minus the length with the opening delimiter removed, over the
    # delimiter's own length, IS that count.
    #
    # `path` and `peer` are resolved independently — a row may carry an
    # expression in either or both (D01 §3: `peer` is the target hint,
    # `path` the address, and 2F's base composition puts a whole unsplit
    # expression in `path` with `peer` NULL). The single `unresolved_reason`
    # column reports `path`'s answer first, `peer`'s only when `path` had
    # nothing to say, so one column still names why a row did not resolve
    # for an environment.
    #
    # With no resolved environments at all the join is empty and so is this
    # answer: "the same rows, unresolved" and "no environments to resolve
    # against" are different claims, and only the first one would be a lie.
    "resolved_peers": """
        WITH environments AS (SELECT DISTINCT environment FROM resolved_config),
        candidates AS (
            SELECT protocol, direction, method, path, peer, caller, catalog_id
            FROM endpoints
            WHERE direction <> 'inbound'
        ),
        paired AS (
            SELECT c.*, e.environment,
                   ((length(coalesce(c.path, '')) -
                     length(replace(coalesce(c.path, ''), '${', ''))) / 2)::INTEGER
                       AS path_placeholders,
                   ((length(coalesce(c.peer, '')) -
                     length(replace(coalesce(c.peer, ''), '${', ''))) / 2)::INTEGER
                       AS peer_placeholders,
                   regexp_extract(coalesce(c.path, ''), '\\$\\{([^}]*)\\}', 1) AS path_key,
                   regexp_extract(coalesce(c.peer, ''), '\\$\\{([^}]*)\\}', 1) AS peer_key
            FROM candidates c CROSS JOIN environments e
        ),
        joined AS (
            SELECT p.*,
                   pk.value AS path_value, pk.unresolved_reason AS path_reason,
                   qk.value AS peer_value, qk.unresolved_reason AS peer_reason
            FROM paired p
            LEFT JOIN resolved_config pk
                   ON pk.key = p.path_key AND pk.environment = p.environment
            LEFT JOIN resolved_config qk
                   ON qk.key = p.peer_key AND qk.environment = p.environment
        )
        SELECT protocol, direction, method, path, peer, caller, catalog_id, environment,
               CASE WHEN path_placeholders = 0 THEN path
                    WHEN path_placeholders > 1 THEN NULL
                    WHEN path_value IS NULL THEN NULL
                    ELSE replace(path, '${' || path_key || '}', path_value) END AS resolved_path,
               CASE WHEN peer_placeholders = 0 THEN peer
                    WHEN peer_placeholders > 1 THEN NULL
                    WHEN peer_value IS NULL THEN NULL
                    ELSE replace(peer, '${' || peer_key || '}', peer_value) END AS resolved_peer,
               coalesce(
                   CASE WHEN path_placeholders > 1 THEN 'multi_placeholder'
                        WHEN path_placeholders = 1 AND path_value IS NULL
                            THEN coalesce(path_reason, 'missing_key') END,
                   CASE WHEN peer_placeholders > 1 THEN 'multi_placeholder'
                        WHEN peer_placeholders = 1 AND peer_value IS NULL
                            THEN coalesce(peer_reason, 'missing_key') END
               ) AS unresolved_reason
        FROM joined
        ORDER BY environment, protocol, method, path, peer, caller
    """,
    # The 2K hand-off ledger (2G design §6). Ordered by the wire identity the
    # row carries, `question` breaking a tie where one endpoint raises both
    # kinds — "rows are ordered by wire identity for NFR-1 determinism", and
    # an ordering with ties is one that can change between runs.
    #
    # Wire identity plus `question` is NOT total, which is why the row's own
    # content closes it: two listeners on one destination are two rows sharing
    # every one of those four columns (`endpoints` itself orders by
    # `handler, caller` for exactly this reason), and their order would
    # otherwise be the insert order rather than an ordering. `candidates` is
    # cast to text because it is the answer that differs between two such
    # rows, and `evidence` is the last tie-break — two rows agreeing on all
    # six are the same question asked twice and may appear in either order
    # without changing a byte.
    "open_questions": """
        SELECT protocol, method, path, question, candidates, evidence
        FROM open_questions
        ORDER BY protocol, method, path, question, candidates::VARCHAR, evidence
    """,
    # A cheap read of what `analyze` already loaded — for `render`, which
    # queries the workspace instead of reloading fact files from disk.
    "facts": "SELECT count(*) AS facts FROM raw_facts",
}

# The tables a bundle carries (D06 §5). `documents`, `endpoints`,
# `resolved_config`, `shapes`, `shape_fields`, `call_sites` and
# `open_questions` (2G Task 8) export through their named query, so the row
# order is the one NFR-1 already fixed; `symbols` and `annotations` have no
# named query and export through their own ordered SELECT below, for the same
# reason. Sorted by name so the manifest's contents list is deterministic too.
_EXPORTED_TABLES = (
    "annotations",
    "call_sites",
    "documents",
    "endpoints",
    "open_questions",
    "resolved_config",
    "shape_fields",
    "shapes",
    "symbols",
)

_EXPORT_QUERIES = {
    "documents": _NAMED_QUERIES["documents"],
    "endpoints": _NAMED_QUERIES["endpoints"],
    "open_questions": _NAMED_QUERIES["open_questions"],
    "resolved_config": _NAMED_QUERIES["resolved_config"],
    "shapes": _NAMED_QUERIES["shapes"],
    "shape_fields": _NAMED_QUERIES["shape_fields"],
    "call_sites": _NAMED_QUERIES["call_sites"],
    "symbols": "SELECT * FROM symbols ORDER BY symbol",
    "annotations": (
        "SELECT target, annotation, args, type_path, retention "
        "FROM annotations ORDER BY target, annotation, type_path"
    ),
}

_NAMED_DERIVATIONS = {
    "endpoints": "derive_endpoints.sql",
    "call_endpoints": "derive_call_endpoints.sql",
    "endpoints_reset": "reset_endpoints.sql",
    "endpoints_merge": "merge_endpoints.sql",
    "endpoint_contracts": "derive_endpoint_contracts.sql",
    "shapes": "derive_shapes.sql",
    "shape_fields": "derive_shape_fields.sql",
    "shapes_reset": "reset_shapes.sql",
    "resolved_config_reset": "reset_resolved_config.sql",
    "resolved_config_insert": "insert_resolved_config.sql",
    "stamp_media": "stamp_media.sql",
    "stamp_declared_response": "stamp_declared_response.sql",
    "stamp_format": "stamp_format.sql",
    "bind_request_shape": "bind_request_shape.sql",
    "reclassify_protocol": "reclassify_protocol.sql",
    "open_questions_reset": "reset_open_questions.sql",
    "open_questions_insert": "insert_open_questions.sql",
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

    def export_tables(self, destination: Path) -> list[str]:
        graph = destination / "graph"
        graph.mkdir(parents=True, exist_ok=True)
        for name in _EXPORTED_TABLES:
            sql = _EXPORT_QUERIES[name]
            self._connection.execute(
                f"COPY ({sql}) TO ? (FORMAT parquet, COMPRESSION zstd)",
                [str(graph / f"{name}.parquet")],
            )
        return list(_EXPORTED_TABLES)

    def export_facts(self, destination: Path) -> int:
        rows = self._connection.execute(
            "SELECT DISTINCT document_id FROM raw_facts ORDER BY document_id"
        ).fetchall()
        for (document_id,) in rows:
            target = destination / "facts" / f"{document_id}.parquet"
            target.parent.mkdir(parents=True, exist_ok=True)
            # Two bound values, not one: DuckDB's `?` positional binding does
            # not carry through a COPY statement's TO clause when the query
            # it wraps also binds a `?` (reproduced against duckdb 1.5.5) —
            # `$1`/`$2` does. `?` still covers the single-parameter case in
            # export_tables above.
            self._connection.execute(
                "COPY (SELECT kind, document_id, payload FROM raw_facts "
                "WHERE document_id = $1 ORDER BY rowid) "
                "TO $2 (FORMAT parquet, COMPRESSION zstd)",
                [document_id, str(target)],
            )
        return len(rows)

    def close(self) -> None:
        self._connection.close()
