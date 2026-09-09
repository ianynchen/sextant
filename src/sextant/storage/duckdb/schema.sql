CREATE TABLE IF NOT EXISTS raw_facts (
    kind        TEXT,
    document_id TEXT,
    payload     JSON
);

-- Pre-declared so the "endpoints" query always succeeds, even when every
-- catalog is skipped by capability gating and derive_endpoints.sql never
-- runs (D02 §2, M04): a weaker scanner must degrade visibly via
-- skipped_catalogs, not crash. derive_endpoints.sql still replaces this
-- table whole via CREATE OR REPLACE TABLE whenever at least one catalog runs.
CREATE TABLE IF NOT EXISTS endpoints (
    protocol          TEXT,
    direction         TEXT,
    method            TEXT,
    path              TEXT,
    handler           TEXT,
    handler_signature JSON,
    -- The client-side method symbol (D01 §3, amended this phase): an
    -- outbound row carries `caller` with `handler` NULL; a `both` row keeps
    -- both. `peer` is the declared target hint — a service name or a literal
    -- authority — that the system tier later resolves to a participant; NULL
    -- where the base address lives in builder code the annotations never see.
    caller            TEXT,
    peer              TEXT,
    resolution        TEXT,
    evidence          TEXT,
    -- The id of the catalog that derived this row (2E-prep design §1a):
    -- provenance for rule scoping, never part of wire identity, never
    -- compared across services.
    catalog_id        TEXT,
    request_shape     TEXT,
    response_shape    TEXT,
    -- JSON arrays of MIME strings, or NULL where no declaration is
    -- derivable from any evidence source (2E design §4): carried data,
    -- never identity — dedup and merge never compare these two columns.
    consumes          TEXT,
    produces          TEXT,
    -- What is on this channel's wire, and how much the answer is worth (2G
    -- design §4, §5). Both are stamped by one late pass over every row
    -- (`resolve/format.py`), never by a derivation: `format` is one of D00's
    -- format values or NULL, and `format_resolution` is the same resolution
    -- set every other column uses — `resolved` where declared evidence named
    -- the wire outright, `narrowed` where only a framework default or the
    -- payload's own type suggested it, `unresolved` where nothing did.
    -- As the ladder writes them, `format` is NULL exactly when
    -- `format_resolution` is `unresolved`. **One statement breaks that pair
    -- on purpose**: merge_endpoints.sql keeps the surviving row's format
    -- while taking the WEAKER of the two halves' markers, so a merged row
    -- may read (`protobuf`, `unresolved`) — "this is the format one
    -- direction declared, and this identity as a whole is not settled",
    -- which is the honest reading of one wire whose two halves were not
    -- equally observable. A reader must therefore treat
    -- `format_resolution` as the authority on trust and `format` as an
    -- answer that may still be worth showing beside it. **That branch has
    -- no live surface today** (merge_endpoints.sql's own header): the merge
    -- is the last statement of `derive_endpoints` and the ladder is the last
    -- pass of a resolve, so both columns are still NULL when the merge runs
    -- and the ladder answers every row afterwards — the pair holds on every
    -- live row, and the exception becomes reachable only if a later phase
    -- stamps a format before the merge.
    format            TEXT,
    format_resolution TEXT
);

-- Pre-declared for the same reason as `endpoints` above: a scanner too weak
-- to populate shapes must still answer the "shapes"/"shape_fields" query
-- with an empty result, not an error, and degrade visibly through
-- skipped_catalogs instead. Tasks 9-11 replace these whole via CREATE OR
-- REPLACE TABLE once shape derivation runs.
CREATE TABLE IF NOT EXISTS shapes (
    shape_id     TEXT,
    content_hash TEXT,
    open         BOOLEAN
);

CREATE TABLE IF NOT EXISTS shape_fields (
    shape_id    TEXT,
    ordinal     INTEGER,
    wire_name   TEXT,
    -- The schema's own field number (protobuf) — NULL for a format with none
    -- (Avro) and for every bytecode-derived (annotation/reflection) shape,
    -- which never carries one at all (2G design §3, Task 5).
    field_number INTEGER,
    wire_type   TEXT,
    wire_format TEXT,
    required    BOOLEAN,
    nullable    BOOLEAN,
    resolution  TEXT,
    evidence    TEXT,
    tags        JSON,
    -- The recursive descriptor {wire_type, wire_format, nullable, shape_id?,
    -- item?} for a collection's element (array) or value (map) type — NULL
    -- for a scalar field. A single wire_type cannot distinguish
    -- List<String> from List<CustomerRef>; without item, DR-5 would match a
    -- caller sending an array of strings against a callee expecting an
    -- array of records (D01 §3 Contracts).
    item        JSON
);

-- Pre-declared for the same reason as `endpoints`/`shapes` above: M04 pass 2
-- (`resolve/config.py`) must answer the "resolved_config" query with an
-- empty result, not an error, when no catalog declares a config_model or no
-- config file was read (2F design §2). `resolve_config` replaces it whole
-- via resolved_config_reset.sql + insert_resolved_config.sql once per
-- resolve — unconditionally, so an empty resolve still leaves an empty
-- table rather than a stale previous run's rows.
CREATE TABLE IF NOT EXISTS resolved_config (
    key               TEXT,
    value             TEXT,
    -- The file that won precedence for this key in this profile's layering
    -- (D02 §2i's config_model) — NULL only when the key was never declared
    -- for this environment at all, so no file ever won it (D01).
    source            TEXT,
    environment       TEXT,
    -- NULL exactly when `value` is non-NULL. One of D01's closed five-value
    -- set (`missing_key`, `environment`, `remote_source`,
    -- `placeholder_cycle`, `multi_placeholder`) — the last reserved for the
    -- peer-resolution join, never emitted by this pass.
    unresolved_reason TEXT
);

-- The 2K hand-off ledger (2G design §6): one row per question a programmatic
-- pass could not answer and refused to guess at. Pre-declared empty for the
-- same reason `endpoints`/`shapes`/`resolved_config` above are — the
-- "open_questions" query must answer with an empty result, never an error,
-- on a run where no pass had anything to ask.
--
-- Replaced WHOLE per resolve through reset_open_questions.sql +
-- insert_open_questions.sql, and the reset runs once, in the pipeline, ahead
-- of every writer rather than inside one of them: MORE THAN ONE pass writes
-- here (the format ladder's `format_conflict`, the parse-binding pass's
-- `payload_binding`), so a reset owned by either would erase the other's
-- rows depending on which ran first.
--
-- Programmatic passes never READ this table (2G design §6): it is a hand-off
-- to 2K's enrichment seat, not an input, and a pass that read its own
-- unanswered questions back would be answering them.
CREATE TABLE IF NOT EXISTS open_questions (
    -- The endpoint's wire identity (D01 §3), carried rather than joined: the
    -- row is an artifact a human and 2K read, and a foreign key into a table
    -- that is rebuilt every resolve would name nothing outside this run.
    protocol   TEXT,
    method     TEXT,
    path       TEXT,
    -- One of the closed set `payload_binding`, `format_conflict`,
    -- `channel_destination`, `service_identity`, `environment_divergence`,
    -- `binder_protocol`, `unselected_binding`, `handler_protocol`,
    -- `registration_activation`
    -- (2G design §6, extended by 2O design §0, F2 §3.4, F2 §3.6 and `OI-64`) — checked in
    -- `resolve/open_questions.py`, which owns the set and refuses anything
    -- outside it. This comment named the original TWO until 2O Task 9, which
    -- shipped the writer `channel_destination` had been waiting for; the
    -- other two gained theirs earlier in the same phase.
    question   TEXT,
    -- The answers that were on the table, as a JSON array — each carrying
    -- what it would have made the format or payload type, where it was seen,
    -- and why no rung could choose it. Sorted by the pass that writes it, so
    -- two runs produce the same bytes (NFR-1).
    candidates JSON,
    -- The evidence TRAIL, in prose: which columns and configuration keys the
    -- pass actually read to reach the impasse. Deliberately NOT one of D00's
    -- closed evidence tiers — an unanswered question has no tier, and the
    -- reader of this table needs to know where to look, not how much to
    -- trust an answer nobody gave.
    evidence   TEXT
);

-- The first of the two NON-WIRE tables (2O design §4): work the framework
-- starts on a clock rather than on a request. It is its own table and not a
-- row in `endpoints` because `endpoints` is wire-true (user ruling) — a
-- scheduled method serves no protocol, no address and no direction, and a row
-- claiming any of the three would be an invented boundary.
--
-- Pre-declared empty for the same reason `endpoints`/`shapes`/
-- `resolved_config`/`open_questions` above are: the "scheduled_work" query
-- must answer with an empty result, never an error, on a module that
-- schedules nothing or a scan too weak to see it.
--
-- Replaced WHOLE per resolve through reset_scheduled_work.sql +
-- insert_scheduled_work.sql, and the reset runs once, in the pipeline, ahead
-- of every writer rather than inside the engine — `derive_endpoints`'s own
-- reason (`resolve/endpoints.py`): 2O design §4a promises "Quartz: later
-- catalog, same table", so more than one catalog will write here and a reset
-- owned by the engine would leave only whichever ran last.
CREATE TABLE IF NOT EXISTS scheduled_work (
    -- The scheduled method's own symbol (D00 §5a), module coordinates
    -- included, exactly as the annotation's target names it.
    handler    TEXT,
    -- Which KIND of schedule the declaration names, as the catalog's own
    -- `triggers` map spells it — `cron`, `fixedRate` or `fixedDelay` today.
    -- Catalog vocabulary rather than a D00 closed set: the framework owns the
    -- word, so it lives in the catalog file with every other framework name
    -- (D02's "there is no `if spring` anywhere in Sextant").
    trigger    TEXT,
    -- The trigger's declared expression, VERBATIM (2O design §4a) — the cron
    -- string, or the delay/rate as it was written. Never normalised, never
    -- evaluated: a `${...}` placeholder is preserved exactly as declared and
    -- `resolution` says `unresolved` beside it.
    expression TEXT,
    -- D00's resolution set. `resolved` where the expression is the literal the
    -- framework will schedule on; `unresolved` where it is a property
    -- placeholder this analysis did not substitute (COVERAGE names the
    -- boundary). NULL never appears here — a row with no expression at all is
    -- not derived.
    resolution TEXT,
    -- D00's evidence set. Always `compiler`: every column above is read off
    -- the annotation the compiler wrote into the class file.
    evidence   TEXT,
    -- The id of the catalog that derived this row — provenance, exactly as
    -- `endpoints.catalog_id` is, and for the same reason: rule scoping, never
    -- identity.
    catalog_id TEXT
);

-- The second non-wire table (2O design §4b): which exceptions a module answers
-- and how. Its own table for the same reason `scheduled_work` is — an error
-- handler is not a boundary anyone can address, it is what happens INSIDE one
-- that already exists — and pre-declared empty for the same reason too.
--
-- Replaced WHOLE per resolve through reset_error_handlers.sql +
-- insert_error_handlers.sql, reset from the pipeline, exactly as above.
CREATE TABLE IF NOT EXISTS error_handlers (
    -- The handler method's own symbol (D00 §5a).
    handler       TEXT,
    -- The type that DECLARES the handler — an advice class, or the controller
    -- whose own handlers are scoped to itself (Spring's own rule, mirrored in
    -- `resolve/engines/error_advice.py`).
    advice        TEXT,
    -- The class-level annotation that made `advice` a handler container, as
    -- the facts spell it. It is what tells the two containers apart, and the
    -- distinction is load-bearing: an advice class declaring NO scope
    -- attributes applies to every controller in the application, while a
    -- controller's own handler applies to that controller alone. A single
    -- NULL `scope` cannot say which of those two a row is.
    declared_by   TEXT,
    -- The advice's scope attributes, VERBATIM, as a JSON object holding only
    -- the keys the declaration actually wrote (`annotations`, `basePackages`,
    -- `assignableTypes` — whichever the catalog names and the declaration
    -- carries). NULL where the declaration writes none, which for an advice
    -- class means "every controller" and for a controller means "this one".
    scope         JSON,
    -- One exception type per row, as its own symbol. A handler naming three
    -- types is three rows: each is a distinct, separately answerable fact, and
    -- an array in one cell cannot be joined against anything.
    exception     TEXT,
    -- The status the declaration names, verbatim as the literal was read — an
    -- enum reference stays the symbol the facts carry. NULL where no
    -- `@ResponseStatus` was found on the handler or on the exception class,
    -- and NULL is an answer: a status computed inside a `ResponseEntity` body
    -- is a STATED BOUNDARY of this phase (2O design §4b), not a gap this
    -- column fills in.
    status        TEXT,
    -- The symbol of the type the handler returns, where the return type names
    -- one — NULL for a handler returning nothing, and NULL for one whose
    -- return type is a framework envelope the catalog declares no wrapper for.
    response_shape TEXT,
    -- D00's resolution and evidence sets, as `scheduled_work` above.
    resolution    TEXT,
    evidence      TEXT,
    catalog_id    TEXT
);

-- 2Q `G3`: the one link a value chain was missing, and the only one that
-- crosses a method boundary (D01 §3).
--
-- Within a method the chain is already complete — a `call_site` carries the
-- value id its call produced (`result`) and every argument carries the
-- `source` id of the call that produced it — so
-- `OmsOrderService#list -> CommonPage#restPage -> CommonResult#success` is
-- three facts today. What nothing said is where the FIRST of those values came
-- from: the caller knows `OmsOrderService#list` produced value 7, and not that
-- 7 is whatever `OmsOrderServiceImpl#list` hands back. One row here is exactly
-- that sentence.
--
-- **Derived, never a fact.** Every column is read off `call_sites`,
-- `method_returns` and the type hierarchy the symbol facts carry; nothing is
-- inferred from a name and nothing is evaluated. It is a table rather than a
-- view because the join is arithmetic (a SHA-256 of the callee's JVM
-- descriptor) and a bounded hierarchy walk, neither of which belongs in SQL.
--
-- **Absence is the third-party boundary, and it is the common case.** A call
-- whose callee this workspace never scanned — a MyBatis mapper, a Spring Data
-- repository, a JDBC driver, anything in the JDK — contributes NO row, because
-- the trace stops there by ruling and a row would claim a body we cannot read.
-- Measured on `macrozheng/mall`'s `mall-admin`: 1,411 of 2,065 value-producing
-- call sites are exactly that.
CREATE TABLE IF NOT EXISTS return_flows (
    -- The method containing the call site, module-prefixed exactly as
    -- `call_sites.caller` spells it (D00 §5a).
    caller         TEXT,
    -- The call site's own control-flow position within `caller` — `caller`
    -- plus `ordinal` is the site's identity, the same pair `call_sites` uses.
    ordinal        INTEGER,
    -- The value id, IN THE CALLER, that this call produced: `call_sites.result`
    -- verbatim. It is what an argument of a later call in the same method
    -- carries as its `source`, which is what makes the chain continue.
    result         INTEGER,
    -- The method whose return this row carries, module-prefixed like `caller`
    -- and like `method_returns.method`. It is the DECLARED callee for a call
    -- the JVM dispatches exactly, and an implementation of it where the JVM
    -- dispatches virtually.
    callee         TEXT,
    -- Which of `callee`'s return instructions this row is —
    -- `method_returns.ordinal` verbatim. A method with two `return` statements
    -- contributes two rows: two possible answers and no single one, exactly as
    -- the fact kind models it. Collapsing them would state a fact about code
    -- that may never run.
    return_ordinal INTEGER,
    -- What `callee` hands back at that return, as D00 §5's argument grammar
    -- wrote it — verbatim JSON, carried rather than flattened. A `source` in
    -- here is a value id in the CALLEE, so a reader that wants the next hop
    -- joins it against that callee's own `call_sites`, never against the
    -- caller's: D00 §5's value ids are meaningless across methods, and this
    -- table is the only thing licensed to cross that line.
    value          JSON,
    -- D00 §4's resolution set, describing the SITE rather than this candidate
    -- (D01 §3's dispatch rule: the tier lives on the site and does not rank
    -- candidates against one another). `resolved` where exactly one method can
    -- run — a static or special call, or a virtual one with a single
    -- candidate; `narrowed` where several can, every one of them listed and
    -- none picked.
    resolution     TEXT,
    -- D00 §4's evidence set. Always `compiler`: the call site, the return, the
    -- descriptors and the hierarchy are all what the compiler wrote into the
    -- class files.
    evidence       TEXT
);

-- 2Q `I1`: the set a trace starts FROM (D01 §3). One row per (method, kind,
-- wire address).
--
-- D00 §4 has documented a `root_kind` set since the fact schema was written
-- and nothing produced it, which is why the two non-wire tables above carry
-- the note that they "feed no root set" — an inbound row and a scheduled row
-- were equally the start of some work and only one of them was ever traced
-- from. This table is that set, made real, and it is what lets a traversal
-- take a ROOT rather than an endpoint handler: the same walk runs from work
-- the framework starts on a clock as from work a request starts, because
-- nothing in it branches on the kind.
--
-- **It carries no trust columns, deliberately.** A row says one thing — this
-- method is where a trace of this kind begins — and every claim underneath it
-- (which address is served, which schedule declares it, how well either
-- resolved) already lives on the row that named the handler. Copying a
-- `resolution` or an `evidence` here would put one claim in two places with
-- nothing keeping the two equal, which is the rule D01 §6 states as "no fact
-- that was merely copied".
--
-- **One ROOT per (handler, kind); one ROW per address that reaches it**
-- (2Q close, defect 1). A method serving three paths is still one root — the
-- walk that runs from it is the same walk whichever address invoked it, and
-- `roots_of` collapses these rows back to one `Root` carrying all of them, so
-- the traversal sees one root and produces one trace. The rows are per address
-- because the address is the only name a READER has for a trace: a document
-- naming a trace by its handler descriptor alone can be searched for
-- `GET /order/list` and answer nothing, which is what shipped and what this
-- column set closes. A root nothing addresses — a scheduled job — is one row
-- with all three NULL, which is an honest absence rather than an invented
-- label.
--
-- **The wire columns are carried, not the trust columns.** `protocol`,
-- `method` and `path` say WHICH address reaches this root; `resolution` and
-- `evidence` would say how well the row that named it resolved, and every such
-- claim already lives on the `endpoints` row, with nothing keeping two copies
-- equal (D01 §6's "no fact that was merely copied"). The distinction is that
-- an address is this row's own identity while a trust column is a judgement
-- about a different row — and both halves are written by ONE pass from ONE
-- read of `endpoints`, replaced whole, so the addresses cannot drift from the
-- rows they came from within a workspace.
--
-- Replaced WHOLE per resolve through reset_roots.sql + insert_roots.sql, and
-- BOTH run from the one pass that writes here — the return_flows discipline
-- rather than the scheduled_work one, because there is exactly one writer.
-- Pre-declared empty like every table above it, so the "roots" query answers
-- with an empty result rather than an error on a module that exposes nothing.
CREATE TABLE IF NOT EXISTS roots (
    -- The method a trace starts at, module-prefixed exactly as the row that
    -- named it spells it (D00 §5a) — `endpoints.handler` or
    -- `scheduled_work.handler`, verbatim, so a reader joins straight back.
    handler   TEXT,
    -- D00 §4's root_kind. `inbound_endpoint` where a row the module EXPOSES
    -- named this handler; `scheduled` where a declaration hands it to a clock.
    -- The third member, `entry_point`, has no producer — which signature
    -- starts a program is knowledge about a language, and ARCHITECTURE §10
    -- keeps that out of the language-blind half, so its producer is a catalog
    -- nobody has written (`docs/open-issues.md`, OI-22).
    root_kind TEXT,
    -- The wire address that reaches this root, carried from the `endpoints`
    -- row that named the handler, column for column and unformatted: the
    -- renderer composes `GET /order/list` from these three with the SAME
    -- function it composes the `## Inbound endpoints` table with, so the two
    -- sections cannot spell one address two ways, and a `path` still passes
    -- the render exit's redactor rather than arriving pre-composed past it.
    --
    -- **All three NULL is the answer for a root nothing addresses** — a
    -- scheduled job is started by a clock, and inventing `(unresolved)` or a
    -- label for it would report a gap where there is none.
    protocol  TEXT,
    method    TEXT,
    path      TEXT
);

-- 2Q `G4`: the call graph a trace walks (D01 §3's Edges). One row per (call
-- site, candidate callee), and one row for a call site whose callee's body this
-- workspace never read — because THAT is the terminal, and a trace that
-- reported nothing there would be indistinguishable from a call nobody made.
--
-- **`return_flows` is the value chain; this is the control one, and the second
-- is the larger.** A return flow exists only where a call produced a value, so
-- a method that hands nothing back — a write, a publish, a delete — contributes
-- no row there at all. A trace has to see those: they are frequently the whole
-- point of the work.
--
-- **Which method a site can run is answered once**, in
-- `resolve/dispatch.py`, and both this table and `return_flows` read it. M04 §4
-- designs a third answer that is not built; the open register carries that as a
-- known future disagreement rather than this table quietly minting a second one.
--
-- Replaced WHOLE per resolve through reset_call_edges.sql +
-- insert_call_edges.sql, both run from the one pass that writes here — the
-- return_flows discipline. Pre-declared empty like every table above it.
CREATE TABLE IF NOT EXISTS call_edges (
    -- The method containing the call site, module-prefixed exactly as
    -- `call_sites.caller` spells it (D00 §5a).
    caller      TEXT,
    -- The call site's own control-flow position within `caller`. `caller` plus
    -- `ordinal` is the site's identity, the same pair `call_sites` uses — and
    -- it is what gives a walk its NESTING, so the order statements were
    -- written survives into anything rendered from this table.
    ordinal     INTEGER,
    -- The dispatch form, carried verbatim from `call_sites.invoke_kind` rather
    -- than re-spelled. It is what tells a reader a `dynamic` row apart, and a
    -- `dynamic` row means something different from every other: the body named
    -- below is CREATED at this site and runs later, elsewhere, if at all. A
    -- new vocabulary for that distinction would have been a second spelling of
    -- a value the facts already carry.
    invoke_kind TEXT,
    -- The method this edge NAMES, as a bare descriptor (D00 §5a): what the
    -- compiler wrote at the site, or — for a `dynamic` site — the
    -- implementation the bootstrap will run, which is the only thing at such a
    -- site that names a body at all. Always present; it is what a reader sees
    -- in the source at that line.
    target      TEXT,
    -- The body this edge REACHES, module-prefixed so a walk can join it
    -- straight to that method's own rows and take the next hop. **NULL is the
    -- third-party boundary and the answer, not a gap**: the workspace read no
    -- body for `target`, so the call IS the terminal. A site whose dispatch
    -- narrowed to several bodies is several rows, one per body, none picked.
    callee      TEXT,
    -- The value id, IN THE CALLER, that this call produced — `call_sites.result`
    -- verbatim, NULL where the callee hands nothing back. It is what an
    -- argument of a later call in the same method carries as its `source`,
    -- which is how a reader follows a value within the caller without this
    -- table having to restate one.
    result      INTEGER,
    -- D00 §4's resolution set, describing the SITE (D01 §3's dispatch rule:
    -- the tier lives on the site and does not rank candidates against one
    -- another). `resolved` where exactly one body can run — and where NONE
    -- can, because the compiler named that target exactly and there is no
    -- candidate set to be uncertain about; `narrowed` where several can, all
    -- listed and none picked.
    resolution  TEXT,
    -- D00 §4's evidence set. Always `compiler`: the call site, the descriptors
    -- and the hierarchy are what the compiler wrote into the class files.
    evidence    TEXT
);

CREATE OR REPLACE VIEW documents AS
SELECT document_id,
       payload ->> 'relative_path'   AS relative_path,
       payload ->> 'module_id'       AS module_id,
       payload ->> 'language'        AS language,
       payload ->> 'origin_tier'     AS origin_tier,
       -- The library this document was extracted from, as its coordinate, and
       -- NULL for the module's own output (D00 §2). Projected here — and so
       -- carried into the exported `documents` table — because opting a
       -- library in is an ASSERTION the reader makes, and an assertion that is
       -- visible in the rendered document but invisible in the published
       -- bundle would be laundered into module-observed evidence exactly where
       -- it travels furthest from the person who made it.
       payload ->> 'origin'          AS origin,
       (payload ->> 'partial')::BOOLEAN AS partial,
       -- JEP 238 (W3): which copy of an overlaid class this document holds, and
       -- the name the JVM knows that class by. Projected so `selected_documents`
       -- below can group copies without re-reading the payload, and so a reader
       -- of the exported table can see that a selection happened at all.
       coalesce(payload ->> 'class_release', 'base') AS class_release,
       coalesce(payload ->> 'class_name', '')       AS class_name
FROM raw_facts WHERE kind = 'document';

-- MULTI-RELEASE SELECTION (W3c, Fork 4 rule 3). The JVM's own rule, applied to
-- the copies W3 tagged: among documents holding the SAME class name, the
-- highest release not exceeding the module's target wins, and base is the
-- fallback. Without this the tag changed nothing — the duplicates were merely
-- LABELLED duplicates, which is the caution Fork 4 attached to its own ruling.
--
-- **A name with exactly one candidate is ALWAYS kept**, whatever its release.
-- The fallback must not be implemented as "base copies only": 626 names across
-- the measured corpus exist ONLY under `META-INF/versions/`, and dropping them
-- would assert they do not load — a stronger claim than keeping them, and a
-- false one.
--
-- The target is the module's own declared release (W3b), and `2147483647` when
-- it declares none: with no stated target nothing is out of reach, so the
-- highest overlay wins rather than base. That is the JVM's behaviour on a
-- modern runtime, and it beats silently preferring a base copy the build may
-- have overlaid precisely because it does not work.
CREATE OR REPLACE VIEW selected_documents AS
WITH target AS (
    -- Spec §2.4 rule 4, in the order it states. The build's DECLARED release
    -- first (W3b) — §8.2 admits it, because it is written in the pom or build
    -- script. Then the module's OWN class-file major, which W1 records on every
    -- document: a module compiled at 21 cannot load an overlay built for 24,
    -- whatever its build forgot to declare. Then base, which is what -1 selects
    -- for, since every real release exceeds it.
    --
    -- `TRY_CAST`, not `::BIGINT`: a malformed pom property reaching this cast
    -- would take down this view and therefore EVERY view that filters on it.
    -- An unusable value is an absent one, which falls to the next tier.
    SELECT coalesce(
               max(TRY_CAST(payload ->> 'declared_release' AS BIGINT)),
               (SELECT max(TRY_CAST(payload ->> 'class_major' AS BIGINT)) - 44
                FROM raw_facts WHERE kind = 'document'
                  AND TRY_CAST(payload ->> 'class_major' AS BIGINT) >= 45),
               -1
           ) AS release
    FROM raw_facts WHERE kind = 'module'
),
candidates AS (
    -- `base` sorts as -1: it is reachable on every runtime, so it is never
    -- excluded by the target and always loses to a reachable overlay.
    SELECT d.document_id,
           d.class_name,
           d.origin,
           CASE WHEN d.class_release = 'base' THEN -1
                ELSE TRY_CAST(d.class_release AS BIGINT) END AS release
    FROM documents d
),
ranked AS (
    SELECT c.document_id,
           c.class_name,
           row_number() OVER (
               -- Scoped BY ARCHIVE as well as by name. JEP 238 lets a jar
               -- overlay ITS OWN classes, never another jar's — and `class_name`
               -- carries no archive identity, so partitioning on it alone put
               -- library A's `com/x/Foo.class` and library B's overlay of the
               -- same name in one group and threw one away. Real for shaded
               -- jars and for two versions of one library in a build.
               -- `origin` is the library coordinate, NULL for the module's own
               -- output, which is its own group.
               PARTITION BY c.origin, c.class_name
               ORDER BY
                   -- 1. a copy the target can actually reach beats one it cannot
                   (c.release <= t.release) DESC,
                   -- 2. among reachable copies, the highest release wins (JEP 238)
                   CASE WHEN c.release <= t.release THEN c.release END DESC,
                   -- 3. among UNREACHABLE ones — every copy overlaid above the
                   --    target and no base copy at all — the lowest wins. The
                   --    spec does not cover this case; dropping the name would
                   --    assert the class does not exist, which is false, and
                   --    the lowest is the one this module reaches first as its
                   --    target rises.
                   c.release ASC NULLS LAST,
                   -- 4. a total order, so the view is deterministic (NFR-1).
                   --    `NULLS LAST` is stated rather than left to the session's
                   --    `default_null_order`: a claim of determinism that rests
                   --    on a setting is not one.
                   c.document_id ASC
           ) AS rank
    FROM candidates c, target t
)
SELECT document_id
FROM ranked
-- A document that is not a class file has no name to group on and is never a
-- candidate for replacement: config, schema and module documents pass through.
WHERE class_name = '' OR rank = 1;

-- Multi-release selection is APPLIED here, not merely computed (W3c). Tagging
-- alone left labelled duplicates; this is where a losing copy stops
-- contributing rows, which is the difference between G-62 fixed and G-62
-- renamed.
CREATE OR REPLACE VIEW symbols AS
-- `seq` is the load order of the fact within its file, and a fact file is
-- written in declaration order (D00 §7). It is the only ordering that survives
-- into the workspace, and shape_fields.ordinal is declaration order (D01 §5),
-- so it is projected here rather than re-derived from anything the payload
-- happens to carry. A view over a table keeps the base table's rowid.
--
-- That rowid follows the order the loader read the lines in is **tested
-- behaviour, not a documented contract** — measured on this engine at 300k
-- rows across 8 files with 10 threads, where the bulk read preserved each
-- file's line order. An engine upgrade is the moment to re-verify it: if it
-- ever stops holding, `ordinal` stops being declaration order and every
-- content hash moves with it (NFR-1).
SELECT rowid                        AS seq,
       document_id,
       payload ->> 'symbol'         AS symbol,
       payload ->> 'construct_kind' AS construct_kind,
       payload ->> 'enclosing'      AS enclosing,
       payload ->  'signature'      AS signature,
       -- D00 §5a: `public` or `other`, as the declaring language sees it.
       -- Carried on every symbol fact and, until 2I's class-gate member rule,
       -- read by nothing — a rule that derives a class's EXPOSED members is
       -- the first thing that has to tell one from a member nobody can call.
       payload ->> 'visibility'     AS visibility,
       -- Declaration modifiers (D00 §5): what only the declaring language can
       -- say about whether a field reaches a payload at all. Absent on every
       -- other construct, and on a fact from a scanner that does not report
       -- them, so each reader supplies its own default rather than this view
       -- inventing one for constructs the modifier means nothing for.
       payload ->  'modifiers'      AS modifiers
FROM raw_facts WHERE kind = 'symbol'
  AND document_id IN (SELECT document_id FROM selected_documents);

-- Multi-release selection is APPLIED here, not merely computed (W3c). Tagging
-- alone left labelled duplicates; this is where a losing copy stops
-- contributing rows, which is the difference between G-62 fixed and G-62
-- renamed.
CREATE OR REPLACE VIEW annotations AS
SELECT document_id,
       payload ->> 'target'              AS target,
       payload -> 'use' ->> 'annotation' AS annotation,
       payload -> 'use' ->  'args'       AS args,
       -- Only a type-use annotation carries this at all: NULL for a
       -- declaration annotation, '' for the outermost type, and a deeper path
       -- for an annotation on a type argument (D00 §5a).
       payload ->> 'type_path'           AS type_path,
       payload ->> 'retention'           AS retention
FROM raw_facts WHERE kind = 'annotation'
  AND document_id IN (SELECT document_id FROM selected_documents);

CREATE OR REPLACE VIEW config_entries AS
-- `seq` is declaration order within the entry's file: a config_entry fact
-- carries no explicit sequence field of its own (D00 §5c) because a fact
-- file is written in declaration order (D00 §7) and `rowid` already
-- reconstructs it losslessly — the same precedent `symbols.seq` states
-- above, reused rather than re-derived.
SELECT document_id,
       payload ->> 'key_raw'              AS key_raw,
       payload ->> 'key_path'             AS key_path,
       payload ->> 'value'                AS value,
       (payload ->> 'doc_index')::INTEGER AS doc_index,
       rowid                              AS seq
FROM raw_facts WHERE kind = 'config_entry';

-- Multi-release selection is APPLIED here, not merely computed (W3c). Tagging
-- alone left labelled duplicates; this is where a losing copy stops
-- contributing rows, which is the difference between G-62 fixed and G-62
-- renamed.
CREATE OR REPLACE VIEW call_sites AS
SELECT document_id,
       payload ->> 'caller'                    AS caller,
       payload -> 'target' ->> 'owner'         AS owner,
       payload -> 'target' ->> 'name'          AS name,
       payload -> 'target' ->> 'descriptor'    AS descriptor,
       payload ->> 'invoke_kind'               AS invoke_kind,
       -- Capability 9.17: the lambda body a `dynamic` site dispatches into,
       -- bare-spelled (D00 §5). `->>` on an absent key is SQL NULL, which is
       -- the answer for every site whose target already names its callee —
       -- the extractor writes the key only where there is a body to name.
       payload ->> 'implementation'            AS implementation,
       (payload ->> 'ordinal')::INTEGER        AS ordinal,
       (payload ->> 'receiver')::INTEGER       AS receiver,
       (payload ->> 'result')::INTEGER         AS result,
       payload ->  'arguments'                 AS arguments
FROM raw_facts WHERE kind = 'call_site'
  AND document_id IN (SELECT document_id FROM selected_documents);

-- Multi-release selection is APPLIED here, not merely computed (W3c). Tagging
-- alone left labelled duplicates; this is where a losing copy stops
-- contributing rows, which is the difference between G-62 fixed and G-62
-- renamed.
CREATE OR REPLACE VIEW method_returns AS
-- D00 §5's method_return (capability 9.18): what a method hands back, one row
-- per return instruction. `value` stays JSON rather than being flattened to a
-- value id, because it is an entry of the argument grammar and the whole point
-- of that shape is that a void return's SQL NULL (`->` on an explicit JSON
-- null, which DuckDB gives as the JSON scalar 'null', is distinguished by the
-- reader) says something a `{"kind":"unresolved"}` does not.
SELECT document_id,
       payload ->> 'method'                    AS method,
       (payload ->> 'ordinal')::INTEGER        AS ordinal,
       payload ->  'value'                     AS value
FROM raw_facts WHERE kind = 'method_return'
  AND document_id IN (SELECT document_id FROM selected_documents);

-- D00 §5's `constant` (W4): a compile-time constant field and its value, from
-- JVMS 4.7.2's `ConstantValue`. Its stated consumer is topic and URL
-- resolution — `static final String TOPIC = "orders"` is how a great many real
-- listeners name their destination.
--
-- `value` stays JSON rather than being cast to text: the attribute admits a
-- String or a numeric, a consumer resolving an address needs the one and a
-- consumer reading a port needs the other, and flattening here would put a
-- re-parse between them and the class file.
CREATE OR REPLACE VIEW constants AS
SELECT document_id,
       payload ->> 'symbol' AS symbol,
       payload ->  'value'  AS value
FROM raw_facts WHERE kind = 'constant'
  AND document_id IN (SELECT document_id FROM selected_documents);

-- Multi-release selection is APPLIED here, not merely computed (W3c). Tagging
-- alone left labelled duplicates; this is where a losing copy stops
-- contributing rows, which is the difference between G-62 fixed and G-62
-- renamed.
CREATE OR REPLACE VIEW field_writes AS
-- D00 §5's field_write: a constructor assigning parameter N straight to
-- field F, constructors only, direct traces only. The field resolution
-- ladder (2F) is its only consumer so far.
SELECT document_id,
       payload ->> 'field'                     AS field,
       (payload ->> 'from_parameter')::INTEGER AS from_parameter
FROM raw_facts WHERE kind = 'field_write'
  AND document_id IN (SELECT document_id FROM selected_documents);
