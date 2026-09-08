# W14 — do class-level and method-level listeners register independently? (F2 §3.5)

**Question.** `spring-kafka.yml` treats a class-level `@KafkaListener` as a PREFIX
for the methods inside the class. That is right for one shape and wrong for
another, and the wrong one composes two topic names into a third that no broker
carries. So, **per framework, before encoding a rule**: does a class-level
listener annotation and a method-level one produce ONE registration or TWO, and
does the class-level handler pattern (`@KafkaHandler` / `@RabbitHandler`) behave
differently from a second `@KafkaListener`?

F2 §3.5 asks for the handler annotations to be measured **separately**, on the
stated grounds that they behave differently. They do, and the reason is simpler
and more decisive than expected: it is visible in the annotation's own declaration
rather than in any registrar's behaviour.

**Version scope (§5.4).** Read against **spring-kafka 3.1.4, spring-rabbit 3.1.4
and spring-cloud-aws-sqs 3.1.1** — the versions the fixture poms pin, so a verdict
here and a verdict from the fixture describe the same libraries. An annotation
gaining a `@Target` or an attribute in a later release is a different answer.
Widening the scope means adding a coordinate to
`scripts/probes/w14_listener_registration/run.sh` and re-running, never assuming.

## Expectation table

| # | If | then |
|---|---|---|
| 1 | an annotation's `@Target` omits `TYPE` | the class-plus-method shape cannot arise for that framework at all |
| 2 | a "handler" annotation declares no destination attribute | it cannot be an independent registration — it can only select which method serves one that is declared elsewhere |
| 3 | a registrar has separate paths for a `Class` and for a `Method`, neither excluding the other | a class carrying both gets both, and the two are independent |
| 4 | the two are independent | composing them into one address is a fabrication, and Sextant does it today |

## Observations

Verbatim from `scripts/probes/w14_listener_registration/run.sh`, which runs `sweep.py`. **Every version below is the one the JAR itself reported** — and **not the version the coordinate list asked for**. WHERE each jar states it differs, so the run says which file answered rather than naming one source for all three: Maven's `META-INF/maven/*/pom.properties` where present, the manifest's `Implementation-Version` otherwise. Spring's own jars carry no `pom.properties` at all. `sweep.py` compares what it read against the coordinate and ABORTS when they disagree, rather than printing a version it did not read.

| what the run read | 3.1.1 | 3.1.4 |
|---|---|---|
| artifacts reporting this version | spring-cloud-aws-sqs | spring-kafka, spring-rabbit |
| annotations read out of it | 1 | 2 |
| where the jar states that version | pom.properties | MANIFEST.MF |

### 1. Where each annotation may be written, and what it declares

| annotation | `@Target` | declares a destination? | attributes |
|---|---|---|---|
| `KafkaListener` | TYPE, METHOD, ANNOTATION_TYPE | **topics, topicPattern, topicPartitions** | 20 |
| `KafkaHandler` | METHOD, ANNOTATION_TYPE | **NO** | 1 |
| `RabbitListener` | TYPE, METHOD, ANNOTATION_TYPE | **queues, queuesToDeclare, bindings** | 20 |
| `RabbitHandler` | METHOD, ANNOTATION_TYPE | **NO** | 1 |
| `SqsListener` | METHOD | **value, queueNames** | 9 |

### 2. The framework's own registrar: are the two levels separate paths?

The second column is read from `postProcessAfterInitialization`'s own BYTECODE — what it loads immediately before branching to the class-level path. The first is the registrar's method signatures, which can show that two paths EXIST and can never show whether one excludes the other.

| registrar | methods taking a `Class` or a `Method` | what gates the class-level path |
|---|---|---|
| `KafkaListenerAnnotationBeanPostProcessor` | `findListenerAnnotations(Class)`, `findListenerAnnotations(Method)`, `processMultiMethodListeners(Method)`, `processKafkaListener(Method)`, `processMainAndRetryListeners(Method)`, `checkProxy(Method)`, `noBeanFoundMessage(Class)`, `getBeansOfType(Class)` | 247: invokedynamic #354, 0 // InvokeDynamic #5:get:(Ljava/util/Map;Ljava/lang/String;)Ljava/util/function/Supplier;<br>252: invokevirtual #357 // debug<br>255: iload 5<br>257: ifeq 270 |
| `RabbitListenerAnnotationBeanPostProcessor` | `buildMetadata(Class)`, `processMultiMethodListeners(Method)`, `processAmqpListener(Method)`, `checkProxy(Method)`, `noBeanFoundMessage(Class)`, `addToMap(Class)` | 110: aload 4<br>112: getfield #259 // handlerMethods<br>115: arraylength<br>116: ifle 135 |
| `AbstractListenerAnnotationBeanPostProcessor` | `detectAnnotationsAndRegisterEndpoints(Class)`, `createAndConfigureEndpoint(Method)` | no class-level path in this jar |

### 3. What Sextant derives, per shape (`spring-kafka.yml`)

| class-level `@KafkaListener` | members | rows | paths derived |
|---|---|---|---|
| — | one `@KafkaListener(topics=payments)` | 1 | `payments` |
| `topics=orders` | one `@KafkaHandler` | 1 | `orders` |
| `topics=orders` | one `@KafkaListener(topics=payments)` | 1 | `payments` |
| `topics=orders` | a `@KafkaHandler` AND a `@KafkaListener(topics=payments)` | 2 | `orders`, `payments` |

## Verdict

**1. `@SqsListener` cannot be written on a type — AT 3.1.1, and not at 4.1.1.**
Its `@Target` is `METHOD` and nothing else in the version this probe reads, and
`AbstractListenerAnnotationBeanPostProcessor` has one endpoint-creating path,
`createAndConfigureEndpoint(…, Method, …)`.

**That bound is load-bearing and was nearly lost.** This verdict first said "the
class-plus-method question does not arise for SQS" and "a rule encoded for SQS
would be a rule with no reachable case" — unbounded sentences under a
version-scope paragraph that correctly said 3.1.1.
`scripts/probes/cp17_containers_and_class_level.md` had already measured 4.1.1:
`@SqsListener` becomes `@Target({METHOD, TYPE})` (rows 2e/2f), `SqsHandler`
appears declaring `isDefault()` (rows 4e/4f), and
`detectAnnotationsAndRegisterEndpoints` runs `if (hasMethodLevelListeners) {…}`
then `if (hasClassLevelListeners) {…}` (row 6f) — the Kafka shape, one major
version later. `spring-sqs.yml`'s own `measured:` block names both versions, so a
catalog written to the unbounded reading would have been wrong against a version
the file claims to have been read against. It declares `class_level: sibling`.
Recorded as OI-59, because the reusable part is the mistake and not the fact.

**2. `@KafkaHandler` and `@RabbitHandler` declare exactly one attribute each —
`isDefault()` — and no destination.** That settles the question §3.5 asks about
them without appealing to any behaviour: an annotation that names no destination
**cannot be an independent registration**. It selects which method serves the
registration the class-level annotation already made. `@KafkaListener` declares 20
attributes including `topics`/`topicPattern`/`topicPartitions`; `@RabbitListener`
declares 20 including `queues`/`queuesToDeclare`/`bindings`. The asymmetry is one
against twenty. (Section 1 reports the counts; the attribute NAME is read the same
way and is stated here rather than in the table.)

This is why `spring-kafka.yml`'s prefix rule was right for the handler shape: a
`@KafkaHandler` contributes an EMPTY suffix, so "prefix plus suffix" is the
class-level topic unchanged. Section 3's second row measures that — `orders` in,
`orders` out — and it still holds under `sibling`.

**3. Two registration paths — and the three frameworks do NOT share a gate.**
Section 2's third column is the guard's own bytecode, and the first version of this
probe got this wrong by reading method SIGNATURES instead: signatures show that two
paths exist and can never show whether one excludes the other. CP-17 says the same
of its own question 5.

| framework | what guards the class-level path | so a class-level listener registers |
|---|---|---|
| Kafka | `iload 5; ifeq` — a boolean local set from the class-level annotation's presence | whenever the class carries one, even with **zero** `@KafkaHandler` methods |
| Rabbit | `getfield handlerMethods; arraylength; ifle` | **only** when a `@RabbitHandler` method exists |
| SQS 3.1.1 | no class-level path in the jar | never |

Both registrars do run the per-method loop regardless, so a method-level listener
is always its own registration — which is what §3.5's conjunct turns on. What
differs is whether the CLASS-level one also binds: Kafka builds and registers a
`MultiMethodKafkaListenerEndpoint` with an empty handler list, so it binds a topic
no method serves; Rabbit does not reach that call at all. "Registers" here means
the registrar builds an endpoint down that path — what a running broker then does
with a handler-less endpoint is not established by reading bytecode, and the
boundary below says so.

**4. Sextant published one row addressed to neither.** Section 3, third row:
`orders` prefixed onto `payments` gave **`orderspayments`** — a topic no broker
carries, at `resolution: resolved` (the table shows the path; the resolution was
checked separately). Row 1 is the control: the same method-level annotation with no
class-level listener above it derives `payments`, so the composition is what broke
it and not the method-level read.

**W15's conjunct fixes it, and row 4 is the row that proves it is a fix rather than
a silencing.** The three-member shape — a class listener, a `@KafkaHandler` serving
it, and a method listener of its own — derives **two** rows, `orders` and
`payments`. A two-member shape cannot tell "no longer composed" from "gone", and
§3.5 rejects the silent loss as firmly as the fabrication.

## What this probe deliberately did not measure

- **A running broker, or a running Spring context.** Every finding above is read
  out of the shipped bytecode: `@Target` and the declared attributes are the
  annotations' own statements, the registrar's paths are its own method set, and
  the class-level guard is that method's own instructions. What is NOT established
  this way is that either container actually starts — only that the framework
  builds an endpoint down each path.
- **Two verdict claims are read the same way as the tables but do not appear in
  them**, and are named here rather than left to look generated: the handler
  attribute's NAME (`isDefault()` — section 1 prints the count), and the
  `resolution: resolved` on the `orderspayments` row (section 3 prints the path).
  Both were read with the same commands the tables use.
- **Whether a class-level and a method-level listener on the SAME topic dedupe.**
  Section 3 uses two different topics because that is the case that fabricates;
  the same-topic case would collapse on wire identity anyway (D02 §5) and says
  nothing about the composition rule.
- **`@KafkaListeners` / `@RabbitListeners`**, the repeatable containers. They fold
  several annotations onto one element, which is a different question from
  composing two levels, and `spring-kafka.yml` and `spring-rabbit.yml` each already
  declare their own.
- **Any framework outside these three.** The sweep answers Kafka, Rabbit and SQS
  because those are what §3.5 names; a fourth messaging catalog needs its own row
  here before a relationship is declared for it.

## How the verdict is consumed

W15 adds the relationship conjunct and fixes the addresses-nothing gate. Finding 1
says SQS needs no conjunct at all; finding 2 says the handler shape is safe under
either value and so does not constrain the choice; finding 3 says Kafka and Rabbit
must both declare SIBLING REGISTRATION; finding 4 is the row that has to change,
and `orderspayments` is the exact string a regression test should refuse.
