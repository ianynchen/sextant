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
-- THIS STATEMENT RUNS ONCE PER RESOLVE, OVER EVERY ANNOTATION-DRIVEN CATALOG
-- AT ONCE (P-4). It used to run once per catalog, and what it cost was its
-- SIZE: binding these 1,300 lines took ~50ms whether the values were
-- placeholders, literals or a table (measured; a prepared statement, comment
-- stripping and MATERIALIZED CTEs each changed nothing), and 28 catalogs paid
-- it 28 times — 1.4s of a 2.5s analyze. So the catalogs arrive together as
-- `$catalogs`, one STRUCT per catalog, and the rows derive into the TEMP table
-- `endpoint_candidates` with each row's `catalog_id`. Every CTE below carries
-- `catalog_id` through its SELECT and its joins, so rows of different catalogs
-- never mix — a catalog's derivation is exactly what it was when it ran alone.
--
-- What did NOT move here is the insert into `endpoints`. It is
-- `insert_endpoints.sql`, run once per catalog at that catalog's own place in
-- `resolve/endpoints.py::derive_endpoints`'s order, with the same
-- earlier-catalog-wins guard this statement's final NOT EXISTS used to carry.
-- The guard has to be asked at that moment and not here: the other engines
-- run BETWEEN annotation-driven catalogs (the order is by filename within a
-- direction), and a wire identity one of them minted in between is refused
-- to a later annotation-driven catalog exactly as it always was.
--
-- Parameters:
--   $catalogs            -- one STRUCT per annotation-driven catalog, with the
--                           fields below. Each field is referred to in the
--                           comments below by the name it was bound under when
--                           the statement ran once per catalog — `$members`
--                           means the `members` field of the catalog whose rows
--                           are being derived, which the code reads as
--                           `cp.members` off `catalog_params`.
--   $catalog_id          -- the id of the catalog (2E-prep design §1a) —
--                           provenance only, never part of wire identity, and
--                           the key every per-catalog CTE below carries.
--   $protocol            -- the catalog's declared protocol (D00's closed set)
--   $direction           -- the catalog's declared direction (D00's closed set)
--   $type_annotation     -- LIST of fqns for the type-level annotation that marks a
--                           controller or client, or NULL where the catalog
--                           declares no type-level gate at all (D02 §2,
--                           amended) — a Retrofit interface carries no marker,
--                           so its method annotations are the whole evidence.
--   $mapping_annotations -- list of {fqn, methods, requires_qualifier,
--                           unless_attribute, unless_equals, path_fallback,
--                           path_fallback_prefixes} rows: one per
--                           mapping annotation. `methods` holds the methods
--                           that annotation pre-sets, or NULL where it pre-sets
--                           none; the `unless_*` pair names the attribute whose
--                           value makes the rule derive NOTHING (2I design §2,
--                           word 4), both NULL where it withdraws nothing; the
--                           `path_fallback*` pair is `$path_fallback`'s answer
--                           FOR THIS ANNOTATION (`OI-5`), already resolved
--                           against the catalog-level default by
--                           `annotation_driven.py::_mapping_annotation`, so this
--                           file never asks which level declared it.
--   $prefix_annotation   -- LIST of fqns for the type-level annotation carrying the
--                           path prefix (§3.1: one annotation, several spellings)
--   $peer_annotation     -- LIST of fqns for the type-level annotation $peer_from is
--                           read off (CP-22 row 2, spec §3f). Defaults to
--                           $prefix_annotation where the catalog declares no
--                           `peer_annotation` key of its own — true for every
--                           catalog shipped before this word, which is why
--                           they derive byte-identically. MicroProfile REST
--                           Client is the one framework where prefix and peer
--                           sit on two different annotations: the prefix is
--                           `@Path`, the peer is `@RegisterRestClient`.
--   $path_from           -- attribute names that alias one another, first present wins
--   $path_from_siblings  -- `OI-35`: {ordinal, annotation, arg} rows naming a
--                           name source that lives on ANOTHER annotation of the
--                           same declaration, `ordinal` counting from the order
--                           the catalog wrote — which is the order the framework
--                           consults them in, and the whole content of the key,
--                           since a set would not say which of two present
--                           sources supplies the name. Consulted only where
--                           every $path_from alias was absent. Empty for every
--                           catalog that declares none, which is every catalog
--                           written before it: an empty list matches no
--                           annotation, the lookup below finds nothing, and the
--                           composed address is exactly what it was.
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
--   $consumes_from       -- attribute names the mapping annotation's declared
--                           request media types are read from, scalar-or-array
--                           (the $path_from pattern), or an empty list where the
--                           catalog declares none — carried data (D01 §4), never
--                           identity, and never a guessed default.
--   $produces_from       -- attribute names the mapping annotation's declared
--                           response media types are read from; same rules as
--                           $consumes_from.
--   $path_fallback       -- what the declared name is when every $path_from
--                           attribute and every $path_from_siblings source is
--                           ABSENT, or NULL to keep the empty
--                           default. The first word was 'construct_name':
--                           the annotated construct's own name. A closed
--                           vocabulary rather than a boolean, so a second
--                           source is a new word here, not a second key.
--                           Read at this level only by a row that carries no
--                           mapping annotation to read a word off — an
--                           unannotated exposed member ($members). Every
--                           ANNOTATED declaration reads `mc.path_fallback`,
--                           which is this value or the annotation's own
--                           override (`OI-5`).
--   $path_fallback_prefixes -- the accessor prefixes $path_fallback's word
--                           strips off the construct's own name before
--                           publishing it, or an empty list for a word that
--                           strips none ('construct_name') and for no word at
--                           all. Which prefixes belong to which word is
--                           `annotation_driven.py::_PATH_FALLBACKS`, measured
--                           by CP-15 rows 4a-4b; the three CONDITIONS of the
--                           strip are spelled below, where the construct's own
--                           name is read. EMPTY for the three words that name
--                           the DECLARING TYPE rather than the construct
--                           (spec 2026-09-22 §2b): they read no member name to
--                           strip a prefix off, so the branch below reads the
--                           WORD for those and this list for the rest.
--   $fallback_prefix_attr -- spec 2026-09-22 §2b, CP-30 row 2: the attribute of
--                           the DECLARING type's own $type_annotation use that
--                           carries the prefix
--                           'prefixed_capitalized_construct_name' composes, or
--                           NULL where the catalog declares no such word —
--                           which is every catalog written before it, so the
--                           read below finds no row and the composition is
--                           inert. Deliberately NOT $prefix_from: that value
--                           feeds $type_prefix, which joins the FRONT of every
--                           composed address, so a catalog naming the prefix
--                           there would compose it a second time onto every
--                           row — including the explicitly-named member that
--                           must not carry it at all.
--   $fallback_scope_separator -- spec 2026-09-22 §1d: the punctuation
--                           'declaring_type_scoped_name' puts between the
--                           DECLARING type's simple name and the name that
--                           won, or NULL where the catalog declares no such
--                           word — which is every catalog written before it,
--                           so the branch below is unreachable for them and
--                           their addresses are byte-identical. Catalog data
--                           for $path_separator's reason: which punctuation
--                           joins two halves of an address is a framework's
--                           convention, and an engine that picked one would be
--                           naming a framework in code.
--                           UNLIKE every other $path_fallback word, the one
--                           reading this composes around a name the
--                           declaration DID write as well as one it did not —
--                           see the branch below for why that is the rule.
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
--                           NULL where $qualifier_format states the whole
--                           composition instead; the two are mutually
--                           exclusive by contract (`annotation_driven.py::
--                           _validate_naming`).
--   $qualifier_format    -- 2I design §2, word 1: a whole composition of
--                           scope and name that no single separator can
--                           state. Today's one word is 'qname' —
--                           `{scope}name`, the XML-namespace notation, ONE
--                           bracketed token whose closing brace has no
--                           separator equivalent at all. NULL restores the
--                           separator composition, which is what every
--                           catalog written before this parameter gets.
--   $namespace_template  -- 2I design §2, word 2: the `printf` template the
--                           declaring type's own reversed package is composed
--                           into, when the attribute carrying the scope is
--                           absent — or NULL to leave the scope absent. A
--                           TEMPLATE rather than the catalog's own word
--                           because the wrapper carries a scheme, and §10
--                           forbids this layer from naming one; which word
--                           maps to which template is
--                           `annotation_driven.py::_NAMESPACE_DEFAULTS`.
--                           A framework whose spec DEFINES this default is
--                           stating a fact about every class in it, so
--                           deriving it is reading the framework rather than
--                           guessing; a catalog that declares no default gets
--                           no scope, never a plausible-looking one (DR-6).
--   $class_level         -- `prefix` or `sibling` (F2 §3.5): whether a type-level
--                           address COMPOSES with each member's, or a member
--                           naming its own destination stands alone
--   $path_separator      -- what joins a TYPE-level prefix to the address it
--                           prefixes, and the character deduped at the seam
--                           where both halves already carry it. NULL where a
--                           catalog declares none, which restores the bare
--                           `prefix || suffix` every catalog composed before
--                           this parameter existed. Catalog data for the same
--                           reason $qualifier_separator is: whether two
--                           address fragments join with a separator, and
--                           which, is the FRAMEWORK's convention — one
--                           framework's address is a sequence of segments and
--                           another's is an opaque name with no segments to
--                           join — and an engine that picked one would be
--                           naming a framework in code.
--                           SINGLE-CHARACTER by contract (`annotation_driven.
--                           py::_validate_naming` refuses anything else): the
--                           dedupe below is `rtrim`/`ltrim`, which trim a SET
--                           of characters, so a multi-character separator
--                           would trim each of its characters individually.
--   $canonical_path      -- 2O design §8: whether the composed address is a
--                           URL THIS MODULE SERVES, whose identity is the
--                           address the framework actually answers at, rather
--                           than an address to be recorded exactly as the
--                           declaration wrote it. The caller decides from the
--                           catalog's own declared protocol and direction
--                           (`domain/paths.py::serves_urls`), so this file
--                           names neither; false leaves every composed address
--                           exactly as it was before the parameter existed,
--                           which is what keeps every other catalog's
--                           derivation byte-identical.
--   $members             -- 2I design §2, word 3: what a GATED CLASS exposes
--                           on its own, with no member-level annotation
--                           anywhere, or NULL where a catalog declares no such
--                           rule (every catalog whose framework exposes only
--                           what an annotation marks). The first word was
--                           'public_methods'; 'declared_type_methods' (spec
--                           2026-09-22 §2c) is that rule plus one conjunct —
--                           the member's DECLARING type must carry the gate
--                           DIRECTLY, never by inheritance. A member-level rule
--                           OVERRIDES either for the member it names — one row
--                           per member, never two — and $path_fallback is
--                           required beside both, since a member carries no
--                           name attribute at all
--                           (`annotation_driven.py::_validate_naming`).
--   $declared_on         -- 2I design §4: the construct kind the enclosing
--                           type must be for this catalog's rules to apply,
--                           or NULL to apply them to any — which is every
--                           catalog written before this parameter, and what
--                           keeps their derivations byte-identical. One
--                           annotation family can mark both a served
--                           interface and the generated client stub of one;
--                           the two are opposite DIRECTIONS of the same wire
--                           identity, so without this each catalog derives
--                           both and a module is published as calling the
--                           operations it serves.
--   $locally_implemented -- 2I design §4, the SEI fence: interface descriptors
--                           this module's own classes implement, or an empty
--                           list where the fence does not apply. Read from
--                           D00 §5a's `implemented_interfaces` and passed as
--                           BARE descriptors, the same strip every other
--                           reader of that fact makes.
--   $flip_direction      -- D02 §2c: the direction a row takes where the
--                           catalog's own resolution condition holds, or NULL
--                           where the catalog declares no such rule — which is
--                           every catalog but one, and what keeps their
--                           derivations byte-identical. A catalog's declared
--                           direction is a DEFAULT for most families and a
--                           genuine ambiguity for one: the same annotation
--                           declares a client to be proxied and an API to be
--                           served, and which it is depends on what else the
--                           module contains.
--   $flip_owners         -- the enclosing types the condition holds for, as
--                           BARE descriptors — the same strip
--                           $locally_implemented is passed under, and for the
--                           same reason. Empty where there is no rule.
--   $flip_handlers       -- {declaration, handler} rows: for a flipped
--                           declaration, the symbol that HANDLES it, which is
--                           not the declaring symbol. A declaration with no
--                           entry keeps its own symbol as the handler — the
--                           declaring method IS what runs where nothing
--                           overrides it. Empty where there is no rule.
--   $flip_canonical_path -- $canonical_path's twin for a flipped row: the same
--                           question asked of the direction the row TOOK
--                           rather than the one the catalog declared. False
--                           where there is no rule, which is inert because
--                           nothing then flips.
--   $synthetic_annotations -- Task 6 (D02 §2, §3): rows the effective-
--                           annotations pre-pass (`resolve/effective_annotations.py`)
--                           synthesizes for a module-local composed annotation
--                           (`@ApiGet` built from `@RequestMapping`) — the same
--                           {target, annotation, args} shape `annotations`
--                           itself carries, `args` JSON-encoded as text the
--                           same way this file's own STRUCT bindings always
--                           are. Empty where a catalog composes nothing.
--                           `inherited` says WHICH pass wrote the row: true
--                           only for the inheritance walk, which carries an
--                           annotation ACROSS a type boundary, and false for
--                           the folded (`OI-36`) and composed (`A-C7`) passes,
--                           which rewrite an annotation the author really did
--                           write on that very target. One rule asks — the
--                           direct gate `members: declared_type_methods` reads
--                           — and `catalog_id` cannot answer it, because all
--                           three passes stamp it.
--                           `gate_type` is NULL except on a ruling-8 row (a
--                           mapping a concrete class inherits without
--                           overriding), where it names that class: the
--                           prefix and the gate come from it, the handler
--                           stays `target`.

-- Named explicitly: `endpoints` also carries request_shape/response_shape
-- (D01 §3 Contracts), which this engine does not populate — that is the
-- shape pass's job, not the annotation-driven endpoint engine's. The same
-- goes for format/format_resolution (2G design §5): a mapping annotation
-- declares a MEDIA type, never a wire format, and the ladder that turns one
-- into the other runs once over the finished table. Both columns are absent
-- from the column list at the end and from `unioned`'s GROUP BY, so every row
-- this engine writes starts at NULL and is answered later.
--
-- A TEMP table rather than a table `schema.sql` declares: it lives for the
-- one resolve that reads it, is replaced by the next, and never reaches the
-- workspace file or an export bundle (`DuckDbWorkspace.schema_objects` leaves
-- it out by name, the way it leaves out the redaction staging tables).
CREATE OR REPLACE TEMP TABLE endpoint_candidates AS
WITH RECURSIVE catalog_params AS (
    -- One row per catalog in the batch: the values `annotation_driven.py::
    -- params_for` builds, every one of them a field, the STRUCT spelled once.
    -- `s.*` expands the struct into columns, so the rest of the file reads
    -- `cp.<field>` where it used to read `$<field>`.
    SELECT s.* FROM (SELECT UNNEST(
        $catalogs::STRUCT(
            catalog_id VARCHAR, protocol VARCHAR, direction VARCHAR,
            type_annotation VARCHAR[], declared_on VARCHAR, locally_implemented VARCHAR[],
            prefix_annotation VARCHAR[], peer_annotation VARCHAR[], class_level VARCHAR,
            mapping_annotations STRUCT(
                fqn VARCHAR, methods VARCHAR[], requires_qualifier BOOLEAN,
                unless_attribute VARCHAR, unless_equals VARCHAR,
                path_fallback VARCHAR, path_fallback_prefixes VARCHAR[]
            )[],
            path_from VARCHAR[],
            path_from_siblings STRUCT(ordinal INTEGER, annotation VARCHAR, arg VARCHAR)[],
            produces_from_siblings STRUCT(ordinal INTEGER, annotation VARCHAR, arg VARCHAR)[],
            consumes_from_siblings STRUCT(ordinal INTEGER, annotation VARCHAR, arg VARCHAR)[],
            type_media_from_siblings
                STRUCT("column" VARCHAR, ordinal INTEGER, annotation VARCHAR, arg VARCHAR)[],
            prefix_from VARCHAR[], peer_from VARCHAR[], method_from VARCHAR,
            all_methods VARCHAR[], consumes_from VARCHAR[], produces_from VARCHAR[],
            path_fallback VARCHAR, path_fallback_prefixes VARCHAR[],
            fallback_prefix_attr VARCHAR, fallback_scope_separator VARCHAR,
            qualifier_from VARCHAR[], qualifier_separator VARCHAR, qualifier_format VARCHAR,
            namespace_template VARCHAR, members VARCHAR, path_separator VARCHAR,
            path_prefix VARCHAR, canonical_path BOOLEAN,
            flip_direction VARCHAR, flip_owners VARCHAR[],
            flip_handlers STRUCT(declaration VARCHAR, handler VARCHAR)[],
            flip_canonical_path BOOLEAN,
            synthetic_annotations
                STRUCT(target VARCHAR, annotation VARCHAR, args VARCHAR, inherited BOOLEAN,
                       gate_type VARCHAR)[]
        )[]
    ) AS s)
),
-- The per-catalog lists, unnested once each into `(catalog_id, ...)` rows so
-- every read below is an equi-join on `catalog_id` rather than a scan of the
-- batch. `list_distinct` on the two gate lists keeps exactly the rows the
-- `list_contains` they replace produced: a spelling listed twice matched an
-- annotation row once, and unnested twice it would match it twice.
type_gates AS (
    SELECT cp.catalog_id AS catalog_id, UNNEST(list_distinct(cp.type_annotation)) AS fqn
    FROM catalog_params cp
),
prefix_gates AS (
    SELECT cp.catalog_id AS catalog_id, UNNEST(list_distinct(cp.prefix_annotation)) AS fqn
    FROM catalog_params cp
),
-- CP-22 row 2 (spec §3f): `peers` below reads `peer_from` off THIS annotation
-- rather than `prefix_gates` — identical shape, mirrors `prefix_gates`
-- exactly, because `$peer_annotation` already defaults to `$prefix_annotation`
-- for every catalog that declares none, so this list is `prefix_gates`'s own
-- fqns for every shipped catalog but the one that names a different one.
peer_gates AS (
    SELECT cp.catalog_id AS catalog_id, UNNEST(list_distinct(cp.peer_annotation)) AS fqn
    FROM catalog_params cp
),
mapping_catalog AS (
    SELECT u.catalog_id AS catalog_id, s.fqn AS fqn, s.methods AS methods,
           coalesce(s.requires_qualifier, FALSE) AS requires_qualifier,
           -- 2I design §2, word 4: the attribute whose value withdraws this
           -- rule, and that value as TEXT — the one representation `json ->>`
           -- reads every scalar back as, so a catalog's YAML boolean and a
           -- bytecode JSON boolean compare without either side guessing at the
           -- other's type. Both NULL where the rule withdraws nothing.
           s.unless_attribute AS unless_attribute,
           s.unless_equals AS unless_equals,
           -- `OI-5`: this annotation's own answer to "what is the declared name
           -- when nothing named one". The framework CP-15 measured chooses the
           -- transformation by WHICH operation annotation matched — the read
           -- direction strips `get`/`is`, the write direction strips `set` —
           -- so one word for the whole file makes one of the two newly wrong.
           -- Both columns already carry the catalog-level default for an entry
           -- that declares no override, so a catalog written before this word
           -- binds one value on every entry and derives byte-identically.
           s.path_fallback AS path_fallback,
           s.path_fallback_prefixes AS path_fallback_prefixes
    FROM (SELECT cp.catalog_id AS catalog_id, UNNEST(cp.mapping_annotations) AS s
          FROM catalog_params cp) u
),
-- Task 6 (D02 §2, §3): widens the annotation set every CTE below reads from
-- the catalog's own declared fqns to those plus the module-local composed
-- ones the Python pre-pass already resolved — a plain UNION ALL, so a
-- catalog composing nothing (every catalog but the two the fixture proves)
-- costs one empty UNNEST.
annotations_effective AS (
    -- W56 tried to filter a SIBLING's annotations out HERE, so that
    -- `drop_borrowed_endpoints.sql` became a belt-and-braces check rather than the
    -- mechanism, and MEASUREMENT refused it twice over.
    --
    -- **It saves nothing.** Six alternating runs on the largest corpus available
    -- (2026-09-11): 95.8s mean with the filter, 94.7s without. An earlier blocked
    -- comparison read 100.2s against 93.3s, which was a cold first run against a
    -- warm one and not a saving at all.
    --
    -- **And it loses a real route.** The delete keys on `coalesce(handler, caller)`;
    -- a filter here keys on the ANNOTATION's own document, and the two come apart
    -- wherever a catalog's `resolves.direction` rebinds a row's handler to an
    -- IMPLEMENTING type: the annotation is then the dependency's and the handler is
    -- this module's own. The delete keeps such a row correctly; this filter dropped
    -- it, taking with it an API the module really serves. That shape is ordinary —
    -- a contract interface in one module, implemented in another — and
    -- `test_module_edge.py::test_an_exchange_interface_a_SIBLING_declares_still_
    -- serves_this_modules_route` is the case, which fails with the filter in.
    --
    -- So deriving from every document and deleting what the module does not own is
    -- LOAD-BEARING rather than wasteful, and the tidier-looking root filter is not
    -- equivalent to it.
    --
    -- `catalog_id` says WHOSE annotation set a row belongs to: NULL for a real
    -- row, which every catalog reads, and the catalog's own id for a synthetic
    -- row, which only that catalog may read — a composed mapping one catalog's
    -- closure resolved is not evidence for another's. So every join below
    -- that reads this CTE carries the conjunct
    -- `(a.catalog_id IS NULL OR a.catalog_id = <the catalog>)`; it is what
    -- keeps one catalog's effective annotations exactly the set it had alone.
    -- The real rows are NOT multiplied by the batch (a CROSS JOIN over
    -- `catalog_params` would be 5 million rows on the largest corpus): each
    -- consumer first equi-joins `annotation` to a fqn a catalog declared,
    -- which is what makes the batch cost the sum of the catalogs rather than
    -- the product.
    --
    -- `inherited` is the second thing a row says about itself, and it answers
    -- a question `catalog_id` cannot: WHICH pre-pass wrote it. A real row is
    -- false because nothing carried it anywhere — a scanner read it off the
    -- target it names. Of the three synthetic passes only the inheritance walk
    -- carries an annotation ACROSS a type boundary; folding and composition
    -- rewrite an annotation the author wrote on that very target into the
    -- spelling the catalog declares. One rule reads this column (the direct
    -- gate below); every other join ignores it and derives what it always did.
    --
    -- `gate_type` is the third, and only ruling 8's rows carry it: a mapping a
    -- concrete class inherits without overriding keeps its declaring method as
    -- `target` — the code that runs — and names here the class it is served
    -- under. `declared` hands it on, and `derived` takes the prefix and the gate
    -- from it through the `coalesce(m.gate_type, s.enclosing)` the member rule
    -- already uses for the same reason. NULL on every other row.
    SELECT CAST(NULL AS VARCHAR) AS catalog_id, target, annotation, args,
           FALSE AS inherited, CAST(NULL AS VARCHAR) AS gate_type
    FROM annotations
    UNION ALL
    SELECT u.catalog_id AS catalog_id, s.target, s.annotation, s.args::JSON,
           s.inherited AS inherited, s.gate_type AS gate_type
    FROM (SELECT cp.catalog_id AS catalog_id, UNNEST(cp.synthetic_annotations) AS s
          FROM catalog_params cp) u
),
-- `OI-35`: the name sources that live on ANOTHER annotation of the same
-- declaration, and the ONE of them a declaration is actually served under.
--
-- **The order is the rule.** CP-15 rows 1a-1b disassemble
-- `OperationCreator.getOperationName` and show it building an array of name
-- sources whose `iconst_N` indices ARE the order, then taking the first entry
-- WITH A VALUE. So a method carrying two of these is served under the earlier
-- one, and a vocabulary that could only name a SET would not say which. The
-- ordinal is attached in `annotation_driven.py::_sibling_sources` because a
-- list's order is not a column, and `min_by` is "first present wins" said over
-- one.
--
-- Grouped by TARGET rather than by the matched annotation, and that is what
-- makes it a sibling read: these annotations sit beside the mapping annotation
-- on the same declaration and are not the mapping annotation, so nothing here
-- joins `mapping_catalog` at all. At most one row per target reaches `declared`
-- below, which is why the LEFT JOIN there cannot fan a declaration out.
--
-- Scalar-or-array like every other attribute read in this file, so a framework
-- that arrays its name attribute needs no second rule.
--
-- Both CTEs are empty for every catalog that declares no sibling source, so the
-- LEFT JOIN below finds nothing and the `coalesce` reduces to what it was.
sibling_path_sources AS (
    SELECT u.catalog_id AS catalog_id,
           s.ordinal AS ordinal, s.annotation AS annotation, s.arg AS arg
    FROM (SELECT cp.catalog_id AS catalog_id, UNNEST(cp.path_from_siblings) AS s
          FROM catalog_params cp) u
),
sibling_names AS (
    SELECT sp.catalog_id AS catalog_id, a.target AS target,
           min_by(coalesce(TRY_CAST(a.args -> sp.arg AS VARCHAR[]), [a.args ->> sp.arg]),
                  sp.ordinal) AS found
    FROM annotations_effective a
    JOIN sibling_path_sources sp ON sp.annotation = a.annotation
         AND (a.catalog_id IS NULL OR a.catalog_id = sp.catalog_id)
    WHERE coalesce(a.args -> sp.arg ->> 0, a.args ->> sp.arg) IS NOT NULL
    GROUP BY sp.catalog_id, a.target
),
-- Spec 2026-09-18 §3b word 1: the media twins of the two CTEs above — same shape, same
-- "first present wins" over the catalog's ordinal, grouped by TARGET because the
-- annotation carrying the media is not the mapping annotation. Empty for every catalog
-- declaring no media sibling, so the LEFT JOINs in `declared` reduce to what they were.
sibling_produces_sources AS (
    SELECT u.catalog_id AS catalog_id, s.ordinal AS ordinal, s.annotation AS annotation, s.arg AS arg
    FROM (SELECT cp.catalog_id AS catalog_id, UNNEST(cp.produces_from_siblings) AS s FROM catalog_params cp) u
),
sibling_produces AS (
    SELECT sp.catalog_id AS catalog_id, a.target AS target,
           min_by(coalesce(TRY_CAST(a.args -> sp.arg AS VARCHAR[]), [a.args ->> sp.arg]), sp.ordinal) AS found
    FROM annotations_effective a
    JOIN sibling_produces_sources sp ON sp.annotation = a.annotation
         AND (a.catalog_id IS NULL OR a.catalog_id = sp.catalog_id)
    WHERE coalesce(a.args -> sp.arg ->> 0, a.args ->> sp.arg) IS NOT NULL
    GROUP BY sp.catalog_id, a.target
),
sibling_consumes_sources AS (
    SELECT u.catalog_id AS catalog_id, s.ordinal AS ordinal, s.annotation AS annotation, s.arg AS arg
    FROM (SELECT cp.catalog_id AS catalog_id, UNNEST(cp.consumes_from_siblings) AS s FROM catalog_params cp) u
),
sibling_consumes AS (
    SELECT sc.catalog_id AS catalog_id, a.target AS target,
           min_by(coalesce(TRY_CAST(a.args -> sc.arg AS VARCHAR[]), [a.args ->> sc.arg]), sc.ordinal) AS found
    FROM annotations_effective a
    JOIN sibling_consumes_sources sc ON sc.annotation = a.annotation
         AND (a.catalog_id IS NULL OR a.catalog_id = sc.catalog_id)
    WHERE coalesce(a.args -> sc.arg ->> 0, a.args ->> sc.arg) IS NOT NULL
    GROUP BY sc.catalog_id, a.target
),
-- D02 §2c's direction resolution, as two lookups. Both UNNEST an empty list
-- for every catalog that declares no rule, so both LEFT JOINs below find
-- nothing and the flip predicate is false for every row — which is what keeps
-- forty catalogs' derivations byte-identical.
flip_owners AS (
    SELECT cp.catalog_id AS catalog_id, UNNEST(cp.flip_owners) AS owner
    FROM catalog_params cp
),
flip_handlers AS (
    SELECT u.catalog_id AS catalog_id, s.declaration AS declaration, s.handler AS handler
    FROM (SELECT cp.catalog_id AS catalog_id, UNNEST(cp.flip_handlers) AS s
          FROM catalog_params cp) u
),
-- The type-level gate is optional (D02 §2, amended): a catalog that declares
-- none matches on method annotations alone — a Retrofit interface has no
-- type-level marker at all. `type_gates` is empty for such a catalog, exactly
-- as `list_contains` over its NULL list matched nothing.
controllers AS (
    SELECT DISTINCT g.catalog_id AS catalog_id, a.target AS type_symbol
    FROM annotations_effective a
    JOIN type_gates g ON g.fqn = a.annotation
         AND (a.catalog_id IS NULL OR a.catalog_id = g.catalog_id)
),
declared AS (
    SELECT
        mc.catalog_id AS catalog_id,
        a.target AS target,
        -- `member_declarations` fills this, and so does a ruling-8 row (a
        -- mapping a concrete class inherits without overriding, carried in
        -- `annotations_effective.gate_type`). Any other ANNOTATED declaration
        -- never needs it, because the type that annotated it IS its own
        -- enclosing type — NULL there rather than `a.target`'s enclosing, so
        -- `derived`'s `coalesce` reads "no gate type was carried" and falls
        -- through to the behaviour every catalog written before `A-M15` had.
        a.gate_type AS gate_type,
        -- The matched annotation's own aliases first, then `OI-35`'s sibling
        -- sources, then the empty default that `$path_fallback` answers. That
        -- ORDER is the framework's, not a convenience: CP-15 row 1 puts the
        -- operation annotation's own `value` at index 0 of the source array,
        -- ahead of all four siblings. A framework consulting a sibling BEFORE
        -- the matched annotation's own attribute cannot be stated in this
        -- grammar, and that boundary is in `docs/COVERAGE.md` rather than
        -- silent.
        coalesce(list_extract(list_filter(list_transform(
            cp.path_from,
            n -> CASE WHEN coalesce(a.args -> n ->> 0, a.args ->> n) IS NOT NULL
                      THEN coalesce(TRY_CAST(a.args -> n AS VARCHAR[]),
                                    [a.args ->> n]) END
        ), v -> v IS NOT NULL), 1), sn.found, ['']) AS paths,
        coalesce(
            CASE WHEN len(coalesce(
                TRY_CAST(a.args -> cp.method_from AS VARCHAR[]),
                CASE WHEN a.args ->> cp.method_from IS NOT NULL
                     THEN [a.args ->> cp.method_from] END,
                []::VARCHAR[]
            )) > 0
            THEN list_transform(
                coalesce(
                    TRY_CAST(a.args -> cp.method_from AS VARCHAR[]),
                    [a.args ->> cp.method_from]
                ),
                v -> regexp_extract(v, '#([A-Za-z0-9_]+)\.$', 1)
            ) END,
            mc.methods,
            cp.all_methods
        ) AS methods,
        -- Task 5: the same scalar-or-array, first-alias-wins read as `paths`
        -- above, applied to the media attributes instead of the path ones.
        -- An empty $consumes_from/$produces_from (every non-HTTP catalog
        -- today) means every alias is absent, so `list_extract` on the
        -- resulting empty list already yields NULL — no default needed, and
        -- none is a guessed one (D01 §4).
        --
        -- Spec 2026-09-18 §3b word 1: `smc.found`/`smp.found` are the media
        -- SIBLING reads (`sibling_consumes`/`sibling_produces` above), consulted
        -- only where the matched annotation's own aliases above found nothing —
        -- `@GET` (CP-18 row 1) carries no attribute at all, so the coalesce is
        -- the whole rule. NULL for every catalog declaring no media sibling,
        -- which is what keeps every catalog written before this word deriving
        -- byte-identically.
        coalesce(list_extract(list_filter(list_transform(
            cp.consumes_from,
            n -> CASE WHEN coalesce(a.args -> n ->> 0, a.args ->> n) IS NOT NULL
                      THEN coalesce(TRY_CAST(a.args -> n AS VARCHAR[]),
                                    [a.args ->> n]) END
        ), v -> v IS NOT NULL), 1), smc.found) AS consumes_list,
        coalesce(list_extract(list_filter(list_transform(
            cp.produces_from,
            n -> CASE WHEN coalesce(a.args -> n ->> 0, a.args ->> n) IS NOT NULL
                      THEN coalesce(TRY_CAST(a.args -> n AS VARCHAR[]),
                                    [a.args ->> n]) END
        ), v -> v IS NOT NULL), 1), smp.found) AS produces_list,
        -- The SCOPE this declaration's name sits inside, read off the same
        -- annotation that carries the name (2H design §1, form 2). Scalar-or-
        -- array and first-alias-wins like every other attribute read here.
        -- NULL where the annotation names no scope, which is what keeps the
        -- composition below a no-op for the annotations that carry a bare
        -- name and for every catalog declaring no `$qualifier_from` at all.
        list_extract(list_filter(list_transform(
            cp.qualifier_from,
            n -> coalesce(a.args -> n ->> 0, a.args ->> n)
        ), v -> v IS NOT NULL), 1) AS qualifier,
        mc.requires_qualifier AS requires_qualifier,
        -- `OI-5`: carried per ROW because it is per ANNOTATION, and the union
        -- with `member_declarations` below puts both kinds of row through one
        -- expression.
        mc.path_fallback AS path_fallback,
        mc.path_fallback_prefixes AS path_fallback_prefixes
    FROM annotations_effective a
    JOIN mapping_catalog mc ON mc.fqn = a.annotation
         AND (a.catalog_id IS NULL OR a.catalog_id = mc.catalog_id)
    JOIN catalog_params cp ON cp.catalog_id = mc.catalog_id
    LEFT JOIN sibling_names sn ON sn.catalog_id = mc.catalog_id AND sn.target = a.target
    LEFT JOIN sibling_produces smp ON smp.catalog_id = mc.catalog_id AND smp.target = a.target
    LEFT JOIN sibling_consumes smc ON smc.catalog_id = mc.catalog_id AND smc.target = a.target
    -- THE WITHDRAWAL FILTER (2I design §2, word 4). A declaration whose named
    -- attribute carries the withdrawing value derives NOTHING: the framework
    -- itself does not expose it, so a row here would be an endpoint nobody
    -- serves, published at `resolved`/`compiler` where nothing downstream can
    -- tell it from an observation.
    --
    -- `IS DISTINCT FROM` rather than `<>`, and that is the whole rule for an
    -- ABSENT attribute: an annotation's declared default is never written into
    -- the annotation USE (Phase 2I Task 2 checkpoint item 4), so the attribute
    -- reads NULL when it was left at its default — and NULL IS DISTINCT FROM
    -- anything, so the declaration is KEPT. Absence is not the withdrawing
    -- value; only the value written out is. A plain `<>` would have made every
    -- absent attribute NULL and dropped every row the filter touched.
    --
    -- Read scalar-or-array like every other attribute here, so a framework
    -- that arrays its flag needs no second rule.
    WHERE mc.unless_attribute IS NULL
       OR coalesce(a.args -> mc.unless_attribute ->> 0, a.args ->> mc.unless_attribute)
          IS DISTINCT FROM mc.unless_equals
),
-- THE CLASS GATE for the member rule below (2I design §2, word 3): every type
-- carrying one of this catalog's own mapping annotations ON THE TYPE ITSELF.
--
-- The same type-level join `qualifier_scopes` performs, and deliberately the
-- same one rather than `controllers`: a framework may gate on a MAPPING
-- annotation written on the type itself, with no separate type-level gate
-- declared at all, and `controllers` is empty for such a catalog because it
-- reads `$type_annotation`.
--
-- (This comment used to give a different reason — that `$type_annotation` was
-- one fqn and so could not name a gate with two spellings, which
-- `mapping.annotations` could because it is a list. §3.1 widened
-- `$type_annotation` to a list too, so that reason no longer holds and the
-- sentence was half-rewritten rather than replaced. The join is still right;
-- the reason above is the one that survives.)
-- Where a catalog declares `$type_annotation` as well, `derived`'s own
-- existing gate filter applies to these rows exactly as it does to every
-- other, so the narrower gate still wins with no second rule here.
--
-- DISTINCT because a type carrying two of the catalog's annotations is one
-- gated class, not two: without it a class annotated with both spellings at
-- once would enumerate each of its members twice.
gate_types AS (
    SELECT DISTINCT mc.catalog_id AS catalog_id, a.target AS type_symbol
    FROM annotations_effective a
    JOIN mapping_catalog mc ON mc.fqn = a.annotation
         AND (a.catalog_id IS NULL OR a.catalog_id = mc.catalog_id)
),
-- THE DIRECT GATE, and the whole of `members: declared_type_methods` (spec
-- 2026-09-22 §2c, M-3): the same gate types as above and the ones
-- `$type_annotation` names, restricted to the types that carry the gate
-- THEMSELVES rather than by inheritance.
--
-- The restriction is one conjunct, `NOT a.inherited`, and the column it reads
-- exists for this rule alone. It is deliberately NOT `a.catalog_id IS NULL`,
-- which is the same sentence read one level too coarsely and was this rule's
-- first spelling: `catalog_id` distinguishes a REAL row from ANY synthetic
-- one, and three passes write synthetic rows. Folding (`OI-36`) reads a
-- repeated annotation out of the container javac actually stored it in, and
-- composition (`A-C7`) reads a module-local stereotype back to the annotation
-- it was built from — in both, the author wrote that annotation on THAT type,
-- and the pass only undoes a spelling. Only the inheritance walk carries an
-- annotation ACROSS a type boundary, which is the one thing this word means
-- to exclude.
--
-- Read as `catalog_id IS NULL`, a contract type wearing a module-local
-- stereotype composed from the gate qualifies nowhere, and the word derives
-- NOTHING for it — the whole contract surface, silently, from ordinary
-- scanned input. That is the failure `_synthetic_annotations`' own comment
-- records as having "deleted the controller's whole surface" one rule over,
-- and it is why the composed gate carries a test of its own.
--
-- The usual `(a.catalog_id IS NULL OR a.catalog_id = <the catalog>)` conjunct
-- is kept rather than subsumed, now that synthetic rows can qualify: a
-- composition one catalog's closure resolved is not evidence for another's.
--
-- WHY THAT IS THE RULE, and it is a fabrication removed rather than a
-- narrowing for its own sake. The gate annotation sits on a CONTRACT type and
-- the inheritance walk carries it onto the implementing class — which is what
-- makes that class a gate type in the first place, so the rows this file
-- derives for it are right. Its OWN declarations are not: a public helper
-- beside the contract's members is an ordinary method nobody calls over a
-- wire, and `public_methods` publishes it as an operation at
-- `resolved`/`compiler`. Enumerating only what the DECLARING type declares is
-- the rule every contract-interface framework follows, and it is why the word
-- that carries it has a NEGATIVE test as well as a positive one.
--
-- BOTH gate shapes, for the reason `_validate_naming`'s own class-gate check
-- accepts both: a catalog may name its gate in `$type_annotation` or write it
-- as a `mapping.annotations` entry found on a TYPE, and a word that read only
-- one of them would derive NOTHING for a file using the other — silently,
-- which is the failure direction this vocabulary is least able to afford.
directly_gated_types AS (
    SELECT DISTINCT mc.catalog_id AS catalog_id, a.target AS type_symbol
    FROM annotations_effective a
    JOIN mapping_catalog mc ON mc.fqn = a.annotation
         AND (a.catalog_id IS NULL OR a.catalog_id = mc.catalog_id)
    WHERE NOT a.inherited
    UNION
    SELECT DISTINCT g.catalog_id AS catalog_id, a.target AS type_symbol
    FROM annotations_effective a
    JOIN type_gates g ON g.fqn = a.annotation
         AND (a.catalog_id IS NULL OR a.catalog_id = g.catalog_id)
    WHERE NOT a.inherited
),
-- `A-M15`: every type whose members a gated class EXPOSES — the gate type
-- itself, then its superclass, then its superclass's, within what was scanned.
--
-- The member rule below used to join `gate_types` on `s.enclosing` alone,
-- which reads "the public members of C" as "the public members DECLARED in C".
-- Every language whose facts this reads says otherwise: a type's members
-- include those it inherits. So a gated class extending a base published none
-- of the base's operations, silently, while the catalog that declares
-- `members` argues at length that an unmarked public member IS an operation —
-- "a catalog that derived only the annotated methods would report a service
-- missing one of its own operations".
--
-- MEASURED rather than inferred from a specification's wording (CP-13 Q3/Q4,
-- and the catalog that consumes this names the framework and the version):
-- the framework enumerates the gated type's inherited public members and drops
-- only those declared by the language's own root type. That exclusion is not
-- restated here, and does not need to be: capability 9.13 emits `superclass`
-- for every superclass EXCEPT the root, so this walk stops there by
-- construction rather than by naming it — which is what keeps the rule
-- language-blind (ARCHITECTURE §10) while mirroring the framework exactly.
--
-- `walked` is `_reach`'s `seen` guard said in SQL, and for the same reason —
-- these are facts, not a compiler's word, and a fact stream that disagreed
-- with its own language about cyclic inheritance must terminate here rather
-- than loop. It replaces the plain `UNION`'s deduplication, which stopped
-- being a cycle guard the moment `depth` joined the row: two visits to one
-- ancestor at different depths are different rows and dedupe against nothing.
--
-- `depth` is how far the declaring class is from the gate, and it exists for
-- one reason: an OVERRIDE has to win. See `exposed_members` below.
--
-- A superclass in a JAR contributes nothing: it has no `symbol` fact here, so
-- the walk ends at it. That is the same within-module boundary every other
-- closure in this codebase keeps.
gate_ancestry AS (
    SELECT catalog_id AS catalog_id, type_symbol AS gate_symbol, type_symbol AS owner_symbol,
           0 AS depth, [type_symbol] AS walked
    FROM gate_types
    UNION ALL
    SELECT a.catalog_id AS catalog_id, a.gate_symbol AS gate_symbol,
           sc.superclass AS owner_symbol,
           a.depth + 1 AS depth, list_append(a.walked, sc.superclass) AS walked
    FROM gate_ancestry a
    JOIN (
        SELECT payload ->> 'symbol' AS symbol, payload ->> 'superclass' AS superclass
        FROM raw_facts
        WHERE kind = 'symbol' AND (payload ->> 'superclass') IS NOT NULL
          -- Multi-release selection (W3c). This walk builds the type
          -- hierarchy, which is exactly where a losing overlay copy does
          -- the most damage: it contributes a superclass under the SAME
          -- symbol as the copy that wins.
          AND document_id IN (SELECT document_id FROM selected_documents)
    ) sc ON sc.symbol = a.owner_symbol
    WHERE NOT list_contains(a.walked, sc.superclass)
),
-- ONE MEMBER PER SIGNATURE, NEAREST DECLARATION WINS — the half the first
-- `A-M15` fix left out, and the fabrication it shipped.
--
-- The walk above enumerates every ancestor's declared members. The enumeration
-- it mirrors does not: MEASURED (CP-13 Q5, on the JDK the probe process itself
-- reported), `Class.getMethods()` over `class BillingWebService extends
-- AbstractBilling` where both declare `public String refund(String)` returns
-- `BillingWebService#refund` and NOT the base's — one entry per signature,
-- declared by the overriding class. JLS 8.4.8.1 is the same sentence, and
-- `RuntimeModeler.processClass` calls exactly that enumeration (CP-13 Q3).
--
-- Joining the ancestry alone therefore published an overridden operation
-- TWICE, the second attributed to a base class the framework never exposes.
-- Worse, and this is why the ordering below is not cosmetic: an override
-- carrying the catalog's own withdrawing annotation was claimed by the
-- annotated rule and withdrawn there, while the base's identical declaration
-- walked straight past the member rule's anti-join and published the withdrawn
-- operation at `resolved`/`compiler`. So the dedup runs BEFORE the exclusions
-- and before the anti-join, exactly as the framework filters `getMethods()`'
-- result rather than its input, and an override's own annotation governs the
-- member it overrides.
--
-- THE KEY IS THE LANGUAGE'S OWN (GUIDELINES §8.1): a method is its name AND
-- its parameter types in order, never its arity and never its descriptor hash
-- — that hash covers the RETURN type too (`ClassScanner.disambiguatorOf`), so
-- keying on it would leave a covariant-return override undeduplicated, which
-- is the fabrication again. `supertype_dispatch._members` builds the same key
-- in Python, down to reading each parameter's symbol bare.
--
-- A member whose fact carries NO signature at all keys as if it took no
-- parameters, so two same-named overloads in one ancestry would collapse to
-- one — an under-report. That holds only while every scanner writes one:
-- `ClassScanner.visitEnd` emits `signatureJson` for every method
-- unconditionally, and this comment stops being true the day a scanner that
-- does not reaches these facts.
--
-- WHAT IS ENUMERATED HERE and what is filtered after, and the split is the
-- framework's: `getMethods()` returns PUBLIC methods, so visibility is part of
-- the enumeration; `isWebMethodBySpec` then tests each result, so `static` is
-- applied to the winner. A SYNTHETIC method is dropped before the dedup rather
-- than after, because a covariant-return override ships a bridge in the SAME
-- class as the real override — at the same depth — and a bridge winning the
-- tie would drop the operation entirely.
exposed_members AS (
    SELECT
        g.catalog_id AS catalog_id,
        s.symbol AS symbol,
        g.gate_symbol AS gate_symbol,
        row_number() OVER (
            PARTITION BY
                g.catalog_id,
                g.gate_symbol,
                split_part(regexp_extract(s.symbol, '[^#]*$'), '(', 1),
                coalesce(
                    -- `erased_symbol`, the DESCRIPTOR's own answer, NOT `type.symbol`.
                    -- `type.symbol` is the SIGNATURE's where the method has one, so a
                    -- parameter declared `T` reads `T` — and a type variable's name is
                    -- scoped to the declaration that named it. An interface declaring
                    -- `void m(E)` and its implementation declaring `void m(T)` are one
                    -- method, and keying on the name puts them in two partitions, so
                    -- both survive the dedup and one method publishes two rows.
                    --
                    -- The fallback is for a fact written before `erased_symbol` existed;
                    -- it is a whole-list fallback, never a per-element one, because the
                    -- two lists must stay the same length. A JSON path wildcard DROPS
                    -- elements whose key is absent, so mixing them per element would
                    -- shorten the key and silently merge two different methods.
                    list_aggregate(
                        list_transform(
                            json_extract_string(s.signature, '$.parameters[*].erased_symbol'),
                            parameter -> regexp_extract(parameter, '[^ ]*$')
                        ),
                        'string_agg', ','
                    ),
                    list_aggregate(
                        list_transform(
                            json_extract_string(s.signature, '$.parameters[*].type.symbol'),
                            parameter -> regexp_extract(parameter, '[^ ]*$')
                        ),
                        'string_agg', ','
                    ),
                    ''
                )
            -- `symbol` breaks a tie no source language this reads can
            -- produce — two declarations of one signature at one depth
            -- differ only in their return type, which a compiled artifact
            -- permits and a declaration does not — so that two runs over the
            -- same facts answer the same (NFR-1).
            ORDER BY g.depth, s.symbol
        ) AS nearest
    FROM symbols s
    JOIN gate_ancestry g ON g.owner_symbol = s.enclosing
    JOIN catalog_params cp ON cp.catalog_id = g.catalog_id
    -- BOTH member words enumerate the same candidates, and they differ by one
    -- conjunct applied AFTER the dedup (`member_declarations` below) rather
    -- than by a second walk here — the split this CTE already makes between
    -- what is enumerated and what is filtered off the winner. Sited before the
    -- dedup instead, the new conjunct would drop an overriding declaration out
    -- of its own partition and let the ancestor declaration it shadows win
    -- there: the same fabrication one level down that the declaring-class
    -- filter below is sited after the dedup to avoid.
    WHERE cp.members IN ('public_methods', 'declared_type_methods')
      AND s.construct_kind = 'method'
      AND s.visibility = 'public'
      AND coalesce(s.modifiers ->> 'synthetic', 'false') <> 'true'
),
-- THE MEMBER RULE (2I design §2, word 3). Where a catalog declares
-- `$members`, a gated class exposes members that carry no annotation at all,
-- and each becomes a declaration with an empty name — which `$path_fallback`
-- (required beside `$members` by `annotation_driven.py::_validate_naming`)
-- then answers with the member's own name.
--
-- WHAT IS NOT A MEMBER, and why each exclusion is a fact rather than a taste.
-- The first three are applied by `exposed_members` above, before the dedup;
-- the fourth here, after it — see that CTE for why the split is the
-- framework's own rather than a convenience:
--   * A CONSTRUCTOR. `construct_kind` tells it apart from a method outright
--     (D00's closed set), and `derived`'s own join already admits only
--     'method'/'function'; naming it there as well says the member rule
--     intends the exclusion rather than inheriting it by luck.
--   * A SYNTHETIC method — a covariant-return bridge, a lambda body, an
--     accessor minted for a nested class. Nobody wrote it, so there is no
--     declaration to expose. Unlike fields, synthetic METHODS do reach the
--     fact stream on purpose (the inheritance walk's bridge rule needs to see
--     them), which is exactly why this has to say so.
--   * A NON-PUBLIC method: not callable from outside the type, so not
--     exposed. This is the one exclusion the word itself names.
--   * A STATIC method. It is bound to the type, not to an instance, so it is
--     not a member of the exposed object at all — the same distinction
--     `modifiers.static` already draws for a field that reaches no payload.
-- `coalesce(..., 'false')` on both modifiers for the reason D00 §5a states:
-- a scanner that does not report a modifier is not asserting the modifier is
-- true, and each reader supplies its own default.
--
-- AND THE ANNOTATED MEMBER. A member that carries ANY of this catalog's
-- mapping annotations is left entirely to that rule — one row per member,
-- never two. The anti-join is against `annotations_effective`, NOT against
-- `declared`, and the difference is the whole of the interaction with word 4:
-- a declaration the withdrawal filter removed from `declared` is still an
-- ANNOTATED declaration, so the member rule must not quietly re-derive the
-- very row the framework withdrew. Joining `declared` instead would have
-- turned every `unless` into a no-op on a gated class.
--
-- It is asked of the member `exposed_members` chose — the OVERRIDE, where one
-- exists — and never of the declaration the override shadows, which is what
-- lets an override's own annotation withdraw the inherited member too. Asking
-- it of every declaration in the ancestry is what shipped an operation
-- `@WebMethod(exclude = true)` explicitly withdraws.
--
-- TWO KNOWN SOFT SPOTS, for whoever writes the second `members` catalog:
--
--   (i) The load-time class-gate check (`annotation_driven.py::
--   _validate_naming`) accepts ANY non-empty `mapping.annotations`, because
--   whether an annotation lands on a TYPE is a fact about the scanned code
--   and not about the file. So a catalog whose annotations are all
--   method-level declares `members` and is silently INERT — `gate_types`
--   matches nothing and no member row is ever derived — rather than refused.
--   That is the safe direction to fail in (nothing wrong is published), but
--   it is a gap in the refusal, not a property of it.
--
--   (ii) `$all_methods` binds here directly, exactly as it does for an
--   annotated declaration, and a member row has no annotation to read a verb
--   off — so this list IS the member's verb. `jakarta-jws.yml` is verbless
--   (`all_methods: []`), which is what makes each of its members ONE
--   unverbed row. `temporal-activity.yml` (spec 2026-09-22 §1c) is the
--   catalog that binds a non-empty one, `[activity]`: every member of an
--   `@ActivityInterface` IS an activity (CP-30 Q4), so the single-element
--   list is what puts the kind in the `method` column of a member row that
--   would otherwise carry NULL — measured on `fixtures/temporal-probe`,
--   where `billing_RefundCard` is derived by this branch. A list with TWO
--   entries would fan every member across both, which may well be right for
--   a framework whose exposed members answer several verbs and is the half
--   of this behaviour no shipped catalog exercises.
member_declarations AS (
    SELECT
        em.catalog_id AS catalog_id,
        s.symbol AS target,
        -- The type whose ANNOTATION made this member an operation, which is
        -- not always the type that declares it (`A-M15`). `derived` composes a
        -- row's scope, prefix and construct gate from this rather than from
        -- `s.enclosing`, because an inherited member's declaring class carries
        -- none of them — it is an ordinary base class, and reading its
        -- `enclosing` would ask the wrong type for the service's namespace and
        -- then drop the row for having none.
        em.gate_symbol AS gate_type,
        [''] AS paths,
        cp.all_methods AS methods,
        CAST(NULL AS VARCHAR[]) AS consumes_list,
        CAST(NULL AS VARCHAR[]) AS produces_list,
        -- A member states no scope of its own — it has no annotation to state
        -- one on — so it takes the one its enclosing type states, through the
        -- same `qualifier_scopes` join every other row uses.
        CAST(NULL AS VARCHAR) AS qualifier,
        -- `requires_qualifier` is a statement about the FRAMEWORK ("what this
        -- framework exposes is a member of a scope"), not about one
        -- annotation, so a catalog that says it of its annotated operations is
        -- saying it of the unannotated ones too — they are the same
        -- operations. Without this a member of a class with no scope anywhere
        -- would publish its bare name as a top-level identity, which is the
        -- confidently-wrong-address failure `requires_qualifier` exists to
        -- close, reached by the one route that carries no annotation.
        (SELECT coalesce(bool_or(requires_qualifier), FALSE) FROM mapping_catalog
         WHERE mapping_catalog.catalog_id = em.catalog_id)
            AS requires_qualifier,
        -- The CATALOG-level word, and never a per-annotation one: this row
        -- exists precisely because the member carries no annotation to read an
        -- override off (`OI-5`). `_validate_naming` already refuses `$members`
        -- declared without `$path_fallback`, so this is never NULL on a catalog
        -- that reaches here.
        cp.path_fallback AS path_fallback,
        cp.path_fallback_prefixes AS path_fallback_prefixes
    FROM exposed_members em
    JOIN symbols s ON s.symbol = em.symbol
    JOIN catalog_params cp ON cp.catalog_id = em.catalog_id
    WHERE em.nearest = 1
      AND coalesce(s.modifiers ->> 'static', 'false') <> 'true'
      -- A `final` member is not exposed either: JAX-WS's `isWebMethodBySpec` (CP-13 Q4)
      -- excludes it beside `static`, and the one catalog that declares
      -- `members: public_methods`, `jakarta-jws.yml`, is JAX-WS.
      -- `modifiers.final` is written for every method (`ClassScanner.methodModifiersJson`).
      AND coalesce(s.modifiers ->> 'final', 'false') <> 'true'
      -- THE DECLARING CLASS MUST ITSELF BE GATED (w63, `jaxws-inherited-unannotated`).
      -- A member with no annotation of its own is an operation only if the class
      -- that DECLARES it carries the gate annotation — not the class the walk
      -- started from. Measured in both runtimes' bytecode and confirmed live
      -- (`scripts/probes/w63_cxf_web_method_rule.md`): jaxws-rt 4.0.2's
      -- `RuntimeModeler.isWebMethodBySpec` offsets 124-147 and Apache CXF 4.0.5's
      -- `JaxWsServiceConfiguration.hasWebServiceAnnotation` offsets 0-17 both read
      -- `method.getDeclaringClass()` then `getAnnotation(WebService.class)`, and
      -- `ifnull` → not an operation; over `BillingWebService extends AbstractBilling`
      -- (no `@WebService` on the base) both produced `charge` alone. Without this the
      -- walk published the base's `refund` as an operation neither runtime serves.
      --
      -- Asked HERE, of the dedup's winner, and not in `exposed_members` of every
      -- declaration: `isWebMethodBySpec` tests what `getMethods()` returned, and
      -- that is the NEAREST declaration (JLS 8.4.8.1: the middle class's
      -- declaration OVERRIDES the ancestor's and is then the one member;
      -- confirmed with `getMethods()` over `C extends D extends E`, D plain
      -- and E annotated, both declaring `op()` — D's is returned). Filtering
      -- before the dedup would
      -- drop D's row and let E's shadowed declaration win the partition — the
      -- same fabrication one level down. And this is a FILTER on the declaring
      -- class, not a stop in `gate_ancestry`: the walk continues past a plain
      -- class, so E's OTHER public methods — declared by an annotated class —
      -- still derive for C, exactly as `getMethods()` still returns them.
      AND s.enclosing IN (SELECT type_symbol FROM gate_types
                          WHERE gate_types.catalog_id = em.catalog_id)
      -- AND, UNDER `declared_type_methods`, IT MUST CARRY THE GATE ITSELF
      -- (spec 2026-09-22 §2c, M-3). The conjunct above is satisfied by an
      -- INHERITED gate, and an inherited gate is precisely what makes an
      -- implementing class a gate type — so on such a class the rule above
      -- enumerates the class's own helper methods beside the contract's
      -- members and publishes each as an operation nothing calls.
      -- `directly_gated_types` is the same set restricted to the annotation
      -- rows a scanner READ, so this admits only members declared where the
      -- contract itself is declared. See that CTE for the whole argument.
      --
      -- Written as a disjunction on the WORD rather than as a second rule, so
      -- `public_methods` evaluates exactly what it always did: the first
      -- branch is true for every row of every catalog written before this
      -- word, and the subquery is never reached for them.
      AND (cp.members <> 'declared_type_methods'
           OR s.enclosing IN (SELECT type_symbol FROM directly_gated_types
                              WHERE directly_gated_types.catalog_id = em.catalog_id))
      AND NOT EXISTS (
          SELECT 1 FROM annotations_effective a
          JOIN mapping_catalog mc ON mc.fqn = a.annotation
               AND (a.catalog_id IS NULL OR a.catalog_id = mc.catalog_id)
          WHERE mc.catalog_id = em.catalog_id
            AND a.target = s.symbol
      )
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
--
-- This is also where $namespace_default is answered, and answering it HERE
-- rather than in `derived` is what makes it a fact instead of a guess: a row
-- exists here only where a scope-carrying annotation was actually FOUND on
-- the type, so the default fires for a type that declares the annotation and
-- leaves its attribute unstated, and NEVER for a type that declares no such
-- annotation at all. A declared default is not written into the class file
-- (Phase 2I Task 2 checkpoint item 4: a bare `@WebService` emits `args: {}`),
-- so "absent" is the only shape the defaulted case can take — and without
-- this gate, "absent attribute" and "absent annotation" would be one thing,
-- minting an endpoint for any class that merely happens to hold a matching
-- method.
qualifier_scopes AS (
    SELECT
        mc.catalog_id AS catalog_id,
        a.target AS type_symbol,
        coalesce(
            list_extract(list_filter(list_transform(
                cp.qualifier_from,
                n -> coalesce(a.args -> n ->> 0, a.args ->> n)
            ), v -> v IS NOT NULL), 1),
            -- The declaring type's own package, reversed and dot-joined, then
            -- composed into $namespace_template. Pinned against BOTH
            -- reference implementations, which agree character for character
            -- (checkpoint item 2):
            -- `com.sun.xml.ws.model.RuntimeModeler#getNamespace` and Apache
            -- CXF's independent `PackageUtils#getNamespace` — including the
            -- trailing separator the template carries, which is not
            -- decoration: an address missing it matches no caller.
            --
            -- The package is read off the type symbol itself: D00 §1 puts it
            -- after the module prefix's last space, and the segment following
            -- the final `/` is the class (a nested `Outer$Inner` included),
            -- which is why the class segment is matched and discarded rather
            -- than kept. A METHOD target reaches this expression too — every
            -- mapping annotation lands in this CTE, not just type-level ones
            -- — and matches nothing, because a method descriptor ends `).`
            -- rather than `#`; so it derives NULL and joins to no type below.
            --
            -- A class in the DEFAULT package has no `/` and so no match,
            -- which yields NULL here — and that is the algorithm, not a gap
            -- in it: both implementations return null for the empty package,
            -- because there is nothing to reverse. A template filled with an
            -- empty package would be neither a scope nor an honest absence.
            CASE WHEN cp.namespace_template IS NOT NULL
                      AND regexp_extract(a.target, '([^ ]*)/[^/ ]*#$', 1) <> ''
                 THEN printf(cp.namespace_template, array_to_string(list_reverse(str_split(
                          regexp_extract(a.target, '([^ ]*)/[^/ ]*#$', 1), '/'
                      )), '.'))
            END
        ) AS qualifier
    FROM annotations_effective a
    JOIN mapping_catalog mc ON mc.fqn = a.annotation
         AND (a.catalog_id IS NULL OR a.catalog_id = mc.catalog_id)
    JOIN catalog_params cp ON cp.catalog_id = mc.catalog_id
),
-- Type-level and method-level annotations are different roles: on
-- @RequestMapping value/path both mean *path*, on @FeignClient value aliases
-- *name* — the service id — and only path means prefix. prefix_from and
-- peer_from keep the roles apart (spec ruling I2).
prefixes AS (
    SELECT
        pg.catalog_id AS catalog_id,
        a.target AS type_symbol,
        coalesce(list_extract(list_filter(list_transform(
            cp.prefix_from,
            n -> coalesce(a.args -> n ->> 0, a.args ->> n)
        ), v -> v IS NOT NULL), 1), '') AS prefix,
        list_extract(list_filter(list_transform(
            cp.peer_from,
            n -> coalesce(a.args -> n ->> 0, a.args ->> n)
        ), v -> v IS NOT NULL), 1) AS peer,
        -- Class-level media, read off the prefix annotation with the SAME
        -- attribute names ($consumes_from/$produces_from) the method
        -- annotations use, because every framework catalogued so far spells
        -- them identically on both levels. Applied below only where the
        -- method declared none: the frameworks' own combine rule returns the
        -- METHOD's declaration whenever it is non-empty and the class's
        -- otherwise, never a union — which is what `coalesce` says and what a
        -- union would get wrong (the measurement is recorded on the catalogs
        -- that declare these words, 2026-09-12). Before this a class-level
        -- `produces = "application/xml"` derived NULL, and a module with a
        -- JSON converter present would have called that XML route `json`.
        list_extract(list_filter(list_transform(
            cp.consumes_from,
            n -> CASE WHEN coalesce(a.args -> n ->> 0, a.args ->> n) IS NOT NULL
                      THEN coalesce(TRY_CAST(a.args -> n AS VARCHAR[]),
                                    [a.args ->> n]) END
        ), v -> v IS NOT NULL), 1) AS consumes_list,
        list_extract(list_filter(list_transform(
            cp.produces_from,
            n -> CASE WHEN coalesce(a.args -> n ->> 0, a.args ->> n) IS NOT NULL
                      THEN coalesce(TRY_CAST(a.args -> n AS VARCHAR[]),
                                    [a.args ->> n]) END
        ), v -> v IS NOT NULL), 1) AS produces_list
    FROM annotations_effective a
    JOIN prefix_gates pg ON pg.fqn = a.annotation
         AND (a.catalog_id IS NULL OR a.catalog_id = pg.catalog_id)
    JOIN catalog_params cp ON cp.catalog_id = pg.catalog_id
),
-- CP-22 row 2 (spec §3f): `prefixes.peer` above is read off the PREFIX gate's
-- own row, which is correct for every catalog whose peer and prefix share one
-- annotation (`@FeignClient`) but wrong for MicroProfile REST Client, whose
-- peer (`baseUri`/`configKey`) sits on `@RegisterRestClient` while the prefix
-- sits on `@Path` — two different annotation rows on the same type. `peers`
-- mirrors `prefixes` exactly (same keying, same scalar-or-array read) but
-- joins through `peer_gates` instead, so it reads `$peer_from` off the row
-- `$peer_annotation` actually names. Below, the final select coalesces
-- `peers.peer` ahead of `prefixes.peer` — `peers` wins wherever it has a row,
-- which is every catalog that declares its own `peer_annotation`; every other
-- catalog's `peer_gates` is byte-identical to its `prefix_gates` (the default
-- in `annotation_driven.py::params_for`), so `peers` joins the SAME
-- annotation row `prefixes` did and the two columns agree — the coalesce is
-- inert for them.
peers AS (
    SELECT
        pg.catalog_id AS catalog_id,
        a.target AS type_symbol,
        list_extract(list_filter(list_transform(
            cp.peer_from,
            n -> coalesce(a.args -> n ->> 0, a.args ->> n)
        ), v -> v IS NOT NULL), 1) AS peer
    FROM annotations_effective a
    JOIN peer_gates pg ON pg.fqn = a.annotation
         AND (a.catalog_id IS NULL OR a.catalog_id = pg.catalog_id)
    JOIN catalog_params cp ON cp.catalog_id = pg.catalog_id
),
-- The prefix `prefixed_capitalized_construct_name` composes (spec 2026-09-22
-- §2b, CP-30 row 2), read off the DECLARING type's own gate annotation —
-- `$fallback_prefix_attr` names the attribute, and `type_gates` is the join,
-- mirroring `prefixes` one attribute over.
--
-- A DIFFERENT prefix from `prefixes.prefix`, and the difference is the point:
-- that one joins the FRONT of every composed address, while this one is
-- reached only by the fallback and therefore only by a member that named
-- nothing. CP-30 Q2 is why that distinction is the framework's own and not a
-- convenience — the prefix composition sits INSIDE the empty-name branch, so a
-- member carrying its own name skips it, and a prefix machinery applying to
-- every row would compose an address nothing answers for exactly that member.
--
-- Empty for every catalog that declares no such attribute, so the LEFT JOIN
-- below finds nothing and the composition is inert. Scalar-or-array like every
-- other attribute read in this file. A type carrying the gate and NOT the
-- attribute yields '' — the same `coalesce(..., '')` `prefixes` makes one
-- level over, and the same reading: the halves compose, and a half nobody
-- wrote contributes nothing rather than removing the other.
fallback_prefixes AS (
    SELECT
        g.catalog_id AS catalog_id,
        a.target AS type_symbol,
        coalesce(a.args -> cp.fallback_prefix_attr ->> 0,
                 a.args ->> cp.fallback_prefix_attr, '') AS prefix
    FROM annotations_effective a
    JOIN type_gates g ON g.fqn = a.annotation
         AND (a.catalog_id IS NULL OR a.catalog_id = g.catalog_id)
    JOIN catalog_params cp ON cp.catalog_id = g.catalog_id
    WHERE cp.fallback_prefix_attr IS NOT NULL
),
-- Spec 2026-09-18 §3b word 2: the class-level media default read off a TYPE-level sibling
-- (`@Produces` on a JAX-RS resource class). Keyed on the type so it joins exactly as
-- `prefixes` does; the combine below is coalesce — the method's declaration, else the
-- class's, never a union (Jersey `resolveProducedTypes`, Quarkus EndpointIndexer 725,
-- CP-18 row 5 / CP-19 row 2).
-- `"column"` is quoted throughout because DuckDB reserves the word in its own
-- grammar, and the STRUCT type declaration just below is exactly where the
-- unquoted spelling fails to parse — verified directly:
-- `CAST({'column': 1} AS STRUCT(column INTEGER))` raises `Parser Error: syntax
-- error at or near "column"`, while the same word unquoted in an expression
-- position (`s.column`, a JOIN or WHERE reference) mostly parses. Quoted
-- everywhere here anyway, rather than only where it is strictly required, so
-- the one field does not carry two different spelling rules depending on
-- where it is written.
type_media_sources AS (
    SELECT u.catalog_id AS catalog_id, s."column" AS "column", s.ordinal AS ordinal, s.annotation AS annotation, s.arg AS arg
    FROM (SELECT cp.catalog_id AS catalog_id, UNNEST(cp.type_media_from_siblings) AS s FROM catalog_params cp) u
),
type_media AS (
    SELECT ts.catalog_id AS catalog_id, a.target AS type_symbol,
           -- No CASE needed inside `min_by` here: the FILTER clause already
           -- restricts each aggregate's input rows to the one `"column"`
           -- value it names, so every row `min_by` ever sees for the
           -- `produces` arm already satisfies `ts."column" = 'produces'` (and
           -- likewise for `consumes`) — a CASE re-testing the same predicate
           -- would only ever take its THEN branch.
           min_by(coalesce(TRY_CAST(a.args -> ts.arg AS VARCHAR[]), [a.args ->> ts.arg]), ts.ordinal)
               FILTER (WHERE ts."column" = 'produces') AS produces_list,
           min_by(coalesce(TRY_CAST(a.args -> ts.arg AS VARCHAR[]), [a.args ->> ts.arg]), ts.ordinal)
               FILTER (WHERE ts."column" = 'consumes') AS consumes_list
    FROM annotations_effective a
    JOIN type_media_sources ts ON ts.annotation = a.annotation
         AND (a.catalog_id IS NULL OR a.catalog_id = ts.catalog_id)
    WHERE coalesce(a.args -> ts.arg ->> 0, a.args ->> ts.arg) IS NOT NULL
    GROUP BY ts.catalog_id, a.target
),
-- Cross product of methods and paths (a two-topic, two-method mapping is
-- four identities): DuckDB zips rather than cross-joins when two UNNESTs sit
-- in the same SELECT (verified empirically), so methods are unnested in
-- their own CTE first, and mapped_methods.paths is unnested from that.
mapped_methods AS (
    SELECT d.catalog_id AS catalog_id,
           d.target AS target,
           d.gate_type AS gate_type,
           UNNEST(CASE WHEN len(d.methods) = 0
                       THEN [CAST(NULL AS VARCHAR)] ELSE d.methods END) AS wire_method,
           d.paths AS paths,
           d.consumes_list AS consumes_list,
           d.produces_list AS produces_list,
           d.qualifier AS qualifier,
           d.requires_qualifier AS requires_qualifier,
           d.path_fallback AS path_fallback,
           d.path_fallback_prefixes AS path_fallback_prefixes
    FROM (SELECT * FROM declared UNION ALL SELECT * FROM member_declarations) d
),
mappings AS (
    SELECT mm.catalog_id AS catalog_id,
           mm.target AS method_symbol,
           mm.gate_type AS gate_type,
           mm.wire_method AS wire_method,
           UNNEST(mm.paths) AS path_suffix,
           mm.consumes_list AS consumes_list,
           mm.produces_list AS produces_list,
           mm.qualifier AS qualifier,
           mm.requires_qualifier AS requires_qualifier,
           mm.path_fallback AS path_fallback,
           mm.path_fallback_prefixes AS path_fallback_prefixes
    FROM mapped_methods mm
),
derived AS (
    SELECT
        cp.protocol AS protocol,
        -- THE DIRECTION FLIP (D02 §2c), spelled ONCE as a column so the four
        -- places it decides something read one predicate rather than four
        -- copies of one. A row flips when the type ENCLOSING its declaration is
        -- one the catalog's own condition holds for — never merely because the
        -- catalog has a rule, which would rewrite every client this catalog
        -- describes into an endpoint the module serves.
        --
        -- `flipped` is projected out of `unioned` below: it decides `direction`,
        -- `handler`, `caller` and the canonical-address question, and none of
        -- those is a second identity column.
        (fl.owner IS NOT NULL) AS flipped,
        -- Computed as `resolved_direction` and read back under that name by
        -- `handler` and `caller` below, then published as `direction`: the
        -- published name is also a column of the joined `cp` row, and a
        -- column of the FROM shadows a select-list alias — read as `direction`
        -- the CASEs below would see the catalog's DECLARED direction and land a
        -- flipped row's symbol on the wrong side. `resolved_direction` is
        -- projected out of `unioned` exactly as `flipped` is.
        CASE WHEN flipped THEN cp.flip_direction ELSE cp.direction END AS resolved_direction,
        resolved_direction AS direction,
        m.wire_method AS method,
        -- Three fragments, in address order (2H design §1): the TYPE-level
        -- prefix, the scope this declaration names on its own annotation, and
        -- the declared name itself. The last two compose here into
        -- `scoped_name`; the prefix joins onto its front just below, because
        -- that seam has a rule of its own and this one does not.
        --
        -- Both new fragments are inert unless a catalog asks for them —
        -- `$qualifier_from` empty leaves `m.qualifier` NULL, `$path_fallback`
        -- NULL fails its equality — so every catalog written before them
        -- reduces this to `m.path_suffix`, which is what it was.
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
        --
        -- HOW the scope composes is catalog data twice over: a separator
        -- between the two halves, or — where no single character can say it
        -- — a whole $qualifier_format. `qname` is the second kind: `{scope}`
        -- brackets the scope and butts the name straight against the closing
        -- brace, and there is no separator value that spells a token with
        -- punctuation on BOTH sides of one half. The two are mutually
        -- exclusive by contract (`annotation_driven.py::_validate_naming`),
        -- so this reads as one rule with two spellings rather than two rules
        -- racing.
        --
        -- The construct's own name, off the symbol the join below already
        -- resolved. D00 §1's descriptor puts it between the type separator and
        -- the signature — the shape `$method_from`'s own read above already
        -- relies on. `$` is in the class because the JVM admits it in a method
        -- name; a symbol this failed to match would yield '' silently, which is
        -- the empty-address failure again. Spelled once as a column because the
        -- fallback branch below reads it several times — four in the accessor
        -- strip, twice more in the capitalising word beside it.
        regexp_extract(s.symbol, '#([A-Za-z0-9_$]+)\(', 1) AS construct_name,
        -- THE TYPE THIS ROW IS ATTRIBUTED TO, for the three words that name a
        -- type instead of the construct (spec 2026-09-22 §2b, CP-30 row 1).
        -- It is the type the ANNOTATION sat on — `m.gate_type` where a member
        -- rule carried one, the annotation target's own enclosing type
        -- otherwise — which is the same `coalesce` every other read in this
        -- CTE already makes, for `A-M15`'s reason.
        --
        -- NAMED for what it is rather than "the declaring type", because on a
        -- member row the two are not always the same type and `A-M15` says so
        -- in `member_declarations` above: an INHERITED member is attributed to
        -- the gate the walk started from, not to the base class that declares
        -- it. So a gated subclass of a gated base publishes the base's member
        -- twice — once under each gate, each with that gate's own name and
        -- prefix — which is `A-M15`/w63 behaviour these words inherit rather
        -- than introduce, and which a test pins so the next reader finds it
        -- stated. For an ANNOTATED declaration, and for every member whose
        -- own declaring type carries the gate directly (which is every member
        -- `declared_type_methods` keeps), this IS the declaring type.
        --
        -- And it is NOT the handler. The two come apart exactly where these
        -- words are needed: the declaration sits on the contract type while
        -- `handler` below may be rebound to the implementor's own override, so
        -- reading the handler's class would publish the implementor's name —
        -- a type no caller ever names, and the whole of what CP-30 Q1
        -- measured (the constructor takes the INTERFACE's simple name on one
        -- branch and the reflected method's own name on every other).
        --
        -- Spelled as three columns because the two words read the same symbol
        -- two ways: the module prefix is everything up to the last space
        -- (D00 §1), the trailing `#` is the type separator, and the SIMPLE
        -- name is what follows the last package separator or nested-type
        -- separator — the innermost name, which is what the measured call
        -- returns for a nested type as well as a top-level one.
        --
        -- A declaration with NO declaring type at all — a free function (D00
        -- §4) — reads NULL here and composes NULL rather than an invented
        -- name, which is the honest answer for a word that names a type where
        -- there is none. It is unreachable for any catalog that can sensibly
        -- declare one of these words: the gate filter below already drops a
        -- row whose enclosing type is NULL, and a word naming the DECLARING
        -- type on a catalog with no type gate would have nothing to name.
        -- No extractor writing into these facts emits one today in any case,
        -- which is the same reason the construct-kind join below calls its own
        -- free-function branch a no-op.
        regexp_extract(coalesce(m.gate_type, s.enclosing), '[^ ]*$') AS declaring_descriptor,
        replace(rtrim(declaring_descriptor, '#'), '/', '.') AS declaring_qualified_name,
        regexp_extract(rtrim(declaring_descriptor, '#'), '[^/$]*$') AS declaring_simple_name,
        CASE WHEN coalesce(m.qualifier, q.qualifier) IS NOT NULL
             THEN CASE WHEN cp.qualifier_format = 'qname'
                       THEN '{' || coalesce(m.qualifier, q.qualifier) || '}'
                       ELSE coalesce(m.qualifier, q.qualifier) || cp.qualifier_separator END
             ELSE '' END
            -- THE FALLBACK, and the ACCESSOR STRIP some words apply to it
            -- (`OI-5`). `m.path_fallback` is the word for THIS row's own
            -- annotation, already resolved against the catalog default, so a
            -- catalog whose two operation annotations face opposite directions
            -- gets one rule each instead of one rule that is wrong for one of
            -- them. NULL means no fallback at all, which is what every catalog
            -- declaring none binds, and the branch is then never taken.
            --
            -- The strip is MEASURED and its three conditions are the
            -- framework's own (CP-15 rows 4a-4b, exercised by row 5's compiled
            -- run): the name starts with the prefix, is LONGER than it, and
            -- carries an upper-case character AT THE SEAM — then the remainder
            -- is taken with its FIRST CHARACTER lowercased, never the whole of
            -- it. `getURL -> uRL` is the edge that tells this rule apart from
            -- every plausible paraphrase, `get -> get` is the length test and
            -- `gettotal -> gettotal` the seam test. A word that strips nothing
            -- ('construct_name') binds an empty prefix list, so the
            -- `list_transform` yields nothing and the `coalesce` hands the name
            -- back unchanged — which is exactly what it did before this key.
            --
            -- `[A-Z]` is ASCII because the name this can ever see is: the
            -- extraction above admits `[A-Za-z0-9_$]` and nothing else, so a
            -- method named with a non-ASCII letter yields '' here long before
            -- the seam test runs. This stops being right the day that character
            -- class widens.
            --
            -- THE THREE DECLARING-TYPE WORDS (spec 2026-09-22 §2b) branch on
            -- the WORD rather than on a prefix list, because none of them
            -- strips anything off a member name — two of them do not read the
            -- member name at all. They are inside the same fallback branch and
            -- not beside it, and that is the rule rather than a tidier
            -- spelling: a declaration that NAMED itself never reaches a
            -- fallback, so the prefix the third word composes is skipped by
            -- construction for exactly the member CP-30 Q2 measured skipping
            -- it (`@…(name = "Charge")` under the prefix `billing_` is
            -- `Charge`, never `billing_Charge`). A flag outside this branch
            -- would have to re-derive that edge and could get it wrong.
            --
            -- The capitalisation is `upper` of the FIRST character and the
            -- remainder untouched — CP-30 Q3's `substring(0, 1).toUpperCase()`
            -- appended to `substring(1)`, offsets 15-26 — never a title-casing
            -- of the whole name, which would rewrite every character after the
            -- first of an all-caps member name.
            --
            -- THE FOURTH DECLARING-TYPE WORD IS HOISTED OUT OF THE
            -- NAMED-NOTHING TEST (spec 2026-09-22 §1d), and it is the ONE word
            -- here that is. Every other answers "what is the name when the
            -- annotation carried none", and skipping a named declaration is
            -- what makes CP-30 Q2's edge free. This one answers a different
            -- question: the SCOPE in front of the name is not a framework
            -- default at all. Temporal's own name for a signal is the bare
            -- member name (CP-30 Q1, offset 122), or the annotation's own
            -- where it wrote one (offset 81's `Optional.orElse`, which wins on
            -- every branch) — the workflow TYPE in front of it is §1d's
            -- identity rule, and it exists so that two workflows' `cancel` are
            -- two endpoints rather than one. A scope applied only to the
            -- declarations that named nothing would leave
            -- `@SignalMethod(name = "Abort")` publishing a bare `Abort`: the
            -- colliding identity §2f refuses for
            -- `WorkflowStub.signal("cancel", …)`, reached by the other route.
            -- So the word composes around WHICHEVER name won — `m.path_suffix`
            -- where the declaration wrote one, `construct_name` where it did
            -- not — and the arm sits ahead of the named-nothing test rather
            -- than inside it.
            --
            -- It is written here rather than beside this whole expression so
            -- that a catalog declaring no such word reaches an unsatisfiable
            -- `WHEN` and falls through to exactly the branch it always did:
            -- every other catalog's address is byte-identical.
            || CASE WHEN m.path_fallback = 'declaring_type_scoped_name'
                    THEN declaring_simple_name || cp.fallback_scope_separator
                         || CASE WHEN m.path_suffix = '' THEN construct_name
                                 ELSE m.path_suffix END
                    WHEN m.path_suffix = '' AND m.path_fallback IS NOT NULL
                    THEN CASE
                         WHEN m.path_fallback = 'declaring_type_simple_name'
                              THEN declaring_simple_name
                         WHEN m.path_fallback = 'declaring_type_qualified_name'
                              THEN declaring_qualified_name
                         WHEN m.path_fallback = 'prefixed_capitalized_construct_name'
                              THEN coalesce(fp.prefix, '')
                                   || upper(substr(construct_name, 1, 1))
                                   || substr(construct_name, 2)
                         ELSE coalesce(list_extract(list_filter(list_transform(
                             m.path_fallback_prefixes,
                             x -> CASE WHEN starts_with(construct_name, x)
                                            AND length(construct_name) > length(x)
                                            AND regexp_matches(
                                                substr(construct_name, length(x) + 1, 1), '[A-Z]')
                                       THEN lower(substr(construct_name, length(x) + 1, 1))
                                            || substr(construct_name, length(x) + 2) END
                         ), v -> v IS NOT NULL), 1), construct_name) END
                    ELSE m.path_suffix END AS scoped_name,
        -- THE CONSTANT PREFIX ($path_prefix), joined onto the FRONT of the
        -- type-level prefix under the same seam rule the address seam below
        -- uses. It is a framework constant rather than anything an annotation
        -- states — a family whose whole surface is served under one fixed base
        -- has nothing on the declaration to read it from — so it cannot come
        -- through `prefixes`, which reads attributes off an annotation that
        -- was found on the type.
        --
        -- NULL for every catalog that declares none, which is every catalog
        -- written before this parameter: the first branch then reduces the
        -- expression to `coalesce(p.prefix, '')`, exactly what the seam below
        -- read before. `annotation_driven.py::_validate_naming` refuses a
        -- constant prefix declared without `$path_separator`, so the middle
        -- branch is reached only for a catalog that has one and whose
        -- type-level prefix is empty — the common case, since a framework
        -- with a fixed base rarely also carries a type-level prefix
        -- annotation.
        CASE WHEN cp.path_prefix IS NULL THEN coalesce(p.prefix, '')
             WHEN coalesce(p.prefix, '') = ''
             THEN cp.path_prefix
             ELSE rtrim(cp.path_prefix, cp.path_separator) || cp.path_separator
                  || ltrim(p.prefix, cp.path_separator) END AS type_prefix,
        -- THE PREFIX SEAM. What joins here, what does not, and why:
        --
        -- A catalog that declares `$path_separator` composes SEGMENTED
        -- addresses, where the two halves are written by two different
        -- authors who each decide independently whether to spell the
        -- separator. The framework joins them with EXACTLY ONE separator
        -- however they were written, so this dedupes the seam: strip the
        -- prefix's trailing separators and the remainder's leading ones,
        -- then join with one. A prefix `/api/gateway` and a suffix
        -- `owners/{ownerId}` compose `/api/gateway/owners/{ownerId}`, and a
        -- prefix `/` with a suffix `/chatclient` composes `/chatclient` —
        -- both real declarations, both derived as `/api/gatewayowners/
        -- {ownerId}` and `//chatclient` by the bare concatenation this
        -- replaces, and both found live against a real repository. An
        -- address nobody serves, published at `resolved`/`compiler` where
        -- nothing downstream can tell it from something observed, is the
        -- same confidently-wrong-address class `$path_fallback` closes from
        -- the other direction.
        --
        -- What does NOT join this way, and must not:
        --   * A catalog declaring NO `$path_separator` — every one written
        --     before this parameter, and every one whose address is an
        --     opaque name rather than a sequence of segments. That is the
        --     live reason the separator is opt-in rather than an engine
        --     default: a catalog whose type-level prefix is a broker
        --     destination NAME has nothing to join, and a separator
        --     inserted into one would invent a destination nobody serves.
        --   * The qualifier seam above, which joins with
        --     `$qualifier_separator` and dedupes nothing — a scope and a
        --     member are written by ONE author on ONE annotation, so
        --     neither half ever spells the separator and there is no seam
        --     to dedupe. The two seams stay separate expressions for that
        --     reason, not by accident.
        --
        -- An EMPTY half contributes nothing and takes no separator with it:
        -- an absent prefix leaves `scoped_name` exactly as written (so a
        -- bare `owners` stays `owners` rather than gaining a leading
        -- separator this engine would be inventing), and an empty
        -- `scoped_name` — the catalogs whose method-level annotation
        -- carries no path attribute at all — leaves the prefix alone.
        --
        -- F2 §3.5's relationship conjunct. `$class_level` says whether the two
        -- halves COMPOSE at all. Under `sibling` a member that names its own
        -- destination is its own registration and takes that address whole,
        -- never the type-level one in front of it.
        --
        -- WHICH frameworks that describes is catalog data and is deliberately
        -- not named here — the catalogs that declare `sibling` carry the
        -- measurement, and `scripts/probes/w14_listener_registration.md` carries
        -- the evidence. What this file needs to know is only the shape: where a
        -- type-level and a member-level declaration each name a destination and
        -- the two are independent registrations, composing them produces a third
        -- address that neither names and nothing serves, published at `resolved`.
        --
        -- A member naming NO destination still takes the type-level one under
        -- either value, which is what keeps the polymorphic-handler shape
        -- working: such a member carries no address, so both values agree, and
        -- they agree by construction rather than by a second rule.
        CASE WHEN cp.class_level = 'sibling' AND scoped_name <> ''
             THEN scoped_name
             WHEN type_prefix = '' OR scoped_name = ''
                  OR cp.path_separator IS NULL
             THEN type_prefix || scoped_name
             ELSE rtrim(type_prefix, cp.path_separator) || cp.path_separator
                  || ltrim(scoped_name, cp.path_separator) END AS composed,
        -- WHICH canonical answer this row takes, decided by the direction the
        -- row ACTUALLY has rather than the one the catalog declared. Both
        -- values are `domain/paths.py::serves_urls`, asked once per direction
        -- by the caller. A flipped row is server-side: an address recorded the
        -- way a client wrote it would be neither the URL the framework answers
        -- at nor the same string as the identical route a controller's own
        -- mapping derives, so the two would not merge (ruling R12). Equal to
        -- `$canonical_path` for every row that did not flip, which is every row
        -- of every catalog declaring no rule.
        CASE WHEN flipped THEN cp.flip_canonical_path ELSE cp.canonical_path END AS canonical,
        -- THE CANONICAL-ADDRESS GATE, wrapped around the whole seam above.
        -- `$canonical_path` says the composed address IS a URL this module
        -- serves rather than an address recorded as written, and the two
        -- rules it applies are the framework's own: one separator per
        -- boundary, and an address that omits its leading separator names the
        -- same thing as one that spells it (2O design §8, checkpoint CP-1 —
        -- confirmed live). Without it a mapping written `owners/{id}` and one
        -- written `/owners/{id}` were two identities for one URL, which
        -- splits dedup and splits every path-keyed anchor downstream.
        --
        -- The caller says false for a broker destination (a topic has no
        -- separators to normalize) AND for a CLIENT-side declaration (ruling
        -- R8): a client mapping without a leading separator resolves against
        -- its base address's path, while one with a leading separator is
        -- root-relative, so prefixing the first would rewrite an address
        -- rather than normalize a spelling.
        --
        -- The rules are stated HERE as well as in `domain/paths.py` because
        -- this address is composed from columns that layer never sees, and
        -- ARCHITECTURE §10 forbids this directory from importing a seam whose
        -- name is a protocol. It is a MIRROR, not a second rule — the
        -- `_destinations_of` precedent, one level down — and
        -- `tests/application/test_endpoints.py::
        -- test_the_sql_path_seam_answers_exactly_what_the_domain_seam_answers`
        -- runs both over one case table so the two cannot drift.
        --
        -- What the gate deliberately leaves alone, in EITHER direction: an
        -- address carrying a scheme or a placeholder is a whole address
        -- rather than a path half (D02 keeps those whole until the peer join
        -- splits them), and prefixing one would publish a URL nobody serves.
        -- BOTH expression notations, mirroring `domain/paths.py`'s own
        -- `_EXPRESSION_OPENS`: a rule that knew only `${` would rewrite an
        -- expression-language address into a URL nobody serves.
        CASE WHEN NOT canonical
                  OR contains(composed, '://')
                  OR contains(composed, '${') OR contains(composed, '#{')
             THEN composed
             WHEN composed = '' THEN '/'
             -- `regexp_replace(..., 'g')` is the collapse `domain/paths.py`
             -- spells as a repeated `replace`; both reduce any run of
             -- separators to one. A TRAILING separator survives both, and
             -- must: Framework 6 removed trailing-slash matching, so `/x/`
             -- and `/x` are different URLs (CP-1, row 6).
             ELSE CASE WHEN starts_with(regexp_replace(composed, '/+', '/', 'g'), '/')
                       THEN regexp_replace(composed, '/+', '/', 'g')
                       ELSE '/' || regexp_replace(composed, '/+', '/', 'g') END
             END AS path,
        -- The symbol lands by direction (D01 §3, amended): the server side
        -- handles, the client side calls, and a later merge may hold both.
        -- The ROW's direction, not the catalog's, so a flipped row lands its
        -- symbol on the side it actually took.
        --
        -- And a flipped row's handler is the symbol that HANDLES the
        -- declaration where one is known, which is not the declaring symbol:
        -- the declaration sits on the type the flip's condition was tested
        -- ABOUT, and what runs is the implementing type's own member. Where
        -- nothing overrides it, `coalesce` leaves the declaring symbol — the
        -- framework really does invoke the declared member there (CP-7 Q3),
        -- so that is the handler rather than a gap. `$flip_handlers` is empty
        -- for every catalog with no rule, so this reduces to `s.symbol`.
        CASE WHEN resolved_direction = 'outbound' THEN NULL
             ELSE coalesce(fh.handler, s.symbol) END AS handler,
        CASE WHEN resolved_direction = 'outbound' THEN s.symbol END AS caller,
        -- `peers.peer` ahead of `prefixes.peer` (CP-22 row 2, spec §3f): the
        -- two agree for every catalog whose `peer_annotation` defaults to its
        -- `prefix_annotation`, and `peers` is the one that reads MicroProfile
        -- REST Client's `@RegisterRestClient` row correctly.
        coalesce(pr.peer, p.peer) AS peer,
        s.signature AS handler_signature,
        -- The class serving the row: the type the prefix and the gate below are
        -- joined on, for the same reason — an inherited row runs its base's
        -- method and exists where its subclass's bean does (ruling 8).
        coalesce(m.gate_type, s.enclosing) AS served_by,
        -- THE UNRESOLVED-PATH GATE (2O Task 7 Step 1). Every row this CTE
        -- derives used to be stamped `resolved` unconditionally, which is a
        -- claim about the ADDRESS that the address itself can contradict: a
        -- destination the author wrote as an expression — a SpEL `#{…}`, a
        -- property `${…}` — is not a value anything here read, and publishing
        -- one at `resolved`/`compiler` presents the characters of the
        -- expression as an observed address (§8). The expression is carried in
        -- `path` VERBATIM (the gate above leaves it uncanonicalized for the
        -- same reason): unresolved is an answer, and the expression is the
        -- only true thing known about the address.
        --
        -- Nothing here RESOLVES the expression, and that is deliberate rather
        -- than a gap: the configuration ladder is a call-site mechanism this
        -- derivation never invokes, and its product is an expression rather
        -- than a value. The comment stops being true the day an
        -- annotation-derived row can read `resolved_config` — today only
        -- `resolve/engines/config_join.py:528` and
        -- `resolve/engines/derived_resource.py:578` read it at all.
        --
        -- Tested against `path`, not `composed`: the two are the same string
        -- for every expression-bearing address (the canonical gate hands one
        -- straight through), and reading the published column is what makes
        -- the claim "the address in this row is unknown" rather than "some
        -- fragment of it was".
        CASE WHEN contains(path, '${') OR contains(path, '#{')
             THEN 'unresolved' ELSE 'resolved' END AS resolution,
        'compiler'  AS evidence,
        m.catalog_id AS catalog_id,
        -- Raw per-row lists (evidence kind (a): mapping attributes) — still
        -- to be unioned and JSON-normalized below, per row group sharing a
        -- wire identity plus handler/caller/resolution/evidence/catalog_id.
        -- The method's own declaration first, the class's where the method
        -- made none (`prefixes` above says why that is coalesce, not union).
        -- `tm` (`type_media` above) is the third and last resort — the TYPE-
        -- level sibling default (Spec 2026-09-18 §3b word 2) — tried only
        -- where neither the method nor its own prefix annotation said anything.
        coalesce(m.consumes_list, p.consumes_list, tm.consumes_list) AS consumes_list,
        coalesce(m.produces_list, p.produces_list, tm.produces_list) AS produces_list
    FROM mappings m
    JOIN catalog_params cp ON cp.catalog_id = m.catalog_id
    -- A handler or caller is always a method. Without this, a TYPE-level
    -- mapping annotation (a prefix-carrying @HttpExchange, a class-level
    -- @RequestMapping) joins its own type symbol and, in a catalog with no
    -- type gate, mints one phantom endpoint per method in all_methods
    -- (pre-flight ruling R2). The inbound catalogs were protected only by
    -- their gate's enclosing-join; this names the real rule instead.
    -- A handler is a method OR a free function (D00 §4); the JVM extractor
    -- emits only 'method', which is what keeps this a no-op today.
    JOIN symbols s ON s.symbol = m.method_symbol AND s.construct_kind IN ('method', 'function')
    -- The enclosing type's own kind, read only so $declared_on can gate on
    -- it. A LEFT join because a free function has no enclosing type at all
    -- (D00 §4) and must keep deriving exactly as it did — which is also why
    -- the gate below tests the KIND rather than the join's success.
    -- `coalesce(m.gate_type, s.enclosing)` on all four, and on the fence
    -- below (`A-M15`): the type that ANNOTATED a declaration is the one whose
    -- scope, prefix and construct kind the row composes from, and for an
    -- INHERITED member that is not the type declaring it. Every catalog
    -- written before the member rule carries `gate_type` NULL, so the coalesce
    -- reads `s.enclosing` and nothing about them changes.
    LEFT JOIN symbols e ON e.symbol = coalesce(m.gate_type, s.enclosing)
    -- Every per-catalog lookup joins on `catalog_id` first: a controller,
    -- prefix, scope or flip one catalog found is not one another catalog's
    -- row may read, or a gateless catalog in the batch would inherit a gated
    -- neighbour's controllers.
    LEFT JOIN controllers c ON c.catalog_id = m.catalog_id
           AND coalesce(m.gate_type, s.enclosing) = c.type_symbol
    LEFT JOIN prefixes p ON p.catalog_id = m.catalog_id
           AND p.type_symbol = coalesce(m.gate_type, s.enclosing)
    -- CP-22 row 2 (spec §3f): `peers`'s own row for this type, read off
    -- `$peer_annotation` rather than `$prefix_annotation` — see `peers`'s own
    -- comment for why the two agree for every catalog but this group's new one.
    LEFT JOIN peers pr ON pr.catalog_id = m.catalog_id
           AND pr.type_symbol = coalesce(m.gate_type, s.enclosing)
    -- Spec 2026-09-22 §2b: the prefix the third fallback word composes, read
    -- off the DECLARING type — the same key every join here uses, so the word
    -- reads the prefix of the type whose name the other two words publish
    -- rather than of whatever type happens to hold the handler. Empty for
    -- every catalog that declares no `$fallback_prefix_attr`.
    LEFT JOIN fallback_prefixes fp ON fp.catalog_id = m.catalog_id
           AND fp.type_symbol = coalesce(m.gate_type, s.enclosing)
    -- `type_media` only ever matches a TYPE symbol because the join key is the
    -- enclosing type; a method-level `@Produces` row in `annotations_effective`
    -- has a method target and never joins here.
    LEFT JOIN type_media tm ON tm.catalog_id = m.catalog_id
           AND tm.type_symbol = coalesce(m.gate_type, s.enclosing)
    LEFT JOIN qualifier_scopes q ON q.catalog_id = m.catalog_id
           AND q.type_symbol = coalesce(m.gate_type, s.enclosing)
    -- D02 §2c's two flip lookups, both keyed on the BARE descriptor for
    -- `$locally_implemented`'s reason: the type this declaration sits on and
    -- the class implementing it are prefixed by whichever module's scan wrote
    -- them, and only the descriptor is ever compared (D00 §5a).
    LEFT JOIN flip_owners fl ON fl.catalog_id = m.catalog_id
           AND fl.owner = regexp_extract(coalesce(m.gate_type, s.enclosing), '[^ ]*$')
    LEFT JOIN flip_handlers fh ON fh.catalog_id = m.catalog_id
           AND fh.declaration = regexp_extract(s.symbol, '[^ ]*$')
    WHERE (cp.type_annotation IS NULL OR c.type_symbol IS NOT NULL)
      AND (cp.declared_on IS NULL OR e.construct_kind = cp.declared_on)
      -- THE IMPLEMENTED-INTERFACE FENCE (2I design §4). An outbound catalog
      -- reading INTERFACE declarations is describing a client stub — a
      -- declaration whose whole content is "somebody else answers this". An
      -- interface THIS MODULE IMPLEMENTS is the opposite claim: the module
      -- answers it. One annotation family can mark both, because a generated
      -- stub and a hand-written interface a local class serves are annotated
      -- identically. Without this, such a pair derives an outbound row here
      -- and an inbound row from its implementing class, the two merge (D02
      -- §3), and the module is published as CALLING an operation it only
      -- serves.
      --
      -- Not new vocabulary — it is what `declared_on: interface` on an
      -- outbound catalog already MEANS, made true. The operation still derives
      -- exactly once, from the implementing class, because a class-gated
      -- inbound catalog is untouched by this.
      --
      -- SCOPED to a catalog that declares the interface gate, and deliberately
      -- not to every outbound catalog. Some client frameworks let a client
      -- interface name a local FALLBACK class that implements it — the thing
      -- that runs when the call fails, never the thing answering it — and the
      -- interface there is still a client. Widening this to every outbound row
      -- would silently delete every such client. Which catalogs make the
      -- stub claim is catalog data, and `declared_on` is where they make it.
      --
      -- IT YIELDS TO THE FLIP (D02 §2c, ruling R12). The fence and the
      -- direction resolution answer the same question about the same row and
      -- give opposite answers, and the fence's is the coarser one: it subtracts
      -- because SOMETHING in the module implements the interface, while the
      -- resolution asks whether that something is what the framework actually
      -- dispatches to. Where the finer condition holds, the row is not deleted
      -- — it becomes the inbound row, handler and all — and shipping both
      -- unconditioned yields no inbound rows at all, which is exactly the
      -- cancellation spec §6 warns of. Where it does NOT hold, the fence
      -- stands: an interface implemented by something the framework serves
      -- nothing through is neither called by this module nor served by it.
      AND NOT (
          cp.direction = 'outbound' AND cp.declared_on = 'interface'
          AND fl.owner IS NULL
          AND list_contains(cp.locally_implemented,
                            regexp_extract(coalesce(m.gate_type, s.enclosing), '[^ ]*$'))
      )
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
-- explicitly would be these same twelve: protocol, direction, method, path,
-- handler, caller, peer, handler_signature, resolution, evidence, catalog_id,
-- served_by. `served_by` follows `handler` for every row but an inherited one,
-- so it splits nothing a handler did not already split.
unioned AS (
    SELECT protocol, direction, method, path, handler, caller, peer,
           handler_signature, resolution, evidence, catalog_id, served_by,
           CASE WHEN count(consumes_list) = 0 THEN NULL
                ELSE to_json(list_sort(list_distinct(flatten(list(consumes_list)
                     FILTER (WHERE consumes_list IS NOT NULL))))) END AS consumes,
           CASE WHEN count(produces_list) = 0 THEN NULL
                ELSE to_json(list_sort(list_distinct(flatten(list(produces_list)
                     FILTER (WHERE produces_list IS NOT NULL))))) END AS produces
    FROM derived
    GROUP BY ALL
)
SELECT protocol, direction, method, path, handler, caller, peer,
       handler_signature, resolution, evidence, catalog_id, consumes, produces, served_by
FROM unioned d
-- THE ADDRESSES-NOTHING GATE (2O Task 7 Step 4; rewritten by the principles
-- sweep's mechanism 3, §4 and §7.7). An empty address is not a destination:
-- nothing subscribes to it and nothing publishes to it, so a row carrying one
-- and nothing else that names an endpoint is an endpoint addressing nothing,
-- published at `resolved`/`compiler` where nothing downstream can tell it from
-- an observation. Silence is the honest answer, and it is the answer the same
-- WHERE clause already gives a declaration whose scope was never found.
--
-- **What this gate used to ask, and why it was the wrong question.** It read
-- `NOT ($path_separator IS NULL AND d.path = '')` — it fired only for a
-- catalog that declared NO separator. `$path_separator` is a FORMATTING
-- property: it says how two halves of an address are joined, and nothing at
-- all about whether the empty address means something. Keying a validity gate
-- on it is the same substitution as matching a method by argument count, and
-- it had the same result: an AMQP broker catalog was protected because an
-- exchange name has no slashes in it, while its structural twin — the same
-- shape, on a protocol whose destinations ARE slash-separated — declared a
-- separator to compose them and switched its own validity gate off in the same
-- line. Seven shipped catalogs declared one and were all unguarded; three had
-- a reachable bare-annotation path and fabricated (`A-C1`), and the other four
-- were safe by luck.
--
-- **What it asks now.** Whether anything in the row names an endpoint at all.
-- Two things can, and the second is not the path:
--   * The address itself, once the protocol has had its say. For the one
--     protocol where the empty address IS real — an inbound HTTP root route,
--     CP-1 row 5, a class prefix with an empty method mapping — the
--     canonical-address gate above has already spelled it `/` by the time this
--     runs, because `$canonical_path` is exactly `domain/paths.py::serves_urls`.
--     So `d.path = ''` here means the protocol had nothing to say, never that
--     the root route was dropped.
--   * A resolved `peer`. A client declaration whose type-level annotation names
--     the service but neither half names a path is a call to that service's
--     base address — real, and exactly one shipped catalog declares a
--     `peer_from` at all. Dropping it would trade `A-C1`'s fabrication for an
--     under-report.
--
-- Two real shapes reach the drop, both boundaries a catalog states rather than
-- reads: a member-level handler annotation that names no destination of its
-- own sitting outside the class-level annotation that would have named one,
-- and a listener that declares its destination only through NESTED
-- annotations, whose arguments no catalog reads yet.
--
-- This stops being right the day a protocol arrives for which the empty
-- address is a real destination AND the row carries no peer to say so — at
-- which point the answer belongs in `domain/paths.py` beside `serves_urls`,
-- which is where the protocol question already lives, rather than here.
WHERE NOT (d.path = '' AND d.peer IS NULL);
-- The earlier-catalog-wins guard — `NOT EXISTS (SELECT 1 FROM endpoints
-- existing WHERE … same wire identity)` — used to close this statement. It is
-- `insert_endpoints.sql` now, asked per catalog at that catalog's own turn in
-- the order (see the header): a candidate row is refused there exactly when a
-- row minted before that turn, by any engine, already carries its identity.
