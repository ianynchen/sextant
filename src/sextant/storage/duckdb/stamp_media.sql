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
-- **HOW WIDE THE REACH IS, settled rather than left to be re-inferred**
-- (principles sweep §7.4, where two sweeps touched this file and neither read
-- it). The WHERE names `(protocol, direction)` and nothing else, so:
--
--   * It DOES stamp rows other catalogs derived, and that is the mechanism
--     rather than a leak: `spring-kafka-media.yml` derives no rows of its own
--     and exists only to fill a column on rows other engines minted.
--   * It CANNOT stamp another module's rows. `endpoints` carries no `module`
--     column (`schema.sql`), every module gets its own workspace
--     (`api.py::_analyze_reactor`), and `resolve()` runs once per module — so
--     the cross-module over-stamp sweep 1 alleged has no path to exist. That
--     half of the allegation is false.
--   * It is an OVER-REPORT for a row whose own catalog does not read the key
--     the rule names — a raw `KafkaProducer` builds its own `Properties` and
--     reads no `spring.kafka.*` key, and inherits the stamp anyway on a module
--     that also declares spring-kafka. `produces`/`consumes` are carried data,
--     never identity: no address, verb or protocol moves, and dedup and merge
--     never compare them. Narrowing it means declaring WHICH catalogs a rule
--     applies to, which is a D02 §2d schema change and must not be done by
--     scoping to the stamping catalog's own id — that would stamp nothing at
--     all. Pinned in both directions by `test_config_join.py`.
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
