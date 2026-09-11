# CP-15 — the operation name MicroProfile GraphQL serves

**Question.** `docs/open-issues.md`'s **`OI-5`** (Major, pre-existing as the
principles sweep's `A-Mi9`) is the highest-value item in that document's probe
backlog, and its whole content is that nobody had run the framework:

> `microprofile-graphql.yml`'s `path_fallback: construct_name` is a prediction:
> MP GraphQL likely strips a `get`/`is` prefix, so `@Query List<Order>
> getOrders()` would be served as `orders` while we publish `getOrders`. **A
> wrong address, not an under-report.**

The catalog says the same thing about itself, in the comment above the key —
"the fallback publishes the method's own name because that is Spring's rule,
and MicroProfile is a different implementation". Six questions, one reading:

| # | what it asks | why the catalog needs it |
|---|---|---|
| 1 | every source `getOperationName` consults, in the order it consults them | the catalog reads ONE — the operation annotation's own `value` — and whether that is the whole rule decides whether an un-annotated operation is the only wrong address it can publish |
| 2 | which annotation TYPE each of those sources is | a cell naming `Annotations.NAME` is a field, and a catalog cannot be written against a field |
| 3 | what the name is when no source in row 1 supplied one | this is the method `path_fallback: construct_name` claims to mirror |
| 4 | the transformation row 3 applies | a table of names could agree with several rules; the `length`, `startsWith` and capitalisation tests are the rule |
| 5 | what the implementation RETURNS for a table of method names | `OI-5`'s close condition is a served name, not a reading of the code that computes one |
| 6 | which MEMBER of each source annotation is read, and what makes a value count | **added 2026-09-06, when `OI-35`'s close needed it.** Rows 1-2 answer WHICH annotations and in what ORDER, and a catalog needs a third thing rows 1-2 do not carry: an ATTRIBUTE NAME. Jackson's `@JsonProperty` declares six members, so taking `value` from the method's own name (`getOneOfTheseMethodAnnotationsValue`) would be §5.3's "assumed a mechanism's behaviour from its name" — the failure that rule was written for |

**Row 5 is not an instruction sequence.** `MethodHelper.getPropertyName` is
public, static, and takes a `Direction` and a `String` — no jandex index and no
deployment — so `probe.py` compiles a driver against the resolved jar and runs
it, exactly as CP-13's Q5 compiled an override pair. The cell is what the
process printed.

**What this probe does not settle, and the verdict must not be read past it.**
(a) **Nothing was deployed.** Row 5 is the schema builder's answer, not an
observed GraphQL request; row 3 is what says nothing transforms the name
between that call and the `Operation`'s own. A live SmallRye deployment stays
rank 2 of the sweep's probe backlog and this does not retire it. (b) **SmallRye
is ONE implementation** of a specification several vendors implement, so every
verdict below is scoped to it and to the two versions named. The API artifact
`microprofile-graphql.yml` gates on declares the annotations and no naming rule
at all, which is why the artifact measured here is not the artifact the catalog
detects — `measured:`'s own contract is that `artifact` is the one a rule was
READ OUT OF, with `spring-web.yml`'s handler gate living in `spring-webmvc` as
the shipped precedent.

**Version scope (§5.4).** Read against **smallrye-graphql-schema-builder 2.0.0
and 2.18.5**. Two minors rather than one, for CP-12's reason: a naming rule is
a version-scoped fact and one reading cannot say whether it is stable. 2.0.0 is
the first release of the line implementing MicroProfile GraphQL 2.0 — the
specification version this catalog gates on — and 2.18.5 is the last release of
that line at the time of the run, so the columns bound the generation at both
ends. **Every verdict below is bounded by those two.**

**How to run.** `bash scripts/probes/cp15_mp_graphql_names/run.sh`. It resolves
each jar through Maven (network on the first run only, cached in `~/.m2`
afterwards), asks `javap` five questions and compiles-and-runs the fifth. Needs
a JDK and Maven. Not a test: nothing in the suite runs it, and NFR-1's
no-network rule governs the suite rather than evidence gathering.

## Expectation table

| # | Under test | Expected |
|---|---|---|
| 1 | `OperationCreator.getOperationName` | the operation annotation's value, then some ordered list of fallbacks |
| 2 | `Annotations`' static initialiser | the fully qualified name behind each field row 1 named |
| 3 | `OperationCreator.getDefaultExecutionTypeName` | the method's own name, transformed or not |
| 4 | `MethodHelper` | a prefix strip, if row 3 transforms at all |
| 5 | `getPropertyName`, run | `getOrders` mapping to something; whichever answer it gives settles `OI-5` |
| 6 | `Annotations.getOneOfTheseMethodAnnotationsValue` and the predicate and reader beneath it | some member accessor, and some test for what counts as a written value |

## Observations

Verbatim from `run.sh`'s generated table (`probe.py` prints it; nothing here is
typed by hand). **Every column header of the first table is a version the JAR
itself reported, and not the version the coordinate list asked for** — out of
each manifest's `Implementation-Version`. `probe.py` reads the value out of the
archive it opened and ABORTS the whole run when it disagrees with the coordinate
that resolved the jar, rather than filling a mislabelled column; that is CP-5's
failure, which printed a version it believed beside output from a version it had
not run.

Row 1's cell is the array construction kept WHOLE rather than filtered to its
`getstatic`s, because the `iconst_N` indices are the ORDER and
`getOneOfTheseMethodAnnotationsValue` takes the first entry with a value. Row 5's
cell is a process's stdout rather than a disassembly, and its version column is
the jar the driver was compiled and run against. Row 6's cell is four bodies
concatenated in call order — the loop, the predicate that decides a source HAS a
value, the predicate under that, and the two `getStringValue` overloads that turn
the chosen instance into the name — because the answer is spread across them and
no one of them carries it.

| what the run read | 2.0.0 | 2.18.5 |
|---|---|---|
| artifacts reporting this version | smallrye-graphql-schema-builder | smallrye-graphql-schema-builder |
| identity read from the archive itself | yes | yes |

| # | question | artifact | version | observed |
|---|---|---|---|---|
| 1a | `OperationCreator.getOperationName` — the name sources, in order | `smallrye-graphql-schema-builder` | 2.0.0 | `aload_1 ; invokestatic Method getOperationAnnotation:(Lio/smallrye/graphql/schema/model/OperationType;)Lorg/jboss/jandex/DotName; ; astore_3 ; aload_2 ; iconst_5 ; anewarray class org/jboss/jandex/DotName ; dup ; iconst_0 ; aload_3 ; aastore ; dup ; iconst_1 ; getstatic Field io/smallrye/graphql/schema/Annotations.NAME:Lorg/jboss/jandex/DotName; ; aastore ; dup ; iconst_2 ; getstatic Field io/smallrye/graphql/schema/Annotations.JAKARTA_JSONB_PROPERTY:Lorg/jboss/jandex/DotName; ; aastore ; dup ; iconst_3 ; getstatic Field io/smallrye/graphql/schema/Annotations.JAVAX_JSONB_PROPERTY:Lorg/jboss/jandex/DotName; ; aastore ; dup ; iconst_4 ; getstatic Field io/smallrye/graphql/schema/Annotations.JACKSON_PROPERTY:Lorg/jboss/jandex/DotName; ; aastore ; invokevirtual Method io/smallrye/graphql/schema/Annotations.getOneOfTheseMethodAnnotationsValue:([Lorg/jboss/jandex/DotName;)Ljava/util/Optional; ; aload_0 ; aload_1 ; invokestatic Method getDefaultExecutionTypeName:(Lorg/jboss/jandex/MethodInfo;Lio/smallrye/graphql/schema/model/OperationType;)Ljava/lang/String; ; invokevirtual Method java/util/Optional.orElse:(Ljava/lang/Object;)Ljava/lang/Object; ; checkcast class java/lang/String ; areturn` |
| 1b | `OperationCreator.getOperationName` — the name sources, in order | `smallrye-graphql-schema-builder` | 2.18.5 | `aload_1 ; invokestatic Method getOperationAnnotation:(Lio/smallrye/graphql/schema/model/OperationType;)Lorg/jboss/jandex/DotName; ; astore_3 ; aload_2 ; iconst_5 ; anewarray class org/jboss/jandex/DotName ; dup ; iconst_0 ; aload_3 ; aastore ; dup ; iconst_1 ; getstatic Field io/smallrye/graphql/schema/Annotations.NAME:Lorg/jboss/jandex/DotName; ; aastore ; dup ; iconst_2 ; getstatic Field io/smallrye/graphql/schema/Annotations.JAKARTA_JSONB_PROPERTY:Lorg/jboss/jandex/DotName; ; aastore ; dup ; iconst_3 ; getstatic Field io/smallrye/graphql/schema/Annotations.JAVAX_JSONB_PROPERTY:Lorg/jboss/jandex/DotName; ; aastore ; dup ; iconst_4 ; getstatic Field io/smallrye/graphql/schema/Annotations.JACKSON_PROPERTY:Lorg/jboss/jandex/DotName; ; aastore ; invokevirtual Method io/smallrye/graphql/schema/Annotations.getOneOfTheseMethodAnnotationsValue:([Lorg/jboss/jandex/DotName;)Ljava/util/Optional; ; aload_0 ; aload_1 ; invokestatic Method getDefaultExecutionTypeName:(Lorg/jboss/jandex/MethodInfo;Lio/smallrye/graphql/schema/model/OperationType;)Ljava/lang/String; ; invokevirtual Method java/util/Optional.orElse:(Ljava/lang/Object;)Ljava/lang/Object; ; checkcast class java/lang/String ; areturn` |
| 2a | the annotation type each `Annotations` field names | `smallrye-graphql-schema-builder` | 2.0.0 | `QUERY = org.eclipse.microprofile.graphql.Query ; MUTATION = org.eclipse.microprofile.graphql.Mutation ; NAME = org.eclipse.microprofile.graphql.Name ; JAKARTA_JSONB_PROPERTY = jakarta.json.bind.annotation.JsonbProperty ; JAVAX_JSONB_PROPERTY = javax.json.bind.annotation.JsonbProperty ; JACKSON_PROPERTY = com.fasterxml.jackson.annotation.JsonProperty` |
| 2b | the annotation type each `Annotations` field names | `smallrye-graphql-schema-builder` | 2.18.5 | `QUERY = org.eclipse.microprofile.graphql.Query ; MUTATION = org.eclipse.microprofile.graphql.Mutation ; NAME = org.eclipse.microprofile.graphql.Name ; JAKARTA_JSONB_PROPERTY = jakarta.json.bind.annotation.JsonbProperty ; JAVAX_JSONB_PROPERTY = javax.json.bind.annotation.JsonbProperty ; JACKSON_PROPERTY = com.fasterxml.jackson.annotation.JsonProperty` |
| 3a | `OperationCreator.getDefaultExecutionTypeName` — the fallback | `smallrye-graphql-schema-builder` | 2.0.0 | `aload_0 ; invokevirtual Method org/jboss/jandex/MethodInfo.name:()Ljava/lang/String; ; astore_2 ; aload_1 ; getstatic Field io/smallrye/graphql/schema/model/OperationType.QUERY:Lio/smallrye/graphql/schema/model/OperationType; ; invokevirtual Method io/smallrye/graphql/schema/model/OperationType.equals:(Ljava/lang/Object;)Z ; ifne ; aload_1 ; getstatic Field io/smallrye/graphql/schema/model/OperationType.SUBSCRIPTION:Lio/smallrye/graphql/schema/model/OperationType; ; invokevirtual Method io/smallrye/graphql/schema/model/OperationType.equals:(Ljava/lang/Object;)Z ; ifeq ; getstatic Field io/smallrye/graphql/schema/helper/Direction.OUT:Lio/smallrye/graphql/schema/helper/Direction; ; aload_2 ; invokestatic Method io/smallrye/graphql/schema/helper/MethodHelper.getPropertyName:(Lio/smallrye/graphql/schema/helper/Direction;Ljava/lang/String;)Ljava/lang/String; ; astore_2 ; goto ; aload_1 ; getstatic Field io/smallrye/graphql/schema/model/OperationType.MUTATION:Lio/smallrye/graphql/schema/model/OperationType; ; invokevirtual Method io/smallrye/graphql/schema/model/OperationType.equals:(Ljava/lang/Object;)Z ; ifeq ; getstatic Field io/smallrye/graphql/schema/helper/Direction.IN:Lio/smallrye/graphql/schema/helper/Direction; ; aload_2 ; invokestatic Method io/smallrye/graphql/schema/helper/MethodHelper.getPropertyName:(Lio/smallrye/graphql/schema/helper/Direction;Ljava/lang/String;)Ljava/lang/String; ; astore_2 ; aload_2 ; areturn` |
| 3b | `OperationCreator.getDefaultExecutionTypeName` — the fallback | `smallrye-graphql-schema-builder` | 2.18.5 | `aload_0 ; invokevirtual Method org/jboss/jandex/MethodInfo.name:()Ljava/lang/String; ; astore_2 ; aload_1 ; getstatic Field io/smallrye/graphql/schema/model/OperationType.QUERY:Lio/smallrye/graphql/schema/model/OperationType; ; invokevirtual Method io/smallrye/graphql/schema/model/OperationType.equals:(Ljava/lang/Object;)Z ; ifne ; aload_1 ; getstatic Field io/smallrye/graphql/schema/model/OperationType.SUBSCRIPTION:Lio/smallrye/graphql/schema/model/OperationType; ; invokevirtual Method io/smallrye/graphql/schema/model/OperationType.equals:(Ljava/lang/Object;)Z ; ifeq ; getstatic Field io/smallrye/graphql/schema/helper/Direction.OUT:Lio/smallrye/graphql/schema/helper/Direction; ; aload_2 ; invokestatic Method io/smallrye/graphql/schema/helper/MethodHelper.getPropertyName:(Lio/smallrye/graphql/schema/helper/Direction;Ljava/lang/String;)Ljava/lang/String; ; astore_2 ; goto ; aload_1 ; getstatic Field io/smallrye/graphql/schema/model/OperationType.MUTATION:Lio/smallrye/graphql/schema/model/OperationType; ; invokevirtual Method io/smallrye/graphql/schema/model/OperationType.equals:(Ljava/lang/Object;)Z ; ifeq ; getstatic Field io/smallrye/graphql/schema/helper/Direction.IN:Lio/smallrye/graphql/schema/helper/Direction; ; aload_2 ; invokestatic Method io/smallrye/graphql/schema/helper/MethodHelper.getPropertyName:(Lio/smallrye/graphql/schema/helper/Direction;Ljava/lang/String;)Ljava/lang/String; ; astore_2 ; aload_2 ; areturn` |
| 4a | `MethodHelper`'s two transformations | `smallrye-graphql-schema-builder` | 2.0.0 | `aload_0 ; getstatic Field io/smallrye/graphql/schema/helper/Direction.IN:Lio/smallrye/graphql/schema/helper/Direction; ; invokevirtual Method io/smallrye/graphql/schema/helper/Direction.equals:(Ljava/lang/Object;)Z ; ifeq ; aload_1 ; invokestatic Method toNameFromSetter:(Ljava/lang/String;)Ljava/lang/String; ; areturn ; aload_0 ; getstatic Field io/smallrye/graphql/schema/helper/Direction.OUT:Lio/smallrye/graphql/schema/helper/Direction; ; invokevirtual Method io/smallrye/graphql/schema/helper/Direction.equals:(Ljava/lang/Object;)Z ; ifeq ; aload_1 ; invokestatic Method toNameFromGetter:(Ljava/lang/String;)Ljava/lang/String; ; areturn ; aload_1 ; areturn ; aload_0 ; ldc String get ; invokevirtual Method java/lang/String.startsWith:(Ljava/lang/String;)Z ; ifeq ; aload_0 ; invokevirtual Method java/lang/String.length:()I ; iconst_3 ; if_icmple ; aload_0 ; iconst_3 ; invokestatic Method hasCapitalAt:(Ljava/lang/String;I)Z ; ifeq ; aload_0 ; iconst_3 ; invokestatic Method removeAndLowerCase:(Ljava/lang/String;I)Ljava/lang/String; ; astore_0 ; goto ; aload_0 ; ldc String is ; invokevirtual Method java/lang/String.startsWith:(Ljava/lang/String;)Z ; ifeq ; aload_0 ; invokevirtual Method java/lang/String.length:()I ; iconst_2 ; if_icmple ; aload_0 ; iconst_2 ; invokestatic Method hasCapitalAt:(Ljava/lang/String;I)Z ; ifeq ; aload_0 ; iconst_2 ; invokestatic Method removeAndLowerCase:(Ljava/lang/String;I)Ljava/lang/String; ; astore_0 ; aload_0 ; areturn ; aload_0 ; ldc String set ; invokevirtual Method java/lang/String.startsWith:(Ljava/lang/String;)Z ; ifeq ; aload_0 ; invokevirtual Method java/lang/String.length:()I ; iconst_3 ; if_icmple ; aload_0 ; iconst_3 ; invokestatic Method hasCapitalAt:(Ljava/lang/String;I)Z ; ifeq ; aload_0 ; iconst_3 ; invokestatic Method removeAndLowerCase:(Ljava/lang/String;I)Ljava/lang/String; ; astore_0 ; aload_0 ; areturn ; aload_0 ; iload_1 ; invokevirtual Method java/lang/String.substring:(I)Ljava/lang/String; ; astore_0 ; aload_0 ; iconst_0 ; iconst_1 ; invokevirtual Method java/lang/String.substring:(II)Ljava/lang/String; ; invokevirtual Method java/lang/String.toLowerCase:()Ljava/lang/String; ; aload_0 ; iconst_1 ; invokevirtual Method java/lang/String.substring:(I)Ljava/lang/String; ; invokedynamic InvokeDynamic #0:makeConcatWithConstants:(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String; ; areturn` |
| 4b | `MethodHelper`'s two transformations | `smallrye-graphql-schema-builder` | 2.18.5 | `aload_0 ; getstatic Field io/smallrye/graphql/schema/helper/Direction.IN:Lio/smallrye/graphql/schema/helper/Direction; ; invokevirtual Method io/smallrye/graphql/schema/helper/Direction.equals:(Ljava/lang/Object;)Z ; ifeq ; aload_1 ; invokestatic Method toNameFromSetter:(Ljava/lang/String;)Ljava/lang/String; ; areturn ; aload_0 ; getstatic Field io/smallrye/graphql/schema/helper/Direction.OUT:Lio/smallrye/graphql/schema/helper/Direction; ; invokevirtual Method io/smallrye/graphql/schema/helper/Direction.equals:(Ljava/lang/Object;)Z ; ifeq ; aload_1 ; invokestatic Method toNameFromGetter:(Ljava/lang/String;)Ljava/lang/String; ; areturn ; aload_1 ; areturn ; aload_0 ; ldc String get ; invokevirtual Method java/lang/String.startsWith:(Ljava/lang/String;)Z ; ifeq ; aload_0 ; invokevirtual Method java/lang/String.length:()I ; iconst_3 ; if_icmple ; aload_0 ; iconst_3 ; invokestatic Method hasCapitalAt:(Ljava/lang/String;I)Z ; ifeq ; aload_0 ; iconst_3 ; invokestatic Method removeAndLowerCase:(Ljava/lang/String;I)Ljava/lang/String; ; astore_0 ; goto ; aload_0 ; ldc String is ; invokevirtual Method java/lang/String.startsWith:(Ljava/lang/String;)Z ; ifeq ; aload_0 ; invokevirtual Method java/lang/String.length:()I ; iconst_2 ; if_icmple ; aload_0 ; iconst_2 ; invokestatic Method hasCapitalAt:(Ljava/lang/String;I)Z ; ifeq ; aload_0 ; iconst_2 ; invokestatic Method removeAndLowerCase:(Ljava/lang/String;I)Ljava/lang/String; ; astore_0 ; aload_0 ; areturn ; aload_0 ; ldc String set ; invokevirtual Method java/lang/String.startsWith:(Ljava/lang/String;)Z ; ifeq ; aload_0 ; invokevirtual Method java/lang/String.length:()I ; iconst_3 ; if_icmple ; aload_0 ; iconst_3 ; invokestatic Method hasCapitalAt:(Ljava/lang/String;I)Z ; ifeq ; aload_0 ; iconst_3 ; invokestatic Method removeAndLowerCase:(Ljava/lang/String;I)Ljava/lang/String; ; astore_0 ; aload_0 ; areturn ; aload_0 ; iload_1 ; invokevirtual Method java/lang/String.substring:(I)Ljava/lang/String; ; astore_0 ; aload_0 ; iconst_0 ; iconst_1 ; invokevirtual Method java/lang/String.substring:(II)Ljava/lang/String; ; invokevirtual Method java/lang/String.toLowerCase:()Ljava/lang/String; ; aload_0 ; iconst_1 ; invokevirtual Method java/lang/String.substring:(I)Ljava/lang/String; ; invokedynamic InvokeDynamic #0:makeConcatWithConstants:(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String; ; areturn` |
| 5a | what `getPropertyName` returned, compiled and run | `smallrye-graphql-schema-builder` | 2.0.0 | `getOrders -> OUT orders, IN getOrders ; isActive -> OUT active, IN isActive ; setStatus -> OUT setStatus, IN status ; orders -> OUT orders, IN orders ; createOrder -> OUT createOrder, IN createOrder ; getX -> OUT x, IN getX ; get -> OUT get, IN get ; gettotal -> OUT gettotal, IN gettotal ; getURL -> OUT uRL, IN getURL` |
| 5b | what `getPropertyName` returned, compiled and run | `smallrye-graphql-schema-builder` | 2.18.5 | `getOrders -> OUT orders, IN getOrders ; isActive -> OUT active, IN isActive ; setStatus -> OUT setStatus, IN status ; orders -> OUT orders, IN orders ; createOrder -> OUT createOrder, IN createOrder ; getX -> OUT x, IN getX ; get -> OUT get, IN get ; gettotal -> OUT gettotal, IN gettotal ; getURL -> OUT uRL, IN getURL` |
| 6a | which MEMBER of each name source is read, and what counts as a value | `smallrye-graphql-schema-builder` | 2.0.0 | `aload_1 ; astore_2 ; aload_2 ; arraylength ; istore_3 ; iconst_0 ; istore ; iload ; iload_3 ; if_icmpge ; aload_2 ; iload ; aaload ; astore ; aload ; ifnull ; aload_0 ; aload ; invokevirtual Method hasValidMethodAnnotation:(Lorg/jboss/jandex/DotName;)Z ; ifeq ; aload_0 ; aload ; invokevirtual Method getStringValue:(Lorg/jboss/jandex/DotName;)Ljava/util/Optional; ; areturn ; iinc ; goto ; invokestatic Method java/util/Optional.empty:()Ljava/util/Optional; ; areturn ; aload_0 ; aload_1 ; invokevirtual Method containsKeyAndValidValue:(Lorg/jboss/jandex/DotName;)Z ; ifeq ; aload_0 ; aload_1 ; invokevirtual Method getAnnotation:(Lorg/jboss/jandex/DotName;)Lorg/jboss/jandex/AnnotationInstance; ; invokestatic Method isMethodAnnotation:(Lorg/jboss/jandex/AnnotationInstance;)Z ; ifeq ; iconst_1 ; goto ; iconst_0 ; ireturn ; aload_0 ; getfield Field annotationsMap:Ljava/util/Map; ; aload_1 ; invokeinterface InterfaceMethod java/util/Map.containsKey:(Ljava/lang/Object;)Z ; ifeq ; aload_0 ; getfield Field annotationsMap:Ljava/util/Map; ; aload_1 ; invokeinterface InterfaceMethod java/util/Map.get:(Ljava/lang/Object;)Ljava/lang/Object; ; checkcast class org/jboss/jandex/AnnotationInstance ; invokevirtual Method org/jboss/jandex/AnnotationInstance.value:()Lorg/jboss/jandex/AnnotationValue; ; ifnull ; iconst_1 ; goto ; iconst_0 ; ireturn ; aload_1 ; invokevirtual Method org/jboss/jandex/AnnotationInstance.value:()Lorg/jboss/jandex/AnnotationValue; ; astore_2 ; aload_2 ; ifnull ; aload_0 ; aload_2 ; invokevirtual Method getStringValue:(Lorg/jboss/jandex/AnnotationValue;)Ljava/util/Optional; ; areturn ; invokestatic Method java/util/Optional.empty:()Ljava/util/Optional; ; areturn ; aload_1 ; ifnull ; aload_1 ; invokevirtual Method org/jboss/jandex/AnnotationValue.asString:()Ljava/lang/String; ; astore_2 ; aload_2 ; ifnull ; aload_2 ; invokevirtual Method java/lang/String.isEmpty:()Z ; ifne ; aload_2 ; invokestatic Method java/util/Optional.of:(Ljava/lang/Object;)Ljava/util/Optional; ; areturn ; invokestatic Method java/util/Optional.empty:()Ljava/util/Optional; ; areturn` |
| 6b | which MEMBER of each name source is read, and what counts as a value | `smallrye-graphql-schema-builder` | 2.18.5 | `aload_1 ; astore_2 ; aload_2 ; arraylength ; istore_3 ; iconst_0 ; istore ; iload ; iload_3 ; if_icmpge ; aload_2 ; iload ; aaload ; astore ; aload ; ifnull ; aload_0 ; aload ; invokevirtual Method hasValidMethodAnnotation:(Lorg/jboss/jandex/DotName;)Z ; ifeq ; aload_0 ; aload ; invokevirtual Method getStringValue:(Lorg/jboss/jandex/DotName;)Ljava/util/Optional; ; areturn ; iinc ; goto ; invokestatic Method java/util/Optional.empty:()Ljava/util/Optional; ; areturn ; aload_0 ; aload_1 ; invokevirtual Method containsKeyAndValidValue:(Lorg/jboss/jandex/DotName;)Z ; ifeq ; aload_0 ; aload_1 ; invokevirtual Method getAnnotation:(Lorg/jboss/jandex/DotName;)Lorg/jboss/jandex/AnnotationInstance; ; invokestatic Method isMethodAnnotation:(Lorg/jboss/jandex/AnnotationInstance;)Z ; ifeq ; iconst_1 ; goto ; iconst_0 ; ireturn ; aload_0 ; getfield Field annotationsMap:Ljava/util/Map; ; aload_1 ; invokeinterface InterfaceMethod java/util/Map.containsKey:(Ljava/lang/Object;)Z ; ifeq ; aload_0 ; getfield Field annotationsMap:Ljava/util/Map; ; aload_1 ; invokeinterface InterfaceMethod java/util/Map.get:(Ljava/lang/Object;)Ljava/lang/Object; ; checkcast class org/jboss/jandex/AnnotationInstance ; invokevirtual Method org/jboss/jandex/AnnotationInstance.value:()Lorg/jboss/jandex/AnnotationValue; ; ifnull ; iconst_1 ; goto ; iconst_0 ; ireturn ; aload_1 ; invokevirtual Method org/jboss/jandex/AnnotationInstance.value:()Lorg/jboss/jandex/AnnotationValue; ; astore_2 ; aload_2 ; ifnull ; aload_0 ; aload_2 ; invokevirtual Method getStringValue:(Lorg/jboss/jandex/AnnotationValue;)Ljava/util/Optional; ; areturn ; invokestatic Method java/util/Optional.empty:()Ljava/util/Optional; ; areturn ; aload_1 ; ifnull ; aload_1 ; invokevirtual Method org/jboss/jandex/AnnotationValue.asString:()Ljava/lang/String; ; astore_2 ; aload_2 ; ifnull ; aload_2 ; invokevirtual Method java/lang/String.isEmpty:()Z ; ifne ; aload_2 ; invokestatic Method java/util/Optional.of:(Ljava/lang/Object;)Ljava/util/Optional; ; areturn ; invokestatic Method java/util/Optional.empty:()Ljava/util/Optional; ; areturn` |

## Verdict

1. **`OI-5` is CONFIRMED, and the prediction it recorded was right about the
   direction and wrong about the size.** Row 5, compiled and run against both
   jars: `getOrders -> OUT orders`. So `@Query List<Order> getOrders()` is
   served as `orders` while `microprofile-graphql.yml` publishes `getOrders`.
   A wrong address, at `resolved`/`compiler`, indistinguishable downstream from
   an observation.

2. **The rule is DIRECTION-DEPENDENT, and the direction is chosen by which
   operation annotation matched — which `OI-5` did not predict.** Row 3:
   `getDefaultExecutionTypeName` switches on the operation type and calls
   `getPropertyName(Direction.OUT, …)` for `QUERY` and `SUBSCRIPTION` and
   `Direction.IN` for `MUTATION`. Row 4: `OUT` strips `get` and `is`; `IN`
   strips `set`, and nothing else. Row 5 shows both halves:
   `setStatus -> OUT setStatus, IN status`. So `@Query` and `@Mutation` obey
   **different** rules, and a single uniform strip is wrong for one of them:
   `@Query String setUp()` is served as `setUp`, `@Mutation Order getOrder()`
   as `getOrder`.

3. **The strip's edges are measured, not assumed.** Row 4 shows a length test
   and a capitalisation test beside the `startsWith`, and row 5 exercises each:
   `get -> get` (too short), `gettotal -> gettotal` (no capital at the seam),
   `getX -> x` (one letter is enough), and `getURL -> uRL` — which is the case
   that distinguishes "lowercase the remainder" from "lowercase its FIRST
   CHARACTER", and it is the second. Any encoding of this rule that does not
   reproduce `uRL` is not this rule.

4. **A SECOND wrong address, which nothing in the register had recorded.** Rows
   1 and 2: before falling back at all, `getOperationName` consults FIVE
   sources in order — the operation annotation's own value, then
   `org.eclipse.microprofile.graphql.Name`, then
   `jakarta.json.bind.annotation.JsonbProperty`, then
   `javax.json.bind.annotation.JsonbProperty`, then
   `com.fasterxml.jackson.annotation.JsonProperty` — and takes the first with a
   value. `microprofile-graphql.yml` reads the first alone. So
   `@Query @Name("allOrders") List<Order> orders()` is served as `allOrders`
   while we publish `orders`. Registered as **`OI-35`**.

5. **Neither divergence is encoded, and that is a grammar finding rather than a
   decision.** `mapping.path_fallback` is ONE catalog-level word and this rule
   needs one per annotation; `mapping.path_from` names attributes on the
   matched annotation and these sources are four OTHER annotations on the same
   method. Encoding half of either makes a case that is right today newly
   wrong — `path_fallback: <strip get/is>` would break every `@Mutation` — and
   §8.1 rule 1 forbids an approximation that fits the examples in front of you.
   Both stay open, with the close conditions on their register rows, and
   `tests/application/test_endpoints.py::test_a_microprofile_query_naming_nothing_publishes_the_wrong_address`
   asserts the wrong output so the defect is a fact in the suite rather than a
   paragraph.

   **Superseded 2026-09-06, the same day, and the supersession is the finding
   working rather than the finding being wrong.** The grammar gap this verdict
   raised was the third of its class in one dispatch, which is GUIDELINES
   §13.8's stop rule; the design pass it triggered added
   `mapping.annotations[].path_fallback` with two measured accessor words and
   `mapping.path_from_siblings`, and both `OI-5` and `OI-35` are closed. The
   test named above is now
   `test_a_microprofile_operation_falls_back_to_the_name_smallrye_serves` and
   asserts `orders`. Nothing in rows 1-5 changed; what changed is that the
   vocabulary can now say what they measured. Question 6 was added at that
   point, for the reason its own row gives.

6. **What is right, and stays right.** An operation that names itself is read
   from its own `value` and reaches the address SmallRye serves: row 1 puts the
   operation annotation's value first, before every other source and before any
   transformation. That is why `path_fallback` was carried rather than dropped
   when `A-Mi9` was first written, and the reasoning survives measurement.

7. **Every one of the five sources is read from its member named `value`, and
   an EMPTY value stops the search rather than falling through.** Row 6,
   byte-identical at both versions, and the question exists because rows 1-2
   could not answer it: they name the annotation TYPES, and a catalog needs an
   ATTRIBUTE. `getOneOfTheseMethodAnnotationsValue` accepts a source only where
   `hasValidMethodAnnotation` holds — which is `containsKeyAndValidValue` (the
   annotation is in the map AND `AnnotationInstance.value()` is non-null) plus
   `isMethodAnnotation` — and then reads the name through `getStringValue`,
   which calls the same `AnnotationInstance.value()`.

   Two consequences a catalog needs, and one boundary. **(a)** The attribute is
   `value` on all five, Jackson's `@JsonProperty` included, which declares six
   members — so `path_from_siblings`' `arg: value` is measured rather than taken
   from the method's own name. **(b)** A source written EMPTY (`@Name("")`)
   returns `Optional.empty()` and does NOT fall through to the next source: the
   loop returns at the first NON-NULL value, and `getStringValue` tests
   `String.isEmpty` afterwards. `microprofile-graphql.yml` reproduces that
   without a rule of its own, because an empty attribute is a present one here
   too and composes an empty suffix, which is exactly what `path_fallback`
   answers. **The boundary:** row 6 shows the CALL and not jandex's contract for
   it. That `AnnotationInstance.value()` returns the member literally named
   `value` is jandex's API rather than something this probe executed; the
   `value(String)` sibling, which takes a member name and which this path never
   calls, is what makes the distinction visible rather than assumed.
