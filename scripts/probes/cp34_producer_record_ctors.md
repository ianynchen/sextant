# CP-34 — `ProducerRecord`'s constructors, and whether `payload_ctor_arg: "last"` is the value

Three shipped catalogs — `kafka-clients.yml`, `spring-kafka-template.yml` and
`spring-kafka-replying.yml` — declare the same block:

```yaml
record_wrappers:
  - { type: org.apache.kafka.clients.producer.ProducerRecord,
      channel_ctor_arg: 0, payload_ctor_arg: last }
```

`single_call._record_arguments` resolves `last` to the linked constructor's own final
argument, and a test docstring in this repository asserted the rule "holds across every
`ProducerRecord` overload (design doc)". Nothing had measured that. This probe asks the
mechanical question instead: **of every constructor `ProducerRecord` declares, which
parameter carries the value, and is it the last one?**

**Version scope (§5.4).** Read against **kafka-clients 3.6.2** — the version the jar
reports for itself, out of its own `kafka/kafka-version.properties`, the entry
kafka-clients' own `AppInfoParser` reads at runtime to report the client version.
`sweep.py` compares that value against the coordinate `run.sh` asked for and **aborts**
when they disagree, so no cell below can carry a version the archive did not state.
kafka-clients writes nothing into its manifest (`META-INF/MANIFEST.MF` is the two-line
default) and ships no `pom.properties`, which is why that entry and not the usual two;
`cp12_sweep_round1b.md` reads this artifact the same way. 3.6.2 is the version
`kafka-clients.yml`'s own `measured:` block already cites. **A kafka-clients release
before or after 3.6.2 is unverified**: a constructor added or removed changes the overload
set this verdict is about, which is what bounding it is for.

## The verdict

**`payload_ctor_arg: "last"` is the value on four of the six constructors and is NOT on
the other two.** Both exceptions are the overloads whose final parameter is
`Iterable<Header>`: on those, `last` reads the record's **headers** and publishes them as
the payload. A fabricated payload, not a miss, on ordinary input —
`new ProducerRecord<>(topic, partition, key, value, headers)` is the documented way to
send a record with headers.

**Arity cannot tell the two apart from the correct ones.** Constructors 2 and 3 below both
take five arguments and disagree: `(String, Integer, Long, K, V)` puts the value last and
`(String, Integer, K, V, Iterable)` does not. Only the descriptor separates them, which is
why the fix is descriptor-discriminated rather than an `arity`.

`channel_ctor_arg: 0` is unaffected: every one of the six takes the topic at argument 0.

## Observations

Verbatim from `scripts/probes/cp34_producer_record_ctors/run.sh`, which runs
`sweep.py`. **The version in the header below is the one the JAR itself
reported** — out of its own `kafka/kafka-version.properties` —
and **not the version the coordinate asked for**;
`checked` compares the two and ABORTS when they disagree.

| what the run read | 3.6.2 |
|---|---|
| artifacts reporting this version | org.apache.kafka:kafka-clients |
| where the jar states it | kafka/kafka-version.properties |
| value type variable, read off the class declaration | `V` |

### Every constructor, and where the value sits

| # | declared parameters | erased descriptor | value slot | last slot | `last` is the value? |
|---|---|---|---|---|---|
| 1 | `java.lang.String, java.lang.Integer, java.lang.Long, K, V, java.lang.Iterable<org.apache.kafka.common.header.Header>` | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Long;Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Iterable;)V` | 4 | 5 | **NO** |
| 2 | `java.lang.String, java.lang.Integer, java.lang.Long, K, V` | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Long;Ljava/lang/Object;Ljava/lang/Object;)V` | 4 | 4 | yes |
| 3 | `java.lang.String, java.lang.Integer, K, V, java.lang.Iterable<org.apache.kafka.common.header.Header>` | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Iterable;)V` | 3 | 4 | **NO** |
| 4 | `java.lang.String, java.lang.Integer, K, V` | `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Object;Ljava/lang/Object;)V` | 3 | 3 | yes |
| 5 | `java.lang.String, K, V` | `(Ljava/lang/String;Ljava/lang/Object;Ljava/lang/Object;)V` | 2 | 2 | yes |
| 6 | `java.lang.String, V` | `(Ljava/lang/String;Ljava/lang/Object;)V` | 1 | 1 | yes |

**6 constructors; `last` is the value on 4 and is NOT on 2.**

* `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Long;Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Iterable;)V` — value at 4, `last` reads 5
* `(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Iterable;)V` — value at 3, `last` reads 4

### The bytecode the generic reading is checked against

One constructor assigns the field; the other five delegate to it, and the order they pass their own locals in is what carries their value into its slot.

```
101: aload         5 ; 103: putfield      #14                 // Field value:Ljava/lang/Object;
```

```
public org.apache.kafka.clients.producer.ProducerRecord(java.lang.String, java.lang.Integer, java.lang.Long, K, V, java.lang.Iterable<org.apache.kafka.common.header.Header>); --- 0: aload_0 ; 1: invokespecial #1                  // Method java/lang/Object."<init>":()V ; 4: aload_1 ; 14: invokespecial #4                  // Method java/lang/IllegalArgumentException."<init>":(Ljava/lang/String;)V ; 18: aload_3 ; 22: aload_3 ; 43: aload_3 ; 48: invokespecial #4                  // Method java/lang/IllegalArgumentException."<init>":(Ljava/lang/String;)V ; 52: aload_2 ; 56: aload_2 ; 75: aload_2 ; 80: invokespecial #4                  // Method java/lang/IllegalArgumentException."<init>":(Ljava/lang/String;)V ; 84: aload_0 ; 85: aload_1 ; 86: putfield      #11                 // Field topic:Ljava/lang/String; ; 89: aload_0 ; 90: aload_2 ; 91: putfield      #12                 // Field partition:Ljava/lang/Integer; ; 94: aload_0 ; 95: aload         4 ; 97: putfield      #13                 // Field key:Ljava/lang/Object; ; 100: aload_0 ; 101: aload         5 ; 103: putfield      #14                 // Field value:Ljava/lang/Object; ; 106: aload_0 ; 107: aload_3 ; 108: putfield      #15                 // Field timestamp:Ljava/lang/Long; ; 111: aload_0 ; 116: aload         6 ; 118: invokespecial #17                 // Method org/apache/kafka/common/header/internals/RecordHeaders."<init>":(Ljava/lang/Iterable;)V ; 121: putfield      #18                 // Field headers:Lorg/apache/kafka/common/header/Headers;
public org.apache.kafka.clients.producer.ProducerRecord(java.lang.String, java.lang.Integer, java.lang.Long, K, V); --- 0: aload_0 ; 1: aload_1 ; 2: aload_2 ; 3: aload_3 ; 4: aload         4 ; 6: aload         5 ; 8: aconst_null ; 9: invokespecial #19                 // Method "<init>":(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Long;Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Iterable;)V
public org.apache.kafka.clients.producer.ProducerRecord(java.lang.String, java.lang.Integer, K, V, java.lang.Iterable<org.apache.kafka.common.header.Header>); --- 0: aload_0 ; 1: aload_1 ; 2: aload_2 ; 3: aconst_null ; 4: aload_3 ; 5: aload         4 ; 7: aload         5 ; 9: invokespecial #19                 // Method "<init>":(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Long;Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Iterable;)V
public org.apache.kafka.clients.producer.ProducerRecord(java.lang.String, java.lang.Integer, K, V); --- 0: aload_0 ; 1: aload_1 ; 2: aload_2 ; 3: aconst_null ; 4: aload_3 ; 5: aload         4 ; 7: aconst_null ; 8: invokespecial #19                 // Method "<init>":(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Long;Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Iterable;)V
public org.apache.kafka.clients.producer.ProducerRecord(java.lang.String, K, V); --- 0: aload_0 ; 1: aload_1 ; 2: aconst_null ; 3: aconst_null ; 4: aload_2 ; 5: aload_3 ; 6: aconst_null ; 7: invokespecial #19                 // Method "<init>":(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Long;Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Iterable;)V
public org.apache.kafka.clients.producer.ProducerRecord(java.lang.String, V); --- 0: aload_0 ; 1: aload_1 ; 2: aconst_null ; 3: aconst_null ; 4: aconst_null ; 5: aload_2 ; 6: aconst_null ; 7: invokespecial #19                 // Method "<init>":(Ljava/lang/String;Ljava/lang/Integer;Ljava/lang/Long;Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Iterable;)V
```
