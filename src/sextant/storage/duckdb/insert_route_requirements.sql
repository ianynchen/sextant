-- Spec 2026-09-19 §4d/§5a. One row per requirement a route's selectors declare, keyed by
-- the columns the engine minted the route with — `caller`, `handler`, `method`, `path`
-- and `catalog_id` — so the requirements pass can find the `endpoints` row it belongs
-- to after `apply_protocol_hints` has settled that row's protocol. Appended per engine
-- run; the reset is the pipeline's.
--
-- **The row is found HERE, not by the requirements pass** (follow-the-object, Ruling 7).
-- Both writers stash right after `call_endpoints` has minted the rows, so the five columns
-- still equal the row's own, and the match binds that row's `row_id`. The requirements pass
-- runs after the path prefix, which rewrites `path`: joined there on the minted path, every
-- requirement of a prefixed route found no row and was dropped. Each column compares
-- NULL-safely, as every other identity match does. Where several rows match, the requirement
-- is one stash row per match; where none does — the engine refused the route, or another
-- catalog's row won its address — `row_id` is NULL and the pass drops it, as before.
INSERT INTO route_requirements (
    row_id, caller, handler, method, path, catalog_id, kind, name, value, requirement,
    resolution, evidence
)
SELECT e.row_id, r.caller, r.handler, r.method, r.path, r.catalog_id,
       r.kind, r.name, r.value, r.requirement, r.resolution, r.evidence
FROM (SELECT UNNEST(
    $rows::STRUCT(
        caller VARCHAR, handler VARCHAR, method VARCHAR, path VARCHAR, catalog_id VARCHAR,
        kind VARCHAR, name VARCHAR, value VARCHAR, requirement VARCHAR, resolution VARCHAR,
        evidence VARCHAR
    )[]
) AS r)
LEFT JOIN endpoints e
  ON e.caller     IS NOT DISTINCT FROM r.caller
 AND e.handler    IS NOT DISTINCT FROM r.handler
 AND e.method     IS NOT DISTINCT FROM r.method
 AND e.path       IS NOT DISTINCT FROM r.path
 AND e.catalog_id IS NOT DISTINCT FROM r.catalog_id;
