-- Clears `bound_receivers` (spec 2026-11-06 §3b) before a round of receiver binding writes
-- it whole. Runs from the PASS (`resolve/receiver_binding.py`, its one writer), the
-- reset_return_flows.sql precedent; the pipeline runs it once more before the first
-- `call_edges` of a resolve, which reads the table, so that read never meets the previous
-- resolve's owners.
--
-- The table itself is never dropped: schema.sql pre-declares it so the "bound_receivers"
-- query still succeeds on a module with no call left to bind, which is every JVM module.
DELETE FROM bound_receivers;
