-- Empties `scan_reuse` before the module's own scan runs (OI-325): the stage has read the
-- previous scan's records first, and a scan that stops part-way must leave none behind, so
-- the next run reads every file rather than trust records for fact files it never finished.
DELETE FROM scan_reuse;
