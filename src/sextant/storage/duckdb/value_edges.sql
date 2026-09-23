-- Value resolution (spec 2026-09-22 §1a): the edges a backward walk follows to
-- answer *what is this value?*, normalised into ONE shape out of the three
-- tables that already hold them.
--
-- **NO DATABASE OBJECT AT ALL, which is §3b taken the whole way.** Every edge
-- below is already held by `call_sites`, `return_flows` or `call_edges`, and
-- §3b refuses a materialised copy because it would add a writer, a reset,
-- schema growth and a second version of rows that can drift from the first.
-- This file was a `CREATE VIEW` for exactly one commit, and a view is still an
-- object in the catalog: `schema_objects()` found it, the export ratchet quite
-- correctly demanded a query for it — an object in the schema with no export
-- query is a TEST FAILURE, with no exclusion class — and every bundle then
-- carried 420 KB of rows derived from three tables shipping beside it. Schema
-- growth is on §3b's own list of costs, so the fix is to stop growing the
-- schema rather than to argue an exception into the ratchet.
--
-- So this is the TEXT of a named query, read by `workspace.py` into
-- `_NAMED_QUERIES` and executed on demand — never `CREATE`d. Nothing is stored,
-- nothing is exported, nothing can drift, and `workspace.query("value_edges")`
-- reads the three tables as they stand at that moment. It is linear in the
-- facts, which is what makes it safe to leave unbounded while the walk on top
-- of it is not (§3a).
--
-- **FIVE kinds, not the design's six, and the absence is an answer.**
-- `written_by` — a binding assigned anywhere but an initialiser — is the one
-- edge with no fact behind it, and it is specified as a scanner CAPABILITY
-- rather than as work on any one backend (§4). Until a backend reports it, a
-- workspace with no binding-write facts yields no such edge at all, which is
-- what a reader can act on; an empty-but-present kind would say the walk looked
-- and found nothing, and the walk has not looked.
--
-- **Its own file rather than a string literal in `workspace.py`.** Five arms,
-- each carrying the fact and the projection behind it, is the value of this
-- text and it would read badly wedged between one-line named queries. A reader
-- who opens this file is reading the WALK's input; `workspace.py` holds the
-- ordering the query is read in and nothing else.
--
-- **Which projection each arm rides, stated per arm rather than assumed** (the
-- I-3 finding: the tables disagreed and nothing said so). `effective_call_sites`
-- — the projection that re-targets a compiler-emitted default-argument bridge
-- and reads a class-compiled lambda as the lambda it is — lives in the
-- application layer, in Python, and SQL cannot see it. What SQL can see is its
-- OUTPUT: `return_flows` and `call_edges` are written by passes that read the
-- projection, so the two arms over them ride it. The three arms over the
-- argument grammar read `call_sites` itself, which is the bytecode's own
-- statement — so at a bridge site their slot numbering is the bridge's and not
-- the function it stands for. That is a stated boundary of this query, and the
-- walk's measurement (§3a) is where its size is learned, not a gap to discover.
--
-- **The columns are nullable per kind, and this is the table of which kind
-- fills which.** NULL here always means *the facts give this position no such
-- value*, never *unknown*:
--
--   kind                | from_value        | to_symbol   | to_ordinal | to_index
--   --------------------|-------------------|-------------|------------|---------
--   produced_by         | the site's result | NULL        | the site   | NULL
--   returned_by         | the site's result | the callee  | the site   | NULL
--   read_from_binding   | NULL              | the binding | the site   | NULL
--   bound_to_parameter  | the argument's    | the callee  | the site   | the
--                       | source, or NULL   |             |            | index
--   names_declaration   | the argument's    | the         | the site   | NULL
--                       | source, or NULL   | declaration |            |
--
-- `to_index` is meaningful for `bound_to_parameter` ALONE — it is a parameter
-- index, and no other edge lands on a parameter.
--
-- **A NULL `from_value` is an ANSWER, not an absence, and it was measured
-- rather than assumed.** Read against the fact files: a binding reference, a
-- type reference and a named constant of its own type each carry a `symbol` and
-- no `source`, while a constructed value carries both (D00 §5's argument
-- grammar). So the facts NAME no produced value at those positions — the value
-- was not produced by running anything in this method, and there is nothing for
-- a walk to follow BACK to. It is the same statement `call_edges.callee` makes
-- with a NULL: the boundary is the answer. A reader must not read it as "the
-- extractor failed to record one"; what an unreadable value looks like is an
-- `unresolved` argument, which carries its `source` and appears here as a
-- `bound_to_parameter` row with a value id.
--
-- `to_symbol` is NULL for `produced_by` on the same terms: that edge lands
-- inside `from_method` itself, where `to_ordinal` is the whole address.
--
-- **Nothing here re-spells a column that already exists somewhere.** The site's
-- own target, dispatch form and arguments are at (`from_method`, `to_ordinal`)
-- in `call_sites` and `call_edges`, and a callee's returns are in
-- `method_returns` and `return_flows`; carrying copies of them would be the
-- "no fact that was merely copied" rule (D01 §6) broken in the one place a walk
-- would be worst served by two spellings of one answer.

-- `produced_by`: the value a call handed back, and the site in the same method
-- that handed it back. The fact is `call_sites.result` — the value id an
-- argument of a later call in the same method carries as its `source`, which is
-- what makes a chain a chain.
--
-- **Read off `call_sites`, and reading it off `call_edges` was a defect.** The
-- edge is about a SITE producing a value, not about a body being reached, and
-- `call_edges` is a table of bodies: it writes no row for a `dynamic` site
-- whose bootstrap names none, which is correct there and fatal here, because
-- string concatenation is exactly such a site. D00 §5's grammar states the
-- contract this edge has to honour — an assembled address is `concat` with a
-- template, and *"what FILLS the hole is the concat site's own call-site fact,
-- reached by `source` -> `result`"*. That hop is this edge. MEASURED while the
-- arm read `call_edges`: every assembled value in both corpora was invisible to
-- it — 7 of 7 producing sites on `orders-service`, 203 of 203 on `mall-admin`,
-- including a client whose URL is `".../orders/" + id`, which is the shape this
-- whole design exists to reach.
--
-- The projection buys this arm nothing, which was also measured rather than
-- argued: `effective_call_sites` re-targets a bridge call's CALLEE, and over
-- `orders-service` its 1,818 rows carry a `(caller, ordinal, result)` set
-- identical to raw `call_sites`'s 1,818. A result is a value id in the caller's
-- own frame; re-targeting the callee cannot move it to another caller or
-- another ordinal. The arms that need the callee still ride the projection,
-- through the tables written from it.
--
-- No DISTINCT: `call_sites` is one row per site, so a site contributes exactly
-- one produced value. The DISTINCT this arm carried existed only to collapse
-- `call_edges`'s per-candidate-body fan-out, and that fan-out is `returned_by`'s
-- question rather than this one.
SELECT 'produced_by'               AS kind,
       caller                      AS from_method,
       result                      AS from_value,
       CAST(NULL AS VARCHAR)       AS to_symbol,
       ordinal                     AS to_ordinal,
       CAST(NULL AS INTEGER)       AS to_index
FROM call_sites
WHERE result IS NOT NULL

UNION ALL

-- `returned_by`: the value a call handed back, and the CALLEE whose returns
-- answer for it. The fact is `return_flows`, which is exactly this join already
-- computed — and which Task 1 re-pointed at `effective_call_sites`, so this arm
-- rides the projection. The row names the callee and stops there, as §1a does
-- ("a callee symbol; read its returns"): the returns themselves are rows of
-- `method_returns` and of `return_flows` itself, and a callee with two `return`
-- statements is two of them — two paths, per §1c, which the walk enumerates
-- from that table rather than from a fan-out baked in here. DISTINCT collapses
-- this query's own duplicate of that fan-out, never the fan-out.
SELECT DISTINCT 'returned_by'      AS kind,
       caller                      AS from_method,
       result                      AS from_value,
       callee                      AS to_symbol,
       ordinal                     AS to_ordinal,
       CAST(NULL AS INTEGER)       AS to_index
FROM return_flows
WHERE callee IS NOT NULL

UNION ALL

-- `read_from_binding`: a value at a call site that was read out of a named
-- mutable location. The fact is the argument grammar's binding kind (D00 §5,
-- spelled `field` there; the edge says `binding` because a named mutable
-- location is a field in one language, a module-level variable in another and a
-- package var or a closure cell elsewhere — §5a). It carries the location's own
-- symbol and NO value id: a read off a binding is no call's result, which is
-- why `from_value` is NULL here and why the walk continues through the
-- binding's writers rather than through this method. Those writers are the
-- sixth edge, and it is not here yet.
--
-- **The projection: `call_sites`, RAW.** §1a asks for `effective_call_sites`,
-- and SQL cannot see it (the header says why), so this arm reads the bytecode's
-- own statement. What that costs is bounded and named: at a compiler-emitted
-- default-argument bridge site the arguments are the bridge's — the defaulted
-- slots carry the mask and marker the bridge takes rather than the values the
-- function it stands for receives. The binding SYMBOL this arm carries is not
-- affected by that (a binding read is a binding read at either site); what is
-- affected is which sites exist and how many slots each has.
SELECT 'read_from_binding'         AS kind,
       caller                      AS from_method,
       CAST(NULL AS INTEGER)       AS from_value,
       argument ->> 'symbol'       AS to_symbol,
       ordinal                     AS to_ordinal,
       CAST(NULL AS INTEGER)       AS to_index
FROM (SELECT caller, ordinal,
             UNNEST(json_extract(arguments, '$[*]')) AS argument
      FROM call_sites)
WHERE (argument ->> 'kind') = 'field'
  AND (argument ->> 'symbol') IS NOT NULL

UNION ALL

-- `bound_to_parameter`: a value in the caller handed to parameter N of a body
-- the call reaches. This is the edge the whole design turns on — it is the one
-- that crosses a method boundary, and §1c's ruling is that it is followed per
-- PATH: a helper called twice is two bindings, never a per-position cross
-- product. The callee comes from `call_edges`; a row whose `callee` is NULL is
-- the third-party boundary and carries no body to walk into, so it contributes
-- no edge. The slot is the argument's own position, which is the index every
-- language numbers its parameters by (D00 §5: a receiver is not a parameter,
-- and the grammar carries one entry per slot, so a varargs call is ONE array
-- argument and not N). `from_value` is the argument's `source` where the facts
-- name a produced value and NULL where they do not — a literal, a type
-- reference and the caller's own parameter are all read from the argument
-- itself, at (`from_method`, `to_ordinal`), slot `to_index`.
--
-- **A `dynamic` site contributes NOTHING, and that is a refusal rather than an
-- omission** — the same decision `return_flow` states for the same reason, one
-- step further along. At an `invokedynamic` site the two halves this arm joins
-- describe different things: `call_edges.callee` is the lambda BODY the
-- bootstrap will run, while the arguments are the metafactory's CAPTURES, and
-- a captured value is not the body's parameter of the same index. The body's
-- own parameters are supplied when it runs, later, elsewhere, if at all —
-- nothing at this site binds them. The grammar says it in one line, in the rule
-- quoted above: a receiver is not a parameter, and at an indy site the captured
-- receiver sits in the argument list. Emitting the join anyway does not MISS an
-- answer, it states a wrong one at `resolved`, which is the cardinal sin: a
-- walk asking for parameter 1 was handed the caller's argument 0. MEASURED
-- before the refusal: 26 of 238 rows on `orders-service` and 8 of 33,926 on
-- `mall-admin` were such rows, every one of them a fabrication. Following
-- `implementation` INTO a lambda body is a traversal step and `call_edges` is
-- the table that takes it; binding a value to that body's parameters is an
-- edge nothing in the facts supports.
--
-- **The projection, both halves, because they differ.** `callee` rides
-- `effective_call_sites` — `call_edges` is written from it, so a bridge call
-- names the function it stands for. The ARGUMENT LIST and the slot numbering do
-- NOT: they are read off raw `call_sites`, so at a `$default` bridge site the
-- slots are the bridge's, which means the trailing mask and marker appear here
-- as parameter indices the function it stands for does not have. That is this
-- arm's stated boundary — Task 4's measurement is where its size is learned.
SELECT 'bound_to_parameter'        AS kind,
       e.caller                    AS from_method,
       (a.argument ->> 'source')::INTEGER AS from_value,
       e.callee                    AS to_symbol,
       e.ordinal                   AS to_ordinal,
       a.slot                      AS to_index
FROM call_edges e
JOIN (SELECT caller, ordinal,
             UNNEST(json_extract(arguments, '$[*]'))            AS argument,
             UNNEST(range(json_array_length(arguments)::BIGINT)) AS slot
      FROM call_sites) a
  ON a.caller = e.caller AND a.ordinal = e.ordinal
WHERE e.callee IS NOT NULL
  AND e.invoke_kind <> 'dynamic'

UNION ALL

-- `names_declaration`: a value that IS a declared thing rather than one
-- produced by running something. The fact is the argument grammar's type and
-- binding REFERENCES (§1a) — a class constant naming a declared type, a named
-- constant of its own type naming a declared constant, and a constructed value
-- naming the concrete type it was built from. The first two carry a symbol and
-- no value id; the third carries both, which is why `from_value` is the
-- argument's `source` where there is one. This is where the walk STOPS with an
-- answer rather than a reason: the declaration is the value, and what the
-- declaration means is the catalog's business and never this query's (§1e).
--
-- **A `lambda` argument is NOT one of these, and the exclusion is stated so it
-- need not be rediscovered.** It carries both a `source` and a body `symbol`,
-- so it would fit the shape — 62 of them on `orders-service`, 24 on
-- `mall-admin` — and it is left out on meaning rather than on shape: a lambda
-- names a BODY, not a declaration whose value can be identified. A walk that
-- reached one and was handed that symbol would have a method descriptor where
-- it asked for a value, so the honest answer is `unresolved`. If a later task
-- needs lambda bodies it is a different edge, named as one (ruled 2026-09-22).
--
-- **The projection: `call_sites`, RAW**, on the same terms as
-- `read_from_binding` above — SQL cannot see `effective_call_sites`, so a
-- `$default` bridge site is read as the bridge. The declaration SYMBOL is
-- unaffected; which sites exist and how many slots each has is not. One case is
-- genuinely lost: a lambda compiled as a CLASS arrives as an `instance`
-- argument — or, for its non-capturing twin, as a named constant of its own
-- type — and the projection is what reads either as the `lambda` it is. Both
-- kinds are read here, so such an argument appears as a `names_declaration` row
-- naming the synthetic class rather than being excluded with the lambdas above.
-- Stated, not silently absorbed: the row is honest about the symbol it carries,
-- and Task 4's measurement is where the size of the difference is learned.
SELECT 'names_declaration'         AS kind,
       caller                      AS from_method,
       (argument ->> 'source')::INTEGER AS from_value,
       argument ->> 'symbol'       AS to_symbol,
       ordinal                     AS to_ordinal,
       CAST(NULL AS INTEGER)       AS to_index
FROM (SELECT caller, ordinal,
             UNNEST(json_extract(arguments, '$[*]')) AS argument
      FROM call_sites)
WHERE (argument ->> 'kind') IN ('class', 'enum', 'instance')
  AND (argument ->> 'symbol') IS NOT NULL

-- Over the whole union, and on every column, which is what makes the ordering
-- TOTAL (NFR-1). `kind, from_method, to_ordinal` is not: one site binds several
-- parameters and names several declarations, and the remaining three columns
-- are what separate those rows from one another. The one tie left is a row
-- identical in all six, which is one edge stated twice — a site reading the
-- same binding at two slots — and the same row either way.
ORDER BY kind, from_method, to_ordinal, to_index, to_symbol, from_value;
