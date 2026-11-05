-- Clears `message_handlers` for one resolve (spec 2026-11-04 §3b). Runs from the PASS rather
-- than from the pipeline, the reset_rpc_hops.sql reasoning: the table has exactly one
-- writer, `resolve/message_handlers.py`, so reset and insert belong together there.
--
-- The table itself is never dropped: schema.sql pre-declares it so the "message_handlers"
-- query still succeeds on a module that builds no behavior. Unconditional, so a resolve with
-- no declaring catalog still leaves an empty table rather than the previous run's rows.
DELETE FROM message_handlers;
