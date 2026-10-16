-- Spec 2026-09-22 §7a's shadow rows: what the walk WOULD resolve at every
-- position a catalog asked about, and what it could not.
--
-- The rows are built in `resolve/shadow.py` — which catalog asks about which
-- slot, and what the walk answers there, are that pass's rules, and restating
-- any of it as SQL would be a second answer (the insert_roots.sql /
-- insert_reachability.sql precedent for a Python-built derivation). This file
-- is handed the finished rows and only inserts them.
--
-- NO insert-if-absent guard. A row is (catalog, caller, ordinal, slot, path)
-- and the pass emits each such tuple once by construction: the positions are
-- deduplicated before the walk runs, and a site's bindings are one per
-- DISTINCT path (§1c). A duplicate surviving to this table would be a defect
-- in the pass, and a silent dedup here would hide it.
--
-- Parameters:
--   $rows -- {catalog, caller, ordinal, slot, path, outcome, answer_kind,
--            literal_kind, value, reason} rows, one per (asked position, path).
INSERT INTO value_resolutions (
    catalog, caller, ordinal, slot, path, outcome, answer_kind, literal_kind, value, reason
)
SELECT r.catalog, r.caller, r.ordinal, r.slot, r.path,
       r.outcome, r.answer_kind, r.literal_kind, r.value, r.reason
FROM (
    SELECT UNNEST($rows::STRUCT(
        catalog VARCHAR, caller VARCHAR, ordinal INTEGER, slot VARCHAR, path VARCHAR,
        outcome VARCHAR, answer_kind VARCHAR, literal_kind VARCHAR,
        value VARCHAR, reason VARCHAR
    )[]) AS r
);
