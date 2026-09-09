-- F5 §6.2 (W29). One row per metadata entry an outbound call carries, already redacted
-- by the pass that read it — `value` is written masked or not at all, never masked later.
INSERT INTO endpoint_metadata (
    protocol, direction, method, path, caller, kind, name, value, resolution, evidence
)
SELECT r.protocol, r.direction, r.method, r.path, r.caller,
       r.kind, r.name, r.value, r.resolution, r.evidence
FROM (SELECT UNNEST(
    $rows::STRUCT(
        protocol VARCHAR, direction VARCHAR, method VARCHAR, path VARCHAR, caller VARCHAR,
        kind VARCHAR, name VARCHAR, value VARCHAR, resolution VARCHAR, evidence VARCHAR
    )[]
) AS r);
