-- Value resolution (spec 2026-09-22 §1a): the edges a backward walk follows to
-- answer *what is this value?*, normalised into ONE shape out of the three
-- tables that already hold them.
--
-- **A VIEW, and §3b is the reason.** Every edge below is already held by
-- `call_sites`, `return_flows` or `call_edges`; a materialised copy would add a
-- writer, a reset, schema growth and a second version of rows that can drift
-- from the first. Nothing is stored here — the view normalises three shapes and
-- is linear in the facts, which is what makes it safe to leave unbounded while
-- the walk on top of it is not (§3a).
--
-- **FIVE kinds, not the design's six, and the absence is an answer.**
-- `written_by` — a binding assigned anywhere but an initialiser — is the one
-- edge with no fact behind it, and it is specified as a scanner CAPABILITY
-- rather than as work on any one backend (§4). Until a backend reports it, a
-- workspace with no binding-write facts yields no such edge at all, which is
-- what a reader can act on; an empty-but-present kind would say the walk looked
-- and found nothing, and the walk has not looked.
--
-- **Its own file, beside `schema.sql` rather than inside it.** It is the only
-- schema object built over DERIVED tables instead of over `raw_facts`, so it
-- must run after the file that declares them; and a reader who opens it is
-- reading the WALK's input, not looking a column up in the DDL every other
-- object shares. `workspace.py` executes the two in that order.
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
-- the function it stands for. That is a stated boundary of this view, and the
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
-- index, and no other edge lands on a parameter. `from_value` is NULL wherever
-- the facts name no produced value at the position: a binding read is nobody's
-- result, and neither is a literal, a type reference or the caller's own
-- parameter. `to_symbol` is NULL for `produced_by` because that edge lands
-- inside `from_method` itself, where `to_ordinal` is the whole address.
--
-- **Nothing here re-spells a column that already exists somewhere.** The site's
-- own target, dispatch form and arguments are at (`from_method`, `to_ordinal`)
-- in `call_sites` and `call_edges`, and a callee's returns are in
-- `method_returns` and `return_flows`; carrying copies of them would be the
-- "no fact that was merely copied" rule (D01 §6) broken in the one place a walk
-- would be worst served by two spellings of one answer.
CREATE OR REPLACE VIEW value_edges AS

-- `produced_by`: the value a call handed back, and the site in the same method
-- that handed it back. THE fact is `call_sites.result` — the value id an
-- argument of a later call in the same method carries as its `source`, which is
-- what makes a chain a chain. Read off `call_edges` rather than off
-- `call_sites`, because that table is written from the projection and the raw
-- site is not: a bridge call's result belongs to the function the bridge stands
-- for. DISTINCT because a site whose dispatch narrowed to several bodies is
-- several `call_edges` rows and exactly ONE produced value — the multiplicity
-- there is about which body runs, which is `returned_by`'s question and not
-- this one.
SELECT DISTINCT 'produced_by'      AS kind,
       caller                      AS from_method,
       result                      AS from_value,
       CAST(NULL AS VARCHAR)       AS to_symbol,
       ordinal                     AS to_ordinal,
       CAST(NULL AS INTEGER)       AS to_index
FROM call_edges
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
-- this view's own duplicate of that fan-out, never the fan-out.
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
-- product. The callee comes from `call_edges`, which Task 1 re-pointed at the
-- projection, so a bridge call names the function it stands for; a row whose
-- `callee` is NULL is the third-party boundary and carries no body to walk
-- into, so it contributes no edge. The slot is the argument's own position,
-- which is the index every language numbers its parameters by (D00 §5: a
-- receiver is not a parameter, and the grammar carries one entry per slot, so a
-- varargs call is ONE array argument and not N). `from_value` is the argument's
-- `source` where the facts name a produced value and NULL where they do not —
-- a literal, a type reference and the caller's own parameter are all read from
-- the argument itself, at (`from_method`, `to_ordinal`), slot `to_index`.
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

UNION ALL

-- `names_declaration`: a value that IS a declared thing rather than one
-- produced by running something. The fact is the argument grammar's type and
-- binding REFERENCES (§1a) — a class constant naming a declared type, a named
-- constant of its own type naming a declared constant, and a constructed value
-- naming the concrete type it was built from. The first two carry a symbol and
-- no value id; the third carries both, which is why `from_value` is the
-- argument's `source` where there is one. This is where the walk STOPS with an
-- answer rather than a reason: the declaration is the value, and what the
-- declaration means is the catalog's business and never this view's (§1e).
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
  AND (argument ->> 'symbol') IS NOT NULL;
