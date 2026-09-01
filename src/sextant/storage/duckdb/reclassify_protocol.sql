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
-- **The scoping is the matched value, not a literal.** `h.protocol` is the
-- row's ORIGINAL protocol, and the pass only ever puts a row in `$rows` when
-- the catalog that named the evidence declares that protocol as its own. So
-- the UPDATE is scoped to exactly the source protocol the catalogs sanction —
-- expressed as data, because a protocol name spliced into this file would be
-- framework knowledge in the storage layer (ARCHITECTURE §10).
--
-- Rows are matched on the same six identity columns `stamp_format.sql` and
-- `bind_request_shape.sql` use: `(protocol, direction, method, path)` is not
-- unique in this table — two listeners on one destination, several NULL-path
-- call sites — and `handler`/`caller` are what separate them. Every column
-- uses IS NOT DISTINCT FROM: a messaging row carries NULLs in most of them,
-- and SQL equality would silently match none.
--
-- Running the statement twice changes nothing the second time: the first run
-- takes the matched rows off their old protocol, and the pass refuses a
-- catalog whose target equals its own source, so no row can match its own
-- rewritten value.
--
-- Parameters:
--   $rows -- {protocol, direction, method, path, handler, caller,
--             reclassified}, one per RECLASSIFIED row. `protocol` is the
--             value the row must still hold; `reclassified` is what replaces
--             it.
UPDATE endpoints e
SET protocol = h.reclassified
FROM (SELECT UNNEST(
    $rows::STRUCT(
        protocol VARCHAR, direction VARCHAR, method VARCHAR, path VARCHAR,
        handler VARCHAR, caller VARCHAR, reclassified VARCHAR
    )[]
) AS h)
WHERE e.protocol  IS NOT DISTINCT FROM h.protocol
  AND e.direction IS NOT DISTINCT FROM h.direction
  AND e.method    IS NOT DISTINCT FROM h.method
  AND e.path      IS NOT DISTINCT FROM h.path
  AND e.handler   IS NOT DISTINCT FROM h.handler
  AND e.caller    IS NOT DISTINCT FROM h.caller;
