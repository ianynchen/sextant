-- The parse-binding write (2G design §6): a bytes-only channel's
-- `request_shape` becomes the payload type its own code parses.
--
-- Nothing is decided here. Which calls are parses, which argument carries the
-- bytes, and which type a parse names are all catalog knowledge applied in
-- `resolve/shapes/parse_binding.py`; this file is handed one finished
-- descriptor per row and only applies it.
--
-- **First-writer discipline, expressed as a compare-and-set.** The rule is
-- that this pass must never overwrite an answer that is not its own. A plain
-- `request_shape IS NULL` guard would be too strong to be useful AND too weak
-- to be safe: too strong, because the rows this pass exists for do carry a
-- value — the opaque bytes their handler declares (`{"wire_type":"string"}`,
-- an array of bytes), which is the wire's shape and not the contract's; too
-- weak, because NULL is also what a row whose payload nobody could read
-- carries. So the pass sends back the exact value it READ while deciding, and
-- the update fires only where the column still holds it. A row answered by
-- anyone else between the read and the write keeps that answer, and running
-- the statement twice changes nothing the second time.
--
-- Rows are matched on the same six identity columns `stamp_format.sql` uses:
-- `(protocol, direction, method, path)` is not unique in this table — two
-- listeners on one destination, several NULL-path call sites — and
-- `handler`/`caller` are what separate them. Every column uses IS NOT
-- DISTINCT FROM: a messaging row carries NULLs in most of them, and SQL
-- equality would silently match none.
--
-- Parameters:
--   $rows -- {protocol, direction, method, path, handler, caller,
--             bytes_shape, request_shape}, one per BOUND row. `bytes_shape`
--             is the value the column must still hold; `request_shape` is
--             what replaces it.
UPDATE endpoints e
SET request_shape = b.request_shape
FROM (SELECT UNNEST(
    $rows::STRUCT(
        protocol VARCHAR, direction VARCHAR, method VARCHAR, path VARCHAR,
        handler VARCHAR, caller VARCHAR, bytes_shape VARCHAR, request_shape VARCHAR
    )[]
) AS b)
WHERE e.protocol      IS NOT DISTINCT FROM b.protocol
  AND e.direction     IS NOT DISTINCT FROM b.direction
  AND e.method        IS NOT DISTINCT FROM b.method
  AND e.path          IS NOT DISTINCT FROM b.path
  AND e.handler       IS NOT DISTINCT FROM b.handler
  AND e.caller        IS NOT DISTINCT FROM b.caller
  AND e.request_shape IS NOT DISTINCT FROM b.bytes_shape;
