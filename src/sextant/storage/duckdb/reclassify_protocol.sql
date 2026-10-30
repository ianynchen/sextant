-- The `protocol_hint` write (2H design §6): a row an engine already minted
-- moves to the protocol its own evidence names.
--
-- Nothing is decided here. Which MIME string names an envelope, which return
-- types mark a stream, and which protocol a row moves TO are all catalog
-- knowledge applied in `resolve/protocol_hint.py`; this file is handed one
-- finished protocol per row and only applies it.
--
-- **ONE column, on rows that already exist.** No INSERT and no DELETE: the
-- pass reclassifies, it never creates or removes an endpoint, so the row
-- count is identical before and after. `direction` is not in the SET clause
-- and never will be — the inbound/outbound merge has already run by the time
-- this statement fires, and a `both` row moves WHOLESALE, staying the one
-- identity the merge made of it.
--
-- **The scoping is the row the pass read, not a literal.** The pass only ever
-- puts a row in `$rows` when the catalog that named the evidence declares
-- that row's protocol as its own, so the UPDATE is scoped to exactly the
-- source protocol the catalogs sanction — expressed as data, because a
-- protocol name spliced into this file would be framework knowledge in the
-- storage layer (ARCHITECTURE §10).
--
-- Rows are matched on `row_id` (follow-the-object, Ruling 7): the id names
-- exactly the row the pass read, where `(protocol, direction, method, path)`
-- is not unique in this table and a path prefix may already have moved the
-- address the row was minted with.
--
-- **`reclassify_open_questions.sql` is this statement's other half**, run from
-- the same call site with the same `$rows` and just BEFORE this one: the 2K
-- ledger snapshots a wire identity rather than joining to it, so a row that
-- moves here must take its questions with it, and that file finds them by the
-- protocol this statement is about to replace. `follow_endpoint_rows.sql`
-- then moves the `endpoint_metadata` entries bound to the row.
--
-- Parameters:
--   $rows -- {row_id, reclassified}, one per RECLASSIFIED row. `reclassified`
--             is the protocol that replaces the row's own.
UPDATE endpoints e
SET protocol = h.reclassified
FROM (SELECT UNNEST(
    $rows::STRUCT(row_id BIGINT, reclassified VARCHAR)[]
) AS h)
WHERE e.row_id = h.row_id;
