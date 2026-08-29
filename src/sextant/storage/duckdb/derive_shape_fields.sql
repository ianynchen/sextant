-- The field half of the shape pass — see derive_shapes.sql for why the pass
-- computes these rows rather than deriving them here, and why the two inserts
-- are two files.
--
-- Insert-if-absent on (shape_id, ordinal) for the same reason shapes are:
-- a type two catalogs both reach keeps the field list it already has.
--
-- `tags` is named as NULL rather than left out of the column list: it is a
-- column this pass has nothing to say about, and saying so is not the same as
-- forgetting it existed.
--
-- Parameters:
--   $fields -- {shape_id, ordinal, wire_name, wire_type, wire_format, required,
--              nullable, resolution, evidence, item} rows, in ordinal order
INSERT INTO shape_fields (
    shape_id, ordinal, wire_name, wire_type, wire_format,
    required, nullable, resolution, evidence, tags, item
)
SELECT f.shape_id, f.ordinal, f.wire_name, f.wire_type, f.wire_format,
       f.required, f.nullable, f.resolution, f.evidence, NULL, f.item::JSON
FROM (SELECT UNNEST(
    $fields::STRUCT(
        shape_id VARCHAR, ordinal INTEGER, wire_name VARCHAR, wire_type VARCHAR,
        wire_format VARCHAR, required BOOLEAN, nullable BOOLEAN,
        resolution VARCHAR, evidence VARCHAR, item VARCHAR
    )[]
) AS f)
WHERE NOT EXISTS (
    SELECT 1 FROM shape_fields existing
    WHERE existing.shape_id = f.shape_id AND existing.ordinal = f.ordinal
);
