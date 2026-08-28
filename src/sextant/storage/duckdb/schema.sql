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
    resolution        TEXT,
    evidence          TEXT
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
SELECT document_id,
       payload ->> 'symbol'         AS symbol,
       payload ->> 'construct_kind' AS construct_kind,
       payload ->> 'enclosing'      AS enclosing,
       payload ->  'signature'      AS signature
FROM raw_facts WHERE kind = 'symbol';

CREATE OR REPLACE VIEW annotations AS
SELECT document_id,
       payload ->> 'target'              AS target,
       payload -> 'use' ->> 'annotation' AS annotation,
       payload -> 'use' ->  'args'       AS args
FROM raw_facts WHERE kind = 'annotation';
