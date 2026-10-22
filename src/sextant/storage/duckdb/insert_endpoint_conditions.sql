-- The conditions pass's rows, insert-if-absent on the whole row: the table is a SET (D01 §3),
-- and two catalogs describing one handler (spring-web and spring-mvc both own inbound http)
-- meet here rather than across statements.
INSERT INTO endpoint_conditions (
    protocol, direction, method, path, handler, kind, expression, environment, holds,
    resolution, evidence
)
SELECT DISTINCT r.protocol, r.direction, r.method, r.path, r.handler, r.kind, r.expression,
       r.environment, r.holds, r.resolution, r.evidence
FROM (SELECT UNNEST(
    $rows::STRUCT(
        protocol VARCHAR, direction VARCHAR, method VARCHAR, path VARCHAR, handler VARCHAR,
        kind VARCHAR, expression VARCHAR, environment VARCHAR, holds VARCHAR,
        resolution VARCHAR, evidence VARCHAR
    )[]
) AS r)
WHERE NOT EXISTS (
    SELECT 1 FROM endpoint_conditions e
    WHERE e.protocol IS NOT DISTINCT FROM r.protocol
      AND e.direction IS NOT DISTINCT FROM r.direction
      AND e.method IS NOT DISTINCT FROM r.method
      AND e.path IS NOT DISTINCT FROM r.path
      AND e.handler IS NOT DISTINCT FROM r.handler
      AND e.kind IS NOT DISTINCT FROM r.kind
      AND e.expression IS NOT DISTINCT FROM r.expression
      AND e.environment IS NOT DISTINCT FROM r.environment
);
