# The sixth edge: a field read reaches the value written into it

**Status:** design. **§4 was ruled by the user 2026-10-18**, and the ruling replaced the question rather than answering it — the rule is ENUMERABILITY, and `narrowed` was the wrong word for an exact answer.
Written 2026-10-18 after `OI-148`'s `setPathPrefixes` half proved to need exactly this edge,
and after measuring it.

**What it closes:** the walk's sixth edge for the shape a backend ALREADY reports —
`OI-141`'s own, and the blocker under `OI-148` §4. **Not** capability 9.19 in full; §5 says
what stays open and why those are separate.

---

## 0. THE CORRECTION THIS RESTS ON

`OI-136` defers the sixth edge, and `value_edges.sql` states the reason in its own header:

> *"`written_by` — a binding assigned anywhere but an initialiser — is the one edge with no
> fact behind it … Until a backend reports it, a workspace with no binding-write facts yields
> no such edge at all."*

**A backend DOES report one, and the walk has never read it.** `MethodFlow.fieldWrites` emits
a `field_write` fact — `{field, from_parameter}` — for every constructor that assigns a
parameter straight to a field. `grep -c field_writes src/sextant/storage/duckdb/value_edges.sql`
is **0**, and `values._binding` returns `no_writer` without being handed the binding's symbol
at all.

So the deferral is right about *writes outside an initialiser* and wrong about the edge: the
commonest shape in a Spring estate — constructor injection — has had a fact behind it all
along.

### Measured, at positions a shipped catalog asks about

Instrumented at `_binding`, where the position carries the symbol, over every built corpus:

| corpus | binding reads reached | writer already described |
|---|---|---|
| `apollo-portal` | 132 | **94** |
| `apollo-configservice` | 45 | 9 |
| `apollo-adminservice` | 18 | 3 |
| `apollo-biz` | 15 | 3 |
| `jhipster-sample-app` | 28 | **0** |
| `mall-admin` | 17 | **0** |
| `orders-service`, `mall-portal`, others | 31 | 2 |
| **total** | **276** | **112 (41%)** |

**And `OI-136`'s "16 of 756" was measured before Apollo joined the corpora.** The same
bounded-measurement mistake as `OI-143`'s *"nothing in the 27 measured corpora reaches it"*,
for the third time: 276 is the count with Apollo in, and it is 17× the figure the deferral
rests on ([[nothing-in-the-corpus-is-about-the-corpus]]).

**The zeros are not failures, and they bound the whole capability.** `mall-admin` and
`jhipster-sample-app` answer 0 because they use `@Autowired` FIELD injection: the container
writes the field reflectively and there is no write instruction in any method to report. That
is §8.2's territory — not a gap to close, and no extractor change reaches it.

---

## 1. What ships, in two steps

### Step 1 — wire the fact that already exists

**One arm in `value_edges.sql`, and `_binding` following it.** No extractor change, no new
fact, no schema change.

```
written_by | the binding symbol | the writing method | parameter N
```

* The arm reads `field_writes`, which already names the field and the parameter index; the
  writing constructor is the field's own owner.
* `_binding` is handed the symbol it already has in its position — `(_BINDING, symbol)`,
  formed at `values.py`'s `kind == "field"` arm — and resolves the writer as a PARAMETER of
  the writing method, which is `_parameter`'s existing crossing. Nothing is invented after the
  edge: the crossing, the path coherence and the multiplicity already carry every other edge.

**Several writers are several answers** — §4's case 1, which `OI-136` itself already recorded
for this shape: *"A field with several writers is not a hazard. It is several POSSIBLE values,
and ruling 1 already says several enumerable answers yield one row per answer."*

**What step 1 gives `ruoyi`:** the two prefixes resolve and pair correctly — `_combine` keeps
`/admin-api` with `**.controller.admin.**`, because both halves read the same `api` and cross
`Api#<init>` identically. What it does NOT give is attribution: the route runs through
`Api#prefix`, a CLASS-level fact, so each read collects both constructions and nothing says
which field it came through. For the output `OI-148` §4 needs — prefix paired with package
pattern — that is sufficient and exact. For a reader asking *"what does `getAdminApi()`
return"* it is two answers where one is true.

### Step 2 — the field's own value, so the instance stops being lost

Step 1's imprecision is not inherent; it is the route. The direct route exists in the
bytecode and has no fact:

```
getAdminApi() returns field WebProperties#adminApi      (method_returns — a fact today)
WebProperties#adminApi  ←  the value `new Api(…)` produced      ← NO FACT (CP-33 row 7)
```

So step 2 is:

* **a widened `field_write`**, carrying `from_value` beside `from_parameter` — the instruction
  index of the value assigned, which is how the extractor already numbers values (a call's
  `result` IS its index, and a constructed instance is referenced as
  `{kind: instance, source: 8}`). CP-33 row 7 measured the shape it must match;
* **receiver-aware field resolution**: where the walk knows the receiver came from
  construction A, a read of A's field resolves against A's arguments and no other
  construction's. The machinery is in hand — `from_receiver` and the `RECEIVER` slot were
  added 2026-10-17 for `OI-142`.

Then `getAdminApi()` answers `/admin-api` exactly and `getAppApi()` answers `/app-api`
exactly, while §4 case 2 — a field read on an object this module never constructs — still
answers `external`.

**Step 1 first, and not merely for size.** It is self-contained, measured at 112 reads, and
step 2 builds on the same edge rather than replacing it: step 2 adds a second thing a field
write can say, and the arm that follows it is the one step 1 writes.

## 2. The worked example, fact by fact

`ruoyi-vue-pro`'s `/admin-api`, which `OI-148` §4 is blocked on. Every row below is a fact in
the workspace today, verified on `yudao-framework/yudao-spring-boot-starter-web`:

| # | step | the fact that answers it |
|---|---|---|
| 1 | `api.getPrefix()` | `method_returns`: returns field `WebProperties$Api#prefix` |
| 2 | that field's writer | `field_writes`: `Api#prefix ← parameter 0` of `Api#<init>` — **the edge this spec adds** |
| 3 | crossing to the constructions | `call_edges`: `WebProperties#<init>` → `Api#<init>`, so `bound_to_parameter` already exists |
| 4 | the values | `call_sites`: `new Api("/admin-api", "**.controller.admin.**")` and `new Api("/app-api", "**.controller.app.**")` |

And the pairing is already right: prefix and package pattern read the same `api`, so
`_combine`'s coherence keeps `/admin-api` with `**.controller.admin.**` on one path and
`/app-api` with `**.controller.app.**` on the other. Two coherent paths, measured before this
spec existed.

---

## 3. Cost (§8.7)

One more arm in `value_edges.sql`, which is linear in the facts and already five arms wide;
`field_writes` is small (52 rows on the module above, 0 on two corpora). The walk gains one
edge to follow per binding read — bounded by the memo on `(position, path)` that already
bounds every other edge, and the 276 reads above are the whole population at asked positions.

Re-run `scripts/measure_value_walk.py`: the no-cap ruling was measured with this edge absent,
and a binding read that answered immediately now crosses into a constructor.

---

## 4. Several values are an EXACT answer where the set is closed — **RULED**

The question this section asked was how to hedge a field read that resolves to several
values. The user's ruling discards the premise: **a complete enumeration is not uncertainty,
it is the answer.** Three cases, in their words (2026-10-18):

| # | the case | the answer |
|---|---|---|
| 1 | *"the parameter is preconstructed, meaning only certain values exist — we should be able to enumerate all possible values, that's exactly match"* | **resolved**, one row per value |
| 2 | *"the parameter … needs to be passed in as parameter. If there is no call to this function, we don't know what are possible values"* | **unresolved** |
| 3 | *"same as 2, but calls to the function exists and contains specific values"* | **resolved**, one row per caller |

**All three are already the walk's behaviour**, which is the strongest argument for the rule:

* case 2 is `_parameter`'s own answer — *"No edge at all is `external`: nothing this
  workspace scanned binds this parameter"* — and `external` publishes an unresolved row;
* case 3 is the `bound_to_parameter` crossing, one path per caller, which is ruling 1's
  multiplicity and has shipped since the walk existed;
* case 1 is what this spec's edge adds: one path per construction, same shape.

So **`narrowed` is NOT used, and reaching for it was the error.** It would mark an exact
answer as a hedge: two `Api` objects with two prefixes is not a doubt about one prefix, it is
two prefixes, both registered, both true. The word stays where it belongs — dispatch that
narrowed to several bodies, and a format rung that narrowed to several candidates.

### The bound this ruling carries, stated rather than discovered later

"Resolved" means resolved **from what this module can see**. An enumeration is exact only if
it is complete, and it can be silently incomplete two ways:

* a construction in a module this workspace did not read — the sibling case `OI-149` just
  widened for types, which does not reach value facts;
* an object the container builds reflectively (`@Autowired` field injection), where no
  construction instruction exists anywhere — §8.2, and the reason `mall-admin` answers 0 of
  17 in §0.

**Neither is new, and that is why the ruling is safe to apply as stated.** The identical bound
already governs `bound_to_parameter`: a method's callers may live in another module, and the
walk answers from the callers it sees without marking the set partial. One more edge with the
same bound is consistent; a different treatment for this one would be the anomaly.

## 5. What stays open, named so the closure list is honest

Capability 9.19's remaining shapes, each with CP-33's measured bytecode:

| CP-33 row | shape | why this spec does not reach it |
|---|---|---|
| 2 | `@PostConstruct` assigning a literal | the value load is `ldc`, not an `xLOAD` — no triple, so no fact |
| 6 | a static initialiser | `ldc; putstatic` — no receiver load and `PUTSTATIC`, not `PUTFIELD` |
| 7 | a field assigned a CALL's result | an `invokeinterface` and a `checkcast` intervene |
| 8 | an instance field initialiser (`ldc`) | inside `<init>`, so the guard passes; the FACT GRAMMAR refuses it (`OI-141`) |
| 1 | a setter assigning its parameter | the triple holds — only the `<init>` guard refuses it |

Row 1 is the cheapest of the five (lift one guard) and row 8 is `OI-141`'s own. All five are
extractor work and a widened fact, and none is needed for the 112 reads above.

**`@Autowired` field injection is NOT on that list** and never will be: there is no write
instruction to read. §8.2 bounds it.

---

## 6. What moves, and standing requirements

* **No wrong row.** A writer is followed only where the fact names it; the parameter crossing
  then resolves or does not, exactly as it does for every other edge.
* **Expected movers:** rows whose address is read from a constructor-injected field. Measured
  before and after on `apollo-portal` (94 of its 132 binding reads gain a writer), and every
  pin re-run with the figures stated.
* **`measure_value_walk.py` re-run**, per §3.
* **A fixture asserts the derived rows first** (§4.1), and a guard pins the multiplicity rule
  §4 settles.
