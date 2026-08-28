-- The annotation_driven engine (D02 §2): a generic interpreter over catalog
-- data. Every annotation identifier, alias list and method mapping arrives as
-- a bound parameter from the loaded catalog — this file matches on the values
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
--   $mapping_annotations -- list of {fqn, methods} rows: one per mapping annotation,
--                           `methods` holding the methods that annotation pre-sets,
--                           or NULL where it pre-sets none
--   $prefix_annotation   -- fqn of the type-level annotation carrying the path prefix
--   $path_from           -- attribute names that alias one another, first present wins
--   $method_from         -- attribute name holding the method, where one is given
--   $all_methods         -- the methods a mapping annotation means when it names none

INSERT INTO endpoints
WITH mapping_catalog AS (
    SELECT s.fqn AS fqn, s.methods AS methods
    FROM (SELECT UNNEST(
        $mapping_annotations::STRUCT(fqn VARCHAR, methods VARCHAR[])[]
    ) AS s)
),
controllers AS (
    SELECT DISTINCT target AS type_symbol
    FROM annotations
    WHERE annotation = $type_annotation
),
-- Every annotation this catalog reads a path from — the mapping annotations and
-- the prefix annotation, which for some frameworks is one of them and for
-- others is not (D02 §2).
declared AS (
    SELECT
        a.target AS target,
        a.annotation AS annotation,
        -- The prefix annotation is not always a mapping annotation, so only a
        -- row that matched the catalog's mapping list may declare an endpoint.
        mc.fqn IS NOT NULL AS is_mapping,
        -- An annotation argument arrives as a JSON array where the annotation
        -- declares an array type, and as a bare value where it declares a
        -- scalar. Both forms occur among the catalogs this engine serves, so
        -- element 0 is read first and the value itself second. The catalog's
        -- alias order decides which name wins, so the result is deterministic;
        -- an annotation naming no path falls back to the empty string rather
        -- than being assumed present.
        coalesce(list_extract(list_filter(list_transform(
            $path_from::VARCHAR[],
            n -> coalesce(a.args -> n ->> 0, a.args ->> n)
        ), v -> v IS NOT NULL), 1), '') AS path,
        -- The attribute wins, then what the annotation pre-sets, then every
        -- method. An enum argument is a symbol reference (D00 §5a), so the
        -- constant is taken from its tail.
        coalesce(
            -- An empty list is absence, not an answer: it is what a dropped
            -- argument looks like, and taking it literally yields no endpoint
            -- at all rather than falling through to the methods below.
            CASE WHEN len(coalesce(
                TRY_CAST(a.args -> $method_from AS VARCHAR[]),
                CASE WHEN a.args ->> $method_from IS NOT NULL
                     THEN [a.args ->> $method_from] END,
                []::VARCHAR[]
            )) > 0
            THEN list_transform(
                coalesce(
                    TRY_CAST(a.args -> $method_from AS VARCHAR[]),
                    [a.args ->> $method_from]
                ),
                v -> regexp_extract(v, '#([A-Za-z0-9_]+)\.$', 1)
            ) END,
            mc.methods,
            $all_methods::VARCHAR[]
        ) AS methods
    FROM annotations a
    LEFT JOIN mapping_catalog mc ON mc.fqn = a.annotation
    WHERE mc.fqn IS NOT NULL OR a.annotation = $prefix_annotation
),
prefixes AS (
    SELECT d.target AS type_symbol, d.path AS prefix
    FROM declared d
    WHERE d.annotation = $prefix_annotation
),
mappings AS (
    -- A mapping annotation naming no method means every method, and each is a
    -- distinct wire contract, so each is its own endpoint (D02 §2).
    SELECT d.target AS method_symbol,
           UNNEST(d.methods) AS wire_method,
           d.path AS path_suffix
    FROM declared d
    WHERE d.is_mapping
),
derived AS (
    SELECT
        $protocol   AS protocol,
        $direction  AS direction,
        m.wire_method AS method,
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
