# W53 — does every serializer class `spring-kafka-media.yml` names exist? (G-88)

**Question.** The file maps configured serializer and deserializer CLASSES to two
different answers: `values` gives a media type, `format_from` gives the wire
format. Between them they name fourteen classes, **eight of them Confluent's**, and
when A2 audited the file no `io.confluent` artifact resolved in `~/.m2` or the
Gradle cache. Those eight were spellings nobody had opened.

**A wrong class name here is silent.** D02's rule is that a class absent from the
map stamps nothing rather than guessing — which is the right rule, and it means a
typo and an unconfigured module are indistinguishable in the output. The row loses
its format and nothing says a name was wrong.

G-88 also called the file "asymmetric": `values` holds 6 rows where `format_from`
holds 14, so the eight Confluent classes get a format and no media, "which nothing
in the file explains." **The file does explain it**, in the paragraph above
`format_from`: a schema-registry serializer has no MIME string anyone registered,
so it answers rung 3 and stamps no media, because a MIME type for it would be
invented. That half of G-88 is answered by reading the file; this probe answers the
half that needs a jar.

**Version scope (§5.4).** Read against **Confluent 7.6.0** (four serializer
artifacts, from `packages.confluent.io`), **spring-kafka 3.1.4** and
**kafka-clients 3.6.2**. A class's package is API surface and can move between
major versions; these are the versions read.

## Expectation table

| # | If | then |
|---|---|---|
| 1 | every class exists | the map is measured, and the catalog leaves `_NOT_MEASURED_YET` |
| 2 | a class does not | that row stamps nothing and looks exactly like an unconfigured module |
| 3 | the catalog names a class this probe does not open | the probe reports it rather than claiming whole coverage |
| 4 | `values` and `format_from` differ in size | that is the design, not a defect — the file says which classes belong to only one and why |

## Observations

Verbatim from `scripts/probes/w53_kafka_serializer_identities/run.sh`, which runs
`sweep.py`. **Every version in the headers below is the one the JAR itself
reported** — out of its own `pom.properties` or its manifest's
`Implementation-Version`, and **not the version the coordinate list asked for**;
`checked` compares the two and ABORTS when they disagree.

| what the run read | 3.1.4 | 3.6.2 | 7.6.0 |
|---|---|---|---|
| artifacts reporting this version | spring-kafka | kafka-clients | kafka-avro-serializer, kafka-protobuf-serializer, kafka-json-schema-serializer, kafka-json-serializer |
| where the jar states it | MANIFEST.MF | kafka/kafka-version.properties | pom.properties |

### Does every class the catalog names exist?

| class | artifact that carries it | present | in `values` | in `format_from` |
|---|---|---|---|---|
| `org.springframework.kafka.support.serializer.JsonSerializer` | `spring-kafka` | **yes** | yes | yes |
| `org.springframework.kafka.support.serializer.JsonDeserializer` | `spring-kafka` | **yes** | yes | yes |
| `org.apache.kafka.common.serialization.StringSerializer` | `kafka-clients` | **yes** | yes | yes |
| `org.apache.kafka.common.serialization.StringDeserializer` | `kafka-clients` | **yes** | yes | yes |
| `org.apache.kafka.common.serialization.ByteArraySerializer` | `kafka-clients` | **yes** | yes | yes |
| `org.apache.kafka.common.serialization.ByteArrayDeserializer` | `kafka-clients` | **yes** | yes | yes |
| `io.confluent.kafka.serializers.KafkaAvroSerializer` | `kafka-avro-serializer` | **yes** | — | yes |
| `io.confluent.kafka.serializers.KafkaAvroDeserializer` | `kafka-avro-serializer` | **yes** | — | yes |
| `io.confluent.kafka.serializers.protobuf.KafkaProtobufSerializer` | `kafka-protobuf-serializer` | **yes** | — | yes |
| `io.confluent.kafka.serializers.protobuf.KafkaProtobufDeserializer` | `kafka-protobuf-serializer` | **yes** | — | yes |
| `io.confluent.kafka.serializers.json.KafkaJsonSchemaSerializer` | `kafka-json-schema-serializer` | **yes** | — | yes |
| `io.confluent.kafka.serializers.json.KafkaJsonSchemaDeserializer` | `kafka-json-schema-serializer` | **yes** | — | yes |
| `io.confluent.kafka.serializers.KafkaJsonSerializer` | `kafka-json-serializer` | **yes** | — | yes |
| `io.confluent.kafka.serializers.KafkaJsonDeserializer` | `kafka-json-serializer` | **yes** | — | yes |

**Named in the catalog and not opened by this probe:** none.
**`values` holds 6; `format_from` holds 14.**

**Verdict: all fourteen CONFIRMED**, including all eight Confluent spellings, and
nothing the catalog names went unopened. The 6-against-14 split is exactly the one
the file describes: the six non-Confluent classes appear in both tables, and the
eight schema-registry ones appear only in `format_from`.

**One identity route worth recording.** `kafka-clients-3.6.2.jar` ships a 25-byte
manifest with no `Implementation-Version` and no maven metadata at all; it states
its version in `kafka/kafka-version.properties`. A reader checking only the
manifest and `pom.properties` would have called it unmeasurable and written
`identity: assumed`. It is `reported`.

## What this probe does NOT establish

That the FORMAT each class is mapped to is correct. It confirms
`io.confluent.kafka.serializers.json.KafkaJsonSchemaSerializer` exists; it does not
confirm the file's claim that it puts plain JSON on the wire and carries the schema
out of band, which is behaviour and would need a running broker. It also says
nothing about Confluent versions other than 7.6.0.
