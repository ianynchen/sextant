# A configured path prefix reaches the rows it moves

**Status:** design. **Both open decisions were ruled by the user on 2026-10-18** — §3 Option B, and §4 in scope rather than a gap statement, with the reason they gave recorded there because it is a reusable rule and not a one-off.
Written 2026-10-18 after `spring-petclinic-rest` — a PINNED corpus — was found publishing 44
routes without the prefix its own `application.properties` sets.

**What it closes:** `OI-148`, and the COVERAGE §5.1 boundary that states the cause in its own
words — *"`annotation_driven` never touches `resolved_config` … a module that overrides the base
path is published under `/actuator` regardless … **Closes the day an annotation-derived row can
read a configuration key**."*

**What it is not:** a way to evaluate application code that decides prefixes. §4 says what stays
a gap and why.

---

## 0. The measurement

| corpus | rows | what the document says | what the app serves |
|---|---|---|---|
| `spring-petclinic-rest` (**pinned**) | 44 inbound | `/api/owners/{ownerId}` | `/petclinic/api/owners/{ownerId}` |
| `ruoyi-vue-pro` (Boot 2.7.18, 3 modules) | 480 inbound | `/system/user/page` | `/admin-api/system/user/page` |

`spring-petclinic-rest/src/main/resources/application.properties` line 25:

```properties
server.servlet.context-path=/petclinic/
```

**The key is already resolved.** `resolved_config` holds it for all five of that module's
environments, every one `/petclinic/`, source `application.properties`. Nothing has to be
read that is not already read; the value is in the workspace and no consumer of the inbound
path looks at it.

**And the pin records the wrong paths**, which is the sharpest statement of the cost: the
field check — the only always-available evidence for §5's beyond-fixture claims — has 44
expectations that disagree with what the application serves.

---

## 1. What already exists, and is not to be reinvented

**`spring-data-rest` has solved this exact problem** (2O design §2b), and the mechanism is
shipped:

* a catalog word — `base_path: {key: spring.data.rest.base-path}`;
* a reader, `engines/derived_resource.py::_base_path`, with **three outcomes already ruled**:

  | configuration | prefix | row |
  |---|---|---|
  | no environment declares the key | `""` | the framework's own default |
  | every environment agrees | that value | resolved |
  | environments disagree | `"${" + key + "}"` | unresolved, and `record_environment_divergence` files the per-environment values as a question |

* and the ruling behind the third row, from `environment_divergence.py`'s own docstring:
  *"One repository is one resource; a prefix that differs between environments does not make
  it two."*

**So this spec adds no vocabulary for the resolution question.** It reuses `_base_path`'s three
outcomes verbatim, and the only new thing on that axis is that **several keys compose in order**
(§2).

---

## 2. The keys, and how they compose

| key | scope | composes |
|---|---|---|
| `server.servlet.context-path` | the embedded servlet container — EVERY path it serves | first |
| `spring.mvc.servlet.path` | the `DispatcherServlet`'s mapping inside that context | second |
| `spring.webflux.base-path` | the reactive stack, where there is no servlet | first, and alone |
| `management.endpoints.web.base-path` | the Actuator surface only, default `/actuator` | after the two above |

So a module setting `context-path=/petclinic` and `spring.mvc.servlet.path=/api` serves
`@GetMapping("/owners")` at `/petclinic/api/owners`, and its Actuator surface at
`/petclinic/api/actuator`.

**Normalisation is `canonical_http_path`'s, not a second rule.** The measured value is
`/petclinic/` WITH a trailing separator, and the joined result must be `/petclinic/api/owners`
rather than `/petclinic//api/owners`. `domain/paths.py` already owns that for inbound HTTP and
the join feeds it rather than pre-trimming.

**STATED BOUNDARY, unmeasured: the management port.** `management.server.port` moves Actuator
to its own container, where the main context path does NOT apply, and
`management.server.base-path` prefixes it there instead. Nothing here reads either key, and a
module setting them gets a wrong Actuator prefix. It is named rather than guessed because no
probe has measured the interaction — CP-5 rows 7-8 measured `base-path` on one port only.

---

## 3. Where the declaration lives — **RULED: Option B**

The prefix is a property of **the module's server**, not of any one catalog: a Boot app with
`context-path=/petclinic` serves every controller under it, including the rows
`spring-data-rest` and `spring-actuator` derive. Catalogs are flat — there is no `family:` key —
so the two shapes are genuinely different pieces of work and the choice is the user's.

### Option A — each catalog declares the keys that prefix ITS rows

```yaml
# spring-web.yml, spring-mvc.yml, spring-webflux-router.yml, spring-mvc-router.yml,
# spring-actuator.yml, spring-data-rest.yml, …
path_prefix_from: [server.servlet.context-path, spring.mvc.servlet.path]
```

Applied per row by its own `catalog_id`, which every endpoint row already carries.

* **For:** it is catalog data, which is where §8.1 puts framework knowledge; the scope of each
  key is stated by the catalog that knows it; a non-Spring row can never pick up a Spring key.
* **Against:** the same block in roughly ten catalogs, and **every future Spring inbound catalog
  has to remember it** — a catalog that forgets publishes unprefixed paths and nothing fails.
  That is the shape [[removing-the-cause-beats-detecting-it]] warns about: N copies plus a test.

### Option B — one declaration of the SERVER, gated on the module's build

One place names the keys and the stack each belongs to; the pass applies them to every inbound
HTTP row in a module whose build declares the matching starter
(`spring-boot-starter-web` → servlet, `spring-boot-starter-webflux` → reactive), which
`dependency_coordinates` already answers.

* **For:** the prefix is modelled where it actually lives — the server — so it reaches rows from
  catalogs that know nothing about it, including future ones, and there is one place to be right.
* **Against:** "which rows does this server serve" becomes an inference rather than a
  declaration. A module embedding Spring Boot's container AND a second framework's routes would
  prefix both, and only one is right. No corpus in the estate does that; `mall-swarm`,
  `ruoyi-vue-pro`, `jhipster-sample-app`, `spring-petclinic-rest` and `apollo-portal` are each
  single-stack.

**RULED: Option B** (user, 2026-10-18). The prefix is one fact about one server, and Option A
spreads it over ten files that must each remember a fact none of them owns. The against-case is
real and unmeasured, so it ships as a stated boundary rather than dismissed: a module embedding
two server stacks gets one prefix applied to rows the other stack serves. No corpus in the
estate has that shape — all six pins are single-stack — and the boundary is written on the
declaration itself so the next reader meets it there.

---

## 4. `setPathPrefixes` IS in scope — **RULED**, and the reason generalises

**The ruling, in the user's own distinction (2026-10-18):**

> *"the lambda is still config … I said business logic in the other case because the path was
> dependent upon the path being called, a runtime logic, whereas this one is configured"*

That is the line this project needs and did not have written down. `OI-143`'s Apollo case is
runtime logic because the address **varies per call** — 64 callers hand in 64 different paths,
and no single answer exists until a call happens. ruoyi's prefix map is built **once at
wiring time** from values fixed before any request arrives. A lambda is not evidence of
runtime logic; *varying per call* is. Written as code or as YAML, a value settled at startup
is configuration.

### What the facts already hold — measured, not assumed

```java
// WebProperties — the values, as string literals
private Api adminApi = new Api("/admin-api", "**.controller.admin.**");
private Api appApi   = new Api("/app-api",   "**.controller.app.**");

// buildPathPrefixes                         putPathPrefix(Map, Api api, AntPathMatcher m)
putPathPrefix(prefixes, props.getAdminApi(), m);   //   m.put(api.getPrefix(), clazz -> …)
putPathPrefix(prefixes, props.getAppApi(),   m);   //   lambda: m.match(api.getController(), clazz.getPackage().getName())
```

Every step is in the fact stream, verified on
`yudao-framework/yudao-spring-boot-starter-web`:

| step | fact |
|---|---|
| the framework call | `RequestMappingHandlerMapping#setPathPrefixes`, one argument — a **Spring** API, so cataloguable |
| the two literals | `WebProperties#<init>` ordinals 1 and 2: `new Api("/app-api", "**.controller.app.**")` and `new Api("/admin-api", "**.controller.admin.**")`, both plain `string` arguments |
| the prefix | `putPathPrefix` ordinal 4: `Map#put(source 15, lambda …)` where 15 is `api.getPrefix()` |
| the pattern | `lambda$putPathPrefix$0` ordinal 4: `AntPathMatcher#match(source 10, source 13)` where 10 is `api.getController()` and 13 is `clazz.getPackage().getName()` |
| the PAIRING | both halves read the same `api` — parameter 1 of `putPathPrefix`, captured into the lambda (`captures: 2`) — so prefix and pattern pair by receiver identity, never by position |

**The parameter crossing and the pairing already work.** Walking `Map#put`'s key answers on
**two paths**, one per `putPathPrefix` call site, which is the walk's multiplicity with
`_combine`'s coherence rule doing exactly the job it exists for: it cannot pair `/admin-api`
with `**.controller.app.**`, because those two readings never happened together.

### One edge is missing, and it is already a register item

Both halves answer `unresolved(no_writer)`:

```
Map#put's key (the prefix)                  → unresolved(no_writer) × 2 paths
AntPathMatcher#match's pattern              → unresolved(no_writer)
```

`no_writer` is the walk's sixth edge — capability 9.19's `written_by`, deferred as `OI-136`.
The hop that needs it is `getAdminApi()` → the field `adminApi` → the value written into it.
Here the field holds a CONSTRUCTED object, so the shape is
`aload_0; new; dup; ldc; ldc; invokespecial; putfield` — a third shape beside `OI-141`'s
`ldc`-into-field, and the same missing capability behind both.

**So `OI-148` splits by mechanism rather than by judgement:**

* **§2's keys ship now.** They are read from `resolved_config`, which is already populated, and
  need nothing from the walk.
* **`setPathPrefixes` ships with the sixth edge.** Catalog, lambda read and pairing are all
  within reach; the field write is not, and guessing past it would invent a prefix.

Until then the document SAYS SO rather than publishing a path nobody serves: where a module
calls `setPathPrefixes`, Known gaps names the call site and states that the paths below are
served under a prefix this analysis did not apply. That is the interim, not the answer.

### What this measurement does to `OI-136`'s deferral

`OI-136` deferred the sixth edge on two grounds, and this case weakens both:

* *"16 of 756 asked positions, about 2%"* — the denominator is positions **a shipped catalog
  asks about**, and no catalog asks about `Map#put`'s key today. The same bounded-measurement
  mistake as `OI-143`'s *"nothing in the 27 measured corpora reaches it"*
  ([[nothing-in-the-corpus-is-about-the-corpus]]).
* *"And it costs no endpoint … a field-held destination costs the ADDRESS, never the
  endpoint … the row publishes with `path` NULL at `unresolved`"* — true for a destination,
  **false here**. These 480 rows publish a path that LOOKS resolved and is wrong by a prefix.
  Nothing reads as unresolved, so nothing tells a reader to doubt it.

That is recorded on `OI-136` itself, where the mechanism lives, rather than restated here.

## 5. What moves, and in the step that moves it

* **`spring-petclinic-rest`'s 44 pinned routes** gain `/petclinic`, and the pin is re-recorded
  in the same commit, reviewed the way `OI-32` requires: the rows looked at, the new spelling
  agreed, and the agreement recorded.
* **No other pin moves, and that is measured rather than assumed.** `resolved_config` was
  queried on all six pins for all six keys in §2 plus `management.server.port` and
  `management.server.base-path`:

  | pin | rows for any prefix key |
  |---|---|
  | `spring-petclinic-rest` | `server.servlet.context-path = /petclinic/` × 5 environments, all agreeing |
  | `jhipster-sample-app`, `mall-admin`, `apollo-portal`, `petclinic-api-gateway`, `petclinic-genai-service` | **none** |

  So one pin moves, by one key, with every environment in agreement — §1's second outcome and
  not the divergent third, which no corpus exercises. `management.server.port` appears in no
  corpus either, which is why §2's boundary stays unexercised as well as unmeasured.
* **Fixtures:** none sets a context path today, so a fixture that does is part of the work
  (§4.1 — the assertion on derived rows comes first and must fail first).

---

## 6. Cost (§8.7)

One read of `resolved_config` per resolve — a table the pipeline already loads five times, and
whose whole content is small (100 rows on `spring-petclinic-rest`) — folded once into
`key -> {environment: value}`, which is `_config`'s existing shape. The pass is then one string
join per inbound HTTP row. Nothing walks, nothing re-queries per row.

**Where it must run:** after `derive_endpoints` and **before** every pass that copies a path —
`record_roots`, `record_routing_conflicts`, `record_self_exchange`. A prefix applied after those
would leave a root and a conflict keyed on the unprefixed path, which is `OI-28`'s shape.

---

## 7. Standing requirements

* **No wrong row.** A prefix is applied only from a value every environment agrees on;
  disagreement publishes the expression and files the divergence question, which is §1's third
  outcome unchanged.
* **The pin moves in this step**, reviewed, with the review recorded.
* **A fixture asserts the derived rows** before the mechanism exists (§4.1).
* **Re-run the field check**, all six pins, and state which moved.
