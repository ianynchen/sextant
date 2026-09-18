# CP-18 — JAX-RS API: verb annotations, `@Path`/`@Produces`/`@Consumes`, the custom-verb boundary, and two implementations' inheritance walk

**Question.** Groups B and C add sibling-annotation reads and inheritance rules to
`jakarta-jaxrs.yml` (and the framework catalogs built on it). Every one of those
rules assumes facts about the JAX-RS API jar that the design spec states but no
probe had measured against the jar itself: that the seven verb annotations
declare no attributes (so `path_from: []` at §3a is not an omission), that
`@Path`/`@Produces`/`@Consumes` are legal on `TYPE` and `METHOD` only, that the
custom-verb mechanism (`@HttpMethod`) is a distinct, `ANNOTATION_TYPE`-only
boundary, that `MediaType`'s constants are the literals the catalog's
`hint_annotations` cite, that Jersey's own resolver prefers the method's
`@Produces` over the class's, that two different implementations (Jersey,
RESTEasy classic) walk `class → interfaces → superclass` to decide whether an
implementor class is a JAX-RS root resource, and that the binding/`@Context`
vocabulary the catalog excludes from `path_from` is the framework's own list.
Row 8 settles the inheritance rule Group B/C's Word 3 is built on: JAX-RS §3.6's
own text.

**What this probe does not settle.** Nothing was deployed; no HTTP request was
dispatched. This records what the jars declare and what two implementations'
class files do, not what a container does at runtime beyond that. Row 5 and
row 6 each open one method; a rule that moved to a caller or a subclass between
versions is outside what that row can see (CP-17's boundary, unchanged).

**Version scope (§5.4).** `jakarta.ws.rs-api` 4.0.0 and 3.1.0, `javax.ws.rs-api`
2.1.1 (rows 1–4; three points across the `javax`→`jakarta` rename and the 3.x→4.x
major), `jersey-server` 4.0.0 (row 5), and `jersey-server` 4.0.0 plus
`resteasy-core` 6.2.12.Final (row 6, one implementation each side of the
rename). Every verdict below is bounded by those five artifacts.

## Environment

```
$ /opt/homebrew/opt/openjdk/bin/javap -version
26.0.2.1
```

`API40=~/.m2/repository/jakarta/ws/rs/jakarta.ws.rs-api/4.0.0/jakarta.ws.rs-api-4.0.0.jar`
`API31=~/.m2/repository/jakarta/ws/rs/jakarta.ws.rs-api/3.1.0/jakarta.ws.rs-api-3.1.0.jar`
`APIJAVAX=<scratchpad>/javax.ws.rs-api-2.1.1.jar` — both `~/.m2` coordinates
(`jakarta.ws.rs-api` 3.1.0 and 4.0.0) already carried a resolved jar; only the
`javax` 2.1.1 jar came from the design-review scratchpad.
`JERSEY=~/.m2/repository/org/glassfish/jersey/core/jersey-server/4.0.0/jersey-server-4.0.0.jar`
`RESTEASY=<scratchpad>/resteasy-core-6.2.12.jar`

## Rows

### 1a–1g — the seven verb annotations declare no attributes

**Command.**
```
javap -cp $API40 jakarta.ws.rs.GET jakarta.ws.rs.POST jakarta.ws.rs.PUT jakarta.ws.rs.DELETE jakarta.ws.rs.PATCH jakarta.ws.rs.HEAD jakarta.ws.rs.OPTIONS
```
repeated with `$API31` (same package) and with `$APIJAVAX` on the `javax.ws.rs`
package.

**Output** (4.0.0; 3.1.0 and the `javax` 2.1.1 jar produced the byte-identical
shape, only the package name differing on the `javax` run):
```
public interface jakarta.ws.rs.GET extends java.lang.annotation.Annotation {
}
public interface jakarta.ws.rs.POST extends java.lang.annotation.Annotation {
}
public interface jakarta.ws.rs.PUT extends java.lang.annotation.Annotation {
}
public interface jakarta.ws.rs.DELETE extends java.lang.annotation.Annotation {
}
public interface jakarta.ws.rs.PATCH extends java.lang.annotation.Annotation {
}
public interface jakarta.ws.rs.HEAD extends java.lang.annotation.Annotation {
}
public interface jakarta.ws.rs.OPTIONS extends java.lang.annotation.Annotation {
}
```

**Claim.** All seven verb annotations declare zero attributes, at 4.0.0, 3.1.0
and the `javax` 2.1.1 predecessor alike — `path_from: []` at spec §3a is the
jar's own shape, not an omission, and this holds across the `javax`→`jakarta`
rename and the 3.x→4.x major.

### 2a–2c — `@Path`, `@Produces`, `@Consumes`: `@Target` and `value()`

**Command.**
```
javap -v -cp $API40 jakarta.ws.rs.Path     | grep -A1 'annotation.Target(' ; javap -v -cp $API40 jakarta.ws.rs.Path     | grep 'public abstract'
javap -v -cp $API40 jakarta.ws.rs.Produces | grep -A1 'annotation.Target(' ; javap -v -cp $API40 jakarta.ws.rs.Produces | grep 'public abstract'
javap -v -cp $API40 jakarta.ws.rs.Consumes | grep -A1 'annotation.Target(' ; javap -v -cp $API40 jakarta.ws.rs.Consumes | grep 'public abstract'
```

**Output.**
```
Path:     value=[Ljava/lang/annotation/ElementType;.TYPE,Ljava/lang/annotation/ElementType;.METHOD]
          public abstract java.lang.String value();
Produces: value=[Ljava/lang/annotation/ElementType;.TYPE,Ljava/lang/annotation/ElementType;.METHOD]
          public abstract java.lang.String[] value();
Consumes: value=[Ljava/lang/annotation/ElementType;.TYPE,Ljava/lang/annotation/ElementType;.METHOD]
          public abstract java.lang.String[] value();
```

**Claim.** `@Target({TYPE, METHOD})` on all three, exactly as the spec's word 2
assumes. `@Path.value()` is a scalar `String`; `@Produces.value()` and
`@Consumes.value()` are both `String[]`.

### 3 — the custom-verb boundary: `@GET`'s `@HttpMethod("GET")` and `@HttpMethod` itself

**Command.**
```
javap -v -cp $API40 jakarta.ws.rs.GET        | grep -A2 'HttpMethod('
javap -v -cp $API40 jakarta.ws.rs.HttpMethod
```

**Output (relevant excerpts).**
```
jakarta.ws.rs.HttpMethod(
  value="GET"
)
```
```
public abstract java.lang.String value();
    descriptor: ()Ljava/lang/String;
RuntimeVisibleAnnotations:
  0: #28(#23=[e#29.#30])
    java.lang.annotation.Target(
      value=[Ljava/lang/annotation/ElementType;.ANNOTATION_TYPE]
    )
  1: #31(#23=e#32.#33)
    java.lang.annotation.Retention(
      value=Ljava/lang/annotation/RetentionPolicy;.RUNTIME
    )
```

**Claim.** `@GET` (and by the same shape the other six verbs) is itself
meta-annotated `@HttpMethod("GET")`; `@HttpMethod` declares one attribute,
`value(): String`, and is `@Target(ANNOTATION_TYPE)`-only, `@Retention(RUNTIME)`
— it cannot be placed on a class or method directly, only on another
annotation type. This is the boundary the design spec calls the custom-verb
mechanism (§3d): a hand-rolled verb annotation is any `@Target(ANNOTATION_TYPE)`
annotation itself meta-annotated `@HttpMethod`, and the seven built-in verbs are
the framework's own instances of exactly that shape.

### 4 — `MediaType` constants

**Command.**
```
javap -constants -cp $API40 jakarta.ws.rs.core.MediaType | grep -E 'SERVER_SENT_EVENTS =|APPLICATION_JSON ='
```

**Output.**
```
public static final java.lang.String APPLICATION_JSON = "application/json";
public static final java.lang.String SERVER_SENT_EVENTS = "text/event-stream";
```

**Claim.** `MediaType.APPLICATION_JSON` is the literal `"application/json"` and
`MediaType.SERVER_SENT_EVENTS` is the literal `"text/event-stream"` — the two
string constants any `hint_annotations` or `@Produces` comparison in the
catalogs must match against.

### 5 — Jersey: method-`@Produces`-over-class

**Command.**
```
javap -c -p -cp $JERSEY org.glassfish.jersey.server.model.IntrospectionModeller | grep -B2 -A12 resolveProducedTypes
```

**Output.**
```
private static java.util.List<jakarta.ws.rs.core.MediaType> resolveProducedTypes(org.glassfish.jersey.server.model.AnnotatedMethod, java.util.List<jakarta.ws.rs.core.MediaType>);
    Code:
         0: aload_0
         1: ldc           #55                 // class jakarta/ws/rs/Produces
         3: invokevirtual #244                // Method org/glassfish/jersey/server/model/AnnotatedMethod.isAnnotationPresent:(Ljava/lang/Class;)Z
         6: ifeq          22
         9: aload_0
        10: ldc           #55                 // class jakarta/ws/rs/Produces
        12: invokevirtual #321                // Method org/glassfish/jersey/server/model/AnnotatedMethod.getAnnotation:(Ljava/lang/Class;)Ljava/lang/annotation/Annotation;
        15: checkcast     #55                 // class jakarta/ws/rs/Produces
        18: invokestatic  #57                 // Method extractMediaTypes:(Ljakarta/ws/rs/Produces;)Ljava/util/List;
        21: areturn
        22: aload_1
```
(bytecode offset 22 falls through to the class-level default list passed in as
the second parameter when the method carries no `@Produces` of its own.)

**Claim.** `resolveProducedTypes` returns the method's own `@Produces` when
`isAnnotationPresent` is true (offsets 1–21); only when the method carries
none does it fall back to the class default (offset 22 onward) — confirming
spec §3b word 2, method-over-class, as Jersey's own resolution order.

### 6a/6b — Jersey and RESTEasy classic: `class → interfaces → superclass`

**Command.**
```
javap -c -p -cp $JERSEY org.glassfish.jersey.server.model.internal.ModelHelper | sed -n '/getAnnotatedResourceClass/,/^$/p'
javap -c -p -cp $RESTEASY org.jboss.resteasy.util.AnnotationResolver | sed -n '/getClassWithAnnotation/,/^$/p'
```

**Output — Jersey `ModelHelper.getAnnotatedResourceClass`.**
```
public static java.lang.Class<?> getAnnotatedResourceClass(java.lang.Class<?>);
    Code:
         0: aconst_null
         ...
         4: aload_2
         5: ldc           #1                  // class jakarta/ws/rs/Path
         7: invokevirtual #3                  // Method java/lang/Class.isAnnotationPresent:(Ljava/lang/Class;)Z
        10: ifeq          15
        13: aload_2
        14: areturn
        15: aload_1
        16: ifnonnull     66
        19: aload_2
        20: invokevirtual #9                  // Method java/lang/Class.getInterfaces:()[Ljava/lang/Class;
        ...
        44: aload         6
        46: ldc           #1                  // class jakarta/ws/rs/Path
        48: invokevirtual #3                  // Method java/lang/Class.isAnnotationPresent:(Ljava/lang/Class;)Z
        ...
        66: aload_2
        67: invokevirtual #13                 // Method java/lang/Class.getSuperclass:()Ljava/lang/Class;
        70: dup
        71: astore_2
        72: ifnonnull     4
```

**Output — RESTEasy classic `AnnotationResolver.getClassWithAnnotation`.**
```
public static java.lang.Class<?> getClassWithAnnotation(java.lang.Class<?>, java.lang.Class<? extends java.lang.annotation.Annotation>);
    Code:
         0: aload_0
         1: aload_1
         2: invokevirtual #7                  // Method java/lang/Class.isAnnotationPresent:(Ljava/lang/Class;)Z
         5: ifeq          10
         8: aload_0
         9: areturn
        10: aload_0
        11: invokevirtual #13                 // Method java/lang/Class.getInterfaces:()[Ljava/lang/Class;
        ...
        33: aload         5
        35: aload_1
        36: invokevirtual #7                  // Method java/lang/Class.isAnnotationPresent:(Ljava/lang/Class;)Z
        ...
        51: aload_0
        52: invokevirtual #17                 // Method java/lang/Class.getSuperclass:()Ljava/lang/Class;
```

**Claim.** Both implementations check the class itself, then `getInterfaces()`,
then loop up `getSuperclass()`, in that order — confirming spec §3b word 3: a
`@Path` interface or a `@Path` superclass makes the implementing/subclassing
class a root resource, independently measured in two unrelated implementations
(Jersey's reflection-based model builder, RESTEasy classic's annotation
resolver).

### 7 — the binding-annotation and `@Context`-injectable vocabulary

**Command.**
```
unzip -l $API40 | grep -E 'rs/(Path|Query|Header|Cookie|Form|Matrix|Bean)Param|DefaultValue|core/Context|container/Suspended'
unzip -l $API40 | grep -E 'core/(UriInfo|HttpHeaders|Request|SecurityContext|Configuration|Application)|ext/Providers|container/ResourceContext|sse/(Sse|SseEventSink)'
```

**Output.**
```
      455  jakarta/ws/rs/BeanParam.class
      490  jakarta/ws/rs/CookieParam.class
      492  jakarta/ws/rs/DefaultValue.class
      486  jakarta/ws/rs/FormParam.class
      490  jakarta/ws/rs/HeaderParam.class
      490  jakarta/ws/rs/MatrixParam.class
      486  jakarta/ws/rs/PathParam.class
      488  jakarta/ws/rs/QueryParam.class
      438  jakarta/ws/rs/container/Suspended.class
      456  jakarta/ws/rs/core/Context.class

      374  jakarta/ws/rs/container/ResourceContext.class
      890  jakarta/ws/rs/core/Application.class
     1299  jakarta/ws/rs/core/Configuration.class
     3245  jakarta/ws/rs/core/HttpHeaders.class
      808  jakarta/ws/rs/core/Request.class
      525  jakarta/ws/rs/core/SecurityContext.class
     1284  jakarta/ws/rs/core/UriInfo.class
     1288  jakarta/ws/rs/ext/Providers.class
     1348  jakarta/ws/rs/sse/Sse.class
      445  jakarta/ws/rs/sse/SseEventSink.class
```

**Claim.** All eight binding-param annotations, `@DefaultValue`, `@Context`
and `@Suspended` are present at these exact fqns in the 4.0.0 jar — the
`bound_by` set. All nine `@Context`-injectable types JAX-RS §9.2 names
(`UriInfo`, `HttpHeaders`, `Request`, `SecurityContext`, `Configuration`,
`Application`, `Providers`, `ResourceContext`, `Sse`/`SseEventSink`) resolve to
real classes in the same jar — the `excludes` set `jakarta-jaxrs.yml` needs so a
`@Context UriInfo` parameter is not mistaken for a path variable.

### 8 — JAX-RS §3.6, the all-or-nothing inheritance rule

**Source.** Quoted, as already cited in
`docs/superpowers/specs/2026-09-18-sibling-reads-and-attribute-conditions-design.md:263-264`,
from the JAX-RS specification text:

> "if a subclass or implementation method has any JAX-RS annotations then all of the
> annotations on the superclass or interface method are ignored."

**Claim.** JAX-RS §3.6 states an all-or-nothing rule per method: once a
subclass/implementor method carries ANY JAX-RS annotation of its own, none of
the ancestor method's annotations apply to it — not a per-annotation merge.
This is the rule Group B/C's Word 3 (`inherited_rows_over`'s
"only when the target method carries none of the catalog's annotations of its
own") implements for JAX-RS-style catalogs, and it is the rule CP-19 row 6 asks
whether Quarkus REST follows or diverges from.

## Verdict

1. Rows 1a–1g close spec §3a: the seven verb annotations are attribute-free at
   every version read, `javax` through `jakarta` 4.0.0.
2. Rows 2a–2c close word 2 of spec §3: `@Path`/`@Produces`/`@Consumes` are all
   `@Target({TYPE, METHOD})`; `@Path` is scalar, `@Produces`/`@Consumes` are
   arrays.
3. Row 3 closes the custom-verb boundary (§3d): `@HttpMethod` is the
   `ANNOTATION_TYPE`-only meta-annotation that marks a verb annotation, and the
   seven built-ins are its own instances.
4. Row 4 gives the two `MediaType` literals the catalogs' hint/produces logic
   compares against.
5. Row 5 confirms Jersey's method-over-class `@Produces` resolution
   (spec §3b word 2) directly in its bytecode.
6. Rows 6a/6b confirm spec §3b word 3 (interface/superclass `@Path` makes an
   implementor a root resource) in two independent implementations.
7. Row 7 gives the full `bound_by`/`excludes` vocabulary for
   `jakarta-jaxrs.yml`, every class confirmed present in the 4.0.0 jar.
8. Row 8 is the JAX-RS §3.6 text Group B/C's Word 3 implements — all-or-nothing
   per method, not a per-annotation merge. This is the baseline CP-19 row 6
   measures Quarkus REST against.

No claim in this probe came back false against the jars read. `measured:
2026-09-18` for every row above.
