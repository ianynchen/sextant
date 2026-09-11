-- The materialisation half of the shape pass. Every decision — which type is
-- mapped rather than expanded, which annotation supplies a wire name, where a
-- field's ordinal falls — is made in the pass and arrives here as bound rows.
-- Nothing is derived below: the recursive `item` descriptor is assembled
-- bottom-up over an expansion queue, which one SQL statement cannot express.
--
-- The fields of these shapes are inserted by derive_shape_fields.sql, which
-- runs first: this row is what marks a shape settled, so writing it before its
-- fields would make the guard there skip them. Two files rather than one
-- because bound parameters reach only the last statement of a script, and a
-- shape row and a field row carry different parameters.
--
-- The derivation appends. Two catalogs may both run (D02 §5), and a type both
-- of them reach is one shape, not two: a shape_id already present keeps the
-- rows it has rather than being written twice — the same insert-if-absent
-- discipline derive_endpoints.sql uses. Clearing the tables for a fresh
-- resolve therefore happens once per resolve, outside this file.
--
-- Parameters:
--   $shapes -- {shape_id, content_hash, open} rows, one per type reached
INSERT INTO shapes (shape_id, content_hash, open, origin_tier)
SELECT s.shape_id, s.content_hash, s."open", s.origin_tier
FROM (SELECT UNNEST(
    $shapes::STRUCT(
        shape_id VARCHAR, content_hash VARCHAR, "open" BOOLEAN, origin_tier VARCHAR
    )[]
) AS s)
WHERE NOT EXISTS (
    SELECT 1 FROM shapes existing WHERE existing.shape_id = s.shape_id
);
