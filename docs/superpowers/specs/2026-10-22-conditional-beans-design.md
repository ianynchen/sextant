# A bean that exists in some environments only — design

**Status: RULED 2026-10-22 — all three decisions (§6).** Replaces the special case PR #61
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

## 2. What is published

One structured table, keyed by the BEAN, read by everything a bean derives:

```
bean_conditions
bean | bean_kind | kind | expression | environment | holds | resolution | evidence
```

* `bean` is the class symbol (the registered type) — for a `@Bean` factory, the class it
  constructs; `bean_kind` is `class` (a condition on the class), `factory` (a condition on
  the `@Bean` method), or `configuration` (inherited from the enclosing configuration class).
  A class constructed by a conditional factory AND anywhere else without one is written
  with `resolution = unresolved` and that reason in `evidence` — never as conditional, never
  as unconditional.
* `kind`, `expression`, `holds`, `resolution`: exactly PR #61's encoding (`profile`,
  `property`, `other`; CP-42, CP-43; `other` verbatim and `unresolved`).
* Rows (endpoints in both directions, scheduled work, error handlers) and call-edge
  candidates find their conditions by JOINING on their owner class — no row copies them.
  `endpoint_conditions` becomes a VIEW over that join, so PR #61's documents and the system
  tier read exactly what they read today, now for outbound rows too.

### 2a. Which classes are beans, and which conditions apply — Spring's rule, read off its jar

Spring evaluates a condition at the point it REGISTERS a bean, and the point decides which
annotations count (to be confirmed by CP-44, §2b, before anything is built):

| how the bean is registered | conditions Spring evaluates |
|---|---|
| a class found by component scan (a stereotype: `@Component` and the annotations built on it) | the class's own |
| a class registered by `@Import` or as a configuration class | the class's own |
| a `@Bean` method | the method's own, AND its configuration class's (a skipped configuration registers none of its `@Bean`s) |
| a class merely CONSTRUCTED inside a `@Bean` method | the factory method's (as above) — the class's own annotations are not consulted on this route |

So a `bean_conditions` row names the class whose code runs: a conditional scanned class
(`bean_kind = class`), or the class a conditional `@Bean` method constructs and returns —
the constructed classes assignable to the method's declared return type (`type_hierarchy`),
which is a structural rule, never a model of what a builder does (`bean_kind = factory` or
`configuration`). A class constructed by a conditional factory and ALSO registered another way
(scanned, or constructed by an unconditional factory) is written `unresolved` with that reason.

**Framework knowledge is data.** PR #61 declared the condition annotations on the two HTTP
catalogs (`matches.mapping.conditions`); that was the special case. They move to the Spring
bean model (`catalogs/bean-models/spring.yml`, D02 §1c), beside `@Bean` and `@Qualifier`,
together with the configuration annotation and the stereotype set — read by one resolve pass
for every bean, naming no framework in code.

### 2b. Probes

CP-44 (new): `OnBeanCondition` — the type an unannotated `@ConditionalOnMissingBean` on a
`@Bean` method deduces (the return type), how `value`/`type`/`name` match, and that the
search sees definitions registered so far (the processing-order caveat decision 2's `partial`
states); `ConditionEvaluator` — the registration points that consult it (scanning, import,
`@Bean` methods, configuration classes), confirming §2a's table. CP-42 and CP-43 stand.

### 2c. `@ConditionalOnMissingBean` / `@ConditionalOnBean` (decision 2, as ruled)

Evaluated per environment AFTER the profile and property conditions, against the module's
own beans of the condition's type (the beans of §2a whose class is the type or a subtype of
it): `OnMissingBean(T)` holds where no OTHER such bean exists there, `OnBean(T)` where at
least one does; a competitor whose own existence there is `unresolved` makes this verdict
`unresolved`; two beans each `OnMissingBean` of the same type (Spring keeps the first one
processed) are `unresolved` with that reason. Every verdict this rule writes carries
`resolution = partial` and the reason *decided from this module's beans only; a library or
the processing order may differ*.

## 3. What the documents say

* Every row of every kind derived from a conditional bean gets PR #61's two detail lines
  (*Exists only when … / Of this module's environments: holds in N of M*). Outbound rows and
  scheduled jobs gain them; the system document's links state an outbound side's condition
  beside the link as they already state the inbound side's.
* A narrowed call site whose candidates carry conditions states, per environment, which
  candidates exist there (*in `prod`: `KafkaWebSocketMessageSender`; in `default`:
  `RedisWebSocketMessageSender`*) — read from `bean_conditions`, never by changing
  `call_edges` or its `narrowed` resolution. Stated, not decided; the trace still shows every
  candidate.

## 4. What it does NOT do

* No row, link or call edge is dropped or added, in any environment (B5; PR #61's ruling).
* `@ConditionalOnMissingBean`/`@ConditionalOnBean` are evaluated from the module's own beans only, at `partial` (decision 2); `@ConditionalOnClass`, `@Conditional(Class)` and the rest stay `other`, verbatim, `unresolved`.
* No condition propagates from a bean to its CALLERS: a controller calling a conditional
  service exists in every environment; what changes is which implementation answers.

## 5. Cost (§8.7)

One read of `annotations` (already indexed once per load), one read of `call_edges` for the
`<init>` targets of `@Bean` methods, one write per (bean, condition, environment). Measured
inputs on the largest module (`apollo-portal`): 13 conditional classes, 74 conditional
factories, 205 affected call sites.

## 6. Decisions for the user

| # | decision |
|---|---|
| 1 | Scope: rows only, or rows AND the call graph (§3's per-environment candidates) — **RULED 2026-10-22: B, both.** Rows and call candidates are both derived from a bean; one table serves both |
| 2 | `@ConditionalOnMissingBean` / `@ConditionalOnBean` among the candidates the module itself registers — **RULED 2026-10-22: C, evaluate from the module's own beans, published at `partial`** with the reason *decided from this module's beans only; a library or the processing order may differ*. Measured: 53 of 210 narrowed sites decidable today, +137 with this rule, 20 never (`@ConditionalOnClass`, `@Conditional(Class)`). A probe (CP-44) reads Spring's own `OnBeanCondition` rule off the jar first: the type an unannotated use checks, how `value`/`name` match |
| 3 | The table's key — **RULED 2026-10-22: A, the bean.** One `bean_conditions` table; every derived row and call candidate finds its conditions through its owner class (`symbols.enclosing`); `endpoint_conditions` becomes a view over that join so PR #61's documents, the system tier and PR #62's diff read the same name |
