-- 2Q `G4`'s rows. Every decision — which methods a call site can dispatch
-- into, how the callee's descriptor is composed from the target triple, which
-- body a `dynamic` site actually creates — is made in the pass itself, in
-- Python, where the symbol grammar and the hierarchy walk live; this file is
-- handed the finished rows and only inserts them. The insert_return_flows.sql
-- precedent for a Python-built derivation.
--
-- NO insert-if-absent guard. A row is (call site, candidate callee), and the
-- pass emits each of those once by construction — a duplicate could only come
-- from a hierarchy walk that reached one implementation twice, which is a
-- defect in the walk and not something a silent dedup should hide.
--
-- Parameters:
--   $rows -- {caller, ordinal, invoke_kind, target, callee, result,
--             resolution, evidence} rows, one per (call site, candidate
--             callee) and one for a call site whose callee's body was never
--             read — that row carries a NULL `callee`, which is the
--             third-party boundary and the point at which a trace stops.
INSERT INTO call_edges (caller, ordinal, invoke_kind, target, callee, result,
                        resolution, evidence)
SELECT r.caller, r.ordinal, r.invoke_kind, r.target, r.callee, r.result,
       r.resolution, r.evidence
FROM (SELECT UNNEST(
    $rows::STRUCT(
        caller VARCHAR, ordinal INTEGER, invoke_kind VARCHAR, target VARCHAR,
        callee VARCHAR, result INTEGER, resolution VARCHAR, evidence VARCHAR
    )[]
) AS r);
