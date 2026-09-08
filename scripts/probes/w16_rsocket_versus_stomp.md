# W16 — what tells a Spring RSocket controller from a STOMP one? (F2 §3.6)

**Question.** `spring-stomp.yml` claims
`org.springframework.messaging.handler.annotation.MessageMapping` and publishes what
it finds as `websocket`. **That annotation is also THE routing annotation for Spring
RSocket controllers.** So an RSocket handler in a scanned module is published on the
wrong PROTOCOL — not an empty address, not a missing row, but a boundary asserted on
a wire the module does not speak.

`docs/COVERAGE.md` has stated that in place since `A-C1`, together with the reason it
stayed open: *"separating them needs a fact that tells an RSocket registration from a
STOMP one, and neither catalog reads one."* This probe looks for that fact.

`protocol` is identity — DR-5 gates cross-bundle linking on protocol equality — so a
row on the wrong protocol does not merely mislead a reader of this bundle. It links,
in someone else's graph, to endpoints this module never speaks to.

**Version scope (§5.4).** Read against **spring-messaging 6.1.6**,
**spring-boot-autoconfigure 3.2.5**, **spring-websocket 6.1.6** and **rsocket-core
1.1.4**. The handler predicates and the auto-configuration conditions are framework
behaviour and can change between releases. `rsocket-core` **states no version of its
own** — no `pom.properties`, no `Implementation-Version` — so its row says so rather
than echoing the coordinate; that is `retrofit.yml`'s `identity: assumed` precedent,
and it is admissible here because the claim that row carries is "this coordinate
carries this class", which does not depend on the version.

## Expectation table

| # | If | then |
|---|---|---|
| 1 | the two handlers scan beans with the SAME predicate | no fact about the class can separate them, and a type gate cannot close this |
| 2 | an annotation belongs to one framework only | it is positive evidence for that framework whatever the build says |
| 3 | each handler bean is `@ConditionalOnClass` | which handler EXISTS is a dependency fact, and `detect.coordinates` already reads one |
| 4 | a condition names a TYPE | a catalog gate needs the COORDINATE that ships it, which is a different question |

## Observations

Verbatim from `scripts/probes/w16_rsocket_versus_stomp/run.sh`, which runs `sweep.py`. **Every version below is the one the JAR itself reported** — and **not the version the coordinate list asked for**; `sweep.py` compares the two and ABORTS when they disagree, rather than printing a version it did not read.

| what the run read | 6.1.6 | 3.2.5 |
|---|---|---|
| artifact reporting this version | spring-messaging | spring-boot-autoconfigure |
| where the jar states that version | MANIFEST.MF | MANIFEST.MF |

### 1. Does the CLASS distinguish an RSocket controller from a STOMP one?

| handler | the bean predicate it scans with |
|---|---|
| STOMP — `SimpAnnotationMethodMessageHandler` | `isHandler` tests `Controller` |
| RSocket — `MessageMappingMessageHandler` (its base) | `lambda$new$0` tests `Controller` |

### 2. Where each annotation may be written

| annotation | `@Target` | framework |
|---|---|---|
| `@MessageMapping` | TYPE, METHOD | both |
| `@ConnectMapping` | METHOD | RSocket only |

### 3. What decides which handler bean EXISTS

| auto-configuration | `@ConditionalOnClass` names |
|---|---|
| RSocket — `RSocketMessagingAutoConfiguration` | `io.rsocket.RSocket`, `io.rsocket.transport.netty.server.TcpServerTransport`, `org.springframework.boot.autoconfigure.rsocket.RSocketMessageHandlerCustomizer`, `org.springframework.messaging.rsocket.RSocketRequester`, `org.springframework.messaging.rsocket.annotation.support.RSocketMessageHandler` |
| STOMP — `WebSocketMessagingAutoConfiguration` | `org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer` |

### 4. Which ARTIFACT carries the type each condition names

A `@ConditionalOnClass` names a TYPE; a catalog gate names a COORDINATE, and the two are different questions. Each row is the jar checked for the class.

| for | coordinate | carries the class |
|---|---|---|
| STOMP | `org.springframework:spring-websocket`, asked for 6.1.6, jar says 6.1.6 (from its MANIFEST.MF) | yes |
| RSocket | `io.rsocket:rsocket-core`, asked for 1.1.4, jar says **states no version** | yes |

## Verdict

**1. Spring does not distinguish them on the class, and that is why the boundary
stood.** Section 1: STOMP's `SimpAnnotationMethodMessageHandler.isHandler` tests
`Controller`. RSocket's chain sets a `Predicate` on the reactive
`AbstractMethodMessageHandler`, and `MessageMappingMessageHandler` defaults it to a
lambda that tests `Controller`. The same stereotype, by the same
`AnnotatedElementUtils.hasAnnotation` call.

So `A-C1`'s type gate — which added `@Controller` to `spring-stomp.yml` — could never
have separated them, and no other fact about the class can either. **An RSocket
controller IS a `@Controller` with `@MessageMapping` methods, and so is a STOMP one.**

**2. `@ConnectMapping` is RSocket-only.** Section 2: it lives in
`org.springframework.messaging.rsocket.annotation`, targets `METHOD`, and has no STOMP
counterpart. §3.6 names it as positive RSocket evidence and it can serve as exactly
that — a module carrying one is an RSocket module regardless of what its build
records.

**3. What separates them is which handler auto-configuration would register.**
Section 3: RSocket's is `@ConditionalOnClass` on `io.rsocket.RSocket`,
`TcpServerTransport` and `RSocketMessageHandler`; STOMP's is `@ConditionalOnClass` on
`WebSocketMessageBrokerConfigurer`. Neither condition is satisfiable by the other
framework's dependencies, so the presence of a library decides which handler bean
exists — and therefore which framework scans the `@Controller` beans at all.

**4. A condition names a TYPE; a gate names a COORDINATE.** Section 4 exists because
those are different questions and inferring one from the other would be a guess.
`WebSocketMessageBrokerConfigurer` ships in `org.springframework:spring-websocket`;
`io.rsocket.RSocket` ships in `io.rsocket:rsocket-core`. Both checked by opening the
jar.

**What the gate must NOT be, and this is the trap the model's own comment names.**
`Catalog.detect_coordinates` records that a module-wide activation gate "would
deactivate ~40 catalogs on every module whose recorded coordinates do not name their
framework, and on Maven — where a starter's OWN dependencies are transitives F1 does
not resolve — a module declaring `spring-boot-starter-web` would lose `spring-mvc.yml`
outright."

That applies here directly: a real RSocket application declaring
`spring-boot-starter-rsocket` records the STARTER, not `rsocket-core`. A gate on the
library alone declines exactly the applications the catalog exists for. Both catalogs
therefore name the starter beside the libraries, and the residual — a module whose
build records NEITHER, through parent-POM inheritance — is §3.6's "neither resolvable"
case.

## What this probe deliberately did not measure

- **A running application.** Every finding is read out of shipped bytecode: the
  predicates are the handlers' own code, the conditions are the auto-configurations'
  own annotations, and the carrier rows are jar listings. What a running Spring
  context does with two handlers registered is not established here.
- **Whether both handlers really do scan the same bean simultaneously** when both
  starters are present. §3.6 asserts they do and treats two rows as the correct
  answer; this probe shows only that both predicates accept the same class, which is
  the necessary half and not the sufficient one.
- **The other `@ConditionalOnClass` members and any `@ConditionalOnMissingBean`.**
  Section 3 lists what each condition names; a Boot auto-configuration can also be
  disabled by property or by a user-supplied bean, and neither is read here.
- **RSocket over WebSocket.** RSocket has a WebSocket transport, so a module can carry
  both libraries for one framework. §3.6's answer — both present derives two rows — is
  a deliberate over-report in that case, and this probe does not measure how common it
  is.

## How the verdict is consumed

W16 gates `spring-stomp.yml` on `spring-websocket` (plus its starter) and ships
`spring-rsocket.yml` gated on the RSocket libraries (plus its starter), with `rsocket`
added to D00's protocol set. Finding 1 is why no type gate could have done it; finding
3 is the fact both gates read; finding 4 is why they name coordinates rather than the
types the conditions name.

`detect.coordinates` was read by NO `annotation_driven` catalog before this — only
`derived_resource` and `config_join` are in `DEPENDENCY_GATED` — so both gates were
inert when first written, and the RSocket catalog derived a second row for the same
controller. Gating the whole style was the wrong repair: 20 of the 22
`annotation_driven` catalogs need no gate because their evidence NAMES their framework,
which is D02's ruling R9. `detect.required` marks the two catalogs whose evidence does
not.
