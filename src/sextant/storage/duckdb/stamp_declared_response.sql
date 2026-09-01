-- The `schema_operations` style's declared-response stamp (D02 §2, 2H design
-- §3's agreement half): fills `response_shape` on the rows whose wire identity
-- a schema's own root operation names, from a descriptor the pass already
-- built out of the schema's field declaration.
--
-- Nothing is decided here. Which types are operation roots, which schema
-- format states them, what each root field's declared type looks like in D01
-- §5's `{wire_type, wire_format, nullable, shape_id?, item?}` grammar, and
-- which value goes in the `method` column are all read in the pass — from the
-- `declared_shape` facts and the catalog's own vocabulary. This file is handed
-- the finished descriptor and the four columns that select the rows.
--
-- **First-writer discipline lives in the WHERE clause**, exactly as
-- stamp_media.sql keeps it: only a row whose `response_shape` IS NULL is
-- touched, which is `coalesce(existing, declared)` written as a guard. A row
-- another evidence kind already answered keeps its own answer.
--
-- **What this actually delivers, stated rather than implied** (the 2F/2G
-- merge-carry honesty bar). This runs inside `derive_endpoints`, where every
-- annotation-derived row still carries `response_shape` NULL —
-- `derive_endpoints.sql` does not populate the payload columns at all, the
-- shape pass does, and the shape pass runs after every engine
-- (`resolve/pipeline.py`). So the rows this statement reaches are:
--
--   * the style's OWN rows, which is how a schema-first operation gets the
--     shape reference its endpoint publishes; and
--   * every annotation twin whose identity the schema also names — where the
--     stamp lands, and then survives only if that row's handler declares NO
--     payload of its own, because `derive_endpoint_contracts.sql` re-answers
--     both payload columns for any row still carrying its own
--     `handler_signature`. That is 2H design §4's rule arriving by ordering
--     rather than by a second guard: an annotated operation keeps the types
--     its own handler signature really serializes, and the schema's declared
--     type is what a row with nothing else to say ends up publishing.
--
-- The narrowest corner of that — a handler with a REQUEST payload and no
-- response, whose owner is therefore in `$contracts` with a NULL response
-- answer, so the stamped type is nulled again and the row publishes no
-- response at all — is pinned as a test
-- (`test_a_handler_with_a_request_and_no_response_ends_with_response_shape_null`).
-- Moving this statement relative to the shape pass changes that published
-- column, so it must fail a test and be argued for rather than flip silently.
--
-- Parameters:
--   $rows -- {protocol, direction, method, path, response_shape} rows, one per
--            root-operation identity the pass derived, already deduplicated on
--            that identity by the pass
UPDATE endpoints e
SET response_shape = r.response_shape
FROM (SELECT UNNEST(
    $rows::STRUCT(
        protocol VARCHAR, direction VARCHAR, method VARCHAR, path VARCHAR,
        response_shape VARCHAR
    )[]
) AS r)
WHERE e.protocol  = r.protocol
  AND e.direction = r.direction
  AND e.method IS NOT DISTINCT FROM r.method
  AND e.path      = r.path
  AND e.response_shape IS NULL;
