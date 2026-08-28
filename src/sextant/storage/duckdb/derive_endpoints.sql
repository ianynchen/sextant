-- The annotation_driven engine (D02 §2): a generic interpreter over catalog
-- data. Every annotation identifier and its HTTP-method mapping arrives as a
-- bound parameter from the loaded catalog — this file matches on the values
-- it is handed, never on a literal it contains, so a second annotation_driven
-- framework is a new YAML file with no change here.
--
-- The derivation appends: D02 §5 allows two catalogs to match the same module,
-- and both produce endpoints. Rows already present for the same wire identity
-- --- protocol, direction, method and path --- are the duplicates that section
-- says merge, so they are not inserted twice. The table is emptied once per
-- resolve by reset_endpoints.sql, never once per catalog.
--
-- Parameters:
--   $protocol            -- the catalog's declared protocol (D00's closed set)
--   $direction           -- the catalog's declared direction (D00's closed set)
--   $type_annotation     -- fqn of the type-level annotation that marks a controller
--   $prefix_annotation   -- fqn of the type-level annotation carrying the path prefix
--   $prefix_arg          -- name of the prefix annotation's path argument
--   $method_annotations  -- list of {fqn, http_method, path_arg} rows, one per
--                           method-level mapping annotation the catalog declares

INSERT INTO endpoints
WITH method_catalog AS (
    SELECT fqn, http_method, path_arg
    FROM (SELECT UNNEST(
        $method_annotations::STRUCT(fqn VARCHAR, http_method VARCHAR, path_arg VARCHAR)[],
        recursive := true
    ))
),
controllers AS (
    SELECT DISTINCT target AS type_symbol
    FROM annotations
    WHERE annotation = $type_annotation
),
prefixes AS (
    -- An annotation argument arrives as a JSON array where the annotation
    -- declares an array type, and as a bare value where it declares a
    -- scalar. Both forms occur among the catalogs this engine serves, so
    -- element 0 is read first and the value itself second; an annotation
    -- used with no argument at all falls back to the empty string rather
    -- than being assumed present.
    SELECT target AS type_symbol,
           coalesce(args -> $prefix_arg ->> 0, args ->> $prefix_arg, '') AS prefix
    FROM annotations
    WHERE annotation = $prefix_annotation
),
mappings AS (
    SELECT a.target AS method_symbol,
           mc.http_method AS http_method,
           coalesce(a.args -> mc.path_arg ->> 0, a.args ->> mc.path_arg, '') AS path_suffix
    FROM annotations a
    JOIN method_catalog mc ON mc.fqn = a.annotation
),
derived AS (
    SELECT
        $protocol   AS protocol,
        $direction  AS direction,
        m.http_method AS method,
        coalesce(p.prefix, '') || m.path_suffix AS path,
        s.symbol    AS handler,
        s.signature AS handler_signature,
        'resolved'  AS resolution,
        'compiler'  AS evidence
    FROM mappings m
    JOIN symbols s ON s.symbol = m.method_symbol
    JOIN controllers c ON s.enclosing = c.type_symbol
    LEFT JOIN prefixes p ON p.type_symbol = c.type_symbol
)
SELECT * FROM derived d
WHERE NOT EXISTS (
    SELECT 1 FROM endpoints existing
    WHERE existing.protocol  = d.protocol
      AND existing.direction = d.direction
      AND existing.method    = d.method
      AND existing.path      = d.path
);
