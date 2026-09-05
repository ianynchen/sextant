# CP-10 — every catalog `descriptor:`, against the bytecode it claims (descriptor sweep, R7)

**Question.** A `methods` row may pin itself to one overload by declaring that
overload's erased JVM `descriptor`, compared verbatim against a call site's own
`target.descriptor`. Load-time validation checks only that the value is a string
opening with `(`. So: **does every descriptor a shipped catalog declares name a
method the framework's own bytecode actually declares, at that name, on that
owner or a supertype of it?**

The question is worth a probe because of the failure mode, not the likelihood. A
descriptor with a wrong return type, a misspelled package or a stale erasure is
*well-formed and wrong*: it passes validation, it CLAIMS its candidate set in
`_matching_method` — every row sharing the name that admits this argument count
— and every overload of that name then derives **nothing at all**. No error, no
`docs/COVERAGE.md` row, and every test asserting absence still passes. Twenty-
three rows gained a descriptor in one sweep; a check that each opens with `(`
would have waved all twenty-three through.

**Version scope (§5.4).** Read against **google-cloud-pubsub 1.129.3,
jakarta.jms-api 3.1.0, spring-cloud-aws-sqs 3.1.1, spring-kafka 3.1.4,
spring-rabbit 3.1.4, kafka-clients 3.6.2, spring-ws-core 4.1.4,
spring-cloud-gcp-pubsub 5.1.2, spring-jms 6.1.6, spring-web 6.1.6 and
spring-websocket 6.1.6**. A descriptor is version-scoped in the strongest sense:
an overload added or a parameter re-typed in a later release is a different
answer, and every verdict below is evidence about those eleven artifacts and no
other. Widening it means adding a coordinate to `ARTIFACTS` in
`scripts/probes/cp10_catalog_descriptors/run.sh` and re-running, never assuming.

Ten of the eleven are the versions a fixture pom already pins. **`spring-websocket`
is the exception and is a stated assumption rather than a measurement**: no
fixture, and no pom anywhere in this repository, depends on it at all, so 6.1.6
was chosen to match the Spring Framework version the fixtures do pin. If a
WebSocket fixture is ever built at a different Spring version, that row is
re-measured, not carried over.

**How to run.** `bash scripts/probes/cp10_catalog_descriptors/run.sh`. It
resolves each artifact above through Maven (network on the first run only,
cached in `~/.m2` afterwards), reads every `descriptor:` out of
`src/sextant/catalogs/*.yml`, indexes class → jar off the archives it opened,
and asks `javap -p -s` for the descriptors the owner declares — walking
superclasses while they are on the same classpath, because
`SqsTemplate.send(String, T)` is declared on `AbstractMessagingTemplate` and a
check blind to inheritance would report a real descriptor as missing. It ends by
printing the two tables below. Needs a JDK and Maven. Not a test: nothing in the
suite runs it, and NFR-1's no-network rule governs the suite rather than evidence
gathering.

`tests/architecture/test_catalog_descriptors.py` is the offline half. It pins
the shipped catalogs against the table below in both directions and fails on any
row whose verdict is not `declared`, so a descriptor added without re-running
this harness fails the suite rather than going quiet.

## Expectation table

| # | Under test | Expected |
|---|---|---|
| 1 | every `descriptor:` in every shipped catalog | named by `javap -p -s` on the owner or a superclass |
| 2 | the jar each owner was resolved out of | the artifact the run opened, not one mapped by hand |
| 3 | the version filed against each row | what that jar reports about itself |
| 4 | a descriptor the jar does not declare | reported `NOT DECLARED`, and fatal to the suite |

## Observations

Verbatim from `run.sh`'s generated tables. **Every column header of the first
table is a version the JAR itself reported** — out of Maven's `pom.properties`,
the manifest's `Implementation-Version`, or Kafka's own
`kafka-version.properties`, whichever that artifact writes — and
**not the version the coordinate list asked for**.
`descriptors.py` reads the value out of
the archive it opened and ABORTS the whole run when it disagrees with the
coordinate that resolved the jar, rather than filling a mislabelled column; that
is CP-5's failure, which printed a version it believed beside output from a
version it had not run. The second table's `artifact` column is likewise the jar
the run found the owner class in, discovered by indexing the archives rather than
by a hand-written owner→artifact map.

| what the run read | 1.129.3 | 3.1.0 | 3.1.1 | 3.1.4 | 3.6.2 | 4.1.4 | 5.1.2 | 6.1.6 |
|---|---|---|---|---|---|---|---|---|
| artifacts reporting this version | google-cloud-pubsub | jakarta.jms-api | spring-cloud-aws-sqs | spring-kafka, spring-rabbit | kafka-clients | spring-ws-core | spring-cloud-gcp-pubsub | spring-jms, spring-web, spring-websocket |
| owner classes resolved out of them | 1 | 1 | 1 | 3 | 2 | 1 | 1 | 1 |
| catalog descriptors checked against them | 1 | 2 | 4 | 10 | 3 | 3 | 3 | 1 |
| of those, NOT declared by the jar | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

| # | catalog | owner | method | arity | descriptor | artifact | version | verdict |
|---|---|---|---|---|---|---|---|---|
| 1 | `google-pubsub-client` | `com.google.cloud.pubsub.v1.Publisher` | `publish` | 1 | `(Lcom/google/pubsub/v1/PubsubMessage;)Lcom/google/api/core/ApiFuture;` | `google-cloud-pubsub` | 1.129.3 | declared |
| 2 | `jakarta-jms` | `jakarta.jms.Session` | `createProducer` | 1 | `(Ljakarta/jms/Destination;)Ljakarta/jms/MessageProducer;` | `jakarta.jms-api` | 3.1.0 | declared |
| 3 | `jakarta-jms` | `jakarta.jms.Session` | `createConsumer` | 1 | `(Ljakarta/jms/Destination;)Ljakarta/jms/MessageConsumer;` | `jakarta.jms-api` | 3.1.0 | declared |
| 4 | `kafka-clients` | `org.apache.kafka.clients.producer.KafkaProducer` | `send` | 1 | `(Lorg/apache/kafka/clients/producer/ProducerRecord;)Ljava/util/concurrent/Future;` | `kafka-clients` | 3.6.2 | declared |
| 5 | `kafka-consumer` | `org.apache.kafka.clients.consumer.KafkaConsumer` | `subscribe` | 1 | `(Ljava/util/Collection;)V` | `kafka-clients` | 3.6.2 | declared |
| 6 | `kafka-consumer` | `org.apache.kafka.clients.consumer.KafkaConsumer` | `subscribe` | 1 | `(Ljava/util/regex/Pattern;)V` | `kafka-clients` | 3.6.2 | declared |
| 7 | `spring-jms-template` | `org.springframework.jms.core.JmsTemplate` | `convertAndSend` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)V` | `spring-jms` | 6.1.6 | declared |
| 8 | `spring-kafka-replying` | `org.springframework.kafka.requestreply.ReplyingKafkaTemplate` | `sendAndReceive` | 1 | `(Lorg/apache/kafka/clients/producer/ProducerRecord;)Lorg/springframework/kafka/requestreply/RequestReplyFuture;` | `spring-kafka` | 3.1.4 | declared |
| 9 | `spring-kafka-replying` | `org.springframework.kafka.requestreply.ReplyingKafkaTemplate` | `sendAndReceive` | 1 | `(Lorg/springframework/messaging/Message;)Lorg/springframework/kafka/requestreply/RequestReplyMessageFuture;` | `spring-kafka` | 3.1.4 | declared |
| 10 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `send` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 11 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `send` | 3 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 12 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `send` | 1 | `(Lorg/apache/kafka/clients/producer/ProducerRecord;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 13 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `send` | 1 | `(Lorg/springframework/messaging/Message;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 14 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `sendDefault` | 1 | `(Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 15 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `publish` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 16 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `publish` | 2 | `(Ljava/lang/String;Lcom/google/pubsub/v1/PubsubMessage;)Ljava/util/concurrent/CompletableFuture;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 17 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `subscribeAndConvert` | 3 | `(Ljava/lang/String;Ljava/util/function/Consumer;Ljava/lang/Class;)Lcom/google/cloud/pubsub/v1/Subscriber;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 18 | `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `convertAndSend` | 3 | `(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;)V` | `spring-rabbit` | 3.1.4 | declared |
| 19 | `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `convertAndSend` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)V` | `spring-rabbit` | 3.1.4 | declared |
| 20 | `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `convertAndSend` | 1 | `(Ljava/lang/Object;)V` | `spring-rabbit` | 3.1.4 | declared |
| 21 | `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsTemplate` | `send` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)Lio/awspring/cloud/sqs/operations/SendResult;` | `spring-cloud-aws-sqs` | 3.1.1 | declared |
| 22 | `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsTemplate` | `send` | 2 | `(Ljava/lang/String;Lorg/springframework/messaging/Message;)Lio/awspring/cloud/sqs/operations/SendResult;` | `spring-cloud-aws-sqs` | 3.1.1 | declared |
| 23 | `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsTemplate` | `send` | 1 | `(Ljava/lang/Object;)Lio/awspring/cloud/sqs/operations/SendResult;` | `spring-cloud-aws-sqs` | 3.1.1 | declared |
| 24 | `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsTemplate` | `send` | 1 | `(Ljava/util/function/Consumer;)Lio/awspring/cloud/sqs/operations/SendResult;` | `spring-cloud-aws-sqs` | 3.1.1 | declared |
| 25 | `spring-ws-template` | `org.springframework.ws.client.core.WebServiceTemplate` | `marshalSendAndReceive` | 1 | `(Ljava/lang/Object;)Ljava/lang/Object;` | `spring-ws-core` | 4.1.4 | declared |
| 26 | `spring-ws-template` | `org.springframework.ws.client.core.WebServiceTemplate` | `marshalSendAndReceive` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)Ljava/lang/Object;` | `spring-ws-core` | 4.1.4 | declared |
| 27 | `spring-ws-template` | `org.springframework.ws.client.core.WebServiceTemplate` | `marshalSendAndReceive` | 3 | `(Ljava/lang/String;Ljava/lang/Object;Lorg/springframework/ws/client/core/WebServiceMessageCallback;)Ljava/lang/Object;` | `spring-ws-core` | 4.1.4 | declared |

Every row `declared`, and the negative control was exercised rather than
assumed: mangling one shipped descriptor's return type (`)V` → `)Z`) turns its
row into `NOT DECLARED` and its version column's failure count from 0 to 1.

## Verdict

1. **Every descriptor a shipped catalog declares is real** — named by `javap -p
   -s` on the owner class or on a superclass reachable from the same jar set, at
   the versions above. Nothing in the sweep was mistyped, and nothing was
   transcribed from a source-level signature.
2. **An inherited method is still the owner's**, and the check has to know it.
   `SqsTemplate` declares only `send(Consumer)` itself; the arity-1 and arity-2
   forms come from `AbstractMessagingTemplate`. A call on a variable typed
   `SqsTemplate` records `SqsTemplate` as the owner all the same — javac emits
   the compile-time qualifying type — so a descriptor check that stopped at
   declared methods would have called a correct row wrong.
3. **The check is offline and the measurement is not.** The suite reads this
   file; only this harness reads a jar. That split is what keeps NFR-1's
   no-network rule and §5.4's measured-evidence rule from pulling against each
   other.

## What this probe deliberately did not measure

- **Whether the owner is the type a real call records.** A call made through an
  interface or supertype records THAT type — `SqsOperations`, `AmqpTemplate`,
  `JmsOperations`, `Consumer` — and matches no shipped catalog, whose
  `matches.owner` is single-valued. The descriptors are identical either way
  (verified while auditing), so this is an **owner** problem a descriptor cannot
  fix; it is a stated boundary in `docs/COVERAGE.md` and engine work, not a
  catalog edit.
- **Whether an overload the catalogs do NOT declare exists.** The table answers
  "is this string real", never "is this the complete overload set". The catalogs'
  own comments carry the overload lists, and each names `javap` as its check.
- **`spring-webflux-router.yml`'s `methods: [route, nest]`.** A bare name list
  read by the `combinator` engine, which has no `descriptor` support at all
  (`engines/combinator.py` matches on owner and name alone). Different grammar,
  different engine; nothing here applies to it.
- **Any language but the JVM's.** `descriptor` is whatever a module's own
  extractor records at `target.descriptor`; this harness reads JVM bytecode
  because every catalog declaring one today names a JVM owner.

## How the verdict is consumed

`tests/architecture/test_catalog_descriptors.py` pins every shipped catalog
against the table above and fails on a descriptor that was never measured, a
measurement no catalog still declares, or a verdict other than `declared`.
