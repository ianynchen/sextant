-- resolve/settings_modules.py: where a `resolved_config` row exists (schema.sql,
-- `config_existence`). The rows are finished in Python; this file only inserts them.
--
-- Parameters:
--   $rows -- {key, environment, route, position, via, kind, expression, holds, resolution,
--             evidence} rows.
INSERT INTO config_existence
SELECT r.key, r.environment, r.route, r.position, r.via, r.kind, r.expression, r.holds,
       r.resolution, r.evidence
FROM (SELECT UNNEST(
    $rows::STRUCT(
        key VARCHAR, environment VARCHAR, route INTEGER, position INTEGER, via VARCHAR,
        kind VARCHAR, expression VARCHAR, holds VARCHAR, resolution VARCHAR, evidence VARCHAR
    )[]
) AS r);
