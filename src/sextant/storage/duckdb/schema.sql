CREATE TABLE IF NOT EXISTS raw_facts (
    kind        TEXT,
    document_id TEXT,
    payload     JSON
);

-- Pre-declared so the "endpoints" query always succeeds, even when every
-- catalog is skipped by capability gating and derive_endpoints.sql never
-- runs (D02 §2, M04): a weaker scanner must degrade visibly via
-- skipped_catalogs, not crash. derive_endpoints.sql still replaces this
-- table whole via CREATE OR REPLACE TABLE whenever at least one catalog runs.
CREATE TABLE IF NOT EXISTS endpoints (
    protocol          TEXT,
    direction         TEXT,
    method            TEXT,
    path              TEXT,
    handler           TEXT,
    handler_signature JSON,
    -- The client-side method symbol (D01 §3, amended this phase): an
    -- outbound row carries `caller` with `handler` NULL; a `both` row keeps
    -- both. `peer` is the declared target hint — a service name or a literal
    -- authority — that the system tier later resolves to a participant; NULL
    -- where the base address lives in builder code the annotations never see.
    caller            TEXT,
    peer              TEXT,
    resolution        TEXT,
    evidence          TEXT,
    -- The id of the catalog that derived this row (2E-prep design §1a):
    -- provenance for rule scoping, never part of wire identity, never
    -- compared across services.
    catalog_id        TEXT,
    request_shape     TEXT,
    response_shape    TEXT,
    -- JSON arrays of MIME strings, or NULL where no declaration is
    -- derivable from any evidence source (2E design §4): carried data,
    -- never identity — dedup and merge never compare these two columns.
    consumes          TEXT,
    produces          TEXT,
    -- What is on this channel's wire, and how much the answer is worth (2G
    -- design §4, §5). Both are stamped by one late pass over every row
    -- (`resolve/format.py`), never by a derivation: `format` is one of D00's
    -- format values or NULL, and `format_resolution` is the same resolution
    -- set every other column uses — `resolved` where declared evidence named
    -- the wire outright, `narrowed` where only a framework default or the
    -- payload's own type suggested it, `unresolved` where nothing did.
    -- As the ladder writes them, `format` is NULL exactly when
    -- `format_resolution` is `unresolved`. **One statement breaks that pair
    -- on purpose**: merge_endpoints.sql keeps the surviving row's format
    -- while taking the WEAKER of the two halves' markers, so a merged row
    -- may read (`protobuf`, `unresolved`) — "this is the format one
    -- direction declared, and this identity as a whole is not settled",
    -- which is the honest reading of one wire whose two halves were not
    -- equally observable. A reader must therefore treat
    -- `format_resolution` as the authority on trust and `format` as an
    -- answer that may still be worth showing beside it. **That branch has
    -- no live surface today** (merge_endpoints.sql's own header): the merge
    -- is the last statement of `derive_endpoints` and the ladder is the last
    -- pass of a resolve, so both columns are still NULL when the merge runs
    -- and the ladder answers every row afterwards — the pair holds on every
    -- live row, and the exception becomes reachable only if a later phase
    -- stamps a format before the merge.
    format            TEXT,
    format_resolution TEXT
);

-- Pre-declared for the same reason as `endpoints` above: a scanner too weak
-- to populate shapes must still answer the "shapes"/"shape_fields" query
-- with an empty result, not an error, and degrade visibly through
-- skipped_catalogs instead. Tasks 9-11 replace these whole via CREATE OR
-- REPLACE TABLE once shape derivation runs.
CREATE TABLE IF NOT EXISTS shapes (
    shape_id     TEXT,
    content_hash TEXT,
    open         BOOLEAN
);

CREATE TABLE IF NOT EXISTS shape_fields (
    shape_id    TEXT,
    ordinal     INTEGER,
    wire_name   TEXT,
    -- The schema's own field number (protobuf) — NULL for a format with none
    -- (Avro) and for every bytecode-derived (annotation/reflection) shape,
    -- which never carries one at all (2G design §3, Task 5).
    field_number INTEGER,
    wire_type   TEXT,
    wire_format TEXT,
    required    BOOLEAN,
    nullable    BOOLEAN,
    resolution  TEXT,
    evidence    TEXT,
    tags        JSON,
    -- The recursive descriptor {wire_type, wire_format, nullable, shape_id?,
    -- item?} for a collection's element (array) or value (map) type — NULL
    -- for a scalar field. A single wire_type cannot distinguish
    -- List<String> from List<CustomerRef>; without item, DR-5 would match a
    -- caller sending an array of strings against a callee expecting an
    -- array of records (D01 §3 Contracts).
    item        JSON
);

-- Pre-declared for the same reason as `endpoints`/`shapes` above: M04 pass 2
-- (`resolve/config.py`) must answer the "resolved_config" query with an
-- empty result, not an error, when no catalog declares a config_model or no
-- config file was read (2F design §2). `resolve_config` replaces it whole
-- via resolved_config_reset.sql + insert_resolved_config.sql once per
-- resolve — unconditionally, so an empty resolve still leaves an empty
-- table rather than a stale previous run's rows.
CREATE TABLE IF NOT EXISTS resolved_config (
    key               TEXT,
    value             TEXT,
    -- The file that won precedence for this key in this profile's layering
    -- (D02 §2i's config_model) — NULL only when the key was never declared
    -- for this environment at all, so no file ever won it (D01).
    source            TEXT,
    environment       TEXT,
    -- NULL exactly when `value` is non-NULL. One of D01's closed five-value
    -- set (`missing_key`, `environment`, `remote_source`,
    -- `placeholder_cycle`, `multi_placeholder`) — the last reserved for the
    -- peer-resolution join, never emitted by this pass.
    unresolved_reason TEXT
);

-- The 2K hand-off ledger (2G design §6): one row per question a programmatic
-- pass could not answer and refused to guess at. Pre-declared empty for the
-- same reason `endpoints`/`shapes`/`resolved_config` above are — the
-- "open_questions" query must answer with an empty result, never an error,
-- on a run where no pass had anything to ask.
--
-- Replaced WHOLE per resolve through reset_open_questions.sql +
-- insert_open_questions.sql, and the reset runs once, in the pipeline, ahead
-- of every writer rather than inside one of them: MORE THAN ONE pass writes
-- here (the format ladder's `format_conflict`, the parse-binding pass's
-- `payload_binding`), so a reset owned by either would erase the other's
-- rows depending on which ran first.
--
-- Programmatic passes never READ this table (2G design §6): it is a hand-off
-- to 2K's enrichment seat, not an input, and a pass that read its own
-- unanswered questions back would be answering them.
CREATE TABLE IF NOT EXISTS open_questions (
    -- The endpoint's wire identity (D01 §3), carried rather than joined: the
    -- row is an artifact a human and 2K read, and a foreign key into a table
    -- that is rebuilt every resolve would name nothing outside this run.
    protocol   TEXT,
    method     TEXT,
    path       TEXT,
    -- One of the closed two-value set `payload_binding`, `format_conflict`
    -- (2G design §6) — checked in `resolve/open_questions.py`, which is the
    -- only writer.
    question   TEXT,
    -- The answers that were on the table, as a JSON array — each carrying
    -- what it would have made the format or payload type, where it was seen,
    -- and why no rung could choose it. Sorted by the pass that writes it, so
    -- two runs produce the same bytes (NFR-1).
    candidates JSON,
    -- The evidence TRAIL, in prose: which columns and configuration keys the
    -- pass actually read to reach the impasse. Deliberately NOT one of D00's
    -- closed evidence tiers — an unanswered question has no tier, and the
    -- reader of this table needs to know where to look, not how much to
    -- trust an answer nobody gave.
    evidence   TEXT
);

CREATE OR REPLACE VIEW documents AS
SELECT document_id,
       payload ->> 'relative_path'   AS relative_path,
       payload ->> 'module_id'       AS module_id,
       payload ->> 'language'        AS language,
       payload ->> 'origin_tier'     AS origin_tier,
       -- The library this document was extracted from, as its coordinate, and
       -- NULL for the module's own output (D00 §2). Projected here — and so
       -- carried into the exported `documents` table — because opting a
       -- library in is an ASSERTION the reader makes, and an assertion that is
       -- visible in the rendered document but invisible in the published
       -- bundle would be laundered into module-observed evidence exactly where
       -- it travels furthest from the person who made it.
       payload ->> 'origin'          AS origin,
       (payload ->> 'partial')::BOOLEAN AS partial
FROM raw_facts WHERE kind = 'document';

CREATE OR REPLACE VIEW symbols AS
-- `seq` is the load order of the fact within its file, and a fact file is
-- written in declaration order (D00 §7). It is the only ordering that survives
-- into the workspace, and shape_fields.ordinal is declaration order (D01 §5),
-- so it is projected here rather than re-derived from anything the payload
-- happens to carry. A view over a table keeps the base table's rowid.
--
-- That rowid follows the order the loader read the lines in is **tested
-- behaviour, not a documented contract** — measured on this engine at 300k
-- rows across 8 files with 10 threads, where the bulk read preserved each
-- file's line order. An engine upgrade is the moment to re-verify it: if it
-- ever stops holding, `ordinal` stops being declaration order and every
-- content hash moves with it (NFR-1).
SELECT rowid                        AS seq,
       document_id,
       payload ->> 'symbol'         AS symbol,
       payload ->> 'construct_kind' AS construct_kind,
       payload ->> 'enclosing'      AS enclosing,
       payload ->  'signature'      AS signature,
       -- D00 §5a: `public` or `other`, as the declaring language sees it.
       -- Carried on every symbol fact and, until 2I's class-gate member rule,
       -- read by nothing — a rule that derives a class's EXPOSED members is
       -- the first thing that has to tell one from a member nobody can call.
       payload ->> 'visibility'     AS visibility,
       -- Declaration modifiers (D00 §5): what only the declaring language can
       -- say about whether a field reaches a payload at all. Absent on every
       -- other construct, and on a fact from a scanner that does not report
       -- them, so each reader supplies its own default rather than this view
       -- inventing one for constructs the modifier means nothing for.
       payload ->  'modifiers'      AS modifiers
FROM raw_facts WHERE kind = 'symbol';

CREATE OR REPLACE VIEW annotations AS
SELECT document_id,
       payload ->> 'target'              AS target,
       payload -> 'use' ->> 'annotation' AS annotation,
       payload -> 'use' ->  'args'       AS args,
       -- Only a type-use annotation carries this at all: NULL for a
       -- declaration annotation, '' for the outermost type, and a deeper path
       -- for an annotation on a type argument (D00 §5a).
       payload ->> 'type_path'           AS type_path,
       payload ->> 'retention'           AS retention
FROM raw_facts WHERE kind = 'annotation';

CREATE OR REPLACE VIEW config_entries AS
-- `seq` is declaration order within the entry's file: a config_entry fact
-- carries no explicit sequence field of its own (D00 §5c) because a fact
-- file is written in declaration order (D00 §7) and `rowid` already
-- reconstructs it losslessly — the same precedent `symbols.seq` states
-- above, reused rather than re-derived.
SELECT document_id,
       payload ->> 'key_raw'              AS key_raw,
       payload ->> 'key_path'             AS key_path,
       payload ->> 'value'                AS value,
       (payload ->> 'doc_index')::INTEGER AS doc_index,
       rowid                              AS seq
FROM raw_facts WHERE kind = 'config_entry';

CREATE OR REPLACE VIEW call_sites AS
SELECT document_id,
       payload ->> 'caller'                    AS caller,
       payload -> 'target' ->> 'owner'         AS owner,
       payload -> 'target' ->> 'name'          AS name,
       payload -> 'target' ->> 'descriptor'    AS descriptor,
       payload ->> 'invoke_kind'               AS invoke_kind,
       (payload ->> 'ordinal')::INTEGER        AS ordinal,
       (payload ->> 'receiver')::INTEGER       AS receiver,
       (payload ->> 'result')::INTEGER         AS result,
       payload ->  'arguments'                 AS arguments
FROM raw_facts WHERE kind = 'call_site';

CREATE OR REPLACE VIEW field_writes AS
-- D00 §5's field_write: a constructor assigning parameter N straight to
-- field F, constructors only, direct traces only. The field resolution
-- ladder (2F) is its only consumer so far.
SELECT document_id,
       payload ->> 'field'                     AS field,
       (payload ->> 'from_parameter')::INTEGER AS from_parameter
FROM raw_facts WHERE kind = 'field_write';
