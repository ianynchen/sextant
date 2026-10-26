-- `resolve/rpc_hops.py`'s rows (spec 2026-10-25 §3d). Every decision — which classes are
-- client stubs, which wire method a stub method names, where its call leaves for the
-- wire, which services the module serves — is made in the pass; this file is handed the
-- finished rows and only inserts them. The insert_resolved_schedules.sql precedent for a
-- Python-built derivation.
--
-- Parameters:
--   $rows -- {caller, ordinal, protocol, path, handler, evidence} rows, one per (stub
--             method, handler); `caller` and `handler` module-prefixed, `handler` NULL
--             where the module serves the service but not this RPC.
INSERT INTO rpc_hops (caller, ordinal, protocol, path, handler, evidence)
SELECT r.caller, r.ordinal, r.protocol, r.path, r.handler, r.evidence
FROM (SELECT UNNEST(
    $rows::STRUCT(
        caller VARCHAR, ordinal INTEGER, protocol VARCHAR, path VARCHAR, handler VARCHAR,
        evidence VARCHAR
    )[]
) AS r);
