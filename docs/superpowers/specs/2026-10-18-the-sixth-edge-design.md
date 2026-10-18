# The sixth edge: a field read reaches the value written into it

**Status:** design, with **one imprecision to rule on** (§4) that is the user's.
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

## 1. What ships

**One arm in `value_edges.sql`, and `_binding` following it.** No extractor change, no new
fact, no schema change.

```
written_by | the binding symbol | the writing method | parameter N
```

* The arm reads `field_writes` joined to nothing: the fact already names the field and the
  parameter index, and the writing constructor is the field's own owner.
* `_binding` is handed the symbol it already has in its position — `(_BINDING, symbol)`,
  formed at `values.py`'s `kind == "field"` arm — and resolves the writer as a PARAMETER of
  the writing method, which is `_parameter`'s existing crossing. Nothing new is invented
  after the edge: the parameter crossing, the path coherence and the multiplicity are the
  machinery that already carries every other edge.

**Several writers are several answers**, which is ruling 1 unchanged and is already the
answer `OI-136` recorded for this case: *"A field with several writers is not a hazard. It is
several POSSIBLE values, and ruling 1 already says several enumerable answers yield one row
per answer."*

---

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

## 4. THE ONE IMPRECISION — and it is the user's to rule on

**The walk has no instance identity.** A field is a property of an OBJECT, and
`field_writes` describes the class. So where a class is constructed twice with different
arguments, a read of that field resolves to BOTH values, on two paths — even though the
object in hand had one of them.

For `ruoyi` that is exactly right: two `Api` instances, two prefixes, both real, and a
consumer wants both rows. In general it is **wider than the truth**: an over-report, never a
single wrong answer, and the same shape ruling 1 already accepts for two callers of one
helper.

Where it could mislead: a destination. Two `KafkaTemplate` wrappers constructed with
different topics, one read in a `send`, and the row publishes both topics for a call that
only ever used one.

* **Option A — follow it, and accept multiplicity.** Consistent with ruling 1, which the
  register already applied to this exact case. A reader sees every value any construction
  supplied.
* **Option B — follow it only where the class is constructed ONCE in the module.** One
  construction means one possible value, so the answer is exact. `ruoyi` has two, so this
  option does not unlock `OI-148` §4 — it would resolve nothing there.

**Recommended: A**, because B's precision is bought by refusing the case this edge was
measured for, and because an over-report that says "one of these two" is the honest shape of
what the bytecode states — a field of a class whose instances differ.

---

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
