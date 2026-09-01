-- The `config_join` style's media stamp (D02 §2d's `media_from_config`):
-- fills ONE declared media column on the rows a rule names, from a value the
-- pass already decided.
--
-- Nothing is decided here. Which configuration key names a media type, which
-- column it fills, which rows it applies to, whether every environment agreed
-- on it, and what the configured class means on the wire are all catalog
-- knowledge applied in the pass; this file is handed the finished string and
-- the two columns that select the rows.
--
-- **First-writer discipline lives in the WHERE clause**: only a row whose
-- target column IS NULL is touched, so a declaration another evidence kind
-- already read off the code itself is never overwritten by a module-level
-- default. That is also why the `CASE` below is safe to write unconditionally
-- for both columns — the WHERE has already excluded every row the named
-- column would not be filling.
--
-- The column is a bound VALUE, not interpolated SQL: `$column` selects which
-- of the two D01 §3 media columns this call fills, and the other keeps
-- whatever it held. A statement that spliced a column name in would put a
-- catalog string into the query text itself.
--
-- Parameters:
--   $column    -- which media column this rule fills: `consumes` or `produces`
--   $value     -- the JSON array of MIME strings to write, exactly the shape
--                 every other evidence kind writes into these columns
--   $protocol  -- the rows' protocol
--   $direction -- the rows' direction
UPDATE endpoints
SET consumes = CASE WHEN $column = 'consumes' THEN $value ELSE consumes END,
    produces = CASE WHEN $column = 'produces' THEN $value ELSE produces END
WHERE protocol = $protocol
  AND direction = $direction
  AND (($column = 'consumes' AND consumes IS NULL)
    OR ($column = 'produces' AND produces IS NULL));
