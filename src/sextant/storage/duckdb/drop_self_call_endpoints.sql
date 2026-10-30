-- Spec 2026-10-25 §3c (rulings 1 and 3): an outbound row for a service this module itself
-- serves is not an outbound call, it is a traceable hop to a handler the module owns.
--
-- Nothing is decided here. Which services the module serves, and which peers count as the
-- module itself, are decided in `resolve/self_calls.py`; this file is handed the finished
-- list of rows to remove and only removes them.
--
-- **DELETE only, and only the rows named.** Rows are matched on `row_id` (follow-the-object,
-- Ruling 7), which names exactly the row the pass chose: two outbound rows of one service
-- differ only in the address they call, and dropping the one that names this module must not
-- take the one that names another host (ruling 3). `follow_endpoint_rows.sql`, run straight
-- after from the same call site, removes the entries bound to a dropped row.
--
-- Running it twice changes nothing the second time: the first run removes every row the
-- list names.
--
-- Parameters:
--   $rows -- {row_id}, one per row to drop.
DELETE FROM endpoints e
USING (SELECT UNNEST(
    $rows::STRUCT(row_id BIGINT)[]
) AS h) d
WHERE e.row_id = d.h.row_id;
