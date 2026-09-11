-- 2Q `I1`'s rows. Which handler is a root, and of which kind, is decided in
-- the pass itself, in Python, where D00 §4's closed set lives — this file is
-- handed the finished rows and only inserts them. The insert_return_flows.sql
-- / insert_scheduled_work.sql precedent for a Python-built derivation, and it
-- is what keeps the kind vocabulary in `domain/closed_sets.py` alone: a CASE
-- expression here spelling `inbound_endpoint` would be a second definition of
-- a closed set, which NFR-5 forbids.
--
-- NO insert-if-absent guard. A row is (handler, kind, address) and the pass
-- emits each such tuple once by construction — it deduplicates the several
-- endpoint rows one handler serves at ONE address before they reach here,
-- because that collapse is the answer rather than housekeeping. A duplicate
-- surviving to this table would be a defect in the pass, and a silent dedup
-- here would hide it.
--
-- Parameters:
--   $rows -- {handler, root_kind, protocol, method, path} rows, one per
--            address a trace can start at, and one all-NULL address for a
--            root nothing addresses.
INSERT INTO roots (handler, root_kind, protocol, method, path)
SELECT r.handler, r.root_kind, r.protocol, r.method, r.path
FROM (
    SELECT UNNEST($rows::STRUCT(
        handler VARCHAR, root_kind VARCHAR,
        protocol VARCHAR, method VARCHAR, path VARCHAR
    )[]) AS r
);
