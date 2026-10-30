-- F5 §6.2 (W29). One row per metadata entry an outbound call carries, already redacted
-- by the pass that read it — `value` is written masked or not at all, never masked later.
-- Since spec 2026-09-19 §5a also one row per entry an inbound endpoint's framework
-- enforces, `requirement` saying what (NULL on every outbound row).
--
-- THREE passes reach this statement, and the sentence above is a claim about all three:
-- `resolve/engines/fluent.py`, `resolve/request_requirements.py` and
-- `resolve/endpoint_attributes.py`. Two of them were writing `value` in the clear until
-- 2026-09-22 — the claim was here the whole time and nothing tied it to a writer, which is
-- how it went unmet. `tests/architecture/test_source_rules.py::
-- test_every_origin_writing_endpoint_metadata_holds_a_redactor` is that tie now: a fourth
-- origin cannot be added without a redactor.
--
-- INSERT-IF-ABSENT ON THE FULL ROW (A8): two catalogs can describe one handler — the two
-- Spring web catalogs both match a `@RestController` class — and the identical entry each
-- derives is one entry, exactly as their identical `endpoints` rows already meet
-- `insert_endpoints.sql`'s guard. Every column compares NULL-safely, because a NULL
-- `value` or `requirement` is a stated answer and two of them are equal. Two halves, one
-- per place a duplicate can come from: `NOT EXISTS` refuses a row an EARLIER statement
-- wrote (it reads the table as it stood when this one began), and `SELECT DISTINCT`
-- collapses duplicates WITHIN this batch — the requirements pass gathers every catalog's
-- rows into one `$rows` list, so the two catalogs describing one handler meet here, not
-- across statements. Row-level DISTINCT treats NULLs as equal, as the guard does; the
-- table is a SET (D01 §3) and this is what makes the statement one.
--
-- EVERY ENTRY IS BOUND TO ITS ROW'S `row_id` HERE (follow-the-object, Ruling 7), by joining
-- `endpoints` on the entry's identity columns. Here is the one moment those columns are
-- certain to equal the row's: `fluent` and `single_call` write in the pass that mints the
-- row, before the path prefix or a protocol reclassification has moved it. The entry's
-- `caller` is the row's `handler` on an inbound row and its `caller` on an outbound one
-- (the column's own comment in `schema.sql`). Where several rows match — two outbound rows
-- of one caller to one path differing only in `peer` — the entry is one row per match, each
-- following its own; where none matches, `row_id` is NULL and the entry is written as before.
-- The guard compares `row_id` too, so the same entry against two rows is two entries.
INSERT INTO endpoint_metadata (
    row_id, protocol, direction, method, path, caller, kind, name, value, resolution, evidence,
    requirement
)
SELECT DISTINCT e.row_id, r.protocol, r.direction, r.method, r.path, r.caller,
       r.kind, r.name, r.value, r.resolution, r.evidence, r.requirement
FROM (SELECT UNNEST(
    $rows::STRUCT(
        protocol VARCHAR, direction VARCHAR, method VARCHAR, path VARCHAR, caller VARCHAR,
        kind VARCHAR, name VARCHAR, value VARCHAR, resolution VARCHAR, evidence VARCHAR,
        requirement VARCHAR
    )[]
) AS r)
LEFT JOIN endpoints e
  ON e.protocol  IS NOT DISTINCT FROM r.protocol
 AND e.direction IS NOT DISTINCT FROM r.direction
 AND e.method    IS NOT DISTINCT FROM r.method
 AND e.path      IS NOT DISTINCT FROM r.path
 AND r.caller    IS NOT DISTINCT FROM
         CASE WHEN e.direction = 'outbound' THEN e.caller ELSE e.handler END
WHERE NOT EXISTS (
    SELECT 1 FROM endpoint_metadata m
    WHERE m.row_id IS NOT DISTINCT FROM e.row_id
      AND m.protocol IS NOT DISTINCT FROM r.protocol
      AND m.direction IS NOT DISTINCT FROM r.direction
      AND m.method IS NOT DISTINCT FROM r.method
      AND m.path IS NOT DISTINCT FROM r.path
      AND m.caller IS NOT DISTINCT FROM r.caller
      AND m.kind IS NOT DISTINCT FROM r.kind
      AND m.name IS NOT DISTINCT FROM r.name
      AND m.value IS NOT DISTINCT FROM r.value
      AND m.resolution IS NOT DISTINCT FROM r.resolution
      AND m.evidence IS NOT DISTINCT FROM r.evidence
      AND m.requirement IS NOT DISTINCT FROM r.requirement
);
