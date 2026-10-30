-- The configured path prefix (spec 2026-10-18 §3, `OI-148`): a row an engine already minted
-- takes the address the module's SERVER actually serves it at.
--
-- Nothing is decided here. Which configuration key is a prefix, which framework and version
-- declares it, how several keys compose and whether the environments agree are all settled in
-- `resolve/path_prefix.py`; this file is handed one finished path per row and applies it.
--
-- **ONE column, on rows that already exist.** No INSERT and no DELETE: a prefix moves an
-- address, it never creates or removes an endpoint, so the row count is identical before and
-- after. `method`, `handler` and `caller` are untouched.
--
-- **Rows are matched on `row_id`, and on nothing else** (follow-the-object, Ruling 7). The
-- id names exactly the row the pass read, where `(protocol, direction, method, path)` is not
-- unique in this table and the address is the very column this statement changes. Matched by
-- address, a row the pass did not choose but which shares the chosen row's address — an
-- outbound call to the same path, a functional route an installed prefix does not cover —
-- moved with it.
--
-- **The entries attached to a moved row follow it in `follow_endpoint_rows.sql`**, run from
-- the same call site straight after this one: DuckDB binds parameters only on the last
-- statement of an execute, so the two cannot share this file, and that one needs none.
--
-- Running it twice would prefix twice; the pass runs it once per resolve, on rows the engines
-- have just minted.
--
-- Parameters:
--   $rows -- {row_id, prefixed}, one per row that moves. `prefixed` is what replaces the
--            row's path, already composed and canonicalised by the pass.
UPDATE endpoints e
SET path = h.prefixed
FROM (SELECT UNNEST(
    $rows::STRUCT(row_id BIGINT, prefixed VARCHAR)[]
) AS h)
WHERE e.row_id = h.row_id;
