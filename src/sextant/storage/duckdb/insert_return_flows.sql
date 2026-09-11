-- 2Q `G3`'s rows. Every decision — which methods a call site can dispatch
-- into, how the callee's descriptor is computed from the target triple, and
-- which of the callee's returns exist — is made in the pass itself, in Python,
-- where the symbol grammar and the hierarchy walk live; this file is handed
-- the finished rows and only inserts them. The insert_scheduled_work.sql /
-- insert_resolved_config.sql precedent for a Python-built derivation.
--
-- `value` arrives as the JSON TEXT the `method_returns` projection handed out,
-- and is cast back on the way in so the column holds JSON rather than a string
-- that looks like it. Round-tripping the extractor's own text, not
-- re-serialising a parsed copy: a re-serialised object would be a second
-- spelling of the same value, and NFR-1 asks that two runs agree byte for
-- byte.
--
-- NO insert-if-absent guard. A row is (call site, callee, return ordinal), and
-- the pass emits each of those once by construction — a duplicate could only
-- come from a hierarchy walk that reached one implementation twice, which is a
-- defect in the walk and not something a silent dedup should hide.
--
-- Parameters:
--   $rows -- {caller, ordinal, result, callee, return_ordinal, value,
--             resolution, evidence} rows, one per (call site, callee, return).
INSERT INTO return_flows (caller, ordinal, result, callee, return_ordinal, value,
                          resolution, evidence)
SELECT r.caller, r.ordinal, r.result, r.callee, r.return_ordinal, r.value::JSON,
       r.resolution, r.evidence
FROM (SELECT UNNEST(
    $rows::STRUCT(
        caller VARCHAR, ordinal INTEGER, result INTEGER, callee VARCHAR,
        return_ordinal INTEGER, value VARCHAR, resolution VARCHAR, evidence VARCHAR
    )[]
) AS r);
