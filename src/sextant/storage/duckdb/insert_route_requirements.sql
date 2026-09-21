-- Spec 2026-09-19 §4d/§5a. One row per requirement a route's selectors declare, keyed by
-- the columns the engine minted the route with — `caller`, `handler`, `method`, `path`
-- and `catalog_id` — so the requirements pass can find the `endpoints` row it belongs
-- to after `apply_protocol_hints` has settled that row's protocol. Appended per engine
-- run; the reset is the pipeline's.
INSERT INTO route_requirements (
    caller, handler, method, path, catalog_id, kind, name, value, requirement, resolution, evidence
)
SELECT r.caller, r.handler, r.method, r.path, r.catalog_id,
       r.kind, r.name, r.value, r.requirement, r.resolution, r.evidence
FROM (SELECT UNNEST(
    $rows::STRUCT(
        caller VARCHAR, handler VARCHAR, method VARCHAR, path VARCHAR, catalog_id VARCHAR,
        kind VARCHAR, name VARCHAR, value VARCHAR, requirement VARCHAR, resolution VARCHAR,
        evidence VARCHAR
    )[]
) AS r);
