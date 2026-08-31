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
--   $type_annotation     -- fqn of the type-level annotation that marks a
--                           controller or client, or NULL where the catalog
--                           declares no type-level gate at all (D02 §2,
--                           amended) — a Retrofit interface carries no marker,
--                           so its method annotations are the whole evidence.
--   $mapping_annotations -- list of {fqn, methods} rows: one per mapping annotation,
--                           `methods` holding the methods that annotation pre-sets,
--                           or NULL where it pre-sets none
--   $prefix_annotation   -- fqn of the type-level annotation carrying the path prefix
--   $path_from           -- attribute names that alias one another, first present wins
--   $prefix_from         -- attribute names the prefix annotation's address
--                           prefix is read from (D02 §2, amended, spec ruling
--                           I2): kept apart from $peer_from because on some
--                           catalogs' marker annotation the same annotation
--                           carries both a prefix and a service name, and only
--                           one of its attributes means each.
--   $peer_from           -- attribute names the prefix annotation's peer hint
--                           (a service name) is read from, or an empty list
--                           where the catalog declares no peer at all.
--   $method_from         -- attribute name holding the method, where one is given
--   $all_methods         -- the methods a mapping annotation means when it names none
--   $catalog_id          -- the id of the catalog running this derivation (2E-prep
--                           design §1a) — provenance only, never part of wire identity

-- Named explicitly: `endpoints` also carries request_shape/response_shape
-- (D01 §3 Contracts), which this engine does not populate — that is the
-- shape pass's job, not the annotation-driven endpoint engine's.
INSERT INTO endpoints (
    protocol, direction, method, path, handler, caller, peer,
    handler_signature, resolution, evidence, catalog_id, consumes, produces
)
WITH mapping_catalog AS (
    SELECT s.fqn AS fqn, s.methods AS methods
    FROM (SELECT UNNEST(
        $mapping_annotations::STRUCT(fqn VARCHAR, methods VARCHAR[])[]
    ) AS s)
),
-- The type-level gate is optional (D02 §2, amended): a catalog that declares
-- none matches on method annotations alone — a Retrofit interface has no
-- type-level marker at all.
controllers AS (
    SELECT DISTINCT target AS type_symbol
    FROM annotations
    WHERE annotation = $type_annotation
),
declared AS (
    SELECT
        a.target AS target,
        coalesce(list_extract(list_filter(list_transform(
            $path_from::VARCHAR[],
            n -> CASE WHEN coalesce(a.args -> n ->> 0, a.args ->> n) IS NOT NULL
                      THEN coalesce(TRY_CAST(a.args -> n AS VARCHAR[]),
                                    [a.args ->> n]) END
        ), v -> v IS NOT NULL), 1), ['']) AS paths,
        coalesce(
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
    JOIN mapping_catalog mc ON mc.fqn = a.annotation
),
-- Type-level and method-level annotations are different roles: on
-- @RequestMapping value/path both mean *path*, on @FeignClient value aliases
-- *name* — the service id — and only path means prefix. prefix_from and
-- peer_from keep the roles apart (spec ruling I2).
prefixes AS (
    SELECT
        a.target AS type_symbol,
        coalesce(list_extract(list_filter(list_transform(
            $prefix_from::VARCHAR[],
            n -> coalesce(a.args -> n ->> 0, a.args ->> n)
        ), v -> v IS NOT NULL), 1), '') AS prefix,
        list_extract(list_filter(list_transform(
            $peer_from::VARCHAR[],
            n -> coalesce(a.args -> n ->> 0, a.args ->> n)
        ), v -> v IS NOT NULL), 1) AS peer
    FROM annotations a
    WHERE a.annotation = $prefix_annotation
),
-- Cross product of methods and paths (a two-topic, two-method mapping is
-- four identities): DuckDB zips rather than cross-joins when two UNNESTs sit
-- in the same SELECT (verified empirically), so methods are unnested in
-- their own CTE first, and mapped_methods.paths is unnested from that.
mapped_methods AS (
    SELECT d.target AS target,
           UNNEST(CASE WHEN len(d.methods) = 0
                       THEN [CAST(NULL AS VARCHAR)] ELSE d.methods END) AS wire_method,
           d.paths AS paths
    FROM declared d
),
mappings AS (
    SELECT mm.target AS method_symbol,
           mm.wire_method AS wire_method,
           UNNEST(mm.paths) AS path_suffix
    FROM mapped_methods mm
),
derived AS (
    SELECT
        $protocol   AS protocol,
        $direction  AS direction,
        m.wire_method AS method,
        coalesce(p.prefix, '') || m.path_suffix AS path,
        -- The symbol lands by direction (D01 §3, amended): the server side
        -- handles, the client side calls, and a later merge may hold both.
        CASE WHEN $direction = 'outbound' THEN NULL ELSE s.symbol END AS handler,
        CASE WHEN $direction = 'outbound' THEN s.symbol END AS caller,
        p.peer      AS peer,
        s.signature AS handler_signature,
        'resolved'  AS resolution,
        'compiler'  AS evidence,
        $catalog_id AS catalog_id,
        -- Task 5 replaces these literals with mapping-attribute media
        -- (spec §4 evidence kind (a)); every other engine passes NULL too.
        NULL        AS consumes,
        NULL        AS produces
    FROM mappings m
    -- A handler or caller is always a method. Without this, a TYPE-level
    -- mapping annotation (a prefix-carrying @HttpExchange, a class-level
    -- @RequestMapping) joins its own type symbol and, in a catalog with no
    -- type gate, mints one phantom endpoint per method in all_methods
    -- (pre-flight ruling R2). The inbound catalogs were protected only by
    -- their gate's enclosing-join; this names the real rule instead.
    -- A handler is a method OR a free function (D00 §4); the JVM extractor
    -- emits only 'method', which is what keeps this a no-op today.
    JOIN symbols s ON s.symbol = m.method_symbol AND s.construct_kind IN ('method', 'function')
    LEFT JOIN controllers c ON s.enclosing = c.type_symbol
    LEFT JOIN prefixes p ON p.type_symbol = s.enclosing
    WHERE $type_annotation IS NULL OR c.type_symbol IS NOT NULL
)
SELECT * FROM derived d
WHERE NOT EXISTS (
    SELECT 1 FROM endpoints existing
    WHERE existing.protocol  = d.protocol
      AND existing.direction = d.direction
      AND existing.method IS NOT DISTINCT FROM d.method
      AND existing.path      = d.path
);
