-- The conditions pass's rows (`resolve/bean_conditions.py`), deduplicated on the whole row:
-- the table is a SET (D01 §3), and the one pass that writes it runs after the reset.
INSERT INTO bean_conditions (
    bean, bean_kind, via, kind, expression, environment, holds, resolution, evidence
)
SELECT DISTINCT r.bean, r.bean_kind, r.via, r.kind, r.expression, r.environment, r.holds,
       r.resolution, r.evidence
FROM (SELECT UNNEST(
    $rows::STRUCT(
        bean VARCHAR, bean_kind VARCHAR, via VARCHAR, kind VARCHAR, expression VARCHAR,
        environment VARCHAR, holds VARCHAR, resolution VARCHAR, evidence VARCHAR
    )[]
) AS r);
