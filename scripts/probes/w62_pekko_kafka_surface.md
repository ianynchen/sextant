# W62 — Pekko Connectors Kafka's consumer sources, subscription factories and producer
sinks, and which argument (if any) carries a topic

**Question.** `pekko-connectors-kafka.yml` (`alpakka-pekko`) reads
`Consumer.plainSource`/`committableSource`/`atMostOnceSource`/
`plainPartitionedSource`/`committablePartitionedSource`: each takes a
`ConsumerSettings` and a `Subscription`, and the subscription itself is built by a
static `Subscriptions` factory — `topics(String...)`, `topicPattern(String)` or
`assignment(TopicPartition...)`. A `single_call` row can only address a wire off an
argument the call site itself carries, or off a linked call's own argument
(`channel_via`), so before any row was written the question is mechanical: of every
method matching `plainSource|committableSource|atMostOnceSource|
plainPartitionedSource|committablePartitionedSource|topics|topicPattern|assignment|
plainSink|committableSink|flexiFlow` on `Consumer`, `Subscriptions` and `Producer`,
which parameter position (if any) carries a value shaped like a topic — a plain
`String`, a `String...`/`TopicPartition...` varargs array, or a `Subscription`/
`AutoSubscription`/`ManualSubscription` built from one?

**Version scope (§5.4).** Read against **pekko-connectors-kafka 1.1.0** — the version
the jar reports for itself, checked against the coordinate before any table is printed.
`fixtures/orders-pekko/pom.xml` pins the same version.

**How to run.** `bash scripts/probes/w62_pekko_kafka_surface/run.sh`. Resolves the
artifact through Maven (network on the first run only), reads the version the jar
states for itself, and asks `javap -p -s` for every method on the three classes
matching the shared name pattern above.

## Expectation table

| # | If | then |
|---|---|---|
| 1 | `Consumer`'s source method takes a `Subscription`/`AutoSubscription` at position 1, built by a `Subscriptions` factory | addressable at `channel_arg: 1` with a `channel_via` form per factory — the shape `kafka-consumer.yml`'s own `List.of`/`Arrays.asList` rows already use |
| 2 | `Subscriptions.topics(String...)`/`topicPattern(String)` return the `Subscription` the source consumes, at a readable position of their own | the `channel_via` form's own `arg`: `all_strings` for the varargs factory, `0` for the single-string one |
| 3 | `Producer`'s sink/flow methods take only `ProducerSettings` and a `Producer`/`CommitterSettings` | no parameter is topic-shaped at all — the outbound half is a stated boundary, not a missing row |
| 4 | `Subscriptions.assignment` (a `TopicPartition...` varargs, or any Scala-collection overload) | outside this catalog's scope: `TopicPartition` carries the topic as a CONSTRUCTOR argument one hop further than `channel_via` reads, the same `assign(Collection<TopicPartition>)` boundary `kafka-consumer.yml`'s own header already states for the raw `KafkaConsumer` |

**MEASURED, this task's own Step 4 (the varargs question).** A live scan of
`fixtures/orders-pekko`'s `OrderFlows.java` (`Consumer.plainSource(settings,
Subscriptions.topics("pk.orders.placed"))` and a two-topic sibling) printed
`Subscriptions.topics`'s own call site: one `{"kind":"array","elements":[...]}`
argument, each element a resolved `{"kind":"string", ...}` — the identical shape
extractor capability 9.15 gives `Arrays.asList`, which `kafka-consumer.yml`'s own
`channel_via` already reads through `all_strings`. `Consumer.plainSource`'s own second
argument arrived as `{"kind":"unresolved","source":<the topics() call's result id>}` —
a linked call, exactly what `channel_via`'s `source`-follow expects. No new engine word
was needed; `pekko-connectors-kafka.yml` ships GREEN off the existing mechanism.

---

## Observations

Verbatim from `scripts/probes/w62_pekko_kafka_surface/run.sh`, which runs
`sweep.py`. **Every version in the headers below is the one the JAR itself
reported** — out of its own `META-INF/maven/.../pom.properties` or its
manifest's `Implementation-Version` — and **not the version the coordinate
list asked for**; `checked` compares the two and ABORTS when they disagree.

| what the run read | 1.1.0 |
|---|---|
| artifacts reporting this version | pekko-connectors-kafka_2.13 |
| where the jar states it | MANIFEST.MF |

### Every method matching `plainSource|committableSource|atMostOnceSource|
### plainPartitionedSource|committablePartitionedSource|topics|topicPattern|
### assignment|plainSink|committableSink|flexiFlow`, and which position (if
### any) carries a topic or a subscription built from one

**`org.apache.pekko.kafka.javadsl.Consumer`** (org.apache.pekko:pekko-connectors-kafka_2.13:1.1.0)

| # | method | descriptor | topic argument |
|---|---|---|---|
| 1 | `committablePartitionedSource` | `(Lorg/apache/pekko/kafka/ConsumerSettings;Lorg/apache/pekko/kafka/AutoSubscription;)Lorg/apache/pekko/stream/javadsl/Source;` | 1 |
| 2 | `plainPartitionedSource` | `(Lorg/apache/pekko/kafka/ConsumerSettings;Lorg/apache/pekko/kafka/AutoSubscription;)Lorg/apache/pekko/stream/javadsl/Source;` | 1 |
| 3 | `atMostOnceSource` | `(Lorg/apache/pekko/kafka/ConsumerSettings;Lorg/apache/pekko/kafka/Subscription;)Lorg/apache/pekko/stream/javadsl/Source;` | 1 |
| 4 | `committableSource` | `(Lorg/apache/pekko/kafka/ConsumerSettings;Lorg/apache/pekko/kafka/Subscription;)Lorg/apache/pekko/stream/javadsl/Source;` | 1 |
| 5 | `plainSource` | `(Lorg/apache/pekko/kafka/ConsumerSettings;Lorg/apache/pekko/kafka/Subscription;)Lorg/apache/pekko/stream/javadsl/Source;` | 1 |

Not printed above (present in the class but outside `_NAME_PATTERN`'s five source
names): the `withMetadata`/`ActorRef`-driven overloads of the same five methods carry
an extra trailing `Function`/`Consumer` argument, same topic position — not declared as
separate catalog rows, out of this task's scope.

**`org.apache.pekko.kafka.Subscriptions`** (org.apache.pekko:pekko-connectors-kafka_2.13:1.1.0)

| # | method | descriptor | topic argument |
|---|---|---|---|
| 1 | `assignment` | `([Lorg/apache/kafka/common/TopicPartition;)Lorg/apache/pekko/kafka/ManualSubscription;` | 0 |
| 2 | `topics` | `([Ljava/lang/String;)Lorg/apache/pekko/kafka/AutoSubscription;` | 0 |
| 3 | `assignment` | `(Ljava/util/Set;)Lorg/apache/pekko/kafka/ManualSubscription;` | *(none)* |
| 4 | `assignment` | `(Lscala/collection/immutable/Seq;)Lorg/apache/pekko/kafka/ManualSubscription;` | *(none)* |
| 5 | `assignment` | `(Lscala/collection/immutable/Set;)Lorg/apache/pekko/kafka/ManualSubscription;` | *(none)* |
| 6 | `topicPattern` | `(Ljava/lang/String;)Lorg/apache/pekko/kafka/AutoSubscription;` | 0 |
| 7 | `topics` | `(Ljava/util/Set;)Lorg/apache/pekko/kafka/AutoSubscription;` | *(none)* |
| 8 | `topics` | `(Lscala/collection/immutable/Seq;)Lorg/apache/pekko/kafka/AutoSubscription;` | *(none)* |
| 9 | `topics` | `(Lscala/collection/immutable/Set;)Lorg/apache/pekko/kafka/AutoSubscription;` | *(none)* |

Row 1's `TopicPartition...` array is `Subscriptions.assignment`'s own varargs form —
declared here as "topic argument 0" because the shape matches, but NOT declared as a
`channel_via` form in `pekko-connectors-kafka.yml`: each `TopicPartition` element
carries the topic as its own constructor argument, one hop further than `all_strings`
reads (the same boundary `kafka-consumer.yml`'s header states for the raw
`KafkaConsumer.assign(Collection<TopicPartition>)`). Rows 3-5 and 7-9 are Scala
collection overloads (`Set`, `Seq`) a Java caller does not write through the factory's
own Java-facing surface and carry no readable shape at all.

**`org.apache.pekko.kafka.javadsl.Producer`** (org.apache.pekko:pekko-connectors-kafka_2.13:1.1.0)

| # | method | descriptor | topic argument |
|---|---|---|---|
| 1 | `flexiFlow` | `(Lorg/apache/pekko/kafka/ProducerSettings;Lorg/apache/kafka/clients/producer/Producer;)Lorg/apache/pekko/stream/javadsl/Flow;` | *(none)* |
| 2 | `flexiFlow` | `(Lorg/apache/pekko/kafka/ProducerSettings;)Lorg/apache/pekko/stream/javadsl/Flow;` | *(none)* |
| 3 | `committableSink` | `(Lorg/apache/pekko/kafka/ProducerSettings;Lorg/apache/pekko/kafka/CommitterSettings;)Lorg/apache/pekko/stream/javadsl/Sink;` | *(none)* |
| 4 | `committableSink` | `(Lorg/apache/pekko/kafka/ProducerSettings;Lorg/apache/kafka/clients/producer/Producer;)Lorg/apache/pekko/stream/javadsl/Sink;` | *(none)* |
| 5 | `committableSink` | `(Lorg/apache/pekko/kafka/ProducerSettings;)Lorg/apache/pekko/stream/javadsl/Sink;` | *(none)* |
| 6 | `plainSink` | `(Lorg/apache/pekko/kafka/ProducerSettings;Lorg/apache/kafka/clients/producer/Producer;)Lorg/apache/pekko/stream/javadsl/Sink;` | *(none)* |
| 7 | `plainSink` | `(Lorg/apache/pekko/kafka/ProducerSettings;)Lorg/apache/pekko/stream/javadsl/Sink;` | *(none)* |

Every `Producer` method carries `ProducerSettings` and, where present, a
`Producer<K,V>`/`CommitterSettings` — never a topic. Confirms `pekko-connectors-
kafka.yml`'s own `slice.outside` entry: the outbound half derives nothing, stated.
