# A configured path prefix reaches the rows it moves

**Status:** design, with **one decision open** (§3) that is the user's and is not picked here.
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

## 3. THE OPEN DECISION — where the declaration lives

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

**Recommended: Option B**, because the prefix is one fact about one server and Option A spreads
it over ten files that must each remember a fact none of them owns. The against-case is real
and unmeasured, so it is stated as a boundary rather than dismissed: a mixed-stack module gets
one prefix applied to rows the other stack serves.

---

## 4. Out of scope, named so the closure list stays honest

**`RequestMappingHandlerMapping.setPathPrefixes` is NOT derived.** `ruoyi-vue-pro` prefixes
`/admin-api` and `/app-api` by handing the mapping a map of prefix → predicate:

```java
mapping.setPathPrefixes(pathPrefixes);     // "/admin-api" -> clazz -> matcher.match("**.controller.admin.**", clazz.getPackage().getName())
```

The VALUES are configuration (`WebProperties.adminApi`, defaulting to `/admin-api`). Which
classes receive which prefix is a lambda over package names, and evaluating it is application
logic — the thing this project does not do.

**What it gets instead: a gap statement.** Where a module calls `setPathPrefixes`, the document
says so in Known gaps, naming the call site, so a reader is told the paths below are served
under a prefix this analysis did not apply. A statement, never a guessed path — publishing
`/system/user/page` for something served at `/admin-api/system/user/page` is the failure, and
publishing it *silently* is the part this fixes.

`OI-148` therefore narrows rather than closes, and the entry says which half closed.

---

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
