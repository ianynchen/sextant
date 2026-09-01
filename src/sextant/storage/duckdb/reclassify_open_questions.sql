-- `reclassify_protocol.sql`'s second half (2H Task 6 fix round 1): the 2K
-- hand-off ledger follows the rows it asks about.
--
-- **Why this exists.** `open_questions.protocol` is a SNAPSHOT of the wire
-- identity taken when a question was recorded, not a foreign key (schema.sql
-- says so: the endpoint table is rebuilt every resolve, so a key into it would
-- name nothing outside the run). `parse_binding` runs BEFORE the
-- reclassification and copies each row's protocol as it stood then, so a
-- reclassified row's `payload_binding` question would keep publishing the old
-- protocol while `endpoints` published the new one — two tables in one bundle
-- disagreeing about one channel. (`format_conflict` questions cannot go stale:
-- the format ladder runs AFTER this pass and reads the protocol it left.)
--
-- **Why a second file rather than a second statement.** DuckDB binds prepared
-- parameters only on the LAST statement of a multi-statement execute, so the
-- two UPDATEs cannot share one file while both read `$rows`. They are one
-- family regardless: the same parameter, the same call site, run back to back
-- in `resolve/protocol_hint.py`.
--
-- **The match is WIDER here, and that is a stated limitation rather than an
-- oversight.** The ledger carries three of the six identity columns — no
-- `direction`, `handler` or `caller` — because a question is about a wire
-- identity, not about a symbol. So where two endpoint rows share
-- `(protocol, method, path)` and only ONE of them reclassifies, a question
-- belonging to the other moves too: the ledger cannot tell them apart, and
-- nothing in it could. Moving is still the right side to err on — the row a
-- reader looks up by identity is the one that just changed protocol — but a
-- future ledger that carried the handler could tighten this.
--
-- Parameters:
--   $rows -- the same struct `reclassify_protocol.sql` is handed. `direction`,
--            `handler` and `caller` ride along unread; a struct per call site,
--            not a struct per statement.
UPDATE open_questions q
SET protocol = h.reclassified
FROM (SELECT UNNEST(
    $rows::STRUCT(
        protocol VARCHAR, direction VARCHAR, method VARCHAR, path VARCHAR,
        handler VARCHAR, caller VARCHAR, reclassified VARCHAR
    )[]
) AS h)
WHERE q.protocol IS NOT DISTINCT FROM h.protocol
  AND q.method   IS NOT DISTINCT FROM h.method
  AND q.path     IS NOT DISTINCT FROM h.path;
