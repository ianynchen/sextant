-- Clears `hops` for one resolve (spec 2026-10-25 §3d; named `rpc_hops` until spec
-- 2026-11-05). Runs from the PIPELINE, once,
-- before both of the table's writers (spec 2026-11-04 §3d item 7): `resolve/rpc_hops.py` and
-- `resolve/dispatch_hops.py` each only insert, so a reset in either would erase the other's.
--
-- The table itself is never dropped: schema.sql pre-declares it so the "hops" query
-- still succeeds on a module that calls no service it serves. Unconditional, so a resolve
-- with no stub catalog, no stub class, no served service and no dispatch send still leaves
-- an empty table rather than the previous run's rows.
DELETE FROM hops;
