-- F5 §6.2 (W29). One row per metadata entry an outbound call carries, already redacted
-- by the pass that read it — `value` is written masked or not at all, never masked later.
-- Since spec 2026-09-19 §5a also one row per entry an inbound endpoint's framework
-- enforces, `requirement` saying what (NULL on every outbound row).
--
-- INSERT-IF-ABSENT ON THE FULL ROW (A8): two catalogs can describe one handler — the two
-- Spring web catalogs both match a `@RestController` class — and the identical entry each
-- derives is one entry, exactly as their identical `endpoints` rows already meet
-- `insert_endpoints.sql`'s guard. Every column compares NULL-safely, because a NULL
-- `value` or `requirement` is a stated answer and two of them are equal. The guard reads
-- the table as it stood when the statement began, the caveat every such guard here
-- carries: rows within ONE call do not refuse each other.
INSERT INTO endpoint_metadata (
    protocol, direction, method, path, caller, kind, name, value, resolution, evidence,
    requirement
)
SELECT r.protocol, r.direction, r.method, r.path, r.caller,
       r.kind, r.name, r.value, r.resolution, r.evidence, r.requirement
FROM (SELECT UNNEST(
    $rows::STRUCT(
        protocol VARCHAR, direction VARCHAR, method VARCHAR, path VARCHAR, caller VARCHAR,
        kind VARCHAR, name VARCHAR, value VARCHAR, resolution VARCHAR, evidence VARCHAR,
        requirement VARCHAR
    )[]
) AS r)
WHERE NOT EXISTS (
    SELECT 1 FROM endpoint_metadata e
    WHERE e.protocol IS NOT DISTINCT FROM r.protocol
      AND e.direction IS NOT DISTINCT FROM r.direction
      AND e.method IS NOT DISTINCT FROM r.method
      AND e.path IS NOT DISTINCT FROM r.path
      AND e.caller IS NOT DISTINCT FROM r.caller
      AND e.kind IS NOT DISTINCT FROM r.kind
      AND e.name IS NOT DISTINCT FROM r.name
      AND e.value IS NOT DISTINCT FROM r.value
      AND e.resolution IS NOT DISTINCT FROM r.resolution
      AND e.evidence IS NOT DISTINCT FROM r.evidence
      AND e.requirement IS NOT DISTINCT FROM r.requirement
);
