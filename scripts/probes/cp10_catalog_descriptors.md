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
jakarta.jms-api 3.1.0, javax.jms-api 2.0.1, spring-cloud-aws-sqs 3.1.1, spring-kafka 3.1.4,
spring-rabbit 3.1.4, kafka-clients 3.6.2, spring-ws-core 4.1.4,
spring-cloud-gcp-pubsub 5.1.2, spring-jms 6.1.6, spring-web 6.1.6 and
spring-websocket 6.1.6**. `javax.jms-api 2.0.1` is the LAST release under that
coordinate — the line does not ship again — so it is the only version a Spring Boot 2
codebase can be on, and W12's `javax-jms.yml` is measured against it here rather than
being trusted as `jakarta-jms.yml` with the package swapped. A descriptor is
version-scoped in the strongest sense:
an overload added or a parameter re-typed in a later release is a different
answer, and every verdict below is evidence about those twelve artifacts and no
other. Widening it means adding a coordinate to `ARTIFACTS` in
`scripts/probes/cp10_catalog_descriptors/run.sh` and re-running, never assuming.

Ten of the twelve are the versions a fixture pom already pins. **Two are not, and
each says why rather than being carried silently.** `spring-websocket` is a stated
assumption rather than a measurement: no fixture, and no pom anywhere in this
repository, depends on it at all, so 6.1.6 was chosen to match the Spring Framework
version the fixtures do pin, and if a WebSocket fixture is ever built at a different
Spring version that row is re-measured rather than carried over. `javax.jms-api
2.0.1` is not a choice at all: it is the last release under that coordinate, so
there is no other version for a row to be measured at.

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


| what the run read | 1.129.3 | 2.0.1 | 3.1.0 | 3.1.1 | 3.1.4 | 3.6.2 | 4.1.4 | 5.1.2 | 6.1.6 |
|---|---|---|---|---|---|---|---|---|---|
| artifacts reporting this version | google-cloud-pubsub | javax.jms-api | jakarta.jms-api | spring-cloud-aws-sqs | spring-amqp, spring-kafka, spring-rabbit | kafka-clients | spring-ws-core | spring-cloud-gcp-pubsub | spring-jms, spring-messaging, spring-web, spring-websocket |
| owner classes resolved out of them | 1 | 1 | 1 | 2 | 5 | 4 | 1 | 1 | 8 |
| catalog descriptors checked against them | 1 | 12 | 12 | 8 | 28 | 12 | 3 | 12 | 86 |
| of those, NOT declared by the jar | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

| # | catalog | owner | method | arity | descriptor | artifact | version | verdict |
|---|---|---|---|---|---|---|---|---|
| 1 | `google-pubsub-client` | `com.google.cloud.pubsub.v1.Publisher` | `publish` | 1 | `(Lcom/google/pubsub/v1/PubsubMessage;)Lcom/google/api/core/ApiFuture;` | `google-cloud-pubsub` | 1.129.3 | declared |
| 2 | `jakarta-jms` | `jakarta.jms.Session` | `createProducer` | 1 | `(Ljakarta/jms/Destination;)Ljakarta/jms/MessageProducer;` | `jakarta.jms-api` | 3.1.0 | declared |
| 3 | `jakarta-jms` | `jakarta.jms.Session` | `createConsumer` | 1 | `(Ljakarta/jms/Destination;)Ljakarta/jms/MessageConsumer;` | `jakarta.jms-api` | 3.1.0 | declared |
| 4 | `jakarta-jms` | `jakarta.jms.Session` | `createConsumer` | 2 | `(Ljakarta/jms/Destination;Ljava/lang/String;)Ljakarta/jms/MessageConsumer;` | `jakarta.jms-api` | 3.1.0 | declared |
| 5 | `jakarta-jms` | `jakarta.jms.Session` | `createConsumer` | 3 | `(Ljakarta/jms/Destination;Ljava/lang/String;Z)Ljakarta/jms/MessageConsumer;` | `jakarta.jms-api` | 3.1.0 | declared |
| 6 | `jakarta-jms` | `jakarta.jms.Session` | `createSharedConsumer` | 2 | `(Ljakarta/jms/Topic;Ljava/lang/String;)Ljakarta/jms/MessageConsumer;` | `jakarta.jms-api` | 3.1.0 | declared |
| 7 | `jakarta-jms` | `jakarta.jms.Session` | `createSharedConsumer` | 3 | `(Ljakarta/jms/Topic;Ljava/lang/String;Ljava/lang/String;)Ljakarta/jms/MessageConsumer;` | `jakarta.jms-api` | 3.1.0 | declared |
| 8 | `jakarta-jms` | `jakarta.jms.Session` | `createDurableSubscriber` | 2 | `(Ljakarta/jms/Topic;Ljava/lang/String;)Ljakarta/jms/TopicSubscriber;` | `jakarta.jms-api` | 3.1.0 | declared |
| 9 | `jakarta-jms` | `jakarta.jms.Session` | `createDurableSubscriber` | 4 | `(Ljakarta/jms/Topic;Ljava/lang/String;Ljava/lang/String;Z)Ljakarta/jms/TopicSubscriber;` | `jakarta.jms-api` | 3.1.0 | declared |
| 10 | `jakarta-jms` | `jakarta.jms.Session` | `createDurableConsumer` | 2 | `(Ljakarta/jms/Topic;Ljava/lang/String;)Ljakarta/jms/MessageConsumer;` | `jakarta.jms-api` | 3.1.0 | declared |
| 11 | `jakarta-jms` | `jakarta.jms.Session` | `createDurableConsumer` | 4 | `(Ljakarta/jms/Topic;Ljava/lang/String;Ljava/lang/String;Z)Ljakarta/jms/MessageConsumer;` | `jakarta.jms-api` | 3.1.0 | declared |
| 12 | `jakarta-jms` | `jakarta.jms.Session` | `createSharedDurableConsumer` | 2 | `(Ljakarta/jms/Topic;Ljava/lang/String;)Ljakarta/jms/MessageConsumer;` | `jakarta.jms-api` | 3.1.0 | declared |
| 13 | `jakarta-jms` | `jakarta.jms.Session` | `createSharedDurableConsumer` | 3 | `(Ljakarta/jms/Topic;Ljava/lang/String;Ljava/lang/String;)Ljakarta/jms/MessageConsumer;` | `jakarta.jms-api` | 3.1.0 | declared |
| 14 | `javax-jms` | `javax.jms.Session` | `createProducer` | 1 | `(Ljavax/jms/Destination;)Ljavax/jms/MessageProducer;` | `javax.jms-api` | 2.0.1 | declared |
| 15 | `javax-jms` | `javax.jms.Session` | `createConsumer` | 1 | `(Ljavax/jms/Destination;)Ljavax/jms/MessageConsumer;` | `javax.jms-api` | 2.0.1 | declared |
| 16 | `javax-jms` | `javax.jms.Session` | `createConsumer` | 2 | `(Ljavax/jms/Destination;Ljava/lang/String;)Ljavax/jms/MessageConsumer;` | `javax.jms-api` | 2.0.1 | declared |
| 17 | `javax-jms` | `javax.jms.Session` | `createConsumer` | 3 | `(Ljavax/jms/Destination;Ljava/lang/String;Z)Ljavax/jms/MessageConsumer;` | `javax.jms-api` | 2.0.1 | declared |
| 18 | `javax-jms` | `javax.jms.Session` | `createSharedConsumer` | 2 | `(Ljavax/jms/Topic;Ljava/lang/String;)Ljavax/jms/MessageConsumer;` | `javax.jms-api` | 2.0.1 | declared |
| 19 | `javax-jms` | `javax.jms.Session` | `createSharedConsumer` | 3 | `(Ljavax/jms/Topic;Ljava/lang/String;Ljava/lang/String;)Ljavax/jms/MessageConsumer;` | `javax.jms-api` | 2.0.1 | declared |
| 20 | `javax-jms` | `javax.jms.Session` | `createDurableSubscriber` | 2 | `(Ljavax/jms/Topic;Ljava/lang/String;)Ljavax/jms/TopicSubscriber;` | `javax.jms-api` | 2.0.1 | declared |
| 21 | `javax-jms` | `javax.jms.Session` | `createDurableSubscriber` | 4 | `(Ljavax/jms/Topic;Ljava/lang/String;Ljava/lang/String;Z)Ljavax/jms/TopicSubscriber;` | `javax.jms-api` | 2.0.1 | declared |
| 22 | `javax-jms` | `javax.jms.Session` | `createDurableConsumer` | 2 | `(Ljavax/jms/Topic;Ljava/lang/String;)Ljavax/jms/MessageConsumer;` | `javax.jms-api` | 2.0.1 | declared |
| 23 | `javax-jms` | `javax.jms.Session` | `createDurableConsumer` | 4 | `(Ljavax/jms/Topic;Ljava/lang/String;Ljava/lang/String;Z)Ljavax/jms/MessageConsumer;` | `javax.jms-api` | 2.0.1 | declared |
| 24 | `javax-jms` | `javax.jms.Session` | `createSharedDurableConsumer` | 2 | `(Ljavax/jms/Topic;Ljava/lang/String;)Ljavax/jms/MessageConsumer;` | `javax.jms-api` | 2.0.1 | declared |
| 25 | `javax-jms` | `javax.jms.Session` | `createSharedDurableConsumer` | 3 | `(Ljavax/jms/Topic;Ljava/lang/String;Ljava/lang/String;)Ljavax/jms/MessageConsumer;` | `javax.jms-api` | 2.0.1 | declared |
| 26 | `kafka-clients` | `org.apache.kafka.clients.producer.KafkaProducer` | `send` | 1 | `(Lorg/apache/kafka/clients/producer/ProducerRecord;)Ljava/util/concurrent/Future;` | `kafka-clients` | 3.6.2 | declared |
| 27 | `kafka-clients` | `org.apache.kafka.clients.producer.Producer` | `send` | 1 | `(Lorg/apache/kafka/clients/producer/ProducerRecord;)Ljava/util/concurrent/Future;` | `kafka-clients` | 3.6.2 | declared |
| 28 | `kafka-clients` | `org.apache.kafka.clients.producer.KafkaProducer` | `send` | 2 | `(Lorg/apache/kafka/clients/producer/ProducerRecord;Lorg/apache/kafka/clients/producer/Callback;)Ljava/util/concurrent/Future;` | `kafka-clients` | 3.6.2 | declared |
| 29 | `kafka-clients` | `org.apache.kafka.clients.producer.Producer` | `send` | 2 | `(Lorg/apache/kafka/clients/producer/ProducerRecord;Lorg/apache/kafka/clients/producer/Callback;)Ljava/util/concurrent/Future;` | `kafka-clients` | 3.6.2 | declared |
| 30 | `kafka-consumer` | `org.apache.kafka.clients.consumer.KafkaConsumer` | `subscribe` | 1 | `(Ljava/util/Collection;)V` | `kafka-clients` | 3.6.2 | declared |
| 31 | `kafka-consumer` | `org.apache.kafka.clients.consumer.Consumer` | `subscribe` | 1 | `(Ljava/util/Collection;)V` | `kafka-clients` | 3.6.2 | declared |
| 32 | `kafka-consumer` | `org.apache.kafka.clients.consumer.KafkaConsumer` | `subscribe` | 1 | `(Ljava/util/regex/Pattern;)V` | `kafka-clients` | 3.6.2 | declared |
| 33 | `kafka-consumer` | `org.apache.kafka.clients.consumer.Consumer` | `subscribe` | 1 | `(Ljava/util/regex/Pattern;)V` | `kafka-clients` | 3.6.2 | declared |
| 34 | `kafka-consumer` | `org.apache.kafka.clients.consumer.KafkaConsumer` | `subscribe` | 2 | `(Ljava/util/Collection;Lorg/apache/kafka/clients/consumer/ConsumerRebalanceListener;)V` | `kafka-clients` | 3.6.2 | declared |
| 35 | `kafka-consumer` | `org.apache.kafka.clients.consumer.Consumer` | `subscribe` | 2 | `(Ljava/util/Collection;Lorg/apache/kafka/clients/consumer/ConsumerRebalanceListener;)V` | `kafka-clients` | 3.6.2 | declared |
| 36 | `kafka-consumer` | `org.apache.kafka.clients.consumer.KafkaConsumer` | `subscribe` | 2 | `(Ljava/util/regex/Pattern;Lorg/apache/kafka/clients/consumer/ConsumerRebalanceListener;)V` | `kafka-clients` | 3.6.2 | declared |
| 37 | `kafka-consumer` | `org.apache.kafka.clients.consumer.Consumer` | `subscribe` | 2 | `(Ljava/util/regex/Pattern;Lorg/apache/kafka/clients/consumer/ConsumerRebalanceListener;)V` | `kafka-clients` | 3.6.2 | declared |
| 38 | `spring-jms-template` | `org.springframework.jms.core.JmsTemplate` | `convertAndSend` | 3 | `(Ljava/lang/String;Ljava/lang/Object;Lorg/springframework/jms/core/MessagePostProcessor;)V` | `spring-jms` | 6.1.6 | declared |
| 39 | `spring-jms-template` | `org.springframework.jms.core.JmsOperations` | `convertAndSend` | 3 | `(Ljava/lang/String;Ljava/lang/Object;Lorg/springframework/jms/core/MessagePostProcessor;)V` | `spring-jms` | 6.1.6 | declared |
| 40 | `spring-jms-template` | `org.springframework.jms.core.JmsTemplate` | `convertAndSend` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)V` | `spring-jms` | 6.1.6 | declared |
| 41 | `spring-jms-template` | `org.springframework.jms.core.JmsOperations` | `convertAndSend` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)V` | `spring-jms` | 6.1.6 | declared |
| 42 | `spring-jms-template` | `org.springframework.jms.core.JmsTemplate` | `convertAndSend` | 2 | `(Ljakarta/jms/Destination;Ljava/lang/Object;)V` | `spring-jms` | 6.1.6 | declared |
| 43 | `spring-jms-template` | `org.springframework.jms.core.JmsOperations` | `convertAndSend` | 2 | `(Ljakarta/jms/Destination;Ljava/lang/Object;)V` | `spring-jms` | 6.1.6 | declared |
| 44 | `spring-jms-template` | `org.springframework.jms.core.JmsTemplate` | `convertAndSend` | 1 | `(Ljava/lang/Object;)V` | `spring-jms` | 6.1.6 | declared |
| 45 | `spring-jms-template` | `org.springframework.jms.core.JmsOperations` | `convertAndSend` | 1 | `(Ljava/lang/Object;)V` | `spring-jms` | 6.1.6 | declared |
| 46 | `spring-kafka-replying` | `org.springframework.kafka.requestreply.ReplyingKafkaTemplate` | `sendAndReceive` | 1 | `(Lorg/apache/kafka/clients/producer/ProducerRecord;)Lorg/springframework/kafka/requestreply/RequestReplyFuture;` | `spring-kafka` | 3.1.4 | declared |
| 47 | `spring-kafka-replying` | `org.springframework.kafka.requestreply.ReplyingKafkaTemplate` | `sendAndReceive` | 1 | `(Lorg/springframework/messaging/Message;)Lorg/springframework/kafka/requestreply/RequestReplyMessageFuture;` | `spring-kafka` | 3.1.4 | declared |
| 48 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `send` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 49 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaOperations` | `send` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 50 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `send` | 3 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 51 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaOperations` | `send` | 3 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 52 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `send` | 1 | `(Lorg/apache/kafka/clients/producer/ProducerRecord;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 53 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaOperations` | `send` | 1 | `(Lorg/apache/kafka/clients/producer/ProducerRecord;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 54 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `send` | 1 | `(Lorg/springframework/messaging/Message;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 55 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaOperations` | `send` | 1 | `(Lorg/springframework/messaging/Message;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 56 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `send` | 4 | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 57 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaOperations` | `send` | 4 | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 58 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `send` | 5 | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Long;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 59 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaOperations` | `send` | 5 | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Long;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 60 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `sendDefault` | 1 | `(Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 61 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaOperations` | `sendDefault` | 1 | `(Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 62 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `sendDefault` | 2 | `(Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 63 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaOperations` | `sendDefault` | 2 | `(Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 64 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `sendDefault` | 3 | `(Ljava/lang/Integer;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 65 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaOperations` | `sendDefault` | 3 | `(Ljava/lang/Integer;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 66 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `sendDefault` | 4 | `(Ljava/lang/Integer;Ljava/lang/Long;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 67 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaOperations` | `sendDefault` | 4 | `(Ljava/lang/Integer;Ljava/lang/Long;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 68 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `publish` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 69 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `publish` | 2 | `(Ljava/lang/String;Lcom/google/pubsub/v1/PubsubMessage;)Ljava/util/concurrent/CompletableFuture;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 70 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `subscribeAndConvert` | 3 | `(Ljava/lang/String;Ljava/util/function/Consumer;Ljava/lang/Class;)Lcom/google/cloud/pubsub/v1/Subscriber;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 71 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `subscribe` | 2 | `(Ljava/lang/String;Ljava/util/function/Consumer;)Lcom/google/cloud/pubsub/v1/Subscriber;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 72 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `pull` | 3 | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Boolean;)Ljava/util/List;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 73 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `pullAsync` | 3 | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Boolean;)Ljava/util/concurrent/CompletableFuture;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 74 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `pullAndConvert` | 4 | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Boolean;Ljava/lang/Class;)Ljava/util/List;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 75 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `pullAndConvertAsync` | 4 | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Boolean;Ljava/lang/Class;)Ljava/util/concurrent/CompletableFuture;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 76 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `pullAndAck` | 3 | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Boolean;)Ljava/util/List;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 77 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `pullAndAckAsync` | 3 | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Boolean;)Ljava/util/concurrent/CompletableFuture;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 78 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `pullNext` | 1 | `(Ljava/lang/String;)Lcom/google/pubsub/v1/PubsubMessage;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 79 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `pullNextAsync` | 1 | `(Ljava/lang/String;)Ljava/util/concurrent/CompletableFuture;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 80 | `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `convertAndSend` | 3 | `(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;)V` | `spring-rabbit` | 3.1.4 | declared |
| 81 | `spring-rabbit-template` | `org.springframework.amqp.core.AmqpTemplate` | `convertAndSend` | 3 | `(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;)V` | `spring-amqp` | 3.1.4 | declared |
| 82 | `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `convertAndSend` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)V` | `spring-rabbit` | 3.1.4 | declared |
| 83 | `spring-rabbit-template` | `org.springframework.amqp.core.AmqpTemplate` | `convertAndSend` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)V` | `spring-amqp` | 3.1.4 | declared |
| 84 | `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `convertAndSend` | 1 | `(Ljava/lang/Object;)V` | `spring-rabbit` | 3.1.4 | declared |
| 85 | `spring-rabbit-template` | `org.springframework.amqp.core.AmqpTemplate` | `convertAndSend` | 1 | `(Ljava/lang/Object;)V` | `spring-amqp` | 3.1.4 | declared |
| 86 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `getForObject` | 3 | `(Ljava/lang/String;Ljava/lang/Class;[Ljava/lang/Object;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 87 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `getForObject` | 3 | `(Ljava/lang/String;Ljava/lang/Class;[Ljava/lang/Object;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 88 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `getForObject` | 3 | `(Ljava/lang/String;Ljava/lang/Class;Ljava/util/Map;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 89 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `getForObject` | 3 | `(Ljava/lang/String;Ljava/lang/Class;Ljava/util/Map;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 90 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `getForObject` | 2 | `(Ljava/net/URI;Ljava/lang/Class;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 91 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `getForObject` | 2 | `(Ljava/net/URI;Ljava/lang/Class;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 92 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `getForEntity` | 3 | `(Ljava/lang/String;Ljava/lang/Class;[Ljava/lang/Object;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 93 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `getForEntity` | 3 | `(Ljava/lang/String;Ljava/lang/Class;[Ljava/lang/Object;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 94 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `getForEntity` | 3 | `(Ljava/lang/String;Ljava/lang/Class;Ljava/util/Map;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 95 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `getForEntity` | 3 | `(Ljava/lang/String;Ljava/lang/Class;Ljava/util/Map;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 96 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `getForEntity` | 2 | `(Ljava/net/URI;Ljava/lang/Class;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 97 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `getForEntity` | 2 | `(Ljava/net/URI;Ljava/lang/Class;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 98 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `postForObject` | 4 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Class;[Ljava/lang/Object;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 99 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `postForObject` | 4 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Class;[Ljava/lang/Object;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 100 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `postForObject` | 4 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Class;Ljava/util/Map;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 101 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `postForObject` | 4 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Class;Ljava/util/Map;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 102 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `postForObject` | 3 | `(Ljava/net/URI;Ljava/lang/Object;Ljava/lang/Class;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 103 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `postForObject` | 3 | `(Ljava/net/URI;Ljava/lang/Object;Ljava/lang/Class;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 104 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `postForEntity` | 4 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Class;[Ljava/lang/Object;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 105 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `postForEntity` | 4 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Class;[Ljava/lang/Object;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 106 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `postForEntity` | 4 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Class;Ljava/util/Map;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 107 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `postForEntity` | 4 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Class;Ljava/util/Map;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 108 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `postForEntity` | 3 | `(Ljava/net/URI;Ljava/lang/Object;Ljava/lang/Class;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 109 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `postForEntity` | 3 | `(Ljava/net/URI;Ljava/lang/Object;Ljava/lang/Class;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 110 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `put` | 3 | `(Ljava/lang/String;Ljava/lang/Object;[Ljava/lang/Object;)V` | `spring-web` | 6.1.6 | declared |
| 111 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `put` | 3 | `(Ljava/lang/String;Ljava/lang/Object;[Ljava/lang/Object;)V` | `spring-web` | 6.1.6 | declared |
| 112 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `put` | 3 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/util/Map;)V` | `spring-web` | 6.1.6 | declared |
| 113 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `put` | 3 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/util/Map;)V` | `spring-web` | 6.1.6 | declared |
| 114 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `put` | 2 | `(Ljava/net/URI;Ljava/lang/Object;)V` | `spring-web` | 6.1.6 | declared |
| 115 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `put` | 2 | `(Ljava/net/URI;Ljava/lang/Object;)V` | `spring-web` | 6.1.6 | declared |
| 116 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `delete` | 2 | `(Ljava/lang/String;[Ljava/lang/Object;)V` | `spring-web` | 6.1.6 | declared |
| 117 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `delete` | 2 | `(Ljava/lang/String;[Ljava/lang/Object;)V` | `spring-web` | 6.1.6 | declared |
| 118 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `delete` | 2 | `(Ljava/lang/String;Ljava/util/Map;)V` | `spring-web` | 6.1.6 | declared |
| 119 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `delete` | 2 | `(Ljava/lang/String;Ljava/util/Map;)V` | `spring-web` | 6.1.6 | declared |
| 120 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `delete` | 1 | `(Ljava/net/URI;)V` | `spring-web` | 6.1.6 | declared |
| 121 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `delete` | 1 | `(Ljava/net/URI;)V` | `spring-web` | 6.1.6 | declared |
| 122 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `exchange` | 5 | `(Ljava/lang/String;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Ljava/lang/Class;[Ljava/lang/Object;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 123 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `exchange` | 5 | `(Ljava/lang/String;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Ljava/lang/Class;[Ljava/lang/Object;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 124 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `exchange` | 5 | `(Ljava/lang/String;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Ljava/lang/Class;Ljava/util/Map;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 125 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `exchange` | 5 | `(Ljava/lang/String;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Ljava/lang/Class;Ljava/util/Map;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 126 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `exchange` | 4 | `(Ljava/net/URI;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Ljava/lang/Class;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 127 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `exchange` | 4 | `(Ljava/net/URI;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Ljava/lang/Class;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 128 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `exchange` | 5 | `(Ljava/lang/String;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Lorg/springframework/core/ParameterizedTypeReference;[Ljava/lang/Object;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 129 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `exchange` | 5 | `(Ljava/lang/String;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Lorg/springframework/core/ParameterizedTypeReference;[Ljava/lang/Object;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 130 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `exchange` | 5 | `(Ljava/lang/String;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Lorg/springframework/core/ParameterizedTypeReference;Ljava/util/Map;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 131 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `exchange` | 5 | `(Ljava/lang/String;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Lorg/springframework/core/ParameterizedTypeReference;Ljava/util/Map;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 132 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `exchange` | 4 | `(Ljava/net/URI;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Lorg/springframework/core/ParameterizedTypeReference;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 133 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `exchange` | 4 | `(Ljava/net/URI;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Lorg/springframework/core/ParameterizedTypeReference;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 134 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `exchange` | 2 | `(Lorg/springframework/http/RequestEntity;Ljava/lang/Class;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 135 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `exchange` | 2 | `(Lorg/springframework/http/RequestEntity;Ljava/lang/Class;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 136 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `exchange` | 2 | `(Lorg/springframework/http/RequestEntity;Lorg/springframework/core/ParameterizedTypeReference;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 137 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `exchange` | 2 | `(Lorg/springframework/http/RequestEntity;Lorg/springframework/core/ParameterizedTypeReference;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 138 | `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsTemplate` | `send` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)Lio/awspring/cloud/sqs/operations/SendResult;` | `spring-cloud-aws-sqs` | 3.1.1 | declared |
| 139 | `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsOperations` | `send` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)Lio/awspring/cloud/sqs/operations/SendResult;` | `spring-cloud-aws-sqs` | 3.1.1 | declared |
| 140 | `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsTemplate` | `send` | 2 | `(Ljava/lang/String;Lorg/springframework/messaging/Message;)Lio/awspring/cloud/sqs/operations/SendResult;` | `spring-cloud-aws-sqs` | 3.1.1 | declared |
| 141 | `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsOperations` | `send` | 2 | `(Ljava/lang/String;Lorg/springframework/messaging/Message;)Lio/awspring/cloud/sqs/operations/SendResult;` | `spring-cloud-aws-sqs` | 3.1.1 | declared |
| 142 | `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsTemplate` | `send` | 1 | `(Ljava/lang/Object;)Lio/awspring/cloud/sqs/operations/SendResult;` | `spring-cloud-aws-sqs` | 3.1.1 | declared |
| 143 | `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsOperations` | `send` | 1 | `(Ljava/lang/Object;)Lio/awspring/cloud/sqs/operations/SendResult;` | `spring-cloud-aws-sqs` | 3.1.1 | declared |
| 144 | `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsTemplate` | `send` | 1 | `(Ljava/util/function/Consumer;)Lio/awspring/cloud/sqs/operations/SendResult;` | `spring-cloud-aws-sqs` | 3.1.1 | declared |
| 145 | `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsOperations` | `send` | 1 | `(Ljava/util/function/Consumer;)Lio/awspring/cloud/sqs/operations/SendResult;` | `spring-cloud-aws-sqs` | 3.1.1 | declared |
| 146 | `spring-stomp-endpoint` | `org.springframework.web.socket.config.annotation.StompEndpointRegistry` | `addEndpoint` | 1 | `([Ljava/lang/String;)Lorg/springframework/web/socket/config/annotation/StompWebSocketEndpointRegistration;` | `spring-websocket` | 6.1.6 | declared |
| 147 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `convertAndSend` | 2 | `(Ljava/lang/Object;Ljava/lang/Object;)V` | `spring-messaging` | 6.1.6 | declared |
| 148 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `convertAndSend` | 2 | `(Ljava/lang/Object;Ljava/lang/Object;)V` | `spring-messaging` | 6.1.6 | declared |
| 149 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `convertAndSend` | 3 | `(Ljava/lang/Object;Ljava/lang/Object;Ljava/util/Map;)V` | `spring-messaging` | 6.1.6 | declared |
| 150 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `convertAndSend` | 3 | `(Ljava/lang/Object;Ljava/lang/Object;Ljava/util/Map;)V` | `spring-messaging` | 6.1.6 | declared |
| 151 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `convertAndSend` | 3 | `(Ljava/lang/Object;Ljava/lang/Object;Lorg/springframework/messaging/core/MessagePostProcessor;)V` | `spring-messaging` | 6.1.6 | declared |
| 152 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `convertAndSend` | 3 | `(Ljava/lang/Object;Ljava/lang/Object;Lorg/springframework/messaging/core/MessagePostProcessor;)V` | `spring-messaging` | 6.1.6 | declared |
| 153 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `convertAndSend` | 4 | `(Ljava/lang/Object;Ljava/lang/Object;Ljava/util/Map;Lorg/springframework/messaging/core/MessagePostProcessor;)V` | `spring-messaging` | 6.1.6 | declared |
| 154 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `convertAndSend` | 4 | `(Ljava/lang/Object;Ljava/lang/Object;Ljava/util/Map;Lorg/springframework/messaging/core/MessagePostProcessor;)V` | `spring-messaging` | 6.1.6 | declared |
| 155 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `convertAndSend` | 1 | `(Ljava/lang/Object;)V` | `spring-messaging` | 6.1.6 | declared |
| 156 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `convertAndSend` | 1 | `(Ljava/lang/Object;)V` | `spring-messaging` | 6.1.6 | declared |
| 157 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `convertAndSend` | 2 | `(Ljava/lang/Object;Lorg/springframework/messaging/core/MessagePostProcessor;)V` | `spring-messaging` | 6.1.6 | declared |
| 158 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `convertAndSend` | 2 | `(Ljava/lang/Object;Lorg/springframework/messaging/core/MessagePostProcessor;)V` | `spring-messaging` | 6.1.6 | declared |
| 159 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `send` | 1 | `(Lorg/springframework/messaging/Message;)V` | `spring-messaging` | 6.1.6 | declared |
| 160 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `send` | 1 | `(Lorg/springframework/messaging/Message;)V` | `spring-messaging` | 6.1.6 | declared |
| 161 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `send` | 2 | `(Ljava/lang/Object;Lorg/springframework/messaging/Message;)V` | `spring-messaging` | 6.1.6 | declared |
| 162 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `send` | 2 | `(Ljava/lang/Object;Lorg/springframework/messaging/Message;)V` | `spring-messaging` | 6.1.6 | declared |
| 163 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `convertAndSendToUser` | 3 | `(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;)V` | `spring-messaging` | 6.1.6 | declared |
| 164 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `convertAndSendToUser` | 3 | `(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;)V` | `spring-messaging` | 6.1.6 | declared |
| 165 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `convertAndSendToUser` | 4 | `(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;Ljava/util/Map;)V` | `spring-messaging` | 6.1.6 | declared |
| 166 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `convertAndSendToUser` | 4 | `(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;Ljava/util/Map;)V` | `spring-messaging` | 6.1.6 | declared |
| 167 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `convertAndSendToUser` | 4 | `(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;Lorg/springframework/messaging/core/MessagePostProcessor;)V` | `spring-messaging` | 6.1.6 | declared |
| 168 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `convertAndSendToUser` | 4 | `(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;Lorg/springframework/messaging/core/MessagePostProcessor;)V` | `spring-messaging` | 6.1.6 | declared |
| 169 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `convertAndSendToUser` | 5 | `(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;Ljava/util/Map;Lorg/springframework/messaging/core/MessagePostProcessor;)V` | `spring-messaging` | 6.1.6 | declared |
| 170 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `convertAndSendToUser` | 5 | `(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;Ljava/util/Map;Lorg/springframework/messaging/core/MessagePostProcessor;)V` | `spring-messaging` | 6.1.6 | declared |
| 171 | `spring-websocket` | `org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry` | `addHandler` | 2 | `(Lorg/springframework/web/socket/WebSocketHandler;[Ljava/lang/String;)Lorg/springframework/web/socket/config/annotation/WebSocketHandlerRegistration;` | `spring-websocket` | 6.1.6 | declared |
| 172 | `spring-ws-template` | `org.springframework.ws.client.core.WebServiceTemplate` | `marshalSendAndReceive` | 1 | `(Ljava/lang/Object;)Ljava/lang/Object;` | `spring-ws-core` | 4.1.4 | declared |
| 173 | `spring-ws-template` | `org.springframework.ws.client.core.WebServiceTemplate` | `marshalSendAndReceive` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)Ljava/lang/Object;` | `spring-ws-core` | 4.1.4 | declared |
| 174 | `spring-ws-template` | `org.springframework.ws.client.core.WebServiceTemplate` | `marshalSendAndReceive` | 3 | `(Ljava/lang/String;Ljava/lang/Object;Lorg/springframework/ws/client/core/WebServiceMessageCallback;)Ljava/lang/Object;` | `spring-ws-core` | 4.1.4 | declared |


## Verdict

**Re-run for W10 (owner alternates).** `matches.owner` may now name a LIST — one library
under the class name and under the interface a codebase more often declares its field as
(§3.1) — and this harness asks its question of each name separately, because an interface
declaring a SUBSET of the class's methods would match some call sites and silently miss the
rest. 53 of the rows above are alternate owners, and every one is `declared`.

`javax-jms.yml` is measured here too, and is NOT an alternate: an alternate is one library
under several names, while `javax.jms-api 2.0.1` and `jakarta.jms-api 3.1.0` are two jars at
two versions, each needing its own measurement (W12). All twelve of its rows come back
`declared`, and none of its descriptors is its `jakarta` counterpart with the package
swapped — `Session`'s own parameter and return types moved with the API.

Three alternates were applied after the first W10 run and are measured here for the first
time: `KafkaOperations` on `spring-kafka-template`, and Kafka's own `Consumer` and
`Producer` interfaces on `kafka-consumer` and `kafka-clients`. They were named in the
design and left out of the catalogs, which is the shape a declared-but-absent capability
takes — the same one the descriptor sweep exists to catch, from the other side.

The run also caught a wrong artifact before it could be committed: `AmqpTemplate` is in
`spring-amqp`, not in `spring-rabbit` where `RabbitTemplate` lives, so the harness ABORTED
with *"add its coordinate to run.sh rather than leaving it unmeasured"* rather than filling
a column it could not resolve. A provenance naming spring-rabbit would have been
uncheckable.


1. **Every descriptor a shipped catalog declares is real** — named by `javap -p
   -s` on the owner class or on a superclass reachable from the same jar set, at
   the versions above. Nothing in the sweep was mistyped, and nothing was
   transcribed from a source-level signature. **This is one direction only, and
   the zero failures are not a completeness result** (`A-Mi5`): the probe asks
   "is every declared descriptor real" and never "is every real overload
   declared". The second question is answered nowhere in this file — see "what
   this probe deliberately did not measure" — so a `0 NOT DECLARED` column
   means no row is wrong, not that no overload is missing. `A-M3`–`A-M7` are
   findings of exactly the second kind.
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

- **Whether the owner is the type a real call records — no longer a gap, and this
  entry is kept as the record of one.** A call made through an interface records
  THAT type, and this paragraph used to say those names "match no shipped catalog,
  whose `matches.owner` is single-valued". Both halves are now false: §3.1 widened
  `matches.owner` to a list, seven catalogs declare an alternate, and 53 of the rows
  in the table above are those very owners — `SqsOperations`, `AmqpTemplate`,
  `JmsOperations`, `RestOperations`, `KafkaOperations`, `Consumer`, `Producer` —
  every one `declared`. What the probe still does not measure is whether some FURTHER
  interface or supertype exists that no catalog names; the harness answers "is this
  owner real", never "is this the complete set of names this library is held under".
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
