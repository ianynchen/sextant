-- Clears `dispatch_registrations` for one resolve (spec 2026-11-05 §3). Runs from the PASS
-- rather than from the pipeline, the reset_hops.sql reasoning: the table has exactly one
-- writer, `resolve/dispatch_registrations.py`, so reset and insert belong together there.
--
-- The table itself is never dropped: schema.sql pre-declares it so the
-- "dispatch_registrations" query still succeeds on a module that registers nothing.
-- Unconditional, so a resolve with no declaring catalog still leaves an empty table rather
-- than the previous run's rows.
DELETE FROM dispatch_registrations;
