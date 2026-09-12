# W60 — Kafka Streams' topic-addressing methods, and which argument carries the topic

**Question.** `kafka-streams.yml` (`G-31`) reads `StreamsBuilder.stream/table/
globalTable`, `KStream.to` and `Topology.addSink`/`addSource`. A `single_call` row
can only address a wire off an argument the call site itself carries, so before any
row is written the question is mechanical: of every method matching
`stream|table|globalTable|to|through|addSource|addSink` on `StreamsBuilder`,
`KStream`, `KTable` and `Topology`, which parameter position (if any) is shaped like
a topic — a plain `String`, a `Collection` of them, a `Pattern`, or a `String...`
array?

**Version scope (§5.4).** Read against **kafka-streams 3.6.2** — the version the jar
reports for itself, checked against the coordinate before any table is printed.
`fixtures/orders-streams/pom.xml` pins the same version.

**How to run.** `bash scripts/probes/w60_kafka_streams_surface/run.sh`. Resolves the
artifact through Maven (network on the first run only), reads the version the jar
states for itself, and asks `javap -p -s` for every method on the four classes
matching the shared name pattern above.

## Expectation table

| # | If | then |
|---|---|---|
| 1 | the first topic-shaped parameter is at position 0 and IS the topic (`stream(String)`, `to(String)`) | addressable at `channel_arg: 0` — the shape `kafka-streams.yml`'s source and sink rows use |
| 2 | the first topic-shaped parameter is a `String` that is NOT the topic — a processor/sink NAME sharing the same JVM type (`addSource`, `addSink`) | this column's naive "first topic-shaped slot" answer is the WRONG position; the catalog states the real one in its own comment, and this table's raw column is not read as the verdict for those two methods |
| 3 | no parameter is topic-shaped at all (`to(TopicNameExtractor)`) | not addressable by this style; declaring a row here would publish an unrelated value as a topic |

**The column is a MEASUREMENT of shape, not of meaning.** `addSource(String name,
String... topics)` and `addSink(String name, String topic, String... parents)` both
open with a `String` that is the processor/sink's own NAME, not a topic — so the
naive "first topic-shaped parameter" this probe computes lands on position 0 for
both, and the catalog's `channel_arg` (1 for both, matching the brief's own measured
table) deliberately disagrees with this column there. The two rows are called out
explicitly below rather than left as a silent mismatch between this document and the
shipped catalog.

---

## Observations

Verbatim from `scripts/probes/w60_kafka_streams_surface/run.sh`, which runs
`sweep.py`. **Every version in the headers below is the one the JAR itself
reported** — out of its own `pom.properties`, its manifest's
`Implementation-Version`, or its own `kafka/kafka-streams-version.properties` —
and **not the version the coordinate list asked for**; `checked` compares the
two and ABORTS when they disagree.

| what the run read | 3.6.2 |
|---|---|
| artifacts reporting this version | kafka-streams |
| where the jar states it | kafka/kafka-streams-version.properties |

### Every method matching `stream|table|globalTable|to|through|addSource|
### addSink`, and which position (if any) carries a topic

**`org.apache.kafka.streams.StreamsBuilder`** (org.apache.kafka:kafka-streams:3.6.2)

| # | method | descriptor | topic argument |
|---|---|---|---|
| 1 | `stream` | `(Ljava/lang/String;)Lorg/apache/kafka/streams/kstream/KStream;` | 0 |
| 2 | `stream` | `(Ljava/lang/String;Lorg/apache/kafka/streams/kstream/Consumed;)Lorg/apache/kafka/streams/kstream/KStream;` | 0 |
| 3 | `stream` | `(Ljava/util/Collection;)Lorg/apache/kafka/streams/kstream/KStream;` | 0 |
| 4 | `stream` | `(Ljava/util/Collection;Lorg/apache/kafka/streams/kstream/Consumed;)Lorg/apache/kafka/streams/kstream/KStream;` | 0 |
| 5 | `stream` | `(Ljava/util/regex/Pattern;)Lorg/apache/kafka/streams/kstream/KStream;` | 0 |
| 6 | `stream` | `(Ljava/util/regex/Pattern;Lorg/apache/kafka/streams/kstream/Consumed;)Lorg/apache/kafka/streams/kstream/KStream;` | 0 |
| 7 | `table` | `(Ljava/lang/String;Lorg/apache/kafka/streams/kstream/Consumed;Lorg/apache/kafka/streams/kstream/Materialized;)Lorg/apache/kafka/streams/kstream/KTable;` | 0 |
| 8 | `table` | `(Ljava/lang/String;)Lorg/apache/kafka/streams/kstream/KTable;` | 0 |
| 9 | `table` | `(Ljava/lang/String;Lorg/apache/kafka/streams/kstream/Consumed;)Lorg/apache/kafka/streams/kstream/KTable;` | 0 |
| 10 | `table` | `(Ljava/lang/String;Lorg/apache/kafka/streams/kstream/Materialized;)Lorg/apache/kafka/streams/kstream/KTable;` | 0 |
| 11 | `globalTable` | `(Ljava/lang/String;Lorg/apache/kafka/streams/kstream/Consumed;)Lorg/apache/kafka/streams/kstream/GlobalKTable;` | 0 |
| 12 | `globalTable` | `(Ljava/lang/String;)Lorg/apache/kafka/streams/kstream/GlobalKTable;` | 0 |
| 13 | `globalTable` | `(Ljava/lang/String;Lorg/apache/kafka/streams/kstream/Consumed;Lorg/apache/kafka/streams/kstream/Materialized;)Lorg/apache/kafka/streams/kstream/GlobalKTable;` | 0 |
| 14 | `globalTable` | `(Ljava/lang/String;Lorg/apache/kafka/streams/kstream/Materialized;)Lorg/apache/kafka/streams/kstream/GlobalKTable;` | 0 |

**`org.apache.kafka.streams.kstream.KStream`** (org.apache.kafka:kafka-streams:3.6.2)

| # | method | descriptor | topic argument |
|---|---|---|---|
| 1 | `through` | `(Ljava/lang/String;)Lorg/apache/kafka/streams/kstream/KStream;` | 0 |
| 2 | `through` | `(Ljava/lang/String;Lorg/apache/kafka/streams/kstream/Produced;)Lorg/apache/kafka/streams/kstream/KStream;` | 0 |
| 3 | `to` | `(Ljava/lang/String;)V` | 0 |
| 4 | `to` | `(Ljava/lang/String;Lorg/apache/kafka/streams/kstream/Produced;)V` | 0 |
| 5 | `to` | `(Lorg/apache/kafka/streams/processor/TopicNameExtractor;)V` | *(none)* |
| 6 | `to` | `(Lorg/apache/kafka/streams/processor/TopicNameExtractor;Lorg/apache/kafka/streams/kstream/Produced;)V` | *(none)* |

**`org.apache.kafka.streams.kstream.KTable`** (org.apache.kafka:kafka-streams:3.6.2)

| # | method | descriptor | topic argument |
|---|---|---|---|
| — | *(no `stream|table|globalTable|to|through|addSource|addSink` method found)* | — | — |

**`org.apache.kafka.streams.Topology`** (org.apache.kafka:kafka-streams:3.6.2)

| # | method | descriptor | topic argument |
|---|---|---|---|
| 1 | `addSource` | `(Ljava/lang/String;[Ljava/lang/String;)Lorg/apache/kafka/streams/Topology;` | 0 |
| 2 | `addSource` | `(Ljava/lang/String;Ljava/util/regex/Pattern;)Lorg/apache/kafka/streams/Topology;` | 0 |
| 3 | `addSource` | `(Lorg/apache/kafka/streams/Topology$AutoOffsetReset;Ljava/lang/String;[Ljava/lang/String;)Lorg/apache/kafka/streams/Topology;` | 1 |
| 4 | `addSource` | `(Lorg/apache/kafka/streams/Topology$AutoOffsetReset;Ljava/lang/String;Ljava/util/regex/Pattern;)Lorg/apache/kafka/streams/Topology;` | 1 |
| 5 | `addSource` | `(Lorg/apache/kafka/streams/processor/TimestampExtractor;Ljava/lang/String;[Ljava/lang/String;)Lorg/apache/kafka/streams/Topology;` | 1 |
| 6 | `addSource` | `(Lorg/apache/kafka/streams/processor/TimestampExtractor;Ljava/lang/String;Ljava/util/regex/Pattern;)Lorg/apache/kafka/streams/Topology;` | 1 |
| 7 | `addSource` | `(Lorg/apache/kafka/streams/Topology$AutoOffsetReset;Lorg/apache/kafka/streams/processor/TimestampExtractor;Ljava/lang/String;[Ljava/lang/String;)Lorg/apache/kafka/streams/Topology;` | 2 |
| 8 | `addSource` | `(Lorg/apache/kafka/streams/Topology$AutoOffsetReset;Lorg/apache/kafka/streams/processor/TimestampExtractor;Ljava/lang/String;Ljava/util/regex/Pattern;)Lorg/apache/kafka/streams/Topology;` | 2 |
| 9 | `addSource` | `(Ljava/lang/String;Lorg/apache/kafka/common/serialization/Deserializer;Lorg/apache/kafka/common/serialization/Deserializer;[Ljava/lang/String;)Lorg/apache/kafka/streams/Topology;` | 0 |
| 10 | `addSource` | `(Ljava/lang/String;Lorg/apache/kafka/common/serialization/Deserializer;Lorg/apache/kafka/common/serialization/Deserializer;Ljava/util/regex/Pattern;)Lorg/apache/kafka/streams/Topology;` | 0 |
| 11 | `addSource` | `(Lorg/apache/kafka/streams/Topology$AutoOffsetReset;Ljava/lang/String;Lorg/apache/kafka/common/serialization/Deserializer;Lorg/apache/kafka/common/serialization/Deserializer;[Ljava/lang/String;)Lorg/apache/kafka/streams/Topology;` | 1 |
| 12 | `addSource` | `(Lorg/apache/kafka/streams/Topology$AutoOffsetReset;Ljava/lang/String;Lorg/apache/kafka/common/serialization/Deserializer;Lorg/apache/kafka/common/serialization/Deserializer;Ljava/util/regex/Pattern;)Lorg/apache/kafka/streams/Topology;` | 1 |
| 13 | `addSource` | `(Lorg/apache/kafka/streams/Topology$AutoOffsetReset;Ljava/lang/String;Lorg/apache/kafka/streams/processor/TimestampExtractor;Lorg/apache/kafka/common/serialization/Deserializer;Lorg/apache/kafka/common/serialization/Deserializer;[Ljava/lang/String;)Lorg/apache/kafka/streams/Topology;` | 1 |
| 14 | `addSource` | `(Lorg/apache/kafka/streams/Topology$AutoOffsetReset;Ljava/lang/String;Lorg/apache/kafka/streams/processor/TimestampExtractor;Lorg/apache/kafka/common/serialization/Deserializer;Lorg/apache/kafka/common/serialization/Deserializer;Ljava/util/regex/Pattern;)Lorg/apache/kafka/streams/Topology;` | 1 |
| 15 | `addSink` | `(Ljava/lang/String;Ljava/lang/String;[Ljava/lang/String;)Lorg/apache/kafka/streams/Topology;` | 0 |
| 16 | `addSink` | `(Ljava/lang/String;Ljava/lang/String;Lorg/apache/kafka/streams/processor/StreamPartitioner;[Ljava/lang/String;)Lorg/apache/kafka/streams/Topology;` | 0 |
| 17 | `addSink` | `(Ljava/lang/String;Ljava/lang/String;Lorg/apache/kafka/common/serialization/Serializer;Lorg/apache/kafka/common/serialization/Serializer;[Ljava/lang/String;)Lorg/apache/kafka/streams/Topology;` | 0 |
| 18 | `addSink` | `(Ljava/lang/String;Ljava/lang/String;Lorg/apache/kafka/common/serialization/Serializer;Lorg/apache/kafka/common/serialization/Serializer;Lorg/apache/kafka/streams/processor/StreamPartitioner;[Ljava/lang/String;)Lorg/apache/kafka/streams/Topology;` | 0 |
| 19 | `addSink` | `(Ljava/lang/String;Lorg/apache/kafka/streams/processor/TopicNameExtractor;[Ljava/lang/String;)Lorg/apache/kafka/streams/Topology;` | 0 |
| 20 | `addSink` | `(Ljava/lang/String;Lorg/apache/kafka/streams/processor/TopicNameExtractor;Lorg/apache/kafka/streams/processor/StreamPartitioner;[Ljava/lang/String;)Lorg/apache/kafka/streams/Topology;` | 0 |
| 21 | `addSink` | `(Ljava/lang/String;Lorg/apache/kafka/streams/processor/TopicNameExtractor;Lorg/apache/kafka/common/serialization/Serializer;Lorg/apache/kafka/common/serialization/Serializer;[Ljava/lang/String;)Lorg/apache/kafka/streams/Topology;` | 0 |
| 22 | `addSink` | `(Ljava/lang/String;Lorg/apache/kafka/streams/processor/TopicNameExtractor;Lorg/apache/kafka/common/serialization/Serializer;Lorg/apache/kafka/common/serialization/Serializer;Lorg/apache/kafka/streams/processor/StreamPartitioner;[Ljava/lang/String;)Lorg/apache/kafka/streams/Topology;` | 0 |

## Verdict

`StreamsBuilder.stream/table/globalTable` and `KStream.to(String[, Produced])` carry
their topic at argument 0, exactly as this column reports — `kafka-streams.yml`
reads all of them at `channel_arg: 0`. `KStream.to(TopicNameExtractor[, Produced])`
carries no topic-shaped argument at all (row 5/6): the catalog states this stated,
never declared, and Step 6's declining test pins it.

`Topology.addSink` (rows 15-22) and the four `addSource(String, String...)`-shaped
rows (1, 3, 5, 7) both open with a `String` that this column reads as argument 0's
"topic" — and for both methods that `String` is the processor/sink's own NAME, not a
topic; the real topic is the TRAILING `String...`/`Pattern` argument, one position
later than this column's naive first-match answer (`AutoOffsetReset`/
`TimestampExtractor` prefixes push it one and two further still, exactly as rows
3-8 and 11-14 show). `kafka-streams.yml` reads `addSink` at `channel_arg: 1` and the
four varargs `addSource` overloads at the position their OWN row lists (1, 2, 2 and
3 respectively) — never at this column's raw answer — stated here so the disagreement
between this table and the shipped catalog is not a silent one. The `Pattern`-taking
`addSource` siblings (rows 2, 4, 6, 8) and the `Deserializer`-taking ones (rows
9-14) are read by NEITHER this catalog's `matches.methods` nor any `channel_via`
form; `kafka-streams.yml`'s own comment records why and that the gap is left open
for later work, not fabricated around.

`through` (rows 1-2) is deprecated, a sink AND a source on one topic in one call, and
is declared `slice.outside` rather than read as either half. `KTable` declares none
of the seven matched names at all — measured here as the empty table above — which is
why it is named in neither `kafka-streams.yml`'s `matches.owner` nor this probe's
`w19_catalog_surface` Surface list.
