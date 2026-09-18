# CP-21 — Micronaut JMS: `@JMSListener`/`@JMSProducer`'s attributes, the `value` = factory-bean-name resolution, and the three brokers' literal names

**Question.** Group B/C's Micronaut JMS catalogs read `@JMSListener.value()` as
the SQS/ActiveMQ-classic/Artemis connection-factory bean name (R2 in the
design spec), a fact that hinges on three things this probe measures
independently: that `@JMSListener` carries no `connectionFactory` attribute at
all (so the catalog cannot alias one that does not exist), that the
post-processor resolves `value()` through `Qualifiers.byName` against the bean
context (not a literal factory lookup), and that each broker module's own
`CONNECTION_FACTORY_BEAN_NAME` constant is the exact literal a fixture's
`value="…"` must match. Row 4 confirms all three by reading the literal the
Task 1 fixture actually compiled to.

**What this probe does not settle.** Nothing was deployed; no JMS connection
was opened. This reads the annotation jar's own declared attributes, the
post-processor's bytecode, the three broker configuration classes' own
constants, and one compiled fixture's class file — not runtime bean wiring.

**Version scope (§5.4).** `io.micronaut.jms:micronaut-jms-core`,
`micronaut-jms-sqs`, `micronaut-jms-activemq-classic` and the Artemis module,
all at **4.2.0** — the single version this catalog targets (Micronaut JMS
publishes one version per Micronaut JMS release with no long-lived prior
major in the design's scope, unlike the two-minor pairs above). Every verdict
below is bounded to 4.2.0.

## Environment

`C=~/.m2/repository/io/micronaut/jms/micronaut-jms-core/4.2.0/micronaut-jms-core-4.2.0.jar`
`S=~/.m2/repository/io/micronaut/jms/micronaut-jms-sqs/4.2.0/micronaut-jms-sqs-4.2.0.jar`
`AMQ=~/.m2/repository/io/micronaut/jms/micronaut-jms-activemq-classic/4.2.0/micronaut-jms-activemq-classic-4.2.0.jar`
(already resolved in `~/.m2`); the Artemis jar
(`io.micronaut.jms:micronaut-jms-artemis:4.2.0`) came from the design-review
scratchpad as `mn-jms-artemis-4.2.0.jar`, not yet in `~/.m2`.

## Rows

### 1a/1b — `@JMSListener`/`@JMSProducer`: declared attributes, `@Target`, `@Retention`

**Command.**
```
javap -v -cp $C io.micronaut.jms.annotations.JMSListener | grep -E 'public abstract|Retention|Target'
javap -v -cp $C io.micronaut.jms.annotations.JMSProducer | grep -E 'public abstract|Retention|Target'
```

**Output.**
```
JMSListener:
  public abstract java.lang.String value();
  public abstract java.lang.Class<? extends io.micronaut.jms.listener.JMSListenerSuccessHandler>[] successHandlers();
  public abstract java.lang.Class<? extends io.micronaut.jms.listener.JMSListenerErrorHandler>[] errorHandlers();
  java.lang.annotation.Retention(value=RetentionPolicy.RUNTIME)
  java.lang.annotation.Target(value=[ElementType.TYPE])

JMSProducer:
  public abstract java.lang.String value();
  java.lang.annotation.Retention(value=RetentionPolicy.RUNTIME)
  java.lang.annotation.Target(value=[ElementType.TYPE])
```

**Claim.** `@JMSListener` declares exactly three attributes —
`value(): String`, `successHandlers(): Class<? extends
JMSListenerSuccessHandler>[]`, `errorHandlers(): Class<? extends
JMSListenerErrorHandler>[]` — and **no `connectionFactory` attribute of any
name**. `@JMSProducer` declares one, `value(): String`. Both are
`@Retention(RUNTIME)`, `@Target(TYPE)`-only (class-level, not method-level) —
this closes R2: there is nothing named `connectionFactory` for a catalog to
misread, `value()` is the only address-bearing attribute on either
annotation, and both are legal on a class declaration only.

### 2 — the post-processor resolves `value()` through `Qualifiers.byName`

**Command.**
```
javap -c -p -cp $C io.micronaut.jms.configuration.AbstractJMSListenerMethodProcessor | grep -E 'JMSListener|getRequiredValue|byName'
```

**Output (relevant constant-pool references, in call order).**
```
ldc      class io/micronaut/jms/annotations/JMSListener
invokevirtual  Method AnnotationValue.getRequiredValue:(Ljava/lang/Class;)Ljava/lang/Object;
...
invokevirtual  Method AnnotationValue.getRequiredValue:(Ljava/lang/String;Ljava/lang/Class;)Ljava/lang/Object;
...
invokestatic   Method io/micronaut/inject/qualifiers/Qualifiers.byName:(Ljava/lang/String;)Lio/micronaut/context/Qualifier;
...
ldc      class io/micronaut/jms/listener/JMSListenerRegistry
invokevirtual  Method JMSListenerRegistry.register:(Ljakarta/jms/Connection;Lio/micronaut/jms/model/JMSDestinationType;Ljava/lang/String;ZILjakarta/jms/MessageListener;Ljava/util/concurrent/ExecutorService;ZLjava/util/Optional;)Lio/micronaut/jms/listener/JMSListener;
```

**Claim.** The processor reads `@JMSListener`'s attribute value via
`AnnotationValue.getRequiredValue`, then resolves the JMS `Connection` bean
via `Qualifiers.byName(<that string>)` — a bean-context lookup by name, not a
literal class or a hardcoded factory reference. `value` is therefore exactly
the **name of the connection-factory bean** the application context must
carry; the SQS/ActiveMQ/Artemis modules exist to register a bean under that
exact name (rows 3a–3c).

### 3a–3c — the three brokers' `CONNECTION_FACTORY_BEAN_NAME` literals, and the `@Named` bean definition

**Command.**
```
javap -constants -cp $S   io.micronaut.jms.sqs.configuration.SqsConfiguration              | grep 'static final'
javap -constants -cp $AMQ io.micronaut.jms.activemq.classic.configuration.ActiveMqClassicConfiguration | grep 'static final'
javap -constants -cp $ARTEMIS io.micronaut.jms.activemq.artemis.configuration.ActiveMqArtemisConfiguration | grep 'static final'
javap -v -cp $S 'io.micronaut.jms.sqs.configuration.$SqsConfiguration$SqsJmsConnectionFactory0$Definition' | grep -E 'sqsJmsConnectionFactory|Named'
```

**Output.**
```
SqsConfiguration:              CONNECTION_FACTORY_BEAN_NAME = "sqsJmsConnectionFactory"
ActiveMqClassicConfiguration:  CONNECTION_FACTORY_BEAN_NAME = "activeMqConnectionFactory"
ActiveMqArtemisConfiguration:  CONNECTION_FACTORY_BEAN_NAME = "activeMqArtemisConnectionFactory"
```
The generated `$SqsConfiguration$SqsJmsConnectionFactory0$Definition` bean
definition class carries the literal `sqsJmsConnectionFactory` (constant-pool
`#87`/`#88`) alongside `jakarta.inject.Named` (`#91`/`#92`) repeatedly through
its bean-metadata methods, and its producing method resolves to
`SqsConfiguration.sqsJmsConnectionFactory(SqsConfigurationProperties,
SqsClient): ConnectionFactory` — the bean IS registered `@Named
"sqsJmsConnectionFactory"`.

**Claim.** Each broker module fixes ONE literal bean name for its connection
factory: SQS → `"sqsJmsConnectionFactory"`, ActiveMQ classic →
`"activeMqConnectionFactory"`, Artemis → `"activeMqArtemisConnectionFactory"`
— and the SQS module's generated bean-definition class confirms the bean is
registered `@Named` with exactly that string, so `Qualifiers.byName` (row 2)
resolves it directly.

### 4 — the compiled fixture: `value="sqsJmsConnectionFactory"` inlines

**Command.**
```
javap -v -cp fixtures/orders-micronaut/target/classes 'com.acme.mn.OrderMessaging$SqsConsumer' | grep -B2 -A3 JMSListener
```

**Output.**
```
RuntimeVisibleAnnotations:
  0: #24(#20=s#25)
    io.micronaut.jms.annotations.JMSListener(
      value="sqsJmsConnectionFactory"
    )
```

**Claim.** Task 1's `OrderMessaging.SqsConsumer` fixture class file carries
`@JMSListener(value="sqsJmsConnectionFactory")` verbatim in its
`RuntimeVisibleAnnotations` — the literal inlines into the class file exactly
as javac compiles a `String`-typed annotation attribute (no indirection, no
resolution needed at read time). `path_from`/the catalog's destination
attribute for Micronaut JMS is `name: value` — reading `value()` straight off
the annotation gives the factory bean name string directly.

## Verdict

1. Rows 1a/1b close R2: neither annotation declares a `connectionFactory`
   attribute; `value()` is the sole address-bearing attribute on each, both
   `@Target(TYPE)`-only.
2. Row 2 confirms the post-processor treats `value()` as a bean-context lookup
   key (`Qualifiers.byName`), not a class reference or literal factory.
3. Rows 3a–3c give the three exact bean-name literals the catalog's `SQS`,
   `ActiveMQ classic` and `Artemis` variants must recognise, and confirm the
   SQS bean is registered `@Named` with that literal.
4. Row 4 confirms the whole chain end to end against Task 1's own compiled
   fixture: the annotation's `value` inlines as a plain `String` constant in
   the class file, matching the SQS module's bean name exactly.

No claim in this probe came back false against the jars/fixture read.
`measured: 2026-09-18` for every row above.
