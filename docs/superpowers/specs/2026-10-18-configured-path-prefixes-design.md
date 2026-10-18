# A configured path prefix reaches the rows it moves

**Status:** **BUILT, both halves** — §2's configuration keys on 2026-10-18 (PR #46) and §4's
`setPathPrefixes` the same day, once the walk's sixth edge landed. §8 records what was measured
and the ONE correction §4 needed. **Both open decisions were ruled by the user on 2026-10-18** — §3 Option B, and §4 in scope rather than a gap statement, with the reason they gave recorded there because it is a reusable rule and not a one-off.
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

## 3. The declaration — **RULED: one table of (key, framework, version), picked per module**

The prefix is a property of **the module's server**, not of any one catalog: a Boot app with
`context-path=/petclinic` serves every controller under it, including the rows
`spring-data-rest` and `spring-actuator` derive. Catalogs are flat — there is no `family:`
key — so one declaration of the server beats the same block in ten catalogs that must each
remember a fact none of them owns. **Option B, ruled by the user 2026-10-18.**

Two gates were proposed and both rot. The user's ruling is the third shape, and it is the
only one that is CORRECT across versions rather than merely loud when stale.

### Why not the build coordinate

Measured: `spring-petclinic-rest` — the one corpus that sets a prefix key — declares
**`spring-boot-starter-webmvc`**, because Boot 4 renamed `spring-boot-starter-web`. A gate
naming the old spelling is inert exactly where it matters, which the register already has a
case of (`gateway-detect-4x-coordinate`: a coordinate list that changes nothing either way).

### Why not the bare key either

The user's objection, and it is right: *"the key can change based on spring version"*. It has
— `server.context-path` became `server.servlet.context-path` in Boot 2.

### The ruling: record the key WITH its framework and version, and pick by what the module uses

```yaml
prefixes:
  - framework: org.springframework.boot
    versions: "[2.0,)"          # measured at 2.7.18 and 4.1.1 — CP-38
    stack: servlet
    keys: [server.servlet.context-path, spring.mvc.servlet.path]   # composed in this order
  - framework: org.springframework.boot
    versions: "[2.0,)"
    stack: reactive
    keys: [spring.webflux.base-path]
```

**Measured, from the framework's own bytes** (CP-38): Boot ships
`META-INF/spring-configuration-metadata.json` naming every property it reads, with
deprecations and their replacements. At **2.7.18** and **4.1.1** both spellings above are
declared and neither is deprecated; 2.7.18 also records `server.servlet.path` as deprecated in
favour of `spring.mvc.servlet.path`. What moved between those versions is the JAR that
declares them — `spring-boot-autoconfigure` to `spring-boot-web-server`/`spring-boot-webmvc` —
not the names.

**Only measured rows are declared.** Boot 1's spellings are not in the table: no Boot 1 jar
was opened, and §5.4 does not let a version scope be written from recollection. A Boot 1
module therefore publishes unprefixed paths exactly as today until someone measures and adds
the row — a known absence, not a guess.

### Picking the row

| the module's framework version | how the row is chosen |
|---|---|
| recorded | it selects the row. Precise, and the ordinary case |
| **not** recorded | every row for that framework is eligible, and the key PRESENT in the module's own `resolved_config` decides — a module configures one Boot generation, so at most one spelling can be there |
| two spellings present at once | a contradiction in the module's own configuration, reported rather than resolved by preference |

**The version is already in the workspace.** The `module` fact carries
`dependency_versions` as `coordinate -> version`: `spring-petclinic-rest` answers **4.1.1** on
eleven coordinates and `mall-swarm/mall-admin` **3.5.14**. No new extraction is needed.

### Where the version is NOT recorded, the answer is to follow the chain — ruled

`ruoyi-vue-pro`'s modules record no Boot version at all, because their versions come from its
own `yudao-dependencies` BOM and a `${revision}` property and the detector follows neither.
The user's ruling on that, 2026-10-18:

> *"it still applies, as it eventually depends on a version of spring anyways. It aligns with
> our design that we should trace through the dependency chain rather than cap at a level"*

Which is `OI-149`'s principle one layer out — *the reactor is the whole tree* — and the
standing instruction already recorded for BOMs: track versions down the chain, not a few
levels. So the fallback above is an INTERIM, not the design: the direction is that
`dependency_versions` answers for a module whose version lives two hops away, which is
`OI-139` (imported BOM chains, Major, open) and `OI-8` (a library version only a parent
manages).

**It changes nothing for `ruoyi` in this spec, and that is worth stating plainly rather than
leaving implied: `ruoyi` sets NONE of these keys** — verified on all three built modules,
`resolved_config` holds no row for any of the four. Its `/admin-api` comes from
`setPathPrefixes` (§4) and waits on the sixth edge. The chain work raises precision for
modules that DO set a key and hide their version; today the corpus has none.

## 4. `setPathPrefixes` — **RULED in scope, and the blocker cleared 2026-10-18**

**The ruling, in the user's own distinction:**

> *"the lambda is still config … I said business logic in the other case because the path was
> dependent upon the path being called, a runtime logic, whereas this one is configured"*

`OI-143`'s Apollo case is runtime logic because the address **varies per call** — 64 callers
hand in 64 paths, and no answer exists until a call happens. ruoyi's prefix map is built
**once at wiring time** from values fixed before any request arrives. A lambda is not evidence
of runtime logic; *varying per call* is.

### The values resolve. Measured, after the sixth edge landed

What blocked this was one walk edge, and `2026-10-18-the-sixth-edge-design.md` shipped it.
Re-measured on `yudao-framework/yudao-spring-boot-starter-web` the same day:

```
Map#put's key              →  "/admin-api"              "/app-api"
AntPathMatcher#match arg 0 →  "**.controller.admin.**"  "**.controller.app.**"
```

Both halves of the declaration are now readable. What is missing is a CONSUMER.

### The shape, read off the facts rather than assumed

```java
mapping.setPathPrefixes(prefixes);                       // the framework call
prefixes.put(api.getPrefix(), clazz ->                   // one entry per prefix
        clazz.isAnnotationPresent(RestController.class)
        && matcher.match(api.getController(), clazz.getPackage().getName()));
```

| what | the fact |
|---|---|
| the installer | a call to `RequestMappingHandlerMapping#setPathPrefixes` — Spring's own API |
| an entry | `Map#put` whose argument 1 is a `lambda` (one such site in the module; the other seven `Map#put` sites carry string keys and no lambda) |
| the prefix | that site's argument 0, resolved by the walk |
| the predicate | inside the lambda body: `AntPathMatcher#match(pattern, …)`, pattern resolved by the walk |
| that it IS a package predicate | `match`'s argument 1 traces to `Package#getName` whose receiver traces to `Class#getPackage` — measured at ordinals 2, 3, 4 of that lambda |

**The last row is the discriminator and the reason this is not a guess.** A module has other
`Map#put` calls and other `match` calls; what identifies a prefix declaration is a lambda that
matches a pattern against *a class's package name*. Without that check any two-argument
`match` would be read as a prefix rule.

### What the pass does

1. **Gate:** the module calls the installer. No call, no prefixes — and no inference from a
   `Map#put` alone, which is what keeps an unrelated map out.
2. **Pair:** for each entry site, the prefix from argument 0 and the pattern from the lambda's
   `match`. They pair by the SITE, not by order, so two entries cannot cross.

   > **CORRECTED AT BUILD TIME, 2026-10-18.** Pairing by site does not hold for the corpus
   > this item exists for — see §8, which has the measurement and what replaced it. The
   > REQUIREMENT ("two entries cannot cross") is unchanged and met.
3. **Apply:** an inbound row whose handler's class package matches the pattern takes the
   prefix, composed after §2's keys — `/admin-api` is inside the context path, not beside it.

**Ant matching over a package name**, with `.` as the separator, which is how Spring itself
reads these patterns (`new AntPathMatcher(".")` in the source above): `*` is one segment and
`**` is zero or more. Implemented and unit-tested rather than approximated by a prefix test —
`**.controller.admin.**` must not match `…controller.administration.user`.

### What it still will NOT do

**Attribute a prefix to one instance.** `getPrefix()` resolves to both `/admin-api` and
`/app-api` because the walk has no instance identity (the sixth edge's §4). ~~so the pairing
above comes from the ENTRY SITE rather than from knowing which `Api` object each read. That is
sound here — each `put` is its own site~~ — **and that was wrong: ruoyi has one `put` site, so
one site's prefix and another's pattern CAN meet there.** What forbids the crossing is the
PATH, not the site (§8). Instance identity is still not needed and is still not claimed.

**Read a predicate that is not a package match.** A prefix whose predicate tests an annotation,
a type or a name resolves to no pattern, and its entry contributes nothing rather than
guessing. The row then publishes its unprefixed path exactly as today, and Known gaps says the
module declares a prefix this analysis did not apply.

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

---

## 8. What was built, and what was measured

**§2 — the configuration keys** (PR #46). `spring-petclinic-rest`'s 44 pinned inbound rows
publish under `/petclinic`, the pin re-recorded in the same commit and the change asserted to
be the prefix alone. No other pin moved.

**§4 — `setPathPrefixes`**, built 2026-10-18 after the sixth edge
(`2026-10-18-the-sixth-edge-design.md`) made ruoyi's getter chain resolve.

| what | where |
|---|---|
| the six symbols, dotted, with a `measured:` block | `catalogs/server-models/spring-boot.yml`, `class_path_prefixes` |
| the reader — gate, map identity, entries, pairing, Ant matching, application | `resolve/path_prefix.py` |
| several positions resolved on ONE coherent path | `values.resolve_positions` (new) |
| the fixture, seven controllers: four prefixed, three that must NOT be | `fixtures/orders-pathprefixes` |
| eight guards | `path_prefix.a-prefix-pairs-with-the-pattern-on-ITS-OWN-path`, `…an-entry-belongs-to-the-map-the-installer-RECEIVES`, `…a-prefix-reaches-only-the-classes-the-predicate-ADMITS`, `…an-UNRESOLVED-prefix-is-refused`, `…a-SUBCLASS-of-the-mapping-installs-prefixes-too`, `…the-ENTRY-is-not-matched-on-the-maps-static-type`, `…a-pattern-segment-matches-a-WHOLE-segment`, `…a-package-predicate-is-what-identifies-a-declaration` |

### Three wrong rows the first build could publish, found by review and fixed

The reader as first written gated on "does this module call the installer anywhere" and then
read every package-keyed predicate map it could find. Measured on probe modules, that
published three addresses no server serves — an uninstalled `auditCategories()` map as
`/AUDIT/…`, a `${api.ext-prefix}` placeholder verbatim, and `/admin-api/fn/items` for a
functional route whose class merely sat in a prefixed package while `RouterFunctionMapping`
has no prefixes at all. `docs/open-issues.md`'s `OI-148` entry has the table, the fix for each
and the guard that pins it; the fixture now carries a controller per case asserting the path
it keeps. Two under-reports were fixed with them (a `LinkedHashMap`-typed variable, a
subclassed mapping), and one is filed rather than fixed: `OI-150`, the walk's missing
lambda-CAPTURE edge, which is a seventh edge and the same shape of work as the sixth.

**Measured on `ruoyi-vue-pro`, the three modules with a scan — 480 inbound rows:**

| module | inbound | `/admin-api` | `/app-api` | unprefixed |
|---|---|---|---|---|
| `yudao-module-system` | 212 | 209 | 3 | 0 |
| `yudao-module-infra` | 116 | 113 | 3 | 0 |
| `yudao-server` | 152 | 144 | 0 | 8 |

Every one of the 480 published a bare `/system/...`-style path before. The 8 that still do are
`yudao-server`'s `DefaultController`, in `cn.iocoder.yudao.server.controller` — a package
neither pattern names, and one the app genuinely serves unprefixed. The figures are identical
before and after the review fixes below, which is the point of them: the three wrong rows they
refuse are not rows this corpus had. The gate is 4159 tests, the guard registry is **175
killed / 0 survived / 0 unmeasurable**, and all six field pins are unchanged.

### The correction: pairing is by PATH, not by site

§4 above said the prefix and its pattern pair by the entry SITE, reasoning that "each `put` is
its own site". **Measured, ruoyi has exactly one `put` site** — `putPathPrefix`, a helper called
once per API group — so the walk answers both prefixes and both patterns at that one site and
per-site pairing is a cross product:

```
/admin-api + **.controller.admin.**   OK            /admin-api + **.controller.app.**     WRONG
/app-api   + **.controller.app.**     OK            /app-api   + **.controller.admin.**   WRONG
```

The two wrong ones would serve a whole package family under another family's prefix, at
`resolved`. What separates them is the walk's own coherence rule: both values leave through the
same context — the two `new Api(…)` sites in `WebProperties#<init>`, reached through the sixth
edge — and a pair that chose differently there is refused. `resolve_positions` is `resolve_site`
generalised from one site's slots to several sites' positions; the coherence rule is the
existing one, unchanged.

Declared as a deviation under GUIDELINES §1.1 rather than made quietly: the mechanism changed,
the requirement §4 states ("two entries cannot cross") did not.
