-- Clears the error-handler table for one resolve. The reset_scheduled_work.sql
-- twin, and it runs from the pipeline for the same reason: a second catalog
-- describing another framework's advice mechanism writes to this same table,
-- and a reset owned by the engine would erase whichever catalog ran first.
--
-- The table itself is never dropped: schema.sql pre-declares it so the
-- "error_handlers" query still succeeds on a module that handles nothing.
DELETE FROM error_handlers;
