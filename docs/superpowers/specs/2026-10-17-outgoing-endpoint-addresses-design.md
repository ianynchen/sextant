# Outgoing endpoint addresses: make the document say where a call goes

**Status:** design. Brainstormed with the user 2026-10-17, measured throughout, two rulings
granted. Not yet planned.

**The deliverable is the rendered `architecture.md`, not a COVERAGE cell.** Ruled by the user
2026-10-17: *"I care about document being right, and don't care about the table, because I care
only about whether we can generate these outgoing endpoints in the final architecture document.
the table isn't the result. it's intermediary."* COVERAGE's Spring Boot *REST outbound* cell is
already `✅`, because it counts whether a row appears and not whether the row says anything. So
this work moves no cell by design, and its measure is the field pins.

## What it closes — measured, not predicted

Every claim below was verified on `spring-petclinic-microservices` (Spring's own reference
microservice app, 8 modules, built, pinned 2026-10-17 as `petclinic-api-gateway` and
`petclinic-genai-service`). This section exists because the last spec's closure list had four
false entries that were only caught at its second-to-last task — see
`verify-what-it-closes-before-planning` and the withdrawal block in
`2026-09-22-value-resolution-design.md`.

**What the document says today.** 17 inbound rows, all resolved. **6 outbound rows, 1 with a
destination.** `genai-service`'s whole Outbound section:

| Endpoint | Peer |
|---|---|
| `GET (unresolved)` | unresolved |
| `GET (unresolved)` | unresolved |
| `POST (unresolved)` | unresolved |
| `POST (unresolved)` | unresolved |

**And 8 rows that never appear at all**: `api-gateway` declares four routes in
`application.yml` and derives neither the paths it serves nor the services it forwards to.

| # | what is missing | rows | cause, measured | needs |
|---|---|---|---|---|
| 1 | the gateway's four routes, both directions | **8** | a chain of imported BOMs is not followed, so the starter's version is unresolved and the gate never admits a correct catalog over data already in `config_entries` (`OI-139`) | no ruling |
| 2 | `VectorStoreController` → vets-service | 1 | `vetsHostname + "vets"`, a LOCAL holding a literal, same method body (`aload_3`; `#63 = String http://vets-service/`, recipe `#261 = \u0001vets`) | ruling 1 |
| 3 | `VisitsServiceClient` → visits-service | 1 | `hostname + "pets/visits?petId={petId}"`, a FIELD holding a literal (`ldc #7; putfield` in `<init>`) | ruling 1 + §3 |
| 4 | `AIDataProvider` → customers-service | 3 | `getCustomerServiceUri() + "/owners"`, where the URI is a runtime registry lookup and only the service NAME is readable (`#147 = String customers-service`) | rulings 1+2 + §4 |

**13 rows.** 1 outbound row with a destination becomes 9, and 4 inbound rows appear.

**What it does NOT close**, stated so nobody reads the list as larger than it is:
`akka-pekko-actors` (probe row 7 — an `actorOf` result cannot be carried by any fact we have);
`OI-110`/`OI-124`/`OI-126` (unrelated mechanisms, measured at Task 13 of the previous spec);
Gateway `filters` rewriting the upstream path (`OI-111`, untouched here).

---

## 1. Ruling 1 — join a concatenation when every piece is a source literal

**Granted by the user 2026-10-17**, in their words: *"join them when every single piece is a
fixed string typed into the source code. If any piece comes from a config file, a method
parameter, or anything that changes at runtime — don't join, behave exactly as today."*

**This amends §6 of `2026-09-22-value-resolution-design.md`**, which reads *"A concatenation is
never **evaluated**; its template is carried verbatim as an `expression` with its holes
unfilled."* That rule stays the default. The exception is narrow and its boundary is the ruling's
own sentence.

### What the facts already hold

Nothing is reverse-engineered. javac emits one `invokedynamic` to
`StringConcatFactory.makeConcatWithConstants` plus a recipe in the constant pool, and
`extractor-jvm/.../MethodFlow.java::concatTemplate` already turns that recipe into a template:
`\u0001` (a runtime value) becomes `{}`, and `\u0002` (one of the bootstrap's own constants) is
**already substituted**, because *"that constant IS known."* So joining a known operand into a
template is existing behaviour for one class of hole; this extends it to holes javac could not
fold.

The operands are reachable: the `concat` fact carries a `source` pointing at the indy's own call
site, whose arguments are the operands. `domain/facts.py` says so — *"What FILLS the hole is the
concat site's own call-site fact, reached by `source` → `result`."*

### What changes

`resolve/values.py::_entry`'s `concat` arm returns the template and stops. It must instead
resolve each hole through the ordinary walk and, **only if every hole answered a `literal` of
`literal_kind: string`**, return the joined string as a `literal`. Any other outcome — one hole
`unresolved`, `external`, an `expression`, a `${…}`, a symbol, an `absent` — returns today's
`expression` with the template unchanged.

### Boundaries this inherits rather than invents

- **Multiplicity (ruling 1 of the previous spec) applies per hole.** Two holes each answering
  two enumerable literals is **four** joined strings, one row each — not one row and not a
  guess. A hole answering a non-enumerable set is `unresolved`, and the template is carried.
- **Memoisation stays keyed on `(position, path)`.** A concat reached on two calling paths with
  different operands is two answers, which is the rule that already governs every other arm.
- **`${…}` never joins.** A configuration placeholder is `expression`, not `literal`, so it fails
  the all-literals test by construction. §8.2 is untouched: this fills no deployment hole.
- **Cost is bounded by the walk, not by this arm** — each hole is one ordinary resolve. The
  measurement harness (`scripts/measure_value_walk.py`) must be re-run, because this arm turns a
  terminal answer into N sub-walks and §3a's no-cap ruling was measured without it.

---

## 2. Ruling 2 — `peer` and `path` may be filled from separate evidence

**Granted by the user 2026-10-17.** Today both come out of one call: `url_of(argument)` →
`split_url(value)` → `(peer, path)`. One string in, two columns out, and there is no other way in.

That is why §4's case cannot be expressed at all: `AIDataProvider` has **no URL anywhere in its
class file** (verified: zero occurrences of `http://`). The service name sits in one method as a
registry lookup's argument; the path sits in another, inside a concatenation. Two facts, two
places, nothing to cut.

**What changes:** a row may take `peer` from one resolved value and `path` from another. The
provenance of each half is recorded independently, so a row can carry a real peer with an
unresolved path, or the reverse, rather than collapsing both to NULL.

**What does not change:** `peer` stays NULL for messaging (D02 §3), and a `peer` still requires
evidence that the value names a callee — never inferred from a string's shape.

---

## 3. A binding's literal value is a fact

`field_write` can say *"field F holds parameter N"* and cannot say *"field F holds this
constant."* Measured at `scripts/probes/cp33_binding_writes.md` row 8: an instance field
initialiser compiles to `aload_0; invokespecial; aload_0; ldc; putfield` — **inside `<init>`**, so
the existing constructor filter already admits it. Only the fact's grammar refuses it:
`MethodFlow.fieldWrites` requires the middle instruction to be a `VarInsnNode` and an `ldc` is not
one, so nothing is emitted. In `VisitsServiceClient`'s constructor the `Builder` parameter write is
recorded and the URL constant write 7 bytes earlier is discarded.

**This is not capability 9.19 and not what `OI-136` deferred.** That capability is a write
*outside* an initialiser — a method-filter change. This is inside `<init>` and is a grammar
change: carry a constant value beside the parameter ordinal.

**Direct traces only still holds.** A computed assignment, and a field assigned another call's
result, both present something that is not a load where the value must be (probe rows 3 and 7),
so neither emits a fact and neither can be joined.

**A local variable needs none of this** (§ case 2): both halves are in one method body, and the
walk already reads a local assigned a literal. That case is unblocked by ruling 1 alone, which is
why it should ship first.

---

## 4. A service name is a destination, and three spellings mean it

All three forms in this estate name a service; the real address exists only at runtime and is not
wanted. Measured from the jars:

| spelling | what names the service | evidence |
|---|---|---|
| `http://visits-service/` | the host position | `ReactorLoadBalancerExchangeFilterFunction` calls `URI.getHost()` **with no scheme check**; `@LoadBalanced` on the builder is what makes it a lookup |
| `lb://orders-service` | the host position | `ReactiveLoadBalancerClientFilter` tests `getScheme().equals("lb")` then reads `getHost()` as the service id (CP-29 Q8). Also handled in `spring-cloud-commons` for HTTP service groups, so it is a Spring Cloud scheme and not Gateway-only |
| `getInstances("customers-service")` | argument 0 | `DiscoveryClient.getInstances(String) → List<ServiceInstance>`; `ServiceInstance.createUri` builds from `%s://%s:%s` — **scheme, host, port, no path** |

**The rule must be value-flow, never call-presence.** *"`getInstances` was called"* does not mean
the module calls that service — a dashboard could list instances and call nothing. The rule is:
**when a value originating at `getInstances`'s argument reaches a URL slot, that argument is the
peer.** Value flow is what the walk does, so this stays a fact about reached values.

**The list is irrelevant to us.** `getInstances` returns every instance and the application picks
one (`.get(0)` here, which is not load balancing). Which instance is a runtime detail; the
service identity is the peer.

**`createUri` emitting no path settles a question raised and withdrawn during the brainstorm:**
the hole in `getCustomerServiceUri() + "/owners"` provably contains no path segments, so `/owners`
is the whole path rather than a suffix of one — on the default implementation. `getUri()` is
abstract on the interface, so a custom `ServiceInstance` could return otherwise; that is a stated
boundary, not an assumption.

### The inconsistency this must not deepen

Two catalogs read the identical string shape two different ways, measured:

| catalog | value | `peer` | `path` |
|---|---|---|---|
| `spring-cloud-gateway-outbound` | `http://orders-service` | NULL | `http://orders-service` *(whole)* |
| `spring-webclient` | `http://customers-service/owners/{ownerId}` | `customers-service` | `/owners/{ownerId}` |

The cause is the reader, not the value: Gateway's catalog declares that slot a **destination**
(`channel_of`, never split — an SQS queue URL would be mangled), WebClient's declares it a **URL**
(`url_of`, split). So we record the uncertain spelling and blank the certain one.

**Scoped out of this spec, deliberately.** `split_url("lb://orders-service")` returns path `''`,
and an empty path is what D02's rule exists to forbid; CP-29 records the current shape as a
deliberate mirror of its sibling. Changing it rewrites 10 pinned fixture rows. §1's work makes the
four Gateway rows appear at all, carrying `lb://vets-service` verbatim as `path` — which already
tells a reader where the route goes. Splitting them is a separate, smaller decision taken with
those rows visible.

---

## 5. Order, and why

Ordered by cost, and the first needs no ruling at all:

1. **`OI-139`, the BOM chain** — 8 rows, the largest single win, and independent of everything
   else here. See §5a: walk the chain to EXHAUSTION, never to a depth limit.
2. **Ruling 1, locals only** — 1 row, and it proves the join end to end with no new fact.
3. **§3, a binding's literal value** — 1 row, and the first extractor change.
4. **Rulings 1+2 plus §4, discovery** — 3 rows, and the only part needing both rulings.

Each step is a document the field pins can check, which is the point of the ordering.


### 5a. Versions down the whole BOM chain — and the chain is not what was broken

**Ruled by the user 2026-10-17:** *"make sure that you track versions down the BOM chain, not
just a few levels."* The requirement stands. **Measuring it showed the walk already satisfies
it, and that an earlier draft of this section named the wrong cause twice.**

`detect/maven.py` already follows both `<parent>` links and `<scope>import</scope>` entries;
already resolves each imported BOM's versions **in that BOM's own property scope** (with a
comment saying why the importing module's properties *"must not answer it"*); and caps at
`_MAX_INHERITANCE_DEPTH = 16`, while this chain is **2**. So there is no depth to raise and no
scope to fix.

**What is broken, proven end to end — a throwaway patch, measured and reverted, took
`api-gateway` from 6 endpoints to 14, with all eight missing rows `resolved`:**

**1. `${project.version}` is a Maven BUILT-IN and `_interpolated` only reads a pom's
`<properties>` block.** It therefore returns `None`, and `_managed_versions` drops the managed
entry with **no message and no `else` branch** — which is why the symptom read as "the BOM was
never opened". It is how a Spring Cloud component BOM versions its own artifacts: 6 of 8 entries
in `spring-cloud-gateway-dependencies`, and every one of the four dependencies this module
reports unresolved. Defining `project.version` in the BOM's own scope took
`dependencies_not_resolved` from 4 to 0.

**2. The catalog's `detect.coordinates` omits the 5.0.0 starter.** With versions resolved the
catalog was still skipped, and `metadata.json` said so: it looks for
`spring-cloud-gateway-server-webflux`, `spring-cloud-starter-gateway` (the pre-5.0 name) and
`spring-cloud-gateway-server`, while the module declares
**`spring-cloud-starter-gateway-server-webflux`**. A transitive-only arrival is deliberately not
counted, so the starter has to be listed. Already half-logged as
`gateway-detect-4x-coordinate`, Minor — read as cosmetic because nobody had measured the cost.

### What this step must do

- **Define Maven's built-in `project.*` properties per pom**, as the inheritance walk visits it,
  scoped to that pom. `project.version` is what this chain needs; `project.groupId` and
  `project.artifactId` belong with it rather than waiting for a second instance.
- **Report, never drop.** A managed entry whose version cannot be interpolated goes into the
  `unreadable` list the surrounding code already threads to `dependencies_not_resolved`. The
  silent drop is the reason this took four wrong guesses to find, and that is the defect worth
  fixing beyond this one property.
- **List the 5.0.0 starter** in `spring-cloud-gateway-properties.yml` and its DSL sibling, each
  with a measured note.
- **Change nothing about the walk's shape.** It is correct. Exhaustion is satisfied by what is
  there, and the visited-set guard it already carries is why a 16 cap is never reached in
  practice — a point worth leaving in place rather than relitigating.

*Method note, recorded because it cost four wrong answers in one sitting: the symptom
("the gateway derives nothing") was consistent with a stale coordinate list, a one-level BOM
walk, a machine-dependent repository and a property-scope bug. Three of those were wrong and
`metadata.json` named the real one in plain words at the first attempt. Read the honest output
before theorising about the cause.*

---

## 6. How this is measured

**The pins record today's blanks verbatim**, so every step above FAILS a pin and forces a
deliberate re-record rather than passing silently:

```
.venv/bin/python scripts/field_check.py petclinic-api-gateway petclinic-genai-service
```

Today: `"outbound": ["GET (unresolved)", "GET /owners/{ownerId}"]` and four `(unresolved)` rows.

**The corpus is pinned because it had to be.** The three older pins are inbound-only — verified,
the upstreams genuinely make no outbound calls — so no field pin exercised an outgoing address
before 2026-10-17, and every earlier yield figure was weighted toward inbound
(`OI-138`, `field-corpus-has-no-outbound-calls`).

**Re-run `scripts/measure_value_walk.py`** after §1: the no-cap ruling of the previous spec was
measured with the concat arm as a terminal.

## 7. Standing requirements

- **No false positives.** Every ambiguity is `unresolved` with a reason. The danger here is the
  usual one inverted — this spec converts blanks into assertions, so each conversion is a new
  claim about a real system.
- **The resolve layer names no framework and no language.** §4's knowledge lives in a catalog with
  a probe behind it, never in `resolve/`.
- **Every framework claim carries a probe with §5.4 provenance.** §4's three rows are measured
  from the jars; the `getInstances` rule needs its own probe row before it ships.
- **Existing output moves only where a step says so**, and the pins that fix it move in that step.
