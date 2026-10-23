# A bean that exists in some environments only — design

**Status: BUILT 2026-10-22 (branch `cov/conditional-beans`) — all three decisions ruled (§6),
and the rulings made while building it recorded in §7.** Each section below states what was
designed and then what was built; where they differ, the built form is the one given, with
the reason. Replaces the special case PR #61
built (`conditional-controllers`: conditions on the class of an INBOUND handler only) with the
general rule it was an instance of, and closes `OI-108` (conditional `@Bean`s) on the way.
The user's ruling that prompted it, recorded as a standing rule: *a generalized approach
over special handling* — a controller is a bean, and `@Profile`/`@ConditionalOn…` on ANY bean
means Spring never registers it in an environment where the condition fails.

**The general concept.** A *conditional bean* is a bean whose registration Spring decides
per environment: a class carrying a condition (component-scanned or not), a `@Bean` method
carrying one, or a `@Bean` method inside a configuration class carrying one. Whatever
Sextant derives from such a bean — a row whose code lives in it, or a call whose callee is
it — exists only where the bean does.

---

## 1. Measured first: the general case across every analysed real project

43 analysed modules under `examples/` (apollo, jhipster, mall, mall-swarm, ruoyi-vue-pro,
spring-petclinic-rest, spring-petclinic-microservices). Harness:
`scripts/probes/measure_conditional_beans.py` (read-only over each workspace).

**How common conditional beans are**

| | count |
|---|---|
| classes carrying a condition | 175 (70 of them configuration classes) |
| `@Bean` methods carrying a condition | 195 |
| `@Bean` methods inside a conditional configuration class | 298 |

| condition annotation | uses | evaluable from configuration? |
|---|---|---|
| `@ConditionalOnProperty` | 147 | yes (CP-43) |
| `@ConditionalOnMissingBean` | 110 | no — depends on the other beans registered |
| `@ConditionalOnClass` | 58 | no — depends on the classpath |
| `@Profile` | 49 | yes (CP-42) |
| `@ConditionalOnBean` | 46 | no |
| `@Conditional(…)` | 10 | no — a `Condition` class |
| `@ConditionalOnSingleCandidate` | 9 | no |

**Where they reach what Sextant publishes**

| path from a conditional bean | measured | today |
|---|---|---|
| a row whose own code is in a conditional class or method | 2 rows (both inbound — Apollo's `HomePageController`, one websocket handler) | stated since PR #61 for inbound only |
| a row whose code is in a class a conditional `@Bean` constructs | 13 rows (10 scheduled jobs, 2 outbound, 1 inbound); 0 of them also constructed unconditionally | not stated |
| a call site whose candidates include a conditional bean, outside that bean | 724 sites: **210 narrowed** (151 on a trace), 514 resolved (31 on a trace) | not stated |
| …of the 210 narrowed, candidates under evaluable conditions only | 53 | — |

**The call graph is where conditional beans matter.** 15 rows have their code in a
conditional bean; 210 dispatch sites choose among implementations that exist in different
environments. Four of them, as the corpus has them:

| module | call site | candidates and their conditions |
|---|---|---|
| ruoyi `yudao-module-system` | `WebSocketSenderApiImpl#send` | `KafkaWebSocketMessageSender`, `RabbitMQWebSocketMessageSender`, `RedisWebSocketMessageSender`, `RocketMQWebSocketMessageSender` — each `@ConditionalOnProperty` |
| Apollo `configservice` | `HomePageController#listAllServices` | `DatabaseDiscoveryService`, `KubernetesDiscoveryService`, `SpringCloudInnerDiscoveryService` — each `@Profile`; `DefaultDiscoveryService` unconditional |
| Apollo `portal` | `ServerPermissionOpenApiService#checkUserExists` | `LdapUserService`, `OidcLocalUserServiceImpl`, `SpringSecurityUserService` — `@Profile` + `@ConditionalOnMissingBean`; `DefaultUserService` `@ConditionalOnMissingBean` |
| spring-petclinic-rest | repository calls | `Jdbc…RepositoryImpl`, `Jpa…RepositoryImpl` — each `@Profile` |

Today each reads `narrowed` with N candidates, and the document cannot say that in an
environment with `ruoyi.websocket.sender-type=kafka` exactly one of them runs — the trace
reaches Kafka there and Redis elsewhere.

### As built — what the pass found on four real modules

Fresh analyses of copies of the modules, read from the new tables and views
(`bean_conditions`, `bean_presence`, `symbol_beans`, `endpoint_conditions`,
`candidate_presence`). The harness above and these counts agree where they overlap: for the four
modules below it found 0, 2, 6 and 0 rows tied to a conditional bean by way 1 and 2, and
the views found the same.

| module (environments it resolves) | beans carrying a condition (class / factory / configuration) | rows stating one: inbound / outbound / schedule / error handler, of all such rows | narrowed call sites given per-environment lines, of all narrowed | beans decided at `partial` | beans left `unresolved`, and why |
|---|---|---|---|---|---|
| Apollo `apollo-portal` (6: `default`, `github`, three `ldap-…-sample`, `oidc-sample`) | 63 (13 / 18 / 47; one bean can be several kinds) | 0 of 288 / 0 of 76 / none / none | 142 of 193 | 3 | 14: 9 under an `@Conditional(…)` class this analysis does not evaluate, 5 inherited bodies no bean runs |
| ruoyi `yudao-module-system` (1: `default`) | 63 (11 / 10 / 45) | 0 of 212 / none / 2 of 2 / none | 11 of 36 | 7 | 25: 22 `@ConditionalOnClass`, 1 `@ConditionalOnSingleCandidate`, 3 inherited bodies no bean runs |
| ruoyi `yudao-spring-boot-starter-websocket` (1: `default`) | 56 (15 / 8 / 35) | 2 of 2 / 2 of 2 / 2 of 2 / none | 8 of 21 | 7 | 15: 12 `@ConditionalOnClass`, 3 inherited bodies no bean runs |
| `spring-petclinic-rest` (5: `default`, `h2`, `hsqldb`, `mysql`, `postgres`) | 19 (16 / 0 / 3) | 0 of 44 / none / none / 0 of 3 | 34 of 34 | 0 | 0 |

These are the counts of the first complete build. Two rules were added after the measurement
showed what it got wrong, and they moved the figures for the modules they touch (§2d and
§2a's last paragraph); the effect is measured separately, here, so the table above stays what
it was:

| what moved | before | after |
|---|---|---|
| `spring-petclinic-rest`: the 34 repository call sites, each answered by `Jdbc…Impl` or `Jpa…Impl` | every site read "in `default`, `h2`, `hsqldb`, `mysql`, `postgres`: none of them" — the document said no implementation exists anywhere, while `application.properties` sets `spring.profiles.active=h2,spring-data-jpa` | every site also names the framework-generated implementation of the Spring Data interface: present in `default`, "not evaluated" in the four profile environments, with the reason. Seven interface beans were found |
| Apollo `configservice` `GET /` (PR #61's line) | "holds in 6 of 8 environments — not in `default`, `github`" | "holds in 6 of 8 environments; not evaluated in `default`, `github`", with the reason: the active profiles come from `${apollo_profile}`, which this module does not fill |
| `apollo-portal` `ServerPermissionOpenApiService#checkUserExists`, candidates `LdapUserService`, `OidcLocalUserServiceImpl`, `SpringSecurityUserService` | absent (`false`, resolved) in all six environments — a decided answer where the answer was unknown | not evaluated in all six, for the same `${apollo_profile}` reason. The bean-by-environment verdicts of the whole module went from 228 `false` / 84 `unresolved` to 12 `false` / 300 `unresolved` |
| `jhipster-sample-app` | its unconditional Spring Data repositories were no candidate of any call | 5 interface beans; 69 call sites name the framework's implementation in their "answered by" line |

On none of the four modules does a narrowed site have DIFFERENT candidates in two environments
that are both decided (0 vary in the first build); what differs, after the active-profiles
rule, is decided in one environment and open in the others (`spring-petclinic-rest`'s
`default` against its four profile environments). The fixture `orders-service` shows the
decided case (`/notify`: `LogNotificationSender` in `default`, `KafkaNotificationSender` in
`prod`). The documents state what is there, not a difference that is not.

## 2. What is published

One structured table, keyed by the BEAN, read by everything a bean derives:

```
bean_conditions
bean | bean_kind | via | kind | expression | environment | holds | resolution | evidence
```

* `bean` is the class symbol (the registered type) — for a `@Bean` factory, the class it
  constructs; `bean_kind` says which registration route the row belongs to: `class` (a
  scanned class), `factory` (the `@Bean` method), `configuration` (the enclosing configuration
  class's condition, applied to that method's bean), `constructed` (a plain `new` outside any
  factory), `inherited` (a body the bean runs but a superclass or interface declares, §2a) or
  `proxy` (an interface the framework implements, §2a). `via` is the factory method (for an
  inherited body, the heir class) and NULL for a scanned class or a proxy. A class registered
  more than one way exists wherever any of its routes registers it — §2a, and the
  `bean_presence` view.
* `kind`, `expression`, `holds`, `resolution`: PR #61's encoding (`profile`, `property`,
  `other`; CP-42, CP-43; `other` verbatim and `unresolved`), plus `presence` (§2c). A route
  with no condition is one row per environment with `kind` NULL.
* Rows (endpoints in both directions, scheduled work, error handlers) and call-edge
  candidates find their conditions by JOINING on the bean their code lives in — no row copies
  them. The one rule for "which bean is this code in" is the view `symbol_beans`: a symbol is
  its own bean where the pass wrote rows for it (a lambda a factory creates, an inherited
  body), otherwise its owner class. `endpoint_conditions` became a VIEW over that join, so
  PR #61's documents and the system tier read what they read before, now for outbound rows
  too; it gained the columns `caller`, `via`, `bean_kind` and `bean`, appended after PR #61's.
* Five objects came of it, all exported ([D01](../../components/D01-graph-schema.md)):
  the table `bean_conditions`; the view `bean_presence(bean, environment, holds, resolution,
  evidence)`, where each bean exists; the view `symbol_beans`; the view `candidate_presence`
  (§3); and the table `interface_beans` (§2a). `GRAPH_SCHEMA_VERSION` moved 3 to 4.

### 2a. Which classes are beans, and which conditions apply — Spring's rule, read off its jar

Spring evaluates a condition at the point it REGISTERS a bean, and the point decides which
annotations count. CP-44 read this off the jars (spring-context and spring-beans 7.0.9,
spring-boot-autoconfigure 4.1.1) before anything was built, and confirmed the table:

| how the bean is registered | conditions Spring evaluates | route (`bean_kind`) |
|---|---|---|
| a class found by component scan (a stereotype: `@Component` and the annotations built on it) | the class's own | `class` |
| a class registered by `@Import` or as a configuration class | the class's own | `class` |
| a `@Bean` method | the method's own, AND its configuration class's (a skipped configuration registers none of its `@Bean`s) | `factory`, with the configuration's conditions as `configuration` |
| a class merely CONSTRUCTED inside a `@Bean` method | the factory method's (as above) — the class's own annotations are not consulted on this route | `factory` |
| an INTERFACE the framework implements at run time (Spring Data repositories) | the interface's own | `proxy` |

So a `bean_conditions` row names the class whose code runs: a conditional scanned class
(`class`), or the class a conditional `@Bean` method constructs and returns — the constructed
classes assignable to the method's declared return type (`type_hierarchy`), a structural rule,
never a model of what a builder does (`factory` or `configuration`). The configuration class's
conditions apply to a `@Bean` method of any enclosing class, not only one carrying
`@Configuration`: a `@Bean` is loaded only from a class the container processed as a
configuration, after evaluating that class's conditions.

**A class registered more than one way exists wherever ANY of its routes registers it** (ruled
2026-10-22, replacing "registered two ways, so `unresolved`", which was over-caution and not a
decision of the user): each scan, import or `@Bean` registers its own definition, so the
verdict is OR across routes and AND across one route's conditions. Measured as the trigger: 6
of the 8 beans `apollo-portal` first read as `unresolved` were several mutually exclusive
conditional factories. Every route of a class with at least one conditional route is written
to `bean_conditions` — conditional routes as their evaluated condition rows, an unconditional
bean route (a stereotype class or `@Bean` with no condition) as a condition-less row holding
`true`, a plain `new` outside any `@Bean` body as a condition-less `constructed` row,
`unresolved` — and the view `bean_presence(bean, environment, holds, resolution, evidence)`
folds them: `true` where any route holds, `false` where every route fails, `unresolved`
otherwise (a plain `new` leaves the class `unresolved` wherever no other route decides `true`,
since which bean's code path runs it is not known). The resolution is the weakest of what
decides the outcome: `unresolved`, then `partial`, then `resolved`.

**What else is a route, as built:**

* **A composed annotation counts.** An annotation is a stereotype, or a condition, when it IS
  one or is meta-annotated by one, transitively — through the module's own annotation types
  and dependency annotation types whose header the classpath read recorded
  (`type_header` facts). Nothing lists `@AutoConfiguration` by name: its header records
  `@Configuration`, which is why it composes. Conditions placed on a composed annotation
  apply to its users. A condition annotation is never composed through what it is itself
  built on — `@ConditionalOnProperty`'s own header records `@Conditional`, and composing
  through it would add an unevaluated `other` row to every direct use — so the condition
  annotations are the vocabulary's leaves. An annotation type whose header was not read
  composes nothing (a stated limit, §4).
* **A lambda a factory creates is the factory's code.** A lambda body whose creating method
  (a `dynamic` call edge from that method, read off `call_edges`, never parsed from the
  `lambda$name$N` spelling) is a `@Bean` method belongs to that factory's route, with `via`
  set to the method; so does a `new` inside such a lambda. Its bean is the lambda body's own
  symbol. Found on ruoyi's websocket starter, whose inbound handler is exactly such a lambda.
* **An inherited body takes the OR of the beans that run it.** A body declared in an abstract
  class or as an interface default method has no bean of its own; it runs as part of every
  bean whose class resolves that method to it, found through the module's own method
  resolution (`method_resolution`, the same `Dispatch.resolve` the call graph uses) — structural
  and exact, no name parsing. The pass writes it as a bean (`bean_kind = inherited`) whose
  routes are those beans' routes, so its presence per environment is the OR of theirs, and an
  unconditional bean among them makes it present everywhere. A body no bean resolves to reads
  `unresolved` with "no bean of this module runs this inherited body". This changed the
  answer on 11 of 11 conditional call sites of ruoyi's system module, which had read "exists
  everywhere" because the abstract owner carries no condition.
* **A bean the framework implements for an interface is a route** (`proxy`; CP-46,
  spring-data-commons 4.1.1). An interface assignable to `org.springframework.data.repository.Repository`,
  or carrying `@RepositoryDefinition` (itself, a meta-annotation, or an interface it
  extends), and not carrying `@NoRepositoryBean` itself (not inherited), is registered by
  Spring Data's scanner, with its own conditions evaluated (the scanner is Spring's, whose
  `isConditionMatch` CP-44 row 4 lists). Its implementation is a runtime proxy with no body of
  the module, so `candidate_presence` lists it as an extra candidate of a call whose named
  type the interface is assignable to — "a framework-generated implementation of
  `SpringDataOwnerRepository`" — and `call_edges` is untouched. The vocabulary is the bean
  model's `interface_registrations`. Every such interface, conditional or not, is written to
  the table `interface_beans(bean, type)`, one row per type it is assignable to.
  Whether scanning runs, and from which packages, is the module's configuration and is not
  read: every admitted interface of the module is treated as scanned.

**Framework knowledge is data.** PR #61 declared the condition annotations on the two HTTP
catalogs (`matches.mapping.conditions`); that was the special case. They moved to the Spring
bean model (`catalogs/bean-models/spring.yml`, D02 §1c), beside `@Bean` and `@Qualifier`,
together with the configuration annotation, the stereotype set, the presence rule's
attributes and the interface registrations — read by one resolve pass for every bean, naming
no framework in code. The vocabulary is the CONTAINER's, so it applies through every Spring
catalog: all 44 catalogs whose `detect.coordinates` names an `org.springframework` artifact
name `bean_model: spring`, and `tests/architecture/test_catalog_bean_model.py` pins that, so
a module cannot silently lose its conditions for want of one line in a catalog. The pass reads
the union of the models the module's catalogs name. A repo-local catalog that still carries
`matches.mapping.conditions` has it ignored (D02's migration note).

### 2b. Probes

CP-44 (new; six rows as built): `OnBeanCondition` — the type an unannotated `@ConditionalOnMissingBean` on a
`@Bean` method deduces (the return type), how `value`/`type`/`name` match, and that the
search sees definitions registered so far (the processing-order caveat decision 2's `partial`
states); `ConditionEvaluator` — the registration points that consult it (scanning, import,
`@Bean` methods, configuration classes), confirming §2a's table; which annotations make a class
a scanned bean (row 5); and how a scanned class is named (row 6, for the presence rule's
`name` criterion). Two more probes were added when building showed what was missing: CP-45
(§2d, the keys that name the active profiles and Boot's rule for them) and CP-46 (§2a, the
repository scanner's filters). CP-42 and CP-43 stand. One claim in CP-44 row 4 is a documented
claim and not a reading of the bytecode: that an imported configuration class is skipped only
if every importer is (the probe shows the tracking wrapper consults the importers, not
whether it means all or any).

### 2c. `@ConditionalOnMissingBean` / `@ConditionalOnBean` (decision 2, as ruled and built)

Evaluated per environment AFTER the profile and property conditions, against the module's
own bean definitions: the scanned classes and `@Bean` methods of §2a, each matched by the
class it registers (a factory, by its declared return type) and named as the framework names
it (CP-44 row 6: a `@Bean`'s name, else the method name; a scanned class's by the stereotype's
name attribute, else its simple name uncapitalised). Rows are written with `kind = presence`
and an expression `{annotation, mode, types, names, annotations}`.

* **What a condition asks**, from CP-44 rows 1 and 2: `value` and `type` are one set of types,
  `name` and `annotation` are separate criteria; `@ConditionalOnBean` needs every listed
  criterion matched, `@ConditionalOnMissingBean` fails if any is. An unannotated use on a
  `@Bean` method checks the method's return type; on a class it names nothing and the
  container refuses it.
* **A competitor is a definition that registers a DIFFERENT class.** The condition asks
  whether *another* bean of the type exists, so two routes of the same class never compete
  (found at review: `DefaultUserService`, registered by an `@ConditionalOnMissingBean`
  factory and by an `@ConditionalOnClass` one, was `unresolved` though the class exists
  either way). A type matches the competitor's type or a supertype of it (`type_hierarchy`),
  a name its bean name, an annotation an annotation its own type carries. A condition on a
  class is judged before that class's own factory methods are read (CP-44 row 4), so they
  are no competitor of it.
* **A competitor exists where all of its conditions hold**, its own presence conditions too, so
  verdicts are settled together, in memory, in rounds until nothing changes. `missing`
  fails where a criterion has a competitor that exists, holds where none has one that exists
  or could, and is `unresolved` otherwise; `present` is the mirror. A competitor whose
  existence there is `unresolved` leaves the verdict `unresolved`.
* **A loop is settled by its shape**, with the reason the model carries (`order_reason`,
  `present_cycle_reason`). A loop of `present` conditions alone FAILS everywhere: the first
  one the container reads finds the others not yet registered (CP-44 row 3), so no order lets
  one in. A loop holding a `missing` one keeps whichever is read first, which the code does not
  say, so it is `unresolved` ("Spring keeps whichever is processed first; the order is not in
  the code").
* **Every decided verdict is `partial`**, with the reason *decided from this module's beans
  only; a library or the processing order may differ* — the container's search sees the
  definitions registered SO FAR, and one configuration class's two `@Bean` methods can decide
  whether both register by the order they are processed in. Every verdict's evidence names
  its competitors as structured JSON after `; competitors: ` — `[{bean, via, holds}]`, with
  a `note` where a competitor's conditions name a profile that no environment of the module
  is ("profile `ldap` is named but this module has no `ldap` environment"). The note is left
  off a profile that is active, or may be, in some environment (§2d).
* **The view `bean_presence` carries it**: a verdict resting on a `partial` one is `partial`
  too.

Not read, and stated in §4: `ignored`/`ignoredType`, `search`, generic containers, `@Bean`
aliases beyond the first name.

### 2d. An environment's active profiles are read from configuration (ruled 2026-10-22)

PR #61 took an environment's active profile to be the name of its file, and nothing else.
Measuring the first complete build on `spring-petclinic-rest` showed what that cost: its
`application.properties` sets `spring.profiles.active=h2,spring-data-jpa`, so in every
environment the Spring Data JPA repositories exist, and the document said no implementation of
a repository exists anywhere. The same rule read Apollo's `ldap` and `oidc` user services as
absent in every environment although `spring.profiles.active=${apollo_profile}` could activate
them — a decided answer where the answer is not known.

Environments are still the profile FILES the module ships (`OI-168`'s boundary is unchanged);
what changed is which profiles are active in each, as Spring would have them (CP-45, read off
spring-core 7.0.9 and spring-boot 4.1.1; the keys live in the config model's `profiles`
block, so resolve code names no framework):

* **the base environment, `default`:** the literal profiles of the base's
  `spring.profiles.active` and `spring.profiles.include`; where neither names one, the
  `spring.profiles.default` profile(s), else the reserved `default`.
* **a profile-file environment `p`:** `p`, plus the base's `spring.profiles.include`. Only the
  base configuration may set these keys (CP-45 row 7: a profile-specific file that sets them is
  refused by Boot). A profile named only in the base's `active` list is `unresolved` there:
  the activation that selects `p` (a command line, an environment variable) replaces or
  extends that list, and which it does is the deployment's, not the code's.
* **a placeholder nothing fills** in either key makes every profile condition not decided by
  the environment's own name `unresolved`, with the reason *the active profiles here come from
  `${apollo_profile}`, which this module does not fill*.

**A decision recorded here because it is visible in the documents.** In a profile-file
environment `p`, a profile that the base's `active` list never names is read as OFF (`false`,
resolved): the activation selecting `p` is assumed to select `p`, as PR #61 assumed, and only
the profiles the base itself names are opened. The alternative — that the activation selecting
`p` could name ANY profile, so every profile other than `p` is "not evaluated" there — was
NOT chosen: it would leave every profile condition in every profile-file environment of a
module that sets the key open, where the chosen reading keeps what PR #61 already stated and
adds only what the base's own list makes uncertain. It is a one-line change (`otherwise` set
in every profile environment whenever the base's `active` key is set). `spring-petclinic-rest`
shows the difference: `@Profile("jdbc")` is off in `mysql` under the chosen reading and "not
evaluated" under the alternative.

**PR #61's verdicts moved, by this rule.** Apollo `configservice`'s `GET /` read "not in
`default`, `github`" and now reads "not evaluated in `default`, `github`", with the reason
(§1, the second table). `spring.profiles.group` and relaxed key spellings are not read
(§4, `OI-170`).

## 3. What the documents say, as built

* **Every row of every kind derived from a conditional bean** — inbound and outbound
  endpoints, scheduled jobs, error handlers — gets PR #61's two detail lines, found through
  `symbol_beans` by one function, so no kind carries its own copy. *Exists only when …* says
  what the registration requires; *Of this module's environments* says where the bean
  exists, read from `bean_presence` alone (two exclusive factories each hold somewhere, and
  read as one list of conditions the bean would exist nowhere). An unconditional row gains
  nothing.
  * **One route:** a single line, its conditions joined by "and" — *Exists only when: the
    active profile matches one of: `prod` and the property `orders.notify` is `kafka`*. This
    is not PR #61's per-condition pairs: presence belongs to the bean, so a bean whose one
    route has two conditions is one statement.
  * **Several routes:** *Exists when any of these registers it*, with a two-column table
    (*Registered by*, *Registers it when*), one row per route — the factory method or the
    class; an unconditional route reads *always*, a plain `new` outside a factory reads
    *constructed outside any bean factory — not decided*, and an inherited body no bean runs
    reads *no bean of this module runs this inherited body — not decided*.
  * **A presence condition** reads *no other bean of type `T` is registered* (or *a bean of
    type `T` is registered*), then *decided from this module's beans only (`partial`)* and
    *the other beans of that type*, each with where it exists and, where its conditions name a
    profile no environment is, why. The competitor JSON the evidence carries is never printed.
  * **The environments line** says *holds in N of M environments — not in `a`; not evaluated
    in `b`*, and where an environment is open it says why, in words (a `@Conditional`
    named by its class, a property by its key, never the stored JSON). A bean open in every
    environment reads *not evaluated by this analysis in any of the M environments* and its
    reason.
* **A call site's candidates, per environment.** Any call site `candidate_presence` lists —
  a NARROWED site one of whose candidates is a conditional bean, or a site of any resolution
  that a framework-generated implementation answers — gets, in the trace block, the site and
  every candidate (*answered by one of: …*), then one line per environment group naming the
  candidates that exist there (*in `prod`: `KafkaWebSocketMessageSender`*), then a line for
  the candidates not evaluated there and why. Environments with the same candidates share a
  line. Where no candidate exists, *none of them*. A line that rests on a bean-presence
  verdict at `partial`, or leaves out a candidate ruled out by one, says *(decided from this
  module's beans only)*. A framework-generated implementation is named *a framework-generated
  implementation of `SpringDataOwnerRepository`*. A reason every candidate of a line shares is
  said once, after them. **Where every candidate of a site holds `true`, `resolved` in every
  environment** (an unconditional Spring Data repository), only the *answered by* line is
  written: a line per environment would repeat it. Stated, not decided — read from
  `candidate_presence`, never by changing `call_edges` or its `narrowed` resolution; the step
  table and the diagram still show every candidate.
* **The system document** states BOTH ends of a link: *called only in `prod`; not in `default`*
  beside the calling side (`Link.from_conditions`) as it already did *exists in `prod`* beside
  the called one (`to_conditions`). Existence on each side is read from the participant's
  `bean_presence`, federated as `system_bean_presence`. Matching is untouched: no link is
  dropped or added for a condition, in any environment.

## 4. What it does NOT do

* No row, link or call edge is dropped or added, in any environment (B5; PR #61's ruling).
* `@ConditionalOnMissingBean`/`@ConditionalOnBean` are evaluated from the module's own beans only, at `partial` (decision 2); `@ConditionalOnClass`, `@Conditional(Class)` and the rest stay `other`, verbatim, `unresolved`.
* No condition propagates from a bean to its CALLERS: a controller calling a conditional
  service exists in every environment; what changes is which implementation answers.

**Stated limits of what was built** — each is the reason for an open verdict or a missing
line, not a wrong one, and where a real input triggers one it has a register entry:

* **Profile groups and relaxed key spellings are not read.** `spring.profiles.group` can make
  a profile active that no key names, and a key spelled `SPRING_PROFILES_ACTIVE` inside a file
  is not matched (the exact key, or `key[N]`, only). None of the 43 analysed modules sets a
  group. `OI-170`.
* **The annotation criterion ignores the type hierarchy.** `@ConditionalOnBean(annotation = X)`
  is matched against the annotations the competitor's own type carries, where Spring's
  `findAnnotationOnBean` also looks above it. `OI-171`.
* **Lambdas created in a helper a `@Bean` calls are not followed** — only a lambda the factory
  method's own body creates belongs to its route. **Kotlin class-compiled lambdas** reach the
  pass through the `lambda_bodies` path, not the `dynamic` call edge a Java lambda has.
* **A body reached only through `super.m()` can read "no bean runs it"**: the inherited-body
  rule finds bodies a virtual or interface call reaches. The wording says only that this
  module's beans do not run it.
* **A generic framework receiver over-lists.** A call declared on `JpaRepository<User, Long>`
  names `JpaRepository`, so every module repository extending it is a candidate; the type
  argument is not used to narrow. Measured on 0 of 69 `jhipster-sample-app` and 0 of 34
  `spring-petclinic-rest` interface sites, so it is logged and not fixed. `OI-169`.
* **Spring Data's bean names are not modelled** (`name` is NULL on a proxy), so a
  `@ConditionalOnMissingBean(name = …)` reads it as "could match".
* **An annotation type whose header was not read composes nothing**, and a module class whose
  supertypes `type_hierarchy` cannot reach gets no factory route above that point.
* **Not read:** `ignored`/`ignoredType`, `search`, container generics, a `@Bean`'s aliases
  beyond its first name; whether Spring Data scanning runs and from which packages; a nested
  repository interface (which Spring Data refuses by default).
* **Symbol parsing in SQL.** `split_part(…, '#', 1)` in `derive_endpoints.sql` (older) and in
  the `candidate_presence` view's proxy arm reads the type out of a symbol string, a known
  exception to "symbol grammar lives in `domain/symbols`". `OI-172`.

## 5. Cost (§8.7), as measured

The pass reads, once per load: the shared `annotation_index`, the factory-method fold
`declared_beans` already keeps, one `constructor_edges`, one `type_hierarchy`, one
`interface_declarations`, one `resolved_config`, one `dispatched_bodies` with one `Dispatch`
(shared through `workspace.once`) and one insert; its presence phase reads nothing more
(competitors are matched in memory, verdicts settle in rounds over (condition, environment)
pairs). On `apollo-portal` (364 endpoints, 63 conditional beans, 588 condition rows) the pass
took 0.05 s, the inherited-body step 10 ms plus 46 ms over 1,945 bodies, and the views 1.4
ms (`endpoint_conditions`), 1 ms (`bean_presence`) and 8.5 ms (`candidate_presence`).

Two costs were found by measuring, not guessed. `endpoint_conditions` first joined on
`bean = symbol OR (bean = enclosing AND NOT EXISTS …)`, which cannot be hashed: 11 s for
20,000 endpoint rows against 12,000 condition rows, against 5 ms as a `UNION ALL` of two
equi-joins. The view is now the second form, and a test fixes the planner's choice by timing
a real-size input (the old form fails it at 25 s). The same rule governs `symbol_beans` and
`candidate_presence`.

## 6. Decisions for the user

| # | decision |
|---|---|
| 1 | Scope: rows only, or rows AND the call graph (§3's per-environment candidates) — **RULED 2026-10-22: B, both.** Rows and call candidates are both derived from a bean; one table serves both |
| 2 | `@ConditionalOnMissingBean` / `@ConditionalOnBean` among the candidates the module itself registers — **RULED 2026-10-22: C, evaluate from the module's own beans, published at `partial`** with the reason *decided from this module's beans only; a library or the processing order may differ*. Measured: 53 of 210 narrowed sites decidable today, +137 with this rule, 20 never (`@ConditionalOnClass`, `@Conditional(Class)`). A probe (CP-44) reads Spring's own `OnBeanCondition` rule off the jar first: the type an unannotated use checks, how `value`/`name` match |
| 3 | The table's key — **RULED 2026-10-22: A, the bean.** One `bean_conditions` table; every derived row and call candidate finds its conditions through its owner class (`symbols.enclosing`); `endpoint_conditions` becomes a view over that join so PR #61's documents, the system tier and PR #62's diff read the same name |

## 7. Rulings made while building it

Recorded where they were made, so the sections above can state the result and this one the
reason. None of them was a decision of the user's unless it says so; each cost nothing but a
catalog edit or a view if wrong.

| ruling | what it replaced or settled | why |
|---|---|---|
| The condition vocabulary is the CONTAINER's, so every catalog detecting an `org.springframework` artifact names `bean_model: spring`, pinned by a test | only three catalogs named it; a module with no such catalog would hand the pass no vocabulary and lose every condition silently | data, not code; a guard against silent omission |
| `StaleParticipantError` (the system tier's stale-participant check) accepts a VIEW of the same name, and refuses a participant still holding the old `endpoint_conditions` TABLE | PR #62's check lists tables only; once `endpoint_conditions` is a view it would refuse every new workspace | without it every system run refuses. Opening a workspace also drops the old table, else every pre-branch workspace crashed on open |
| A class exists wherever ANY of its routes registers it (§2a) | "registered two ways, so `unresolved`" | Spring's own rule; 6 of the 8 first-unresolved beans of `apollo-portal` were exclusive factories |
| A stereotype or condition counts through composed annotations; a condition annotation is never composed through what it is built on (§2a) | direct placement only | the real input: ruoyi's `@AutoConfiguration` classes |
| A lambda a factory creates is the factory's code (§2a) | the lambda carried only its class's conditions | ruoyi's websocket starter |
| `endpoint_conditions` carries `via` and `bean_kind`; "exists in N of M" is read from `bean_presence` only | two exclusive factories read as AND (exists nowhere) | found at review |
| A competitor is a route of a DIFFERENT class; presence evidence names its competitors (§2c) | a second route of the same class counted as a competitor; evidence named nobody | found at review: `DefaultUserService` |
| One rule maps code to its bean (`symbol_beans`); the document and the call candidates both read it | `_bean_of` in Python beside the view's SQL | removing the cause: two copies of one rule |
| An inherited body is a bean whose routes are its heirs' (§2a) | the abstract owner carried no condition, so the body read "exists everywhere" (11 of 11 ruoyi sites) | measured at review; copying the heirs' rows by the same pass was chosen over recursive SQL |
| The `@ConditionalOnMissingBean` default stays hedged where a module bean provably exists in the environment | the hedge was questioned for `StandardPricing` in `prod` | the container evaluates the condition at REGISTER_BEAN against definitions registered so far (CP-44 row 3): in one configuration class the processing order of two `@Bean` methods decides whether both register. Exactly what `partial` is for |
| Active profiles are read from configuration (§2d) | an environment's active profile was its file's name | `spring-petclinic-rest`'s `spring.profiles.active`, Apollo's `${apollo_profile}` |
| In a profile-file environment, a profile the base's `active` list never names is OFF (§2d) | the alternative: "not evaluated" for every other profile | keeps PR #61's assumption; flagged as a user-visible decision |
| A bean the framework implements for an interface is a route (§2a), listed as a candidate of an interface call | Spring Data repository interfaces were never candidates, so petclinic's document said no implementation exists | found by re-measuring after the active-profiles rule left petclinic unchanged |

