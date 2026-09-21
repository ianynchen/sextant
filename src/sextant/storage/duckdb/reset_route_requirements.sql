-- Spec 2026-09-19 §4d/§5a: the combinator's per-route requirements, stashed at engine time
-- and joined to `endpoints` by the requirements pass once every row's protocol is final.
--
-- A TEMP table rather than a table `schema.sql` declares, for `endpoint_candidates`'
-- reason: it lives for the one resolve that reads it, is replaced by the next, and never
-- reaches the workspace file or an export bundle (`DuckDbWorkspace.schema_objects` leaves
-- it out by name). Replaced WHOLE, once per resolve, from `derive_endpoints` beside
-- `endpoints_reset` — several catalogs write it, so a reset owned by the engine would
-- erase whichever ran first.
CREATE OR REPLACE TEMP TABLE route_requirements (
    caller TEXT, handler TEXT, method TEXT, path TEXT, catalog_id TEXT,
    kind TEXT, name TEXT, value TEXT, requirement TEXT, resolution TEXT, evidence TEXT
);
