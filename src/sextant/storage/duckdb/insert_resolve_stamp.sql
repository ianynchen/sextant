-- The stamp of the resolve that just finished (OI-325): its key and the part of its report
-- no table holds.
--
-- Parameters:
--   $key    -- the digest of everything the resolve read.
--   $report -- that part of the report, as JSON.
INSERT INTO resolve_stamp (key, report) VALUES ($key, $report);
