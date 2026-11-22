-- The 2K hand-off ledger follows the rows the configured prefix moves
-- (`reclassify_open_questions.sql`'s precedent, restated for the prefix pass).
--
-- **Why this exists.** `open_questions.path` is a SNAPSHOT of the wire identity taken
-- when a question was recorded, not a foreign key (schema.sql says so). The engines file
-- `handler_pass_through` and `mount_prefix` questions while deriving endpoints, BEFORE
-- `apply_path_prefixes` runs — so a context-path module published `GET /app/x` rows whose
-- "why is this partial" question still said `GET /x`: an address no row has, orphaned in
-- the rendered document and missed by every later identity match.
--
-- **Run FIRST, before `prefix_endpoint_paths.sql`**: the question is found by the row's
-- identity as it STANDS, read off the row each `row_id` names, and that statement is the
-- one that changes it. A second file rather than a second statement for the same reason
-- the reclassify pair records: DuckDB binds parameters only on the last statement of an
-- execute.
--
-- **The match is WIDER than the row** — a question carries `(protocol, method, path)` and
-- no handler, so where two rows share that identity and only one moves, the other row's
-- question moves too. The same stated limitation as the reclassify pair, and the same
-- right side to err on.
--
-- Parameters:
--   $rows -- {row_id, prefixed}, exactly the rows `prefix_endpoint_paths.sql` is about to
--            move. `prefixed` replaces the path of every question matching the row's
--            CURRENT identity.
UPDATE open_questions q
SET path = h.prefixed
FROM (SELECT UNNEST(
    $rows::STRUCT(row_id BIGINT, prefixed VARCHAR)[]
) AS h), endpoints e
WHERE e.row_id = h.row_id
  AND q.protocol IS NOT DISTINCT FROM e.protocol
  AND q.method   IS NOT DISTINCT FROM e.method
  AND q.path     = e.path;
