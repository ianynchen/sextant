-- The module's own scan's records (OI-325, `ports/scanner.py` `ReuseRecord`), one per
-- document it wrote or kept, for the next run's scan. The scanner built them; this file
-- only inserts them.
--
-- Parameters:
--   $rows -- {target, key, detail} rows.
INSERT INTO scan_reuse (target, key, detail)
SELECT r.target, r.key, r.detail
FROM (SELECT UNNEST($rows::STRUCT(target VARCHAR, key VARCHAR, detail VARCHAR)[]) AS r);
