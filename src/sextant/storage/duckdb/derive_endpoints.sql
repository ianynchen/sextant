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
--   $mapping_annotations -- list of {fqn, methods, requires_qualifier,
--                           unless_attribute, unless_equals} rows: one per
--                           mapping annotation. `methods` holds the methods
--                           that annotation pre-sets, or NULL where it pre-sets
--                           none; the `unless_*` pair names the attribute whose
--                           value makes the rule derive NOTHING (2I design §2,
--                           word 4), both NULL where it withdraws nothing.
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
--   $members             -- 2I design §2, word 3: what a GATED CLASS exposes
--                           on its own, with no member-level annotation
--                           anywhere, or NULL where a catalog declares no such
--                           rule (every catalog whose framework exposes only
--                           what an annotation marks). Today's one word is
--                           'public_methods'. A member-level rule OVERRIDES
--                           this for the member it names — one row per member,
--                           never two — and $path_fallback is required beside
--                           it, since a member carries no name attribute at
--                           all (`annotation_driven.py::_validate_naming`).
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
           coalesce(s.requires_qualifier, FALSE) AS requires_qualifier,
           -- 2I design §2, word 4: the attribute whose value withdraws this
           -- rule, and that value as TEXT — the one representation `json ->>`
           -- reads every scalar back as, so a catalog's YAML boolean and a
           -- bytecode JSON boolean compare without either side guessing at the
           -- other's type. Both NULL where the rule withdraws nothing.
           s.unless_attribute AS unless_attribute,
           s.unless_equals AS unless_equals
    FROM (SELECT UNNEST(
        $mapping_annotations::STRUCT(
            fqn VARCHAR, methods VARCHAR[], requires_qualifier BOOLEAN,
            unless_attribute VARCHAR, unless_equals VARCHAR
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
    -- THE WITHDRAWAL FILTER (2I design §2, word 4). A declaration whose named
    -- attribute carries the withdrawing value derives NOTHING: the framework
    -- itself does not expose it, so a row here would be an endpoint nobody
    -- serves, published at `resolved`/`compiler` where nothing downstream can
    -- tell it from an observation.
    --
    -- `IS DISTINCT FROM` rather than `<>`, and that is the whole rule for an
    -- ABSENT attribute: an annotation's declared default is never written into
    -- the class file (Phase 2I Task 2 checkpoint item 4), so the attribute
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
-- same one rather than `controllers`: `$type_annotation` is a single fqn, and
-- a framework whose gate has TWO spellings (one library renamed, both still in
-- the wild) cannot be named by it — `mapping.annotations` is a list, so it
-- can. Where a catalog declares `$type_annotation` as well, `derived`'s own
-- existing gate filter applies to these rows exactly as it does to every
-- other, so the narrower gate still wins with no second rule here.
--
-- DISTINCT because a type carrying two of the catalog's annotations is one
-- gated class, not two: without it a class annotated with both spellings at
-- once would enumerate each of its members twice.
gate_types AS (
    SELECT DISTINCT a.target AS type_symbol
    FROM annotations_effective a
    JOIN mapping_catalog mc ON mc.fqn = a.annotation
),
-- THE MEMBER RULE (2I design §2, word 3). Where a catalog declares
-- `$members`, a gated class exposes members that carry no annotation at all,
-- and each becomes a declaration with an empty name — which `$path_fallback`
-- (required beside `$members` by `annotation_driven.py::_validate_naming`)
-- then answers with the member's own name.
--
-- WHAT IS NOT A MEMBER, and why each exclusion is a fact rather than a taste:
--   * A CONSTRUCTOR. `construct_kind` tells it apart from a method outright
--     (D00's closed set), and `derived`'s own join already admits only
--     'method'/'function'; naming it here as well says the member rule
--     intends the exclusion rather than inheriting it by luck.
--   * A STATIC method. It is bound to the type, not to an instance, so it is
--     not a member of the exposed object at all — the same distinction
--     `modifiers.static` already draws for a field that reaches no payload.
--   * A SYNTHETIC method — a covariant-return bridge, a lambda body, an
--     accessor minted for a nested class. Nobody wrote it, so there is no
--     declaration to expose. Unlike fields, synthetic METHODS do reach the
--     fact stream on purpose (the inheritance walk's bridge rule needs to see
--     them), which is exactly why this has to say so.
--   * A NON-PUBLIC method: not callable from outside the type, so not
--     exposed. This is the one exclusion the word itself names.
-- `coalesce(..., 'false')` on both modifiers for the reason D00 §5a states:
-- a scanner that does not report a modifier is not asserting the modifier is
-- true, and each reader supplies its own default.
--
-- AND THE OVERRIDE. A member that carries ANY of this catalog's mapping
-- annotations is left entirely to that rule — one row per member, never two.
-- The anti-join is against `annotations_effective`, NOT against `declared`,
-- and the difference is the whole of the interaction with word 4: a
-- declaration the withdrawal filter removed from `declared` is still an
-- ANNOTATED declaration, so the member rule must not quietly re-derive the
-- very row the framework withdrew. Joining `declared` instead would have
-- turned every `unless` into a no-op on a gated class.
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
--   annotated declaration. Every catalog declaring `members` today is
--   verbless (`all_methods: []`), which is what makes each member ONE row;
--   a future one with a non-empty `$all_methods` would fan every member
--   across every verb in that list. That may well be right for a framework
--   whose exposed members really do answer several verbs — but it has never
--   been exercised, so it is untested behaviour rather than a decision.
member_declarations AS (
    SELECT
        s.symbol AS target,
        [''] AS paths,
        $all_methods::VARCHAR[] AS methods,
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
        (SELECT coalesce(bool_or(requires_qualifier), FALSE) FROM mapping_catalog)
            AS requires_qualifier
    FROM symbols s
    JOIN gate_types g ON g.type_symbol = s.enclosing
    WHERE $members = 'public_methods'
      AND s.construct_kind = 'method'
      AND s.visibility = 'public'
      AND coalesce(s.modifiers ->> 'static', 'false') <> 'true'
      AND coalesce(s.modifiers ->> 'synthetic', 'false') <> 'true'
      AND NOT EXISTS (
          SELECT 1 FROM annotations_effective a
          JOIN mapping_catalog mc ON mc.fqn = a.annotation
          WHERE a.target = s.symbol
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
        a.target AS type_symbol,
        coalesce(
            list_extract(list_filter(list_transform(
                $qualifier_from::VARCHAR[],
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
            CASE WHEN $namespace_template IS NOT NULL
                      AND regexp_extract(a.target, '([^ ]*)/[^/ ]*#$', 1) <> ''
                 THEN printf($namespace_template, array_to_string(list_reverse(str_split(
                          regexp_extract(a.target, '([^ ]*)/[^/ ]*#$', 1), '/'
                      )), '.'))
            END
        ) AS qualifier
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
    FROM (SELECT * FROM declared UNION ALL SELECT * FROM member_declarations) d
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
        CASE WHEN coalesce(m.qualifier, q.qualifier) IS NOT NULL
             THEN CASE WHEN $qualifier_format = 'qname'
                       THEN '{' || coalesce(m.qualifier, q.qualifier) || '}'
                       ELSE coalesce(m.qualifier, q.qualifier) || $qualifier_separator END
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
                    ELSE m.path_suffix END AS scoped_name,
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
        CASE WHEN coalesce(p.prefix, '') = '' OR scoped_name = ''
                  OR $path_separator IS NULL
             THEN coalesce(p.prefix, '') || scoped_name
             ELSE rtrim(p.prefix, $path_separator) || $path_separator
                  || ltrim(scoped_name, $path_separator) END AS path,
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
    -- The enclosing type's own kind, read only so $declared_on can gate on
    -- it. A LEFT join because a free function has no enclosing type at all
    -- (D00 §4) and must keep deriving exactly as it did — which is also why
    -- the gate below tests the KIND rather than the join's success.
    LEFT JOIN symbols e ON e.symbol = s.enclosing
    LEFT JOIN controllers c ON s.enclosing = c.type_symbol
    LEFT JOIN prefixes p ON p.type_symbol = s.enclosing
    LEFT JOIN qualifier_scopes q ON q.type_symbol = s.enclosing
    WHERE ($type_annotation IS NULL OR c.type_symbol IS NOT NULL)
      AND ($declared_on IS NULL OR e.construct_kind = $declared_on)
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
      AND NOT (
          $direction = 'outbound' AND $declared_on = 'interface'
          AND list_contains($locally_implemented::VARCHAR[],
                            regexp_extract(s.enclosing, '[^ ]*$'))
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
