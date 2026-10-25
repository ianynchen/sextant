-- Spec 2026-10-25 §3c (rulings 1 and 3): an outbound row for a service this module itself
-- serves is not an outbound call, it is a traceable hop to a handler the module owns.
--
-- Nothing is decided here. Which services the module serves, and which peers count as the
-- module itself, are decided in `resolve/self_calls.py`; this file is handed the finished
-- list of rows to remove and only removes them.
--
-- **DELETE only, and only the rows named.** Rows are matched on the six identity columns
-- `reclassify_protocol.sql` uses, plus `peer`: two outbound rows of one service differ only
-- in the address they call, and dropping the one that names this module must not take the
-- one that names another host (ruling 3). Every column uses IS NOT DISTINCT FROM, since an
-- outbound client row carries NULLs in `method` and `handler`, and SQL equality would match
-- none of them.
--
-- Running it twice changes nothing the second time: the first run removes every row the
-- list names.
--
-- Parameters:
--   $rows -- {protocol, direction, method, path, handler, caller, peer}, one per row to drop.
DELETE FROM endpoints e
USING (SELECT UNNEST(
    $rows::STRUCT(
        protocol VARCHAR, direction VARCHAR, method VARCHAR, path VARCHAR,
        handler VARCHAR, caller VARCHAR, peer VARCHAR
    )[]
) AS h) d
WHERE e.protocol  IS NOT DISTINCT FROM d.h.protocol
  AND e.direction IS NOT DISTINCT FROM d.h.direction
  AND e.method    IS NOT DISTINCT FROM d.h.method
  AND e.path      IS NOT DISTINCT FROM d.h.path
  AND e.handler   IS NOT DISTINCT FROM d.h.handler
  AND e.caller    IS NOT DISTINCT FROM d.h.caller
  AND e.peer      IS NOT DISTINCT FROM d.h.peer;
