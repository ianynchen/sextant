-- The field half of the shape pass — see derive_shapes.sql for why the pass
-- computes these rows rather than deriving them here, and why the two inserts
-- are two files.
--
-- Insert-if-absent on `shape_id` alone, and therefore all-or-nothing per
-- shape: a type two catalogs both reach keeps the field list it already has,
-- whole. Keyed on (shape_id, ordinal) instead, a second catalog whose rules
-- yield *more* fields appends its surplus onto the first catalog's list, and
-- the stored content_hash then describes neither — a field list DR-5 compares
-- that no catalog ever produced.
--
-- This runs *before* derive_shapes.sql, which is what makes `shapes` the one
-- key both halves test: a shape_id already in `shapes` is a shape some earlier
-- catalog already settled, fields and hash together.
--
-- `tags` is named as NULL rather than left out of the column list: it is a
-- column this pass has nothing to say about, and saying so is not the same as
-- forgetting it existed.
--
-- Parameters:
--   $fields -- {shape_id, ordinal, wire_name, field_number, wire_type,
--              wire_format, required, nullable, resolution, evidence, item}
--              rows, in ordinal order. `field_number` is NULL except for a
--              declared shape's own protobuf fields (2G design §3, Task 5).
INSERT INTO shape_fields (
    shape_id, ordinal, wire_name, field_number, wire_type, wire_format,
    required, nullable, resolution, evidence, tags, item
)
SELECT f.shape_id, f.ordinal, f.wire_name, f.field_number, f.wire_type, f.wire_format,
       f.required, f.nullable, f.resolution, f.evidence, NULL, f.item::JSON
FROM (SELECT UNNEST(
    $fields::STRUCT(
        shape_id VARCHAR, ordinal INTEGER, wire_name VARCHAR, field_number INTEGER,
        wire_type VARCHAR, wire_format VARCHAR, required BOOLEAN, nullable BOOLEAN,
        resolution VARCHAR, evidence VARCHAR, item VARCHAR
    )[]
) AS f)
WHERE NOT EXISTS (
    SELECT 1 FROM shapes existing WHERE existing.shape_id = f.shape_id
);
