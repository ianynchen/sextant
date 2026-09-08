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

Verbatim from `scripts/probes/w14_listener_registration/run.sh`, which runs `sweep.py`. **Every version below is the one the JAR itself reported** — read out of its own `META-INF/maven/*/pom.properties` — and **not the version the coordinate list asked for**. `sweep.py` compares the two and ABORTS when they disagree, rather than printing a version it did not read.

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

| registrar | methods taking a `Class` or a `Method` |
|---|---|
| `KafkaListenerAnnotationBeanPostProcessor` | `findListenerAnnotations(Class)`, `findListenerAnnotations(Method)`, `processMultiMethodListeners(Method)`, `processKafkaListener(Method)`, `processMainAndRetryListeners(Method)`, `checkProxy(Method)`, `noBeanFoundMessage(Class)`, `getBeansOfType(Class)` |
| `RabbitListenerAnnotationBeanPostProcessor` | `buildMetadata(Class)`, `processMultiMethodListeners(Method)`, `processAmqpListener(Method)`, `checkProxy(Method)`, `noBeanFoundMessage(Class)`, `addToMap(Class)` |
| `AbstractListenerAnnotationBeanPostProcessor` | `detectAnnotationsAndRegisterEndpoints(Class)`, `createAndConfigureEndpoint(Method)` |

### 3. What Sextant derives today, per shape (`spring-kafka.yml`)

| class-level `@KafkaListener` | method carries | rows | path derived |
|---|---|---|---|
| — | `@KafkaListener(topics=payments)` | 1 | `payments` |
| `topics=orders` | `@KafkaHandler` | 1 | `orders` |
| `topics=orders` | `@KafkaListener(topics=payments)` | 1 | `orderspayments` |

## Verdict

**1. `@SqsListener` cannot be written on a type.** Its `@Target` is `METHOD` and
nothing else, and `AbstractListenerAnnotationBeanPostProcessor` has exactly one
endpoint-creating path, `createAndConfigureEndpoint(…, Method, …)`. **The
class-plus-method question does not arise for SQS**, so a third of F2 §3.5's
"measure per framework" is answered by the annotation's own declaration. A rule
encoded for SQS would be a rule with no reachable case.

**2. `@KafkaHandler` and `@RabbitHandler` declare exactly one attribute each —
`isDefault()` — and no destination.** That settles the question §3.5 asks about
them without appealing to any behaviour: an annotation that names no destination
**cannot be an independent registration**. It selects which method serves the
registration the class-level annotation already made. `@KafkaListener` declares 20
attributes including `topics`/`topicPattern`/`topicPartitions`; `@RabbitListener`
declares 20 including `queues`/`queuesToDeclare`/`bindings`. The asymmetry is one
against twenty, not a subtlety.

This is why `spring-kafka.yml`'s prefix rule is right for the handler shape: a
`@KafkaHandler` contributes an EMPTY suffix, so "prefix plus suffix" is the
class-level topic unchanged. Row 2 of section 3 measures that — `orders` in,
`orders` out.

**3. Kafka and Rabbit each carry two independent registration paths.**
`KafkaListenerAnnotationBeanPostProcessor` declares `findListenerAnnotations` twice
— once taking a `Class`, once taking a `Method` — and then
`processMultiMethodListeners(…)` for the class-level collection beside
`processKafkaListener(…)` for each method-level one. `RabbitListener`'s registrar
has the same pair (`processMultiMethodListeners` / `processAmqpListener`). Neither
path excludes the other: both are invoked from the same post-processing method,
the class-level one behind an emptiness check on the class-level collection and
the method-level one in a loop over the annotated methods.

**So a class carrying a class-level `@KafkaListener(topics="orders")` and a
method-level `@KafkaListener(topics="payments")` registers TWO containers, on two
different topics.**

**4. Sextant publishes one row, addressed to neither.** Section 3, row 3: `orders`
prefixed onto `payments` gives **`orderspayments`** — a topic no broker carries,
at `resolved`. Two readable destinations become one unreadable one. Row 1 is the
control: the same method-level annotation with no class-level listener above it
derives `payments` correctly, so the composition is what breaks it and not the
method-level read.

**What this means for W15.** The distinction to encode is not "Kafka versus HTTP".
It is between an annotation that CARRIES a destination and one that does not:

- a class-level annotation carrying a destination is a **sibling registration** —
  its address stands alone, and so does each method-level one;
- a class-level annotation whose methods carry no destination of their own is a
  **prefix** in effect, though only because the suffix is empty.

Encoding the relationship as a per-catalog conjunct (§3.5's proposal) covers both,
and the `@KafkaHandler` case keeps working under either reading — which is what
makes the conjunct safe to add before every framework has been re-examined.

## What this probe deliberately did not measure

- **A running broker, or a running Spring context.** Every finding above is read
  out of the shipped bytecode: `@Target` and the declared attributes are the
  annotations' own statements, and the registrar's paths are its own method set.
  What is NOT established this way is that both containers actually start — only
  that the framework builds an endpoint down each path.
- **Whether a class-level and a method-level listener on the SAME topic dedupe.**
  Section 3 uses two different topics because that is the case that fabricates;
  the same-topic case would collapse on wire identity anyway (D02 §5) and says
  nothing about the composition rule.
- **`@KafkaListeners` / `@RabbitListeners`**, the repeatable containers. They fold
  several annotations onto one element, which is a different question from
  composing two levels, and `spring-kafka.yml` already declares the Kafka one.
- **Any framework outside these three.** The sweep answers Kafka, Rabbit and SQS
  because those are what §3.5 names; a fourth messaging catalog needs its own row
  here before a relationship is declared for it.

## How the verdict is consumed

W15 adds the relationship conjunct and fixes the addresses-nothing gate. Finding 1
says SQS needs no conjunct at all; finding 2 says the handler shape is safe under
either value and so does not constrain the choice; finding 3 says Kafka and Rabbit
must both declare SIBLING REGISTRATION; finding 4 is the row that has to change,
and `orderspayments` is the exact string a regression test should refuse.
