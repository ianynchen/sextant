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
-- **Rows are matched on identity plus every column the decision read**, not
-- on wire identity alone. `(protocol, direction, method, path)` is not unique
-- in this table — two listeners on one topic, two unresolved call sites with
-- NULL paths — and `handler`/`caller` are what separate them (the same
-- tie-break the "endpoints" named query orders by).
--
-- The four carried columns ride along because they are INPUTS to the answer:
-- `consumes`/`produces` are what rung 2 reads and `request_shape`/
-- `response_shape` are what rungs 4 and 5 read. Two rows agreeing on all
-- eight were therefore handed the same answer, so a duplicate match is
-- idempotent rather than ambiguous — which is the property that lets this
-- statement have no unique key at all. Every column uses IS NOT DISTINCT
-- FROM: a messaging row whose destination could not be read carries NULLs in
-- most of them, and SQL equality would silently match none of them.
--
-- Parameters:
--   $rows -- {protocol, direction, method, path, handler, caller, consumes,
--             produces, request_shape, response_shape, format,
--             format_resolution}, one per row of `endpoints`, in the table's
--             own query order
UPDATE endpoints e
SET format = f.format,
    format_resolution = f.format_resolution
FROM (SELECT UNNEST(
    $rows::STRUCT(
        protocol VARCHAR, direction VARCHAR, method VARCHAR, path VARCHAR,
        handler VARCHAR, caller VARCHAR, consumes VARCHAR, produces VARCHAR,
        request_shape VARCHAR, response_shape VARCHAR, format VARCHAR,
        format_resolution VARCHAR
    )[]
) AS f)
WHERE e.protocol       IS NOT DISTINCT FROM f.protocol
  AND e.direction      IS NOT DISTINCT FROM f.direction
  AND e.method         IS NOT DISTINCT FROM f.method
  AND e.path           IS NOT DISTINCT FROM f.path
  AND e.handler        IS NOT DISTINCT FROM f.handler
  AND e.caller         IS NOT DISTINCT FROM f.caller
  AND e.consumes       IS NOT DISTINCT FROM f.consumes
  AND e.produces       IS NOT DISTINCT FROM f.produces
  AND e.request_shape  IS NOT DISTINCT FROM f.request_shape
  AND e.response_shape IS NOT DISTINCT FROM f.response_shape;
