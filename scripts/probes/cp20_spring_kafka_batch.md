# CP-20 — Spring Kafka's `batch` attribute: a `String`, parsed as `Boolean.parseBoolean` with no resolution, and where the boundary against factory config sits

**Question.** Group B/C's attribute-conditional rules need to know exactly what
`@KafkaListener.batch()` is (type, default), exactly how the post-processor
turns it into the boolean `setBatchListener` call (so a catalog's condition
predicate matches the framework's own parse, not an invented one — DR-6,
`framework-behavior-mirroring.md`), what shapes the batch listener method
itself is allowed to take, and where the FACTORY's own `setBatchListener`
config-driven path sits relative to the annotation attribute, so the catalog
does not conflate "annotation says batch=true" with "container factory is
configured for batch" — two different, independently-sufficient triggers for
the same runtime behaviour.

**What this probe does not settle.** Nothing was deployed; no `@KafkaListener`
method was invoked against a running broker. This reads the post-processor's
own bytecode for how it turns the annotation's `String` into a `boolean`, and
the listener-adapter class's own method signatures for what shapes a batch
handler may take — not what actually arrives on the wire.

**Version scope (§5.4).** `org.springframework.kafka:spring-kafka` **3.1.4 and
4.1.1** (both already resolved in `~/.m2`), CP-16's own two-minor pair for the
same framework, spanning the 3.x→4.x major. Every verdict below is bounded by
those two.

## Environment

`K=~/.m2/repository/org/springframework/kafka/spring-kafka/$v/spring-kafka-$v.jar`
for `$v` in `3.1.4`, `4.1.1`.

**How to run.** `bash scripts/probes/cp20_spring_kafka_batch/run.sh`. It
resolves both jars through Maven (network on the first run only, cached in
`~/.m2` afterwards), asks `javap` this probe's questions, and greps this
repository's own catalog files for row 5. Needs a JDK, Maven and `git`. Not a
test: nothing in the suite runs it, and NFR-1's no-network rule governs the
suite rather than evidence gathering.

## Observations

Verbatim from `run.sh`'s generated table (`probe.py` prints it; nothing here
is typed by hand). **Every column header of the first table is a version the
JAR itself REPORTED, and not the version the coordinate list asked for** — out
of each manifest's `Implementation-Version`. `probe.py` reads the value out of
the archive it opened and ABORTS the whole run when it disagrees with the
coordinate that resolved the jar, rather than filling a mislabelled column;
that is CP-5's failure, which printed a version it believed beside output from
a version it had not run. Row 5 is not a jar read at all — its identity is the
git commit `run.sh` resolves HEAD to, printed by the harness itself rather
than assumed.

```
| what the run read | 3.1.4 | 4.1.1 |
|---|---|---|
| artifacts reporting this version | org.springframework.kafka:spring-kafka | org.springframework.kafka:spring-kafka |
| identity read from the archive itself | yes | yes |

| # | question | artifact | version | observed |
|---|---|---|---|---|
| 1 | batch()'s declared type and default | `org.springframework.kafka:spring-kafka` | 3.1.4 | `batch(): java.lang.String ; AnnotationDefault: ""` |
| 2 | the post-processor's batch()->hasText->parseBoolean->setBatchListener parse | `org.springframework.kafka:spring-kafka` | 3.1.4 | `invokeinterface InterfaceMethod org/springframework/kafka/annotation/KafkaListener.batch:()Ljava/lang/String; ; invokestatic Method org/springframework/util/StringUtils.hasText:(Ljava/lang/String;)Z ; ifeq ; aload_1 ; aload_2 ; invokeinterface InterfaceMethod org/springframework/kafka/annotation/KafkaListener.batch:()Ljava/lang/String; ; invokestatic Method java/lang/Boolean.parseBoolean:(Ljava/lang/String;)Z ; invokevirtual Method org/springframework/kafka/config/MethodKafkaListenerEndpoint.setBatchListener:(Z)V` |
| 3 | BatchMessagingMessageListenerAdapter.onMessage's accepted shapes | `org.springframework.kafka:spring-kafka` | 3.1.4 | `public void onMessage(org.apache.kafka.clients.consumer.ConsumerRecords<K, V>, org.springframework.kafka.support.Acknowledgment, org.apache.kafka.clients.consumer.Consumer<K, V>) ; public void onMessage(java.util.List<org.apache.kafka.clients.consumer.ConsumerRecord<K, V>>, org.springframework.kafka.support.Acknowledgment, org.apache.kafka.clients.consumer.Consumer<?, ?>) ; public void onMessage(java.lang.Object, org.springframework.kafka.support.Acknowledgment, org.apache.kafka.clients.consumer.Consumer)` |
| 4 | the factory's own, config-driven setBatchListener | `org.springframework.kafka:spring-kafka` | 3.1.4 | `ConcurrentKafkaListenerContainerFactory declares batch member: False ; AbstractKafkaListenerContainerFactory: private org.springframework.kafka.support.converter.BatchMessageConverter batchMessageConverter ; private java.lang.Boolean batchListener ; private org.springframework.kafka.listener.adapter.BatchToRecordAdapter<K, V> batchToRecordAdapter ; public void setBatchMessageConverter(org.springframework.kafka.support.converter.BatchMessageConverter) ; public java.lang.Boolean isBatchListener() ; public void setBatchListener(java.lang.Boolean) ; public void setBatchToRecordAdapter(org.springframework.kafka.listener.adapter.BatchToRecordAdapter<K, V>)` |
| 1 | batch()'s declared type and default | `org.springframework.kafka:spring-kafka` | 4.1.1 | `batch(): java.lang.String ; AnnotationDefault: ""` |
| 2 | the post-processor's batch()->hasText->parseBoolean->setBatchListener parse | `org.springframework.kafka:spring-kafka` | 4.1.1 | `invokeinterface InterfaceMethod org/springframework/kafka/annotation/KafkaListener.batch:()Ljava/lang/String; ; invokestatic Method org/springframework/util/StringUtils.hasText:(Ljava/lang/String;)Z ; ifeq ; aload_1 ; aload_2 ; invokeinterface InterfaceMethod org/springframework/kafka/annotation/KafkaListener.batch:()Ljava/lang/String; ; invokestatic Method java/lang/Boolean.parseBoolean:(Ljava/lang/String;)Z ; invokevirtual Method org/springframework/kafka/config/MethodKafkaListenerEndpoint.setBatchListener:(Z)V` |
| 3 | BatchMessagingMessageListenerAdapter.onMessage's accepted shapes | `org.springframework.kafka:spring-kafka` | 4.1.1 | `public void onMessage(org.apache.kafka.clients.consumer.ConsumerRecords<K, V>, org.springframework.kafka.support.Acknowledgment, org.apache.kafka.clients.consumer.Consumer<K, V>) ; public void onMessage(java.util.List<org.apache.kafka.clients.consumer.ConsumerRecord<K, V>>, org.springframework.kafka.support.Acknowledgment, org.apache.kafka.clients.consumer.Consumer<?, ?>) ; public void onMessage(java.lang.Object, org.springframework.kafka.support.Acknowledgment, org.apache.kafka.clients.consumer.Consumer)` |
| 4 | the factory's own, config-driven setBatchListener | `org.springframework.kafka:spring-kafka` | 4.1.1 | `ConcurrentKafkaListenerContainerFactory declares batch member: False ; AbstractKafkaListenerContainerFactory: private org.springframework.kafka.support.converter.BatchMessageConverter batchMessageConverter ; private java.lang.Boolean batchListener ; private org.springframework.kafka.listener.adapter.BatchToRecordAdapter<K, V> batchToRecordAdapter ; public void setBatchMessageConverter(org.springframework.kafka.support.converter.BatchMessageConverter) ; public java.lang.Boolean isBatchListener() ; public void setBatchListener(java.lang.Boolean) ; public void setBatchToRecordAdapter(org.springframework.kafka.listener.adapter.BatchToRecordAdapter<K, V>)` |
| 5 | List<Message<T>> as a wrapper type in the shipped catalogs | `spring-kafka.yml, spring-kafka-message.yml` | repo@7fc977b | `spring-kafka.yml: no match ; spring-kafka-message.yml: no match` |
```

## Rows

### 1 — `batch()`: type and default, both versions

**Command.**
```
javap -v -cp $K org.springframework.kafka.annotation.KafkaListener | grep -A4 'String batch()'
```

**Output (3.1.4; 4.1.1 is byte-identical for this member).**
```
public abstract java.lang.String batch();
    descriptor: ()Ljava/lang/String;
    flags: (0x0401) ACC_PUBLIC, ACC_ABSTRACT
    AnnotationDefault:
      default_value: s#10
```
Constant-pool entry `#10` is `Utf8` with zero characters — confirmed by
`javap -v` printing `#10 = Utf8` with no trailing text, and by the
`AnnotationDefault` attribute's byte length (a length-prefixed UTF-8 with
length 0).

**Claim.** `batch(): String`, default value the empty string, at 3.1.4 and
4.1.1 alike.

### 2 — the bean-post-processor's parse: `StringUtils.hasText` → `Boolean.parseBoolean` → `setBatchListener`

**Command.**
```
javap -c -p -cp $K org.springframework.kafka.annotation.KafkaListenerAnnotationBeanPostProcessor | grep -B6 -A3 'KafkaListener.batch:()'
```

**Output (3.1.4; 4.1.1 differs only in constant-pool indices, same op sequence).**
```
       205: aload_2
       206: invokeinterface  InterfaceMethod KafkaListener.batch:()Ljava/lang/String;
       211: invokestatic     Method org/springframework/util/StringUtils.hasText:(Ljava/lang/String;)Z
       214: ifeq          230
       217: aload_1
       218: aload_2
       219: invokeinterface  InterfaceMethod KafkaListener.batch:()Ljava/lang/String;
       224: invokestatic     Method java/lang/Boolean.parseBoolean:(Ljava/lang/String;)Z
       227: invokevirtual    Method MethodKafkaListenerEndpoint.setBatchListener:(Z)V
       230: aload_1
```

**Claim.** The post-processor reads `batch()` twice: once through
`StringUtils.hasText` as a GATE (empty/blank string → skip the `if` block
entirely, offset 214), and — only when non-blank — again through
`Boolean.parseBoolean` to produce the `boolean` passed to
`setBatchListener(Z)`. `Boolean.parseBoolean` is Java's own case-insensitive,
no-throw parse: any string not case-insensitively equal to `"true"` parses to
`false`, including typos — there is no validation and no exception path. So:
**`parses_true`** is exactly `Boolean.parseBoolean(batch())`, case-insensitive,
no resolution against a bean or property; **an empty `batch` attribute is not
"false"** — `StringUtils.hasText` gates the whole `setBatchListener` call away
entirely when `batch` is blank, leaving whatever the CONTAINER FACTORY already
has configured untouched ("factory decides", confirming spec §2/§5a). This is
identical at 3.1.4 and 4.1.1.

### 3 — `BatchMessagingMessageListenerAdapter.onMessage`: the accepted shapes

**Command.**
```
javap -p -cp $K org.springframework.kafka.listener.adapter.BatchMessagingMessageListenerAdapter | grep onMessage
```

**Output (4.1.1; 3.1.4 carries the same three `onMessage` overloads).**
```
public void onMessage(org.apache.kafka.clients.consumer.ConsumerRecords<K, V>, org.springframework.kafka.support.Acknowledgment, org.apache.kafka.clients.consumer.Consumer<K, V>);
public void onMessage(java.util.List<org.apache.kafka.clients.consumer.ConsumerRecord<K, V>>, org.springframework.kafka.support.Acknowledgment, org.apache.kafka.clients.consumer.Consumer<?, ?>);
public void onMessage(java.lang.Object, org.springframework.kafka.support.Acknowledgment, org.apache.kafka.clients.consumer.Consumer);
```

**Claim.** The batch adapter accepts exactly three shapes at the framework
boundary: `ConsumerRecords<K,V>`, `List<ConsumerRecord<K,V>>`, or a raw
`Object` (the fallback the framework's own message-converter machinery
resolves at runtime — not a fourth distinct binding). No fourth overload
exists at either version read.

### 4 — the factory's independent, config-driven `setBatchListener`

**Command.**
```
javap -p -cp $K org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory
javap -p -cp $K org.springframework.kafka.config.AbstractKafkaListenerContainerFactory | grep -i batch
```

**Output.**
`ConcurrentKafkaListenerContainerFactory` itself declares no batch-related
member at all — only `concurrency` and the container-instance factory
methods. Its superclass,
`org.springframework.kafka.config.AbstractKafkaListenerContainerFactory`,
carries:
```
private java.lang.Boolean batchListener;
public java.lang.Boolean isBatchListener();
public void setBatchListener(java.lang.Boolean);
```

**Claim.** `setBatchListener(Boolean)` lives on the FACTORY
(`AbstractKafkaListenerContainerFactory`), configured by the application
(a bean property / `spring.kafka.listener.type=batch`, outside annotation
scope), with no annotation read anywhere in either class. This confirms the
boundary: when `@KafkaListener.batch()` is blank (row 2's gate), the endpoint
inherits whatever the factory's own `batchListener` property already says —
config-driven batching leaves the attribute empty and is a SEPARATE,
independently-sufficient trigger from the annotation's own `batch` attribute.

### 5 — `List<Message<T>>` as a wrapper type in the catalogs

**Command.**
```
grep -rn "Message<\|springframework.messaging.Message" src/sextant/catalogs/spring-kafka.yml src/sextant/catalogs/spring-kafka-message.yml
```

**Output.** No match in either file.

**Claim.** Neither `spring-kafka.yml` nor `spring-kafka-message.yml` declares
`org.springframework.messaging.Message<T>` as a wrapper type anywhere.
`List<Message<T>>` (row 3's third `onMessage` overload resolves through the
framework's own message conversion, not a type this repo's catalogs model) is
confirmed to stay a disclosed OPEN type unless a later task (Task 11) adds an
explicit row for it — this probe does not add one.

## Verdict

1. Row 1: `batch(): String`, empty default, unchanged 3.1.4 → 4.1.1.
2. Row 2: `parses_true` is `Boolean.parseBoolean(batch())`, gated by
   `StringUtils.hasText` so a blank attribute makes no `setBatchListener`
   call at all — the framework's own no-resolution, case-insensitive,
   "empty means factory decides" behaviour, confirmed in bytecode at both
   versions (§2, §5a).
3. Row 3: the batch adapter's three accepted shapes are
   `ConsumerRecords<K,V>`, `List<ConsumerRecord<K,V>>`, and raw `Object`.
4. Row 4: the container factory's `setBatchListener(Boolean)` is an
   independent, non-annotation, bean-configured trigger — the boundary the
   catalog's condition predicate must not conflate with the annotation
   attribute.
5. Row 5: `List<Message<T>>` is confirmed absent from both catalogs' wrapper
   declarations; it remains a disclosed open type.

No claim in this probe came back false against the jars read. `measured:
2026-09-18` for every row above.
