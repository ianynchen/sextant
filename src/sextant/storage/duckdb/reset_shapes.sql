-- Clears both shape tables for one resolve, for the reason
-- reset_endpoints.sql clears its own: derive_shapes.sql and
-- derive_shape_fields.sql are insert-if-absent, because two catalogs may both
-- reach the same type and it is one shape rather than two. That discipline
-- makes the whole-table rebuild a once-per-resolve act, not a per-catalog one
-- — and without it a reused workspace keeps a previous resolve's shapes,
-- which is a field list nothing in the current run produced.
--
-- Fields first, then the shape rows: `shapes` is the key both halves test for
-- "already settled" (see derive_shape_fields.sql), so emptying it first would
-- leave a window in which the fields are orphaned rather than gone. The
-- tables themselves are never dropped — schema.sql pre-declares them so the
-- "shapes"/"shape_fields" queries still answer when capability gating skips
-- every catalog and no derivation runs at all.
DELETE FROM shape_fields;
DELETE FROM shapes;
