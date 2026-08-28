-- The annotation_driven engine (D02 §2): a generic interpreter over catalog
-- data. Every annotation identifier and its HTTP-method mapping arrives as a
-- bound parameter from the loaded catalog — this file matches on the values
-- it is handed, never on a literal it contains, so a second annotation_driven
-- framework is a new YAML file with no change here.
--
-- Parameters:
--   $type_annotation     -- fqn of the type-level annotation that marks a controller
--   $prefix_annotation   -- fqn of the type-level annotation carrying the path prefix
--   $prefix_arg          -- name of the prefix annotation's path argument
--   $method_annotations  -- list of {fqn, http_method, path_arg} rows, one per
--                           method-level mapping annotation the catalog declares

CREATE OR REPLACE TABLE endpoints AS
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
    -- A compiled array-typed annotation argument arrives as a JSON array;
    -- the first element is the path, and an annotation used with no
    -- argument at all falls back to the empty string rather than being
    -- assumed present.
    SELECT target AS type_symbol,
           coalesce(args -> $prefix_arg ->> 0, '') AS prefix
    FROM annotations
    WHERE annotation = $prefix_annotation
),
mappings AS (
    SELECT a.target AS method_symbol,
           mc.http_method AS http_method,
           coalesce(a.args -> mc.path_arg ->> 0, '') AS path_suffix
    FROM annotations a
    JOIN method_catalog mc ON mc.fqn = a.annotation
)
SELECT
    'http'      AS protocol,
    'inbound'   AS direction,
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
ORDER BY method, path;
