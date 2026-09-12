# W59 — the RECEIVE-shaped methods on the four messaging templates, and which take a destination at argument 0

**Question.** `spring-rabbit-template.yml`, `spring-jms-template.yml`,
`spring-kafka-template.yml` and `spring-sqs-template.yml` all model their SEND half only
(`G-44`). A `single_call` row can only address a wire off an argument the call site itself
carries, so before writing any receive row the question is mechanical: of every `receive*`
method each template declares, which put the destination — queue, JMS destination, topic,
or the SQS queue — at argument 0 as a plain `String` (addressable, one row per call), and
which read a template-configured default or bury the destination inside a
`Consumer<...Options>` lambda (not addressable by this style at all)?

**Version scope (§5.4).** Read against **spring-rabbit 3.1.4, spring-jms 6.1.6,
spring-kafka 3.1.4 and spring-cloud-aws-sqs 3.1.1** — each the version the jar reports for
itself, checked against the coordinate before any table is printed. `fixtures/orders-receivers/pom.xml`
pins the same four versions.

**How to run.** `bash scripts/probes/w59_template_receive_halves/run.sh`. Resolves each
artifact through Maven (network on the first run only), reads the version the jar states
for itself, and asks `javap -p -s` for every method matching the class's own `receive*`
name pattern. Everything below the rule is that script's own output, pasted verbatim.

## Expectation table

| # | If | then |
|---|---|---|
| 1 | argument 0 is a `String` | addressable — one row per call, the shape `G-44`'s receive rows use |
| 2 | argument 0 is a `Consumer<…Options>` (SQS) | the queue is inside a lambda; not addressable by `single_call` |
| 3 | argument 0 is a `long`/`Duration` (a timeout) or absent | the method reads the template's configured DEFAULT destination; not addressable |
| 4 | argument 0 is a `Destination`/`ReceiveAndReplyCallback` instance | not a string constant a call site can carry; not addressable |

---

## Observations

Verbatim from `scripts/probes/w59_template_receive_halves/run.sh`, which runs
`sweep.py`. **Every version in the headers below is the one the JAR itself
reported** — out of its own `pom.properties` or its manifest's
`Implementation-Version`, and **not the version the coordinate list asked for**;
`checked` compares the two and ABORTS when they disagree.

| what the run read | 3.1.4 | 6.1.6 | 3.1.1 |
|---|---|---|---|
| artifacts reporting this version | spring-rabbit, spring-kafka | spring-jms | spring-cloud-aws-sqs |
| where the jar states it | MANIFEST.MF | MANIFEST.MF | pom.properties |

### Every `receive*` method each template declares, and whether it addresses
### a wire

**`org.springframework.amqp.rabbit.core.RabbitTemplate`** (org.springframework.amqp:spring-rabbit:3.1.4)

| # | method | descriptor | argument 0 type | addressable |
|---|---|---|---|---|
| 1 | `receive` | `()Lorg/springframework/amqp/core/Message;` | `*(none)*` | no |
| 2 | `receive` | `(Ljava/lang/String;)Lorg/springframework/amqp/core/Message;` | `java.lang.String` | **yes** |
| 3 | `receive` | `(J)Lorg/springframework/amqp/core/Message;` | `long` | no |
| 4 | `receive` | `(Ljava/lang/String;J)Lorg/springframework/amqp/core/Message;` | `java.lang.String` | **yes** |
| 5 | `receiveAndConvert` | `()Ljava/lang/Object;` | `*(none)*` | no |
| 6 | `receiveAndConvert` | `(Ljava/lang/String;)Ljava/lang/Object;` | `java.lang.String` | **yes** |
| 7 | `receiveAndConvert` | `(J)Ljava/lang/Object;` | `long` | no |
| 8 | `receiveAndConvert` | `(Ljava/lang/String;J)Ljava/lang/Object;` | `java.lang.String` | **yes** |
| 9 | `receiveAndConvert` | `(Lorg/springframework/core/ParameterizedTypeReference;)Ljava/lang/Object;` | `org.springframework.core.ParameterizedTypeReference` | no |
| 10 | `receiveAndConvert` | `(Ljava/lang/String;Lorg/springframework/core/ParameterizedTypeReference;)Ljava/lang/Object;` | `java.lang.String` | **yes** |
| 11 | `receiveAndConvert` | `(JLorg/springframework/core/ParameterizedTypeReference;)Ljava/lang/Object;` | `long` | no |
| 12 | `receiveAndConvert` | `(Ljava/lang/String;JLorg/springframework/core/ParameterizedTypeReference;)Ljava/lang/Object;` | `java.lang.String` | **yes** |
| 13 | `receiveAndReply` | `(Lorg/springframework/amqp/core/ReceiveAndReplyCallback;)Z` | `org.springframework.amqp.core.ReceiveAndReplyCallback` | no |
| 14 | `receiveAndReply` | `(Ljava/lang/String;Lorg/springframework/amqp/core/ReceiveAndReplyCallback;)Z` | `java.lang.String` | **yes** |
| 15 | `receiveAndReply` | `(Lorg/springframework/amqp/core/ReceiveAndReplyCallback;Ljava/lang/String;Ljava/lang/String;)Z` | `org.springframework.amqp.core.ReceiveAndReplyCallback` | no |
| 16 | `receiveAndReply` | `(Ljava/lang/String;Lorg/springframework/amqp/core/ReceiveAndReplyCallback;Ljava/lang/String;Ljava/lang/String;)Z` | `java.lang.String` | **yes** |
| 17 | `receiveAndReply` | `(Lorg/springframework/amqp/core/ReceiveAndReplyCallback;Lorg/springframework/amqp/core/ReplyToAddressCallback;)Z` | `org.springframework.amqp.core.ReceiveAndReplyCallback` | no |
| 18 | `receiveAndReply` | `(Ljava/lang/String;Lorg/springframework/amqp/core/ReceiveAndReplyCallback;Lorg/springframework/amqp/core/ReplyToAddressCallback;)Z` | `java.lang.String` | **yes** |

**`org.springframework.jms.core.JmsTemplate`** (org.springframework:spring-jms:6.1.6)

| # | method | descriptor | argument 0 type | addressable |
|---|---|---|---|---|
| 1 | `receive` | `()Ljakarta/jms/Message;` | `*(none)*` | no |
| 2 | `receive` | `(Ljakarta/jms/Destination;)Ljakarta/jms/Message;` | `jakarta.jms.Destination` | no |
| 3 | `receive` | `(Ljava/lang/String;)Ljakarta/jms/Message;` | `java.lang.String` | **yes** |
| 4 | `receiveSelected` | `(Ljava/lang/String;)Ljakarta/jms/Message;` | `java.lang.String` | **yes** |
| 5 | `receiveSelected` | `(Ljakarta/jms/Destination;Ljava/lang/String;)Ljakarta/jms/Message;` | `jakarta.jms.Destination` | no |
| 6 | `receiveSelected` | `(Ljava/lang/String;Ljava/lang/String;)Ljakarta/jms/Message;` | `java.lang.String` | **yes** |
| 7 | `receiveAndConvert` | `()Ljava/lang/Object;` | `*(none)*` | no |
| 8 | `receiveAndConvert` | `(Ljakarta/jms/Destination;)Ljava/lang/Object;` | `jakarta.jms.Destination` | no |
| 9 | `receiveAndConvert` | `(Ljava/lang/String;)Ljava/lang/Object;` | `java.lang.String` | **yes** |
| 10 | `receiveSelectedAndConvert` | `(Ljava/lang/String;)Ljava/lang/Object;` | `java.lang.String` | **yes** |
| 11 | `receiveSelectedAndConvert` | `(Ljakarta/jms/Destination;Ljava/lang/String;)Ljava/lang/Object;` | `jakarta.jms.Destination` | no |
| 12 | `receiveSelectedAndConvert` | `(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/Object;` | `java.lang.String` | **yes** |

**`org.springframework.kafka.core.KafkaTemplate`** (org.springframework.kafka:spring-kafka:3.1.4)

| # | method | descriptor | argument 0 type | addressable |
|---|---|---|---|---|
| 1 | `receive` | `(Ljava/lang/String;IJLjava/time/Duration;)Lorg/apache/kafka/clients/consumer/ConsumerRecord;` | `java.lang.String` | **yes** |
| 2 | `receive` | `(Ljava/util/Collection;Ljava/time/Duration;)Lorg/apache/kafka/clients/consumer/ConsumerRecords;` | `java.util.Collection` | no |

**`io.awspring.cloud.sqs.operations.SqsTemplate`** (io.awspring.cloud:spring-cloud-aws-sqs:3.1.1)

| # | method | descriptor | argument 0 type | addressable |
|---|---|---|---|---|
| 1 | `receive` | `(Ljava/util/function/Consumer;)Ljava/util/Optional;` | `java.util.function.Consumer` | no |
| 2 | `receive` | `(Ljava/util/function/Consumer;Ljava/lang/Class;)Ljava/util/Optional;` | `java.util.function.Consumer` | no |
| 3 | `receiveMany` | `(Ljava/util/function/Consumer;)Ljava/util/Collection;` | `java.util.function.Consumer` | no |
| 4 | `receiveMany` | `(Ljava/util/function/Consumer;Ljava/lang/Class;)Ljava/util/Collection;` | `java.util.function.Consumer` | no |
| 5 | `receiveAsync` | `(Ljava/util/function/Consumer;)Ljava/util/concurrent/CompletableFuture;` | `java.util.function.Consumer` | no |
| 6 | `receiveAsync` | `(Ljava/util/function/Consumer;Ljava/lang/Class;)Ljava/util/concurrent/CompletableFuture;` | `java.util.function.Consumer` | no |
| 7 | `receiveManyAsync` | `(Ljava/util/function/Consumer;)Ljava/util/concurrent/CompletableFuture;` | `java.util.function.Consumer` | no |
| 8 | `receiveManyAsync` | `(Ljava/util/function/Consumer;Ljava/lang/Class;)Ljava/util/concurrent/CompletableFuture;` | `java.util.function.Consumer` | no |

