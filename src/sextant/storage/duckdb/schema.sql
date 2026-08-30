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
    response_shape    TEXT
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

CREATE OR REPLACE VIEW documents AS
SELECT document_id,
       payload ->> 'relative_path'   AS relative_path,
       payload ->> 'module_id'       AS module_id,
       payload ->> 'language'        AS language,
       payload ->> 'origin_tier'     AS origin_tier,
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
