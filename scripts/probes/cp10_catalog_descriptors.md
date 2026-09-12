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
spring-cloud-gcp-pubsub 5.1.2, spring-jms 6.1.6, spring-messaging 6.1.6,
spring-web 6.1.6, spring-websocket 6.1.6, jakarta.websocket-client-api 2.2.0 and
jakarta.websocket-api 2.1.1** (the last added 2026-09-11 for row 189, `G-34`; opened with
`javap -s` rather than assumed from the client-api sibling). `javax.jms-api 2.0.1` is the LAST release under that
coordinate — the line does not ship again — so it is the only version a Spring Boot 2
codebase can be on, and W12's `javax-jms.yml` is measured against it here rather than
being trusted as `jakarta-jms.yml` with the package swapped. A descriptor is
version-scoped in the strongest sense:
an overload added or a parameter re-typed in a later release is a different
answer, and every verdict below is evidence about those fourteen artifacts and no
other. Widening it means adding a coordinate to `ARTIFACTS` in
`scripts/probes/cp10_catalog_descriptors/run.sh` and re-running, never assuming.

Ten of the twelve are the versions a fixture pom already pins. **Two are not, and
each says why rather than being carried silently.** `spring-websocket` 6.1.6 is what
`fixtures/orders-service/pom.xml` declares directly, and has since W16 — *this paragraph
called it "a stated assumption rather than a measurement: no fixture, and no pom anywhere in
this repository, depends on it at all", which stopped being true then. The version is right
and the reason given for it was not*, and if a WebSocket fixture is ever built at a different
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


| what the run read | 1.129.3 | 2.0.1 | 2.1.1 | 2.2.0 | 3.1.0 | 3.1.1 | 3.1.4 | 3.6.2 | 4.1.4 | 5.1.2 | 6.1.6 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| artifacts reporting this version | google-cloud-pubsub | javax.jms-api | jakarta.websocket-api | jakarta.websocket-client-api | jakarta.jms-api | spring-cloud-aws-sqs | spring-amqp, spring-kafka, spring-rabbit | kafka-clients | spring-ws-core | spring-cloud-gcp-pubsub | spring-jms, spring-messaging, spring-web, spring-websocket |
| owner classes resolved out of them | 1 | 1 | 1 | 1 | 1 | 2 | 5 | 4 | 1 | 1 | 10 |
| catalog descriptors checked against them | 1 | 12 | 1 | 4 | 12 | 8 | 48 | 12 | 3 | 12 | 104 |
| of those, NOT declared by the jar | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

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
| 14 | `jakarta-websocket-client` | `jakarta.websocket.WebSocketContainer` | `connectToServer` | 2 | `(Ljava/lang/Object;Ljava/net/URI;)Ljakarta/websocket/Session;` | `jakarta.websocket-client-api` | 2.2.0 | declared |
| 15 | `jakarta-websocket-client` | `jakarta.websocket.WebSocketContainer` | `connectToServer` | 2 | `(Ljava/lang/Class;Ljava/net/URI;)Ljakarta/websocket/Session;` | `jakarta.websocket-client-api` | 2.2.0 | declared |
| 16 | `jakarta-websocket-client` | `jakarta.websocket.WebSocketContainer` | `connectToServer` | 3 | `(Ljakarta/websocket/Endpoint;Ljakarta/websocket/ClientEndpointConfig;Ljava/net/URI;)Ljakarta/websocket/Session;` | `jakarta.websocket-client-api` | 2.2.0 | declared |
| 17 | `jakarta-websocket-client` | `jakarta.websocket.WebSocketContainer` | `connectToServer` | 3 | `(Ljava/lang/Class;Ljakarta/websocket/ClientEndpointConfig;Ljava/net/URI;)Ljakarta/websocket/Session;` | `jakarta.websocket-client-api` | 2.2.0 | declared |
| 18 | `jakarta-websocket-programmatic` | `jakarta.websocket.server.ServerEndpointConfig$Builder` | `create` | 2 | `(Ljava/lang/Class;Ljava/lang/String;)Ljakarta/websocket/server/ServerEndpointConfig$Builder;` | `jakarta.websocket-api` | 2.1.1 | declared |
| 19 | `javax-jms` | `javax.jms.Session` | `createProducer` | 1 | `(Ljavax/jms/Destination;)Ljavax/jms/MessageProducer;` | `javax.jms-api` | 2.0.1 | declared |
| 20 | `javax-jms` | `javax.jms.Session` | `createConsumer` | 1 | `(Ljavax/jms/Destination;)Ljavax/jms/MessageConsumer;` | `javax.jms-api` | 2.0.1 | declared |
| 21 | `javax-jms` | `javax.jms.Session` | `createConsumer` | 2 | `(Ljavax/jms/Destination;Ljava/lang/String;)Ljavax/jms/MessageConsumer;` | `javax.jms-api` | 2.0.1 | declared |
| 22 | `javax-jms` | `javax.jms.Session` | `createConsumer` | 3 | `(Ljavax/jms/Destination;Ljava/lang/String;Z)Ljavax/jms/MessageConsumer;` | `javax.jms-api` | 2.0.1 | declared |
| 23 | `javax-jms` | `javax.jms.Session` | `createSharedConsumer` | 2 | `(Ljavax/jms/Topic;Ljava/lang/String;)Ljavax/jms/MessageConsumer;` | `javax.jms-api` | 2.0.1 | declared |
| 24 | `javax-jms` | `javax.jms.Session` | `createSharedConsumer` | 3 | `(Ljavax/jms/Topic;Ljava/lang/String;Ljava/lang/String;)Ljavax/jms/MessageConsumer;` | `javax.jms-api` | 2.0.1 | declared |
| 25 | `javax-jms` | `javax.jms.Session` | `createDurableSubscriber` | 2 | `(Ljavax/jms/Topic;Ljava/lang/String;)Ljavax/jms/TopicSubscriber;` | `javax.jms-api` | 2.0.1 | declared |
| 26 | `javax-jms` | `javax.jms.Session` | `createDurableSubscriber` | 4 | `(Ljavax/jms/Topic;Ljava/lang/String;Ljava/lang/String;Z)Ljavax/jms/TopicSubscriber;` | `javax.jms-api` | 2.0.1 | declared |
| 27 | `javax-jms` | `javax.jms.Session` | `createDurableConsumer` | 2 | `(Ljavax/jms/Topic;Ljava/lang/String;)Ljavax/jms/MessageConsumer;` | `javax.jms-api` | 2.0.1 | declared |
| 28 | `javax-jms` | `javax.jms.Session` | `createDurableConsumer` | 4 | `(Ljavax/jms/Topic;Ljava/lang/String;Ljava/lang/String;Z)Ljavax/jms/MessageConsumer;` | `javax.jms-api` | 2.0.1 | declared |
| 29 | `javax-jms` | `javax.jms.Session` | `createSharedDurableConsumer` | 2 | `(Ljavax/jms/Topic;Ljava/lang/String;)Ljavax/jms/MessageConsumer;` | `javax.jms-api` | 2.0.1 | declared |
| 30 | `javax-jms` | `javax.jms.Session` | `createSharedDurableConsumer` | 3 | `(Ljavax/jms/Topic;Ljava/lang/String;Ljava/lang/String;)Ljavax/jms/MessageConsumer;` | `javax.jms-api` | 2.0.1 | declared |
| 31 | `kafka-clients` | `org.apache.kafka.clients.producer.KafkaProducer` | `send` | 1 | `(Lorg/apache/kafka/clients/producer/ProducerRecord;)Ljava/util/concurrent/Future;` | `kafka-clients` | 3.6.2 | declared |
| 32 | `kafka-clients` | `org.apache.kafka.clients.producer.Producer` | `send` | 1 | `(Lorg/apache/kafka/clients/producer/ProducerRecord;)Ljava/util/concurrent/Future;` | `kafka-clients` | 3.6.2 | declared |
| 33 | `kafka-clients` | `org.apache.kafka.clients.producer.KafkaProducer` | `send` | 2 | `(Lorg/apache/kafka/clients/producer/ProducerRecord;Lorg/apache/kafka/clients/producer/Callback;)Ljava/util/concurrent/Future;` | `kafka-clients` | 3.6.2 | declared |
| 34 | `kafka-clients` | `org.apache.kafka.clients.producer.Producer` | `send` | 2 | `(Lorg/apache/kafka/clients/producer/ProducerRecord;Lorg/apache/kafka/clients/producer/Callback;)Ljava/util/concurrent/Future;` | `kafka-clients` | 3.6.2 | declared |
| 35 | `kafka-consumer` | `org.apache.kafka.clients.consumer.KafkaConsumer` | `subscribe` | 1 | `(Ljava/util/Collection;)V` | `kafka-clients` | 3.6.2 | declared |
| 36 | `kafka-consumer` | `org.apache.kafka.clients.consumer.Consumer` | `subscribe` | 1 | `(Ljava/util/Collection;)V` | `kafka-clients` | 3.6.2 | declared |
| 37 | `kafka-consumer` | `org.apache.kafka.clients.consumer.KafkaConsumer` | `subscribe` | 1 | `(Ljava/util/regex/Pattern;)V` | `kafka-clients` | 3.6.2 | declared |
| 38 | `kafka-consumer` | `org.apache.kafka.clients.consumer.Consumer` | `subscribe` | 1 | `(Ljava/util/regex/Pattern;)V` | `kafka-clients` | 3.6.2 | declared |
| 39 | `kafka-consumer` | `org.apache.kafka.clients.consumer.KafkaConsumer` | `subscribe` | 2 | `(Ljava/util/Collection;Lorg/apache/kafka/clients/consumer/ConsumerRebalanceListener;)V` | `kafka-clients` | 3.6.2 | declared |
| 40 | `kafka-consumer` | `org.apache.kafka.clients.consumer.Consumer` | `subscribe` | 2 | `(Ljava/util/Collection;Lorg/apache/kafka/clients/consumer/ConsumerRebalanceListener;)V` | `kafka-clients` | 3.6.2 | declared |
| 41 | `kafka-consumer` | `org.apache.kafka.clients.consumer.KafkaConsumer` | `subscribe` | 2 | `(Ljava/util/regex/Pattern;Lorg/apache/kafka/clients/consumer/ConsumerRebalanceListener;)V` | `kafka-clients` | 3.6.2 | declared |
| 42 | `kafka-consumer` | `org.apache.kafka.clients.consumer.Consumer` | `subscribe` | 2 | `(Ljava/util/regex/Pattern;Lorg/apache/kafka/clients/consumer/ConsumerRebalanceListener;)V` | `kafka-clients` | 3.6.2 | declared |
| 43 | `spring-jms-template` | `org.springframework.jms.core.JmsTemplate` | `convertAndSend` | 3 | `(Ljava/lang/String;Ljava/lang/Object;Lorg/springframework/jms/core/MessagePostProcessor;)V` | `spring-jms` | 6.1.6 | declared |
| 44 | `spring-jms-template` | `org.springframework.jms.core.JmsOperations` | `convertAndSend` | 3 | `(Ljava/lang/String;Ljava/lang/Object;Lorg/springframework/jms/core/MessagePostProcessor;)V` | `spring-jms` | 6.1.6 | declared |
| 45 | `spring-jms-template` | `org.springframework.jms.core.JmsTemplate` | `convertAndSend` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)V` | `spring-jms` | 6.1.6 | declared |
| 46 | `spring-jms-template` | `org.springframework.jms.core.JmsOperations` | `convertAndSend` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)V` | `spring-jms` | 6.1.6 | declared |
| 47 | `spring-jms-template` | `org.springframework.jms.core.JmsTemplate` | `convertAndSend` | 2 | `(Ljakarta/jms/Destination;Ljava/lang/Object;)V` | `spring-jms` | 6.1.6 | declared |
| 48 | `spring-jms-template` | `org.springframework.jms.core.JmsOperations` | `convertAndSend` | 2 | `(Ljakarta/jms/Destination;Ljava/lang/Object;)V` | `spring-jms` | 6.1.6 | declared |
| 49 | `spring-jms-template` | `org.springframework.jms.core.JmsTemplate` | `convertAndSend` | 1 | `(Ljava/lang/Object;)V` | `spring-jms` | 6.1.6 | declared |
| 50 | `spring-jms-template` | `org.springframework.jms.core.JmsOperations` | `convertAndSend` | 1 | `(Ljava/lang/Object;)V` | `spring-jms` | 6.1.6 | declared |
| 51 | `spring-jms-template` | `org.springframework.jms.core.JmsTemplate` | `receive` | 1 | `(Ljava/lang/String;)Ljakarta/jms/Message;` | `spring-jms` | 6.1.6 | declared |
| 52 | `spring-jms-template` | `org.springframework.jms.core.JmsOperations` | `receive` | 1 | `(Ljava/lang/String;)Ljakarta/jms/Message;` | `spring-jms` | 6.1.6 | declared |
| 53 | `spring-jms-template` | `org.springframework.jms.core.JmsTemplate` | `receiveSelected` | 2 | `(Ljava/lang/String;Ljava/lang/String;)Ljakarta/jms/Message;` | `spring-jms` | 6.1.6 | declared |
| 54 | `spring-jms-template` | `org.springframework.jms.core.JmsOperations` | `receiveSelected` | 2 | `(Ljava/lang/String;Ljava/lang/String;)Ljakarta/jms/Message;` | `spring-jms` | 6.1.6 | declared |
| 55 | `spring-jms-template` | `org.springframework.jms.core.JmsTemplate` | `receiveAndConvert` | 1 | `(Ljava/lang/String;)Ljava/lang/Object;` | `spring-jms` | 6.1.6 | declared |
| 56 | `spring-jms-template` | `org.springframework.jms.core.JmsOperations` | `receiveAndConvert` | 1 | `(Ljava/lang/String;)Ljava/lang/Object;` | `spring-jms` | 6.1.6 | declared |
| 57 | `spring-jms-template` | `org.springframework.jms.core.JmsTemplate` | `receiveSelectedAndConvert` | 2 | `(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/Object;` | `spring-jms` | 6.1.6 | declared |
| 58 | `spring-jms-template` | `org.springframework.jms.core.JmsOperations` | `receiveSelectedAndConvert` | 2 | `(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/Object;` | `spring-jms` | 6.1.6 | declared |
| 59 | `spring-kafka-replying` | `org.springframework.kafka.requestreply.ReplyingKafkaTemplate` | `sendAndReceive` | 1 | `(Lorg/apache/kafka/clients/producer/ProducerRecord;)Lorg/springframework/kafka/requestreply/RequestReplyFuture;` | `spring-kafka` | 3.1.4 | declared |
| 60 | `spring-kafka-replying` | `org.springframework.kafka.requestreply.ReplyingKafkaTemplate` | `sendAndReceive` | 1 | `(Lorg/springframework/messaging/Message;)Lorg/springframework/kafka/requestreply/RequestReplyMessageFuture;` | `spring-kafka` | 3.1.4 | declared |
| 61 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `send` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 62 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaOperations` | `send` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 63 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `send` | 3 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 64 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaOperations` | `send` | 3 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 65 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `send` | 1 | `(Lorg/apache/kafka/clients/producer/ProducerRecord;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 66 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaOperations` | `send` | 1 | `(Lorg/apache/kafka/clients/producer/ProducerRecord;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 67 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `send` | 1 | `(Lorg/springframework/messaging/Message;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 68 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaOperations` | `send` | 1 | `(Lorg/springframework/messaging/Message;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 69 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `send` | 4 | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 70 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaOperations` | `send` | 4 | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 71 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `send` | 5 | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Long;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 72 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaOperations` | `send` | 5 | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Long;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 73 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `sendDefault` | 1 | `(Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 74 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaOperations` | `sendDefault` | 1 | `(Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 75 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `sendDefault` | 2 | `(Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 76 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaOperations` | `sendDefault` | 2 | `(Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 77 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `sendDefault` | 3 | `(Ljava/lang/Integer;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 78 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaOperations` | `sendDefault` | 3 | `(Ljava/lang/Integer;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 79 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `sendDefault` | 4 | `(Ljava/lang/Integer;Ljava/lang/Long;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 80 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaOperations` | `sendDefault` | 4 | `(Ljava/lang/Integer;Ljava/lang/Long;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-kafka` | 3.1.4 | declared |
| 81 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaTemplate` | `receive` | 4 | `(Ljava/lang/String;IJLjava/time/Duration;)Lorg/apache/kafka/clients/consumer/ConsumerRecord;` | `spring-kafka` | 3.1.4 | declared |
| 82 | `spring-kafka-template` | `org.springframework.kafka.core.KafkaOperations` | `receive` | 4 | `(Ljava/lang/String;IJLjava/time/Duration;)Lorg/apache/kafka/clients/consumer/ConsumerRecord;` | `spring-kafka` | 3.1.4 | declared |
| 83 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `publish` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 84 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `publish` | 2 | `(Ljava/lang/String;Lcom/google/pubsub/v1/PubsubMessage;)Ljava/util/concurrent/CompletableFuture;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 85 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `subscribeAndConvert` | 3 | `(Ljava/lang/String;Ljava/util/function/Consumer;Ljava/lang/Class;)Lcom/google/cloud/pubsub/v1/Subscriber;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 86 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `subscribe` | 2 | `(Ljava/lang/String;Ljava/util/function/Consumer;)Lcom/google/cloud/pubsub/v1/Subscriber;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 87 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `pull` | 3 | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Boolean;)Ljava/util/List;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 88 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `pullAsync` | 3 | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Boolean;)Ljava/util/concurrent/CompletableFuture;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 89 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `pullAndConvert` | 4 | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Boolean;Ljava/lang/Class;)Ljava/util/List;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 90 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `pullAndConvertAsync` | 4 | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Boolean;Ljava/lang/Class;)Ljava/util/concurrent/CompletableFuture;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 91 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `pullAndAck` | 3 | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Boolean;)Ljava/util/List;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 92 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `pullAndAckAsync` | 3 | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Boolean;)Ljava/util/concurrent/CompletableFuture;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 93 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `pullNext` | 1 | `(Ljava/lang/String;)Lcom/google/pubsub/v1/PubsubMessage;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 94 | `spring-pubsub` | `com.google.cloud.spring.pubsub.core.PubSubTemplate` | `pullNextAsync` | 1 | `(Ljava/lang/String;)Ljava/util/concurrent/CompletableFuture;` | `spring-cloud-gcp-pubsub` | 5.1.2 | declared |
| 95 | `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `convertAndSend` | 3 | `(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;)V` | `spring-rabbit` | 3.1.4 | declared |
| 96 | `spring-rabbit-template` | `org.springframework.amqp.core.AmqpTemplate` | `convertAndSend` | 3 | `(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;)V` | `spring-amqp` | 3.1.4 | declared |
| 97 | `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `convertAndSend` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)V` | `spring-rabbit` | 3.1.4 | declared |
| 98 | `spring-rabbit-template` | `org.springframework.amqp.core.AmqpTemplate` | `convertAndSend` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)V` | `spring-amqp` | 3.1.4 | declared |
| 99 | `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `convertAndSend` | 1 | `(Ljava/lang/Object;)V` | `spring-rabbit` | 3.1.4 | declared |
| 100 | `spring-rabbit-template` | `org.springframework.amqp.core.AmqpTemplate` | `convertAndSend` | 1 | `(Ljava/lang/Object;)V` | `spring-amqp` | 3.1.4 | declared |
| 101 | `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `receive` | 1 | `(Ljava/lang/String;)Lorg/springframework/amqp/core/Message;` | `spring-rabbit` | 3.1.4 | declared |
| 102 | `spring-rabbit-template` | `org.springframework.amqp.core.AmqpTemplate` | `receive` | 1 | `(Ljava/lang/String;)Lorg/springframework/amqp/core/Message;` | `spring-amqp` | 3.1.4 | declared |
| 103 | `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `receive` | 2 | `(Ljava/lang/String;J)Lorg/springframework/amqp/core/Message;` | `spring-rabbit` | 3.1.4 | declared |
| 104 | `spring-rabbit-template` | `org.springframework.amqp.core.AmqpTemplate` | `receive` | 2 | `(Ljava/lang/String;J)Lorg/springframework/amqp/core/Message;` | `spring-amqp` | 3.1.4 | declared |
| 105 | `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `receiveAndConvert` | 1 | `(Ljava/lang/String;)Ljava/lang/Object;` | `spring-rabbit` | 3.1.4 | declared |
| 106 | `spring-rabbit-template` | `org.springframework.amqp.core.AmqpTemplate` | `receiveAndConvert` | 1 | `(Ljava/lang/String;)Ljava/lang/Object;` | `spring-amqp` | 3.1.4 | declared |
| 107 | `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `receiveAndConvert` | 2 | `(Ljava/lang/String;J)Ljava/lang/Object;` | `spring-rabbit` | 3.1.4 | declared |
| 108 | `spring-rabbit-template` | `org.springframework.amqp.core.AmqpTemplate` | `receiveAndConvert` | 2 | `(Ljava/lang/String;J)Ljava/lang/Object;` | `spring-amqp` | 3.1.4 | declared |
| 109 | `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `receiveAndConvert` | 2 | `(Ljava/lang/String;Lorg/springframework/core/ParameterizedTypeReference;)Ljava/lang/Object;` | `spring-rabbit` | 3.1.4 | declared |
| 110 | `spring-rabbit-template` | `org.springframework.amqp.core.AmqpTemplate` | `receiveAndConvert` | 2 | `(Ljava/lang/String;Lorg/springframework/core/ParameterizedTypeReference;)Ljava/lang/Object;` | `spring-amqp` | 3.1.4 | declared |
| 111 | `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `receiveAndConvert` | 3 | `(Ljava/lang/String;JLorg/springframework/core/ParameterizedTypeReference;)Ljava/lang/Object;` | `spring-rabbit` | 3.1.4 | declared |
| 112 | `spring-rabbit-template` | `org.springframework.amqp.core.AmqpTemplate` | `receiveAndConvert` | 3 | `(Ljava/lang/String;JLorg/springframework/core/ParameterizedTypeReference;)Ljava/lang/Object;` | `spring-amqp` | 3.1.4 | declared |
| 113 | `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `receiveAndReply` | 2 | `(Ljava/lang/String;Lorg/springframework/amqp/core/ReceiveAndReplyCallback;)Z` | `spring-rabbit` | 3.1.4 | declared |
| 114 | `spring-rabbit-template` | `org.springframework.amqp.core.AmqpTemplate` | `receiveAndReply` | 2 | `(Ljava/lang/String;Lorg/springframework/amqp/core/ReceiveAndReplyCallback;)Z` | `spring-amqp` | 3.1.4 | declared |
| 115 | `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `receiveAndReply` | 4 | `(Ljava/lang/String;Lorg/springframework/amqp/core/ReceiveAndReplyCallback;Ljava/lang/String;Ljava/lang/String;)Z` | `spring-rabbit` | 3.1.4 | declared |
| 116 | `spring-rabbit-template` | `org.springframework.amqp.core.AmqpTemplate` | `receiveAndReply` | 4 | `(Ljava/lang/String;Lorg/springframework/amqp/core/ReceiveAndReplyCallback;Ljava/lang/String;Ljava/lang/String;)Z` | `spring-amqp` | 3.1.4 | declared |
| 117 | `spring-rabbit-template` | `org.springframework.amqp.rabbit.core.RabbitTemplate` | `receiveAndReply` | 3 | `(Ljava/lang/String;Lorg/springframework/amqp/core/ReceiveAndReplyCallback;Lorg/springframework/amqp/core/ReplyToAddressCallback;)Z` | `spring-rabbit` | 3.1.4 | declared |
| 118 | `spring-rabbit-template` | `org.springframework.amqp.core.AmqpTemplate` | `receiveAndReply` | 3 | `(Ljava/lang/String;Lorg/springframework/amqp/core/ReceiveAndReplyCallback;Lorg/springframework/amqp/core/ReplyToAddressCallback;)Z` | `spring-amqp` | 3.1.4 | declared |
| 119 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `getForObject` | 3 | `(Ljava/lang/String;Ljava/lang/Class;[Ljava/lang/Object;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 120 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `getForObject` | 3 | `(Ljava/lang/String;Ljava/lang/Class;[Ljava/lang/Object;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 121 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `getForObject` | 3 | `(Ljava/lang/String;Ljava/lang/Class;Ljava/util/Map;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 122 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `getForObject` | 3 | `(Ljava/lang/String;Ljava/lang/Class;Ljava/util/Map;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 123 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `getForObject` | 2 | `(Ljava/net/URI;Ljava/lang/Class;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 124 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `getForObject` | 2 | `(Ljava/net/URI;Ljava/lang/Class;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 125 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `getForEntity` | 3 | `(Ljava/lang/String;Ljava/lang/Class;[Ljava/lang/Object;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 126 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `getForEntity` | 3 | `(Ljava/lang/String;Ljava/lang/Class;[Ljava/lang/Object;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 127 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `getForEntity` | 3 | `(Ljava/lang/String;Ljava/lang/Class;Ljava/util/Map;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 128 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `getForEntity` | 3 | `(Ljava/lang/String;Ljava/lang/Class;Ljava/util/Map;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 129 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `getForEntity` | 2 | `(Ljava/net/URI;Ljava/lang/Class;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 130 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `getForEntity` | 2 | `(Ljava/net/URI;Ljava/lang/Class;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 131 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `postForObject` | 4 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Class;[Ljava/lang/Object;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 132 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `postForObject` | 4 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Class;[Ljava/lang/Object;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 133 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `postForObject` | 4 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Class;Ljava/util/Map;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 134 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `postForObject` | 4 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Class;Ljava/util/Map;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 135 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `postForObject` | 3 | `(Ljava/net/URI;Ljava/lang/Object;Ljava/lang/Class;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 136 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `postForObject` | 3 | `(Ljava/net/URI;Ljava/lang/Object;Ljava/lang/Class;)Ljava/lang/Object;` | `spring-web` | 6.1.6 | declared |
| 137 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `postForEntity` | 4 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Class;[Ljava/lang/Object;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 138 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `postForEntity` | 4 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Class;[Ljava/lang/Object;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 139 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `postForEntity` | 4 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Class;Ljava/util/Map;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 140 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `postForEntity` | 4 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Class;Ljava/util/Map;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 141 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `postForEntity` | 3 | `(Ljava/net/URI;Ljava/lang/Object;Ljava/lang/Class;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 142 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `postForEntity` | 3 | `(Ljava/net/URI;Ljava/lang/Object;Ljava/lang/Class;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 143 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `put` | 3 | `(Ljava/lang/String;Ljava/lang/Object;[Ljava/lang/Object;)V` | `spring-web` | 6.1.6 | declared |
| 144 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `put` | 3 | `(Ljava/lang/String;Ljava/lang/Object;[Ljava/lang/Object;)V` | `spring-web` | 6.1.6 | declared |
| 145 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `put` | 3 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/util/Map;)V` | `spring-web` | 6.1.6 | declared |
| 146 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `put` | 3 | `(Ljava/lang/String;Ljava/lang/Object;Ljava/util/Map;)V` | `spring-web` | 6.1.6 | declared |
| 147 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `put` | 2 | `(Ljava/net/URI;Ljava/lang/Object;)V` | `spring-web` | 6.1.6 | declared |
| 148 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `put` | 2 | `(Ljava/net/URI;Ljava/lang/Object;)V` | `spring-web` | 6.1.6 | declared |
| 149 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `delete` | 2 | `(Ljava/lang/String;[Ljava/lang/Object;)V` | `spring-web` | 6.1.6 | declared |
| 150 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `delete` | 2 | `(Ljava/lang/String;[Ljava/lang/Object;)V` | `spring-web` | 6.1.6 | declared |
| 151 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `delete` | 2 | `(Ljava/lang/String;Ljava/util/Map;)V` | `spring-web` | 6.1.6 | declared |
| 152 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `delete` | 2 | `(Ljava/lang/String;Ljava/util/Map;)V` | `spring-web` | 6.1.6 | declared |
| 153 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `delete` | 1 | `(Ljava/net/URI;)V` | `spring-web` | 6.1.6 | declared |
| 154 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `delete` | 1 | `(Ljava/net/URI;)V` | `spring-web` | 6.1.6 | declared |
| 155 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `exchange` | 5 | `(Ljava/lang/String;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Ljava/lang/Class;[Ljava/lang/Object;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 156 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `exchange` | 5 | `(Ljava/lang/String;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Ljava/lang/Class;[Ljava/lang/Object;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 157 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `exchange` | 5 | `(Ljava/lang/String;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Ljava/lang/Class;Ljava/util/Map;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 158 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `exchange` | 5 | `(Ljava/lang/String;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Ljava/lang/Class;Ljava/util/Map;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 159 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `exchange` | 4 | `(Ljava/net/URI;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Ljava/lang/Class;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 160 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `exchange` | 4 | `(Ljava/net/URI;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Ljava/lang/Class;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 161 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `exchange` | 5 | `(Ljava/lang/String;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Lorg/springframework/core/ParameterizedTypeReference;[Ljava/lang/Object;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 162 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `exchange` | 5 | `(Ljava/lang/String;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Lorg/springframework/core/ParameterizedTypeReference;[Ljava/lang/Object;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 163 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `exchange` | 5 | `(Ljava/lang/String;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Lorg/springframework/core/ParameterizedTypeReference;Ljava/util/Map;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 164 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `exchange` | 5 | `(Ljava/lang/String;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Lorg/springframework/core/ParameterizedTypeReference;Ljava/util/Map;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 165 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `exchange` | 4 | `(Ljava/net/URI;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Lorg/springframework/core/ParameterizedTypeReference;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 166 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `exchange` | 4 | `(Ljava/net/URI;Lorg/springframework/http/HttpMethod;Lorg/springframework/http/HttpEntity;Lorg/springframework/core/ParameterizedTypeReference;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 167 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `exchange` | 2 | `(Lorg/springframework/http/RequestEntity;Ljava/lang/Class;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 168 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `exchange` | 2 | `(Lorg/springframework/http/RequestEntity;Ljava/lang/Class;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 169 | `spring-resttemplate` | `org.springframework.web.client.RestTemplate` | `exchange` | 2 | `(Lorg/springframework/http/RequestEntity;Lorg/springframework/core/ParameterizedTypeReference;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 170 | `spring-resttemplate` | `org.springframework.web.client.RestOperations` | `exchange` | 2 | `(Lorg/springframework/http/RequestEntity;Lorg/springframework/core/ParameterizedTypeReference;)Lorg/springframework/http/ResponseEntity;` | `spring-web` | 6.1.6 | declared |
| 171 | `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsTemplate` | `send` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)Lio/awspring/cloud/sqs/operations/SendResult;` | `spring-cloud-aws-sqs` | 3.1.1 | declared |
| 172 | `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsOperations` | `send` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)Lio/awspring/cloud/sqs/operations/SendResult;` | `spring-cloud-aws-sqs` | 3.1.1 | declared |
| 173 | `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsTemplate` | `send` | 2 | `(Ljava/lang/String;Lorg/springframework/messaging/Message;)Lio/awspring/cloud/sqs/operations/SendResult;` | `spring-cloud-aws-sqs` | 3.1.1 | declared |
| 174 | `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsOperations` | `send` | 2 | `(Ljava/lang/String;Lorg/springframework/messaging/Message;)Lio/awspring/cloud/sqs/operations/SendResult;` | `spring-cloud-aws-sqs` | 3.1.1 | declared |
| 175 | `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsTemplate` | `send` | 1 | `(Ljava/lang/Object;)Lio/awspring/cloud/sqs/operations/SendResult;` | `spring-cloud-aws-sqs` | 3.1.1 | declared |
| 176 | `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsOperations` | `send` | 1 | `(Ljava/lang/Object;)Lio/awspring/cloud/sqs/operations/SendResult;` | `spring-cloud-aws-sqs` | 3.1.1 | declared |
| 177 | `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsTemplate` | `send` | 1 | `(Ljava/util/function/Consumer;)Lio/awspring/cloud/sqs/operations/SendResult;` | `spring-cloud-aws-sqs` | 3.1.1 | declared |
| 178 | `spring-sqs-template` | `io.awspring.cloud.sqs.operations.SqsOperations` | `send` | 1 | `(Ljava/util/function/Consumer;)Lio/awspring/cloud/sqs/operations/SendResult;` | `spring-cloud-aws-sqs` | 3.1.1 | declared |
| 179 | `spring-stomp-client` | `org.springframework.web.socket.messaging.WebSocketStompClient` | `connectAsync` | 3 | `(Ljava/lang/String;Lorg/springframework/messaging/simp/stomp/StompSessionHandler;[Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-websocket` | 6.1.6 | declared |
| 180 | `spring-stomp-client` | `org.springframework.web.socket.messaging.WebSocketStompClient` | `connectAsync` | 4 | `(Ljava/lang/String;Lorg/springframework/web/socket/WebSocketHttpHeaders;Lorg/springframework/messaging/simp/stomp/StompSessionHandler;[Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-websocket` | 6.1.6 | declared |
| 181 | `spring-stomp-client` | `org.springframework.web.socket.messaging.WebSocketStompClient` | `connect` | 3 | `(Ljava/lang/String;Lorg/springframework/messaging/simp/stomp/StompSessionHandler;[Ljava/lang/Object;)Lorg/springframework/util/concurrent/ListenableFuture;` | `spring-websocket` | 6.1.6 | declared |
| 182 | `spring-stomp-client` | `org.springframework.web.socket.messaging.WebSocketStompClient` | `connect` | 4 | `(Ljava/lang/String;Lorg/springframework/web/socket/WebSocketHttpHeaders;Lorg/springframework/messaging/simp/stomp/StompSessionHandler;[Ljava/lang/Object;)Lorg/springframework/util/concurrent/ListenableFuture;` | `spring-websocket` | 6.1.6 | declared |
| 183 | `spring-stomp-client` | `org.springframework.web.socket.messaging.WebSocketStompClient` | `connectAsync` | 5 | `(Ljava/lang/String;Lorg/springframework/web/socket/WebSocketHttpHeaders;Lorg/springframework/messaging/simp/stomp/StompHeaders;Lorg/springframework/messaging/simp/stomp/StompSessionHandler;[Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-websocket` | 6.1.6 | declared |
| 184 | `spring-stomp-client` | `org.springframework.web.socket.messaging.WebSocketStompClient` | `connect` | 5 | `(Ljava/lang/String;Lorg/springframework/web/socket/WebSocketHttpHeaders;Lorg/springframework/messaging/simp/stomp/StompHeaders;Lorg/springframework/messaging/simp/stomp/StompSessionHandler;[Ljava/lang/Object;)Lorg/springframework/util/concurrent/ListenableFuture;` | `spring-websocket` | 6.1.6 | declared |
| 185 | `spring-stomp-client` | `org.springframework.web.socket.messaging.WebSocketStompClient` | `connectAsync` | 4 | `(Ljava/net/URI;Lorg/springframework/web/socket/WebSocketHttpHeaders;Lorg/springframework/messaging/simp/stomp/StompHeaders;Lorg/springframework/messaging/simp/stomp/StompSessionHandler;)Ljava/util/concurrent/CompletableFuture;` | `spring-websocket` | 6.1.6 | declared |
| 186 | `spring-stomp-client` | `org.springframework.web.socket.messaging.WebSocketStompClient` | `connect` | 4 | `(Ljava/net/URI;Lorg/springframework/web/socket/WebSocketHttpHeaders;Lorg/springframework/messaging/simp/stomp/StompHeaders;Lorg/springframework/messaging/simp/stomp/StompSessionHandler;)Lorg/springframework/util/concurrent/ListenableFuture;` | `spring-websocket` | 6.1.6 | declared |
| 187 | `spring-stomp-endpoint` | `org.springframework.web.socket.config.annotation.StompEndpointRegistry` | `addEndpoint` | 1 | `([Ljava/lang/String;)Lorg/springframework/web/socket/config/annotation/StompWebSocketEndpointRegistration;` | `spring-websocket` | 6.1.6 | declared |
| 188 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `convertAndSend` | 2 | `(Ljava/lang/Object;Ljava/lang/Object;)V` | `spring-messaging` | 6.1.6 | declared |
| 189 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `convertAndSend` | 2 | `(Ljava/lang/Object;Ljava/lang/Object;)V` | `spring-messaging` | 6.1.6 | declared |
| 190 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `convertAndSend` | 3 | `(Ljava/lang/Object;Ljava/lang/Object;Ljava/util/Map;)V` | `spring-messaging` | 6.1.6 | declared |
| 191 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `convertAndSend` | 3 | `(Ljava/lang/Object;Ljava/lang/Object;Ljava/util/Map;)V` | `spring-messaging` | 6.1.6 | declared |
| 192 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `convertAndSend` | 3 | `(Ljava/lang/Object;Ljava/lang/Object;Lorg/springframework/messaging/core/MessagePostProcessor;)V` | `spring-messaging` | 6.1.6 | declared |
| 193 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `convertAndSend` | 3 | `(Ljava/lang/Object;Ljava/lang/Object;Lorg/springframework/messaging/core/MessagePostProcessor;)V` | `spring-messaging` | 6.1.6 | declared |
| 194 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `convertAndSend` | 4 | `(Ljava/lang/Object;Ljava/lang/Object;Ljava/util/Map;Lorg/springframework/messaging/core/MessagePostProcessor;)V` | `spring-messaging` | 6.1.6 | declared |
| 195 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `convertAndSend` | 4 | `(Ljava/lang/Object;Ljava/lang/Object;Ljava/util/Map;Lorg/springframework/messaging/core/MessagePostProcessor;)V` | `spring-messaging` | 6.1.6 | declared |
| 196 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `convertAndSend` | 1 | `(Ljava/lang/Object;)V` | `spring-messaging` | 6.1.6 | declared |
| 197 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `convertAndSend` | 1 | `(Ljava/lang/Object;)V` | `spring-messaging` | 6.1.6 | declared |
| 198 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `convertAndSend` | 2 | `(Ljava/lang/Object;Lorg/springframework/messaging/core/MessagePostProcessor;)V` | `spring-messaging` | 6.1.6 | declared |
| 199 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `convertAndSend` | 2 | `(Ljava/lang/Object;Lorg/springframework/messaging/core/MessagePostProcessor;)V` | `spring-messaging` | 6.1.6 | declared |
| 200 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `send` | 1 | `(Lorg/springframework/messaging/Message;)V` | `spring-messaging` | 6.1.6 | declared |
| 201 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `send` | 1 | `(Lorg/springframework/messaging/Message;)V` | `spring-messaging` | 6.1.6 | declared |
| 202 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `send` | 2 | `(Ljava/lang/Object;Lorg/springframework/messaging/Message;)V` | `spring-messaging` | 6.1.6 | declared |
| 203 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `send` | 2 | `(Ljava/lang/Object;Lorg/springframework/messaging/Message;)V` | `spring-messaging` | 6.1.6 | declared |
| 204 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `convertAndSendToUser` | 3 | `(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;)V` | `spring-messaging` | 6.1.6 | declared |
| 205 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `convertAndSendToUser` | 3 | `(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;)V` | `spring-messaging` | 6.1.6 | declared |
| 206 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `convertAndSendToUser` | 4 | `(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;Ljava/util/Map;)V` | `spring-messaging` | 6.1.6 | declared |
| 207 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `convertAndSendToUser` | 4 | `(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;Ljava/util/Map;)V` | `spring-messaging` | 6.1.6 | declared |
| 208 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `convertAndSendToUser` | 4 | `(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;Lorg/springframework/messaging/core/MessagePostProcessor;)V` | `spring-messaging` | 6.1.6 | declared |
| 209 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `convertAndSendToUser` | 4 | `(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;Lorg/springframework/messaging/core/MessagePostProcessor;)V` | `spring-messaging` | 6.1.6 | declared |
| 210 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessagingTemplate` | `convertAndSendToUser` | 5 | `(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;Ljava/util/Map;Lorg/springframework/messaging/core/MessagePostProcessor;)V` | `spring-messaging` | 6.1.6 | declared |
| 211 | `spring-stomp-template` | `org.springframework.messaging.simp.SimpMessageSendingOperations` | `convertAndSendToUser` | 5 | `(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Object;Ljava/util/Map;Lorg/springframework/messaging/core/MessagePostProcessor;)V` | `spring-messaging` | 6.1.6 | declared |
| 212 | `spring-websocket-client` | `org.springframework.web.socket.client.WebSocketClient` | `execute` | 3 | `(Lorg/springframework/web/socket/WebSocketHandler;Ljava/lang/String;[Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;` | `spring-websocket` | 6.1.6 | declared |
| 213 | `spring-websocket-client` | `org.springframework.web.socket.client.WebSocketClient` | `execute` | 3 | `(Lorg/springframework/web/socket/WebSocketHandler;Lorg/springframework/web/socket/WebSocketHttpHeaders;Ljava/net/URI;)Ljava/util/concurrent/CompletableFuture;` | `spring-websocket` | 6.1.6 | declared |
| 214 | `spring-websocket` | `org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry` | `addHandler` | 2 | `(Lorg/springframework/web/socket/WebSocketHandler;[Ljava/lang/String;)Lorg/springframework/web/socket/config/annotation/WebSocketHandlerRegistration;` | `spring-websocket` | 6.1.6 | declared |
| 215 | `spring-ws-template` | `org.springframework.ws.client.core.WebServiceTemplate` | `marshalSendAndReceive` | 1 | `(Ljava/lang/Object;)Ljava/lang/Object;` | `spring-ws-core` | 4.1.4 | declared |
| 216 | `spring-ws-template` | `org.springframework.ws.client.core.WebServiceTemplate` | `marshalSendAndReceive` | 2 | `(Ljava/lang/String;Ljava/lang/Object;)Ljava/lang/Object;` | `spring-ws-core` | 4.1.4 | declared |
| 217 | `spring-ws-template` | `org.springframework.ws.client.core.WebServiceTemplate` | `marshalSendAndReceive` | 3 | `(Ljava/lang/String;Ljava/lang/Object;Lorg/springframework/ws/client/core/WebServiceMessageCallback;)Ljava/lang/Object;` | `spring-ws-core` | 4.1.4 | declared |


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
