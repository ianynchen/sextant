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
--   $consumes_from       -- attribute names the mapping annotation's declared
--                           request media types are read from, scalar-or-array
--                           (the $path_from pattern), or an empty list where the
--                           catalog declares none — carried data (D01 §4), never
--                           identity, and never a guessed default.
--   $produces_from       -- attribute names the mapping annotation's declared
--                           response media types are read from; same rules as
--                           $consumes_from.
--   $path_fallback       -- what the declared name is when every $path_from
--                           attribute is ABSENT, or NULL to keep the empty
--                           default. Today's one word is 'construct_name':
--                           the annotated construct's own name. A closed
--                           vocabulary rather than a boolean, so a second
--                           source is a new word here, not a second key.
--   $qualifier_from      -- attribute names holding the SCOPE the declared
--                           name sits inside, read off the SAME (method-level)
--                           annotation, first present wins — kept apart from
--                           $prefix_from, which reads a TYPE-level annotation
--                           through an entirely different join. Empty where a
--                           catalog declares no such scope, which is every
--                           catalog but the ones that need it.
--   $qualifier_separator -- what joins a qualifier to the name it qualifies.
--                           Catalog data, never a literal here: which
--                           punctuation separates a scope from a member is a
--                           framework's convention, and an engine that baked
--                           one in would be naming a framework in code.
--   $synthetic_annotations -- Task 6 (D02 §2, §3): rows the effective-
--                           annotations pre-pass (`resolve/effective_annotations.py`)
--                           synthesizes for a module-local composed annotation
--                           (`@ApiGet` built from `@RequestMapping`) — the same
--                           {target, annotation, args} shape `annotations`
--                           itself carries, `args` JSON-encoded as text the
--                           same way this file's own STRUCT bindings always
--                           are. Empty where a catalog composes nothing.

-- Named explicitly: `endpoints` also carries request_shape/response_shape
-- (D01 §3 Contracts), which this engine does not populate — that is the
-- shape pass's job, not the annotation-driven endpoint engine's. The same
-- goes for format/format_resolution (2G design §5): a mapping annotation
-- declares a MEDIA type, never a wire format, and the ladder that turns one
-- into the other runs once over the finished table. Both columns are absent
-- from the insert list below and from `unioned`'s GROUP BY, so every row
-- this engine writes starts at NULL and is answered later.
INSERT INTO endpoints (
    protocol, direction, method, path, handler, caller, peer,
    handler_signature, resolution, evidence, catalog_id, consumes, produces
)
WITH mapping_catalog AS (
    SELECT s.fqn AS fqn, s.methods AS methods,
           coalesce(s.requires_qualifier, FALSE) AS requires_qualifier
    FROM (SELECT UNNEST(
        $mapping_annotations::STRUCT(
            fqn VARCHAR, methods VARCHAR[], requires_qualifier BOOLEAN
        )[]
    ) AS s)
),
-- Task 6 (D02 §2, §3): widens the annotation set every CTE below reads from
-- the catalog's own declared fqns to those plus the module-local composed
-- ones the Python pre-pass already resolved — a plain UNION ALL, so a
-- catalog composing nothing (every catalog but the two the fixture proves)
-- costs one empty UNNEST.
annotations_effective AS (
    SELECT target, annotation, args FROM annotations
    UNION ALL
    SELECT s.target, s.annotation, s.args::JSON FROM (SELECT UNNEST(
        $synthetic_annotations::STRUCT(target VARCHAR, annotation VARCHAR, args VARCHAR)[]
    ) AS s)
),
-- The type-level gate is optional (D02 §2, amended): a catalog that declares
-- none matches on method annotations alone — a Retrofit interface has no
-- type-level marker at all.
controllers AS (
    SELECT DISTINCT target AS type_symbol
    FROM annotations_effective
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
        ) AS methods,
        -- Task 5: the same scalar-or-array, first-alias-wins read as `paths`
        -- above, applied to the media attributes instead of the path ones.
        -- An empty $consumes_from/$produces_from (every non-HTTP catalog
        -- today) means every alias is absent, so `list_extract` on the
        -- resulting empty list already yields NULL — no default needed, and
        -- none is a guessed one (D01 §4).
        list_extract(list_filter(list_transform(
            $consumes_from::VARCHAR[],
            n -> CASE WHEN coalesce(a.args -> n ->> 0, a.args ->> n) IS NOT NULL
                      THEN coalesce(TRY_CAST(a.args -> n AS VARCHAR[]),
                                    [a.args ->> n]) END
        ), v -> v IS NOT NULL), 1) AS consumes_list,
        list_extract(list_filter(list_transform(
            $produces_from::VARCHAR[],
            n -> CASE WHEN coalesce(a.args -> n ->> 0, a.args ->> n) IS NOT NULL
                      THEN coalesce(TRY_CAST(a.args -> n AS VARCHAR[]),
                                    [a.args ->> n]) END
        ), v -> v IS NOT NULL), 1) AS produces_list,
        -- The SCOPE this declaration's name sits inside, read off the same
        -- annotation that carries the name (2H design §1, form 2). Scalar-or-
        -- array and first-alias-wins like every other attribute read here.
        -- NULL where the annotation names no scope, which is what keeps the
        -- composition below a no-op for the annotations that carry a bare
        -- name and for every catalog declaring no `$qualifier_from` at all.
        list_extract(list_filter(list_transform(
            $qualifier_from::VARCHAR[],
            n -> coalesce(a.args -> n ->> 0, a.args ->> n)
        ), v -> v IS NOT NULL), 1) AS qualifier,
        mc.requires_qualifier AS requires_qualifier
    FROM annotations_effective a
    JOIN mapping_catalog mc ON mc.fqn = a.annotation
),
-- The same scope read, one level out: a catalog's mapping annotation sitting
-- on a TYPE states the scope once for every method the type declares, instead
-- of each method repeating it. Mirrors `prefixes` below exactly — same
-- attribute list, same scalar-or-array read, joined on `s.enclosing` the same
-- way — because it is the same idea at the same level; only the attribute it
-- reads and the separator it composes with differ.
--
-- A type-level annotation mints no row of its own: `derived`'s join to
-- `symbols` keeps methods and functions only, so a type target never reaches
-- `mappings`. That is what lets one annotation play both roles here without
-- the two colliding — the `prefix_annotation` precedent, unchanged.
qualifier_scopes AS (
    SELECT
        a.target AS type_symbol,
        list_extract(list_filter(list_transform(
            $qualifier_from::VARCHAR[],
            n -> coalesce(a.args -> n ->> 0, a.args ->> n)
        ), v -> v IS NOT NULL), 1) AS qualifier
    FROM annotations_effective a
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
    FROM annotations_effective a
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
           d.paths AS paths,
           d.consumes_list AS consumes_list,
           d.produces_list AS produces_list,
           d.qualifier AS qualifier,
           d.requires_qualifier AS requires_qualifier
    FROM declared d
),
mappings AS (
    SELECT mm.target AS method_symbol,
           mm.wire_method AS wire_method,
           UNNEST(mm.paths) AS path_suffix,
           mm.consumes_list AS consumes_list,
           mm.produces_list AS produces_list,
           mm.qualifier AS qualifier,
           mm.requires_qualifier AS requires_qualifier
    FROM mapped_methods mm
),
derived AS (
    SELECT
        $protocol   AS protocol,
        $direction  AS direction,
        m.wire_method AS method,
        -- Three fragments, in address order (2H design §1): the TYPE-level
        -- prefix, the scope this declaration names on its own annotation, and
        -- the declared name itself.
        --
        -- Both new fragments are inert unless a catalog asks for them —
        -- `$qualifier_from` empty leaves `m.qualifier` NULL, `$path_fallback`
        -- NULL fails its equality — so every catalog written before them
        -- composes exactly `coalesce(p.prefix, '') || m.path_suffix`, which is
        -- what this expression was.
        --
        -- The fallback fires only on an EMPTY suffix, which is the same fact
        -- as "every `$path_from` alias was absent" (`declared` defaults the
        -- list to `['']`). An annotation's declared default is not in the
        -- bytecode, so absent and defaulted are one thing, and a framework
        -- whose default IS the construct's own name is describing an
        -- identity that is present in the code rather than one nobody wrote.
        -- Reading it as '' instead published a resolved endpoint with no
        -- address — the failure D02 §2 already names for `path_from`
        -- ("wrong output rather than a missing one"), reached by a second
        -- route.
        -- The scope is the declaration's own where it states one, else the
        -- one its enclosing type states (2H design §1): the nearer
        -- declaration wins, which is the precedence every framework with
        -- both levels keeps. Where neither states one this is NULL and
        -- composes nothing — no scope, no separator.
        coalesce(p.prefix, '')
            || CASE WHEN coalesce(m.qualifier, q.qualifier) IS NOT NULL
                    THEN coalesce(m.qualifier, q.qualifier) || $qualifier_separator
                    ELSE '' END
            || CASE WHEN m.path_suffix = '' AND $path_fallback = 'construct_name'
                    -- The construct's own name, off the symbol the join below
                    -- already resolved. D00 §1's descriptor puts it between
                    -- the type separator and the signature — the shape
                    -- `$method_from`'s own read above already relies on.
                    -- `$` is in the class because the JVM admits it in a
                    -- method name; a symbol this failed to match would yield
                    -- '' silently, which is the empty-address failure again.
                    THEN regexp_extract(s.symbol, '#([A-Za-z0-9_$]+)\(', 1)
                    ELSE m.path_suffix END AS path,
        -- The symbol lands by direction (D01 §3, amended): the server side
        -- handles, the client side calls, and a later merge may hold both.
        CASE WHEN $direction = 'outbound' THEN NULL ELSE s.symbol END AS handler,
        CASE WHEN $direction = 'outbound' THEN s.symbol END AS caller,
        p.peer      AS peer,
        s.signature AS handler_signature,
        'resolved'  AS resolution,
        'compiler'  AS evidence,
        $catalog_id AS catalog_id,
        -- Raw per-row lists (evidence kind (a): mapping attributes) — still
        -- to be unioned and JSON-normalized below, per row group sharing a
        -- wire identity plus handler/caller/resolution/evidence/catalog_id.
        m.consumes_list AS consumes_list,
        m.produces_list AS produces_list
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
    LEFT JOIN qualifier_scopes q ON q.type_symbol = s.enclosing
    WHERE ($type_annotation IS NULL OR c.type_symbol IS NOT NULL)
      -- A declaration whose annotation only means anything INSIDE a scope,
      -- with no scope found at either level, has no address — so it derives
      -- NO ROW rather than the bare member name. The bare name would read as
      -- a top-level identity, which is a different endpoint from the one the
      -- code declares, and `resolved`/`compiler` beside it would present that
      -- as observed. Silence is the honest answer: the declaration is real,
      -- but what it is a member OF is stated somewhere these facts do not
      -- reach (a parameter's type, for the framework that infers it there).
      AND NOT (m.requires_qualifier AND coalesce(m.qualifier, q.qualifier) IS NULL)
),
-- Within-batch union (D01 §4, spec §4): rows differing ONLY in declared
-- media are one endpoint, so this groups on every OTHER column derived
-- above and folds consumes/produces into the sorted-distinct union of
-- whatever each grouped row declared. Everything else — including
-- content-negotiation siblings, which differ in `handler` — stays apart,
-- since `handler` (or `caller`) is one of the grouped columns, not an
-- aggregate. `GROUP BY ALL` groups on every non-aggregated select-list
-- column, verified empirically against the CASE aggregates below; listed
-- explicitly would be these same eleven: protocol, direction, method, path,
-- handler, caller, peer, handler_signature, resolution, evidence, catalog_id.
unioned AS (
    SELECT protocol, direction, method, path, handler, caller, peer,
           handler_signature, resolution, evidence, catalog_id,
           CASE WHEN count(consumes_list) = 0 THEN NULL
                ELSE to_json(list_sort(list_distinct(flatten(list(consumes_list)
                     FILTER (WHERE consumes_list IS NOT NULL))))) END AS consumes,
           CASE WHEN count(produces_list) = 0 THEN NULL
                ELSE to_json(list_sort(list_distinct(flatten(list(produces_list)
                     FILTER (WHERE produces_list IS NOT NULL))))) END AS produces
    FROM derived
    GROUP BY ALL
)
SELECT * FROM unioned d
WHERE NOT EXISTS (
    SELECT 1 FROM endpoints existing
    WHERE existing.protocol  = d.protocol
      AND existing.direction = d.direction
      AND existing.method IS NOT DISTINCT FROM d.method
      AND existing.path      = d.path
);
