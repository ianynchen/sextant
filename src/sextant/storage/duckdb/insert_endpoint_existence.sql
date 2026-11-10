-- OI-368: where each registered row exists, one entry per (row, alternative, test,
-- environment), written by the engine that minted the rows, right after them
-- (`resolve/registration_conditions.py`).
--
-- EVERY ENTRY IS BOUND TO ITS ROW'S `row_id` HERE (follow-the-object, Ruling 7), as
-- `insert_endpoint_metadata.sql` binds its entries and for its reason: the identity columns
-- equal the row's only now, before the path prefix or a protocol reclassification moves it.
-- An inbound row is identified by its address, handler and registering method. Where no row
-- matches, nothing is written: an entry says where a ROW exists. Insert-if-absent on the
-- whole entry, with `SELECT DISTINCT` for duplicates within the batch.
INSERT INTO endpoint_existence (
    row_id, protocol, direction, method, path, handler, caller, route, position, via, kind,
    expression, environment, holds, resolution, evidence
)
SELECT DISTINCT e.row_id, r.protocol, r.direction, r.method, r.path, r.handler, r.caller,
       r.route, r.position, r.via, r.kind, r.expression, r.environment, r.holds, r.resolution,
       r.evidence
FROM (SELECT UNNEST(
    $rows::STRUCT(
        protocol VARCHAR, direction VARCHAR, method VARCHAR, path VARCHAR, handler VARCHAR,
        caller VARCHAR, route INTEGER, position INTEGER, via VARCHAR, kind VARCHAR,
        expression VARCHAR, environment VARCHAR, holds VARCHAR, resolution VARCHAR, evidence VARCHAR
    )[]
) AS r)
JOIN endpoints e
  ON e.protocol  IS NOT DISTINCT FROM r.protocol
 AND e.direction IS NOT DISTINCT FROM r.direction
 AND e.method    IS NOT DISTINCT FROM r.method
 AND e.path      IS NOT DISTINCT FROM r.path
 AND e.handler   IS NOT DISTINCT FROM r.handler
 AND e.caller    IS NOT DISTINCT FROM r.caller
WHERE NOT EXISTS (
    SELECT 1 FROM endpoint_existence x
    WHERE x.row_id = e.row_id
      AND x.route IS NOT DISTINCT FROM r.route
      AND x.position IS NOT DISTINCT FROM r.position
      AND x.via IS NOT DISTINCT FROM r.via
      AND x.kind IS NOT DISTINCT FROM r.kind
      AND x.expression IS NOT DISTINCT FROM r.expression
      AND x.environment IS NOT DISTINCT FROM r.environment
);
