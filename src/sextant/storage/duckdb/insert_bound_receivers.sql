-- `resolve/receiver_binding.py`'s rows (spec 2026-11-06 §3b): every decision — what the
-- walk reached each receiver as, on which path, and the reason where it reached no type — is
-- made in the pass; this file is handed the finished rows and only inserts them, the
-- insert_resolved_schedules.sql precedent for a Python-built derivation.
--
-- Parameters:
--   $rows -- {caller, ordinal, path_id, owner, evidence, resolution, reason, detail} rows, one
--             per (call site, path); `owner` is NULL exactly when `reason` is set, one word of
--             the general reason list (`values._REASONS`), and `detail` says where.
INSERT INTO bound_receivers (caller, ordinal, path_id, owner, evidence, resolution, reason,
                             detail)
SELECT r.caller, r.ordinal, r.path_id, r.owner, r.evidence, r.resolution, r.reason, r.detail
FROM (SELECT UNNEST(
    $rows::STRUCT(
        caller VARCHAR, ordinal INTEGER, path_id VARCHAR, owner VARCHAR, evidence VARCHAR,
        resolution VARCHAR, reason VARCHAR, detail VARCHAR
    )[]
) AS r);
