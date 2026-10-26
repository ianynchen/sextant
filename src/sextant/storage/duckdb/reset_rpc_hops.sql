-- Clears `rpc_hops` for one resolve (spec 2026-10-25 §3d). Runs from the PASS rather than
-- from the pipeline, the reset_return_flows.sql reasoning: the table has exactly one
-- writer, `resolve/rpc_hops.py`, so reset and insert belong together there.
--
-- The table itself is never dropped: schema.sql pre-declares it so the "rpc_hops" query
-- still succeeds on a module that calls no service it serves. Unconditional, so a resolve
-- with no stub catalog, no stub class or no served service still leaves an empty table
-- rather than the previous run's rows.
DELETE FROM rpc_hops;
