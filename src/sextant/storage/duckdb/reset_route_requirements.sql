-- Spec 2026-09-19 §4d/§5a: the combinator's per-route requirements, stashed at engine time
-- and joined to `endpoints` by the requirements pass once every row's protocol is final.
--
-- A TEMP table rather than a table `schema.sql` declares, for `endpoint_candidates`'
-- reason: it lives for the one resolve that reads it, is replaced by the next, and never
-- reaches the workspace file or an export bundle (`DuckDbWorkspace.schema_objects` leaves
-- it out by name). Replaced WHOLE, once per resolve, from `derive_endpoints` beside
-- `endpoints_reset` — several catalogs write it, so a reset owned by the engine would
-- erase whichever ran first.
--
-- `row_id` is the `endpoints` row the requirement belongs to (follow-the-object, Ruling 7),
-- bound by `insert_route_requirements.sql` when the requirement is stashed and the only
-- column the requirements pass joins on: by the time it reads this table the path prefix
-- may have moved the row, and the minted columns beside it no longer name it.
CREATE OR REPLACE TEMP TABLE route_requirements (
    row_id BIGINT,
    caller TEXT, handler TEXT, method TEXT, path TEXT, catalog_id TEXT,
    kind TEXT, name TEXT, value TEXT, requirement TEXT, resolution TEXT, evidence TEXT
);
