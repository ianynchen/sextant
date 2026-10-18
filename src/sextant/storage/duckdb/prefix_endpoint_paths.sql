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
-- Rows are matched on the same six identity columns `reclassify_protocol.sql` and
-- `stamp_format.sql` use, with IS NOT DISTINCT FROM on every one: `(protocol, direction,
-- method, path)` is not unique in this table and a messaging row carries NULLs in most of
-- these, where SQL equality would silently match none.
--
-- **Running it twice changes nothing the second time**, by the same construction as
-- `reclassify_protocol.sql`: `h.path` is the row's ORIGINAL path and `h.prefixed` is the
-- replacement, so once a row has been rewritten it no longer matches its own old key. That is
-- what makes the statement safe to re-run and is why the match carries `path` at all.
--
-- Parameters:
--   $rows -- {protocol, direction, method, path, handler, caller, prefixed}, one per row that
--            moves. `path` is the value the row must still hold; `prefixed` is what replaces
--            it, already composed and canonicalised by the pass.
UPDATE endpoints e
SET path = h.prefixed
FROM (SELECT UNNEST(
    $rows::STRUCT(
        protocol VARCHAR, direction VARCHAR, method VARCHAR, path VARCHAR,
        handler VARCHAR, caller VARCHAR, prefixed VARCHAR
    )[]
) AS h)
WHERE e.protocol  IS NOT DISTINCT FROM h.protocol
  AND e.direction IS NOT DISTINCT FROM h.direction
  AND e.method    IS NOT DISTINCT FROM h.method
  AND e.path      IS NOT DISTINCT FROM h.path
  AND e.handler   IS NOT DISTINCT FROM h.handler
  AND e.caller    IS NOT DISTINCT FROM h.caller;
