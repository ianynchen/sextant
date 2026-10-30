-- The format ladder's write (2G design §5): every endpoint row gains its
-- `(format, format_resolution)` pair, decided by `resolve/format.py`.
--
-- Nothing is decided here. Which rung answered, what a MIME string or a
-- configured serializer class means on the wire, and whether a bound shape
-- was described by a schema are all catalog knowledge applied in the pass;
-- this file is handed one finished pair per row and only applies it.
--
-- No first-writer guard, unlike stamp_media.sql: the pass answers EVERY row
-- exactly once per resolve — a row nothing could be said about arrives here
-- carrying NULL and `unresolved`, which is an answer — so there is no
-- earlier writer to protect and no column left untouched.
--
-- **Rows are matched on `row_id`** (follow-the-object, Ruling 7), which names
-- exactly the row the answer was read off. Until then the match was the six
-- identity columns plus the four the decision read — `(protocol, direction,
-- method, path)` is not unique in this table, and only the inputs made a
-- duplicate match idempotent rather than ambiguous. The id makes the match
-- exact, so the inputs no longer ride along.
--
-- Parameters:
--   $rows -- {row_id, format, format_resolution}, one per row of `endpoints`,
--             in the table's own query order
UPDATE endpoints e
SET format = f.format,
    format_resolution = f.format_resolution
FROM (SELECT UNNEST(
    $rows::STRUCT(row_id BIGINT, format VARCHAR, format_resolution VARCHAR)[]
) AS f)
WHERE e.row_id = f.row_id;
