# CP-19 — Quarkus REST's scanner and endpoint indexer: root-resource gates, the SSE hint, context types, parameter-container order, the relocation, and the inheritance merge

**Question.** `quarkus-rest.yml` rides on Group B/C's Word 3 (sibling-annotation
inheritance) and the `hint_annotations`/`implicit_bindings` additions Group B/C
add on top of `jakarta-jaxrs.yml`. Six facts about Quarkus's own build-time
scanner and endpoint indexer were assumed in the design spec and not yet
measured against the 3.39.4 sources: that the class-`@Path`/interface-`@Path`/
method-only-HTTP-verb root-resource gate (R1) is unchanged from the design
review's reading; that the SSE default-produces hint reads
`@RestStreamElementType` then `@RestSseElementType`; that Quarkus's own
`DEFAULT_CONTEXT_TYPES` plus the Vert.x additions form the `excludes` set;
that the parameter-resolution order is annotation → context type → container
type → path-variable name → body; that the artifact relocated from
`quarkus-resteasy-reactive` to `quarkus-rest`, and at which version; and,
row 6, whether Quarkus's `AnnotationStore` merges JAX-RS annotations across an
interface/implementor pair the way §3.6 all-or-nothing does, or some other
way.

**What this probe does not settle.** Nothing was compiled or deployed against a
running Quarkus application; no HTTP request was dispatched. Rows are read
from Quarkus 3.39.4's own processor/indexer sources and from the compiled
3.39.4 deployment jar's bytecode, both already staged in the scratchpad from
the design review. Row 6 opens exactly the methods it names — a rule that
moved to a caller between versions is outside what it can see, CP-17's bound
unchanged.

**Version scope (§5.4).** `io.quarkus:quarkus-rest`, `quarkus-rest-deployment`
and `io.quarkus.resteasy.reactive:resteasy-reactive-common` **3.39.4** for the
source/bytecode rows (1–4, 6); the relocation question (row 5) is read against
Maven Central's own metadata for both `io.quarkus:quarkus-rest` and
`io.quarkus:quarkus-resteasy-reactive`, unscoped by version because it asks
which versions of the COORDINATE exist, not a single jar's behaviour. Every
source-code verdict below is bounded to 3.39.4.

## Environment

Sources and jars from the scratchpad (already staged from the design review):
`ResteasyReactiveScanner.java`, `EndpointIndexer.java`,
`ResteasyReactiveDotNames.java`, `ParamContainerScanner.java` (=
`ResteasyReactiveParameterContainerScanner.java`); `quarkus-rest-3.39.4.jar`,
`quarkus-rest-deployment-3.39.4.jar`, `rr-common-3.39.4.jar`,
`rr-common-processor-3.39.4.jar`.

## Rows

### 1 — root-resource gate: class `@Path`, `@Path` interface implementors, HTTP-verb-only sub-resources, client interfaces

**Command.**
```
sed -n '232,260p' ResteasyReactiveScanner.java
sed -n '296,330p' ResteasyReactiveScanner.java
sed -n '340,395p' ResteasyReactiveScanner.java
```

**Output (excerpted, line numbers from the file).**
```
247   for (AnnotationInstance annotation : allPaths) {
248       if (annotation.target().kind() == AnnotationTarget.Kind.CLASS) {
249           ClassInfo clazz = annotation.target().asClass();
250           if (!Modifier.isInterface(clazz.flags())) {
251               scannedResources.put(clazz.name(), clazz);
252               scannedResourcePaths.put(clazz.name(), annotation.value().asString());
253           } else {
254               pathInterfaces.put(clazz.name(), annotation.value().asString());
```
```
309   for (Map.Entry<DotName, String> i : pathInterfaces.entrySet()) {
310       for (ClassInfo clazz : index.getAllKnownImplementors(i.getKey())) {
311           if (!Modifier.isAbstract(clazz.flags())) {
312               if ((clazz.enclosingClass() == null || Modifier.isStatic(clazz.flags())) &&
313                       clazz.enclosingMethod() == null) {
314                   if (!scannedResources.containsKey(clazz.name())) {
315                       scannedResources.put(clazz.name(), clazz);
316                       scannedResourcePaths.put(clazz.name(), i.getValue());
```
```
344   // for clients, it is also enough to only have @GET, @POST, etc on methods and no PATH whatsoever
345   Set<DotName> methodAnnotations = httpAnnotationToMethod.keySet();
346   for (DotName methodAnnotation : methodAnnotations) {
347       for (AnnotationInstance methodAnnotationInstance : index.getAnnotations(methodAnnotation)) {
348           if (methodAnnotationInstance.target().kind() == AnnotationTarget.Kind.METHOD) {
349               MethodInfo annotatedMethod = methodAnnotationInstance.target().asMethod();
350               ClassInfo classWithJaxrsMethod = annotatedMethod.declaringClass();
351               if (Modifier.isAbstract(annotatedMethod.flags())
352                       && Modifier.isInterface(classWithJaxrsMethod.flags())
353                       && !clientInterfaces.containsKey(classWithJaxrsMethod.name())) {
354                   clientInterfaces.put(classWithJaxrsMethod.name(), "");
...
361   //now index possible sub resources. These are all classes that have method annotations
362   //that are not annotated @Path
...
382   Map<DotName, ClassInfo> possibleSubResources = new HashMap<>();
```

**Claim.** Confirmed at 3.39.4, matching the design review's R1 reading exactly:
a class-level `@Path` registers a root resource directly (247–254); a `@Path`
INTERFACE's non-abstract, non-inner implementors are registered as root
resources under the interface's own path (309–316); a method carrying only an
HTTP-verb annotation (no class `@Path`) with an interface, abstract declaring
class marks that class a `clientInterface` (344–354, "no PATH whatsoever");
otherwise such a class becomes a `possibleSubResource` (361–390). The gate
stands unchanged; R1 holds.

### 2 — the SSE default-produces hint: `@RestStreamElementType` then `@RestSseElementType`

**Command.**
```
sed -n '710,740p' EndpointIndexer.java
sed -n '860,870p' EndpointIndexer.java
```

**Output.**
```
714   String streamElementType = basicResourceClassInfo.getStreamElementType();
715   String streamElementTypeInMethod = getStreamAnnotationValue(currentMethodInfo);
716   if (streamElementTypeInMethod != null) {
717       streamElementType = streamElementTypeInMethod;
718   }
719
720   String[] produces = extractProducesConsumesValues(getAnnotationStore().getAnnotation(currentMethodInfo, PRODUCES));
721   if (((produces == null) || (produces.length == 0)) && (streamElementType != null)) {
722       // when @RestStreamElementType is used, we automatically determine SSE as the @Produces MediaType
723       produces = new String[] { MediaType.SERVER_SENT_EVENTS };
724   } else if (produces == null || produces.length == 0) {
725       // use the @Produces annotation at class level if exists
726       produces = basicResourceClassInfo.getProduces();
727   }
```
```
861   private String getStreamAnnotationValue(AnnotationTarget target) {
862       String value = getAnnotationValueAsString(target, REST_STREAM_ELEMENT_TYPE);
863       if (value == null) {
864           value = getAnnotationValueAsString(target, REST_SSE_ELEMENT_TYPE);
865       }
866       return value;
867   }
```

**Claim.** Element type comes from the method (`getStreamAnnotationValue`) and
falls back to the class's stream element type (714–717); when no `@Produces`
is declared and a stream element type is present, `produces` defaults to
`SERVER_SENT_EVENTS` (720–723); otherwise it falls back to the class-level
`@Produces` (725). `getStreamAnnotationValue` reads `REST_STREAM_ELEMENT_TYPE`
first and `REST_SSE_ELEMENT_TYPE` only when the first is absent (862–865) —
this is `hint_annotations`, and both fqns (`@RestStreamElementType` /
`@RestSseElementType`) are the two the catalog must name, in that priority
order.

### 3 — `DEFAULT_CONTEXT_TYPES` and the Vert.x additions `addContextTypes` brings in

**Command.**
```
sed -n '153,158p' EndpointIndexer.java
grep -rl addContextTypes dep-classes         # dep-classes = quarkus-rest-deployment-3.39.4.jar, unzipped
javap -c -p -cp dep-classes io.quarkus.resteasy.reactive.server.deployment.ResteasyReactiveProcessor | grep -B4 -A1 addContextTypes
javap -c -p -cp dep-classes io.quarkus.resteasy.reactive.server.deployment.ResteasyReactiveProcessor | sed -n '/private.*additionalContextTypes/,/areturn/p'
```

**Output.**
```
153   private static final Set<DotName> DEFAULT_CONTEXT_TYPES = Set.of(URI_INFO, HTTP_HEADERS, REQUEST, SECURITY_CONTEXT,
154           PROVIDERS, RESOURCE_CONTEXT, CONFIGURATION, SSE,
155           SSE_EVENT_SINK,
156           // extras
157           SERVER_REQUEST_CONTEXT,
158           DotName.createSimple("org.jboss.resteasy.reactive.server.SimpleResourceInfo"), //TODO: fixme
```
The one caller of `addContextTypes` is
`io.quarkus.resteasy.reactive.server.deployment.ResteasyReactiveProcessor`:
```
364: invokevirtual  Method QuarkusServerEndpointIndexer$Builder.addContextTypes:(Ljava/util/Collection;)EndpointIndexer$Builder;
```
its argument comes from `additionalContextTypes(List<ContextTypeBuildItem>)`,
which unions the incoming `ContextTypeBuildItem`s with a static
`CONTEXT_TYPES` field. That field's initializer (`static {}`, disassembled):
```
17: ldc  class io/vertx/core/http/HttpServerRequest
20: invokevirtual Class.getName:()String
23: invokestatic  DotName.createSimple:(String)DotName
26: ldc  class io/vertx/core/http/HttpServerResponse
...  DotName.createSimple
35: ldc  class io/vertx/ext/web/RoutingContext
...  DotName.createSimple
44: invokestatic  Set.of:(Object,Object,Object)Set;
47: putstatic     Field CONTEXT_TYPES:Set;
```

**Claim.** `DEFAULT_CONTEXT_TYPES` (JAX-RS `@Context` types plus Quarkus's own
`ServerRequestContext` and `SimpleResourceInfo`) is the base set
`EndpointIndexer` itself carries. `ResteasyReactiveProcessor` (the ONLY caller
of `addContextTypes` in the deployment jar) adds exactly three Vert.x types —
`io.vertx.core.http.HttpServerRequest`, `io.vertx.core.http.HttpServerResponse`,
`io.vertx.ext.web.RoutingContext` — as its always-present `CONTEXT_TYPES`
constant, merged with whatever `ContextTypeBuildItem`s other extensions
contribute. These three Vert.x fqns are the `excludes` addition
`quarkus-rest.yml` needs beyond `jakarta-jaxrs.yml`'s own `@Context` list.

### 4 — parameter-resolution order and the container rule

**Command.**
```
sed -n '1380,1416p' EndpointIndexer.java
sed -n '14,31p' ParamContainerScanner.java
sed -n '265,268p' ResteasyReactiveDotNames.java
```

**Output.**
```
1386  } else {
1387      // auto context parameters
1388      if (!field
1389              && paramType.kind() == Kind.CLASS
1390              && isContextType(paramType.asClassType())) {
1391          // no name required
1392          builder.setType(ParameterType.CONTEXT);
1393      } else if (!field
1394              && paramType.kind() == Kind.CLASS
1395              && isParameterContainerType(paramType.asClassType())) {
1396          // auto @BeanParam/@MultipartForm parameters
1397          builder.setType(ParameterType.BEAN);
1398      } else if (!field && pathParameters.contains(sourceName)) {
1399          builder.setName(sourceName);
1400          builder.setType(ParameterType.PATH);
1401          builder.setErrorLocation(builder.getRawErrorLocation()
1402              + " (this parameter name matches the @Path parameter name, so it has been implicitly assumed to be an @PathParam and not the request body)",
1403              builder.getErrorLocationParameters());
1404          convertible = true;
...
1408      } else {
1409          //un-annotated field
...
1412          builder.setName(sourceName);
1413          builder.setType(ParameterType.BODY);
1414      }
1415  }
```
(This block is reached only once an explicit binding annotation —
`@PathParam`/`@QueryParam`/etc — has already been checked earlier in the same
method and found absent, so the full order this method implements is:
explicit binding annotation → context type → container type → path-variable
name match → body.)
```
19   for (DotName fieldAnnotation : ResteasyReactiveDotNames.JAX_RS_ANNOTATIONS_FOR_FIELDS) {
20       for (AnnotationInstance annotationInstance : index.getAnnotations(fieldAnnotation)) {
21           // these annotations can be on fields or properties
22           if (annotationInstance.target().kind() == Kind.FIELD) {
23               ClassInfo klass = annotationInstance.target().asField().declaringClass();
24               res.add(klass.name());
25           } else if (annotationInstance.target().kind() == Kind.METHOD) {
26               ClassInfo klass = annotationInstance.target().asMethod().declaringClass();
27               res.add(klass.name());
28           }
29       }
30   }
```
```
265  public static final Set<DotName> JAX_RS_ANNOTATIONS_FOR_FIELDS = new HashSet<>(
266          Arrays.asList(BEAN_PARAM, MULTI_PART_FORM_PARAM, PATH_PARAM, QUERY_PARAM, HEADER_PARAM, FORM_PARAM, MATRIX_PARAM,
267                  COOKIE_PARAM, REST_PATH_PARAM, REST_QUERY_PARAM, REST_HEADER_PARAM, REST_FORM_PARAM, REST_MATRIX_PARAM,
268                  COOKIE_PARAM_from_REST_COOKIE_PARAM)); -- see note
```

**Claim.** Once no explicit binding annotation applies, a parameter is
resolved in this order: **context type → container (bean-param) type →
path-variable name match → body** (1388–1414), confirming the order the spec
names, with the message quoted verbatim at 1401–1403. `ParamContainerScanner`
(`scanParameterContainers`) discovers a container type by finding ANY class
that declares a field or a bean-property setter/getter carrying one of the
`JAX_RS_ANNOTATIONS_FOR_FIELDS` set (14–31); that set includes the standard
eight `@*Param` annotations plus `@Context`, `@DefaultValue`, `@Suspended` and
Quarkus's own `@Rest*Param` aliases (265–268) — this is the `implicit_bindings`
container rule and the Quarkus-specific additions to `bound_by`.

### 5 — the relocation: `quarkus-resteasy-reactive` → `quarkus-rest`

**Command.**
```
curl -s https://repo1.maven.org/maven2/io/quarkus/quarkus-rest/maven-metadata.xml | grep -o '<version>3\.[0-9]*\.0</version>' | head -3
curl -s https://repo1.maven.org/maven2/io/quarkus/quarkus-resteasy-reactive/maven-metadata.xml | grep -o '<version>3\.[0-9]*\.[0-9]*</version>' | tail -5
cat <scratchpad>/quarkus-resteasy-reactive-3.15.7.pom
```

**Output.**
```
quarkus-rest earliest versions: 3.9.0.CR1, 3.9.0.CR2, 3.9.0
quarkus-resteasy-reactive last versions: ...3.14.4, 3.15.0, 3.15.1 .. 3.15.7
```
`quarkus-resteasy-reactive-3.15.7.pom` (the LAST version ever published under
that coordinate):
```xml
<distributionManagement>
    <relocation>
        <groupId>io.quarkus</groupId>
        <artifactId>quarkus-rest</artifactId>
        <version>${project.version}</version>
        <message>Update the artifactId in your project build file. Refer to
        https://github.com/quarkusio/quarkus/wiki/Migration-Guide-3.9 for more
        information.</message>
    </relocation>
</distributionManagement>
```

**Claim.** `quarkus-rest` first exists at **3.9.0** (`.CR1`/`.CR2`/GA); every
`quarkus-resteasy-reactive` release up to and including its LAST published
version, **3.15.7**, carries an explicit Maven relocation POM pointing at
`quarkus-rest` — the migration guide the POM cites is titled for 3.9. Both
coordinates' `detect.coordinates` in `quarkus-rest.yml` should therefore treat
3.9.0 as the boundary: `quarkus-resteasy-reactive` before it, `quarkus-rest`
at and after.

### 6 — `AnnotationStore`, and whether an implementor's own `@Produces` still inherits the interface's `@GET`

**Command.**
```
grep -n "AnnotationStore\|getAnnotation(" EndpointIndexer.java | head -30
javap -c -p -cp rr-common-processor-classes org.jboss.resteasy.reactive.common.processor.transformation.AnnotationStore
sed -n '456,530p' EndpointIndexer.java     # collectEndpoints
sed -n '1067,1076p' EndpointIndexer.java   # getInheritableAnnotation
```

**Output — `AnnotationStore` itself is a thin Jandex delegate.**
```
public org.jboss.jandex.AnnotationInstance getAnnotation(AnnotationTarget, DotName);
    Code:
         0: aload_0
         1: getfield      #23      // Field delegate:Lorg/jboss/jandex/AnnotationOverlay;
         4: aload_1
         5: invokeinterface       // AnnotationTarget.asDeclaration:()Declaration;
        10: aload_2
        11: invokeinterface       // AnnotationOverlay.annotation:(Declaration,DotName)AnnotationInstance;
        16: areturn
```
`getAnnotation(target, name)` looks up the annotation declared on THAT
declaration alone via the Jandex `AnnotationOverlay` — no class-hierarchy walk
happens inside `AnnotationStore` itself.

**Output — `EndpointIndexer.collectEndpoints`, the actual hierarchy walk (line
numbers from the file).**
```
476   for (DotName httpMethod : httpAnnotationToMethod.keySet().stream().sorted().toList()) {
477       List<MethodInfo> methods = currentClassInfo.methods();
478       for (MethodInfo info : methods) {
479           AnnotationInstance annotation = annotationStore.getAnnotation(info, httpMethod);
480           if (annotation != null) {
...
486                   seenMethods.add(descriptor);
487                   ret.add(new FoundEndpoint(currentClassInfo, classNameBindings, info, httpMethod));
...
512   DotName superClassName = currentClassInfo.superName();
513   if (superClassName != null && !superClassName.equals(OBJECT)) {
514       ClassInfo superClass = index.getClassByName(superClassName);
515       if (superClass != null) {
516           ret.addAll(collectEndpoints(superClass, actualEndpointInfo, seenMethods, ...));
520   List<DotName> interfaces = currentClassInfo.interfaceNames();
521   for (DotName i : interfaces) {
522       ClassInfo superClass = index.getClassByName(i);
523       if (superClass != null) {
524           ret.addAll(collectEndpoints(superClass, actualEndpointInfo, seenMethods, ...));
```
`getInheritableAnnotation` (1068–1075) — method-then-declaring-CLASS fallback
— exists but is used ONLY for `@Blocking`/`@NonBlocking`/`@RunOnVirtualThread`
(lines 881–923); it is never called for `PATH`/`PRODUCES`/`CONSUMES` or any
HTTP-verb annotation.

**Claim (settling row 6).** Quarkus REST does **not** implement JAX-RS §3.6's
all-or-nothing rule, and it does not do a full per-annotation merge either. It
does a third thing: `collectEndpoints` recurses `currentClassInfo` →
superclass → every interface (512–524), and at EACH level independently scans
that class's OWN declared methods for the searched httpMethod annotation
(478–480). The FIRST class in that `self, superclass, interfaces…` order whose
OWN method declaration carries the annotation wins and is deduplicated by
method descriptor (`seenMethods`, 481–487) — but the `FoundEndpoint` it
creates carries THAT WINNING CLASS's `MethodInfo` as `endpoint.methodInfo`
(487), and every other endpoint-shaping annotation (`@Produces`/`@Consumes`/
`@Path`, e.g. line 720's `getAnnotationStore().getAnnotation(currentMethodInfo,
PRODUCES)`) is then read off that SAME `MethodInfo` — never off the
implementor's own override.

Concretely: if an interface method carries `@GET` and an implementing class's
OVERRIDE of that method carries only `@Produces` (no `@GET` of its own), the
implementor's own method is never added to `seenMethods` at line 486 (its scan
at the implementor level finds no `@GET` on it), so `collectEndpoints`
recurses into the interface, finds `@GET` there, and registers the endpoint
with the INTERFACE's `MethodInfo`. The implementor's own `@Produces` is then
never read for that endpoint — `getAnnotation(currentMethodInfo, PRODUCES)`
is called against the interface's method, not the implementor's override — so
the produces value falls through to the interface method's own `@Produces`
(none, here) or the class-level default, silently dropping the implementor's
override. This is the OPPOSITE of both readings §3.6 offers: it is neither
"the implementor method has any annotation so the interface's are all
ignored" (§3.6, which would drop the endpoint) nor "each attribute is looked
up independently across levels" (a full merge, which would combine the
interface's `@GET` with the implementor's own `@Produces`) — it is **whole
ancestor member wins**, decided solely by which class-hierarchy level's OWN
declaration first satisfies the sought httpMethod annotation.

`quarkus-rest.yml` must state this divergence from §3.6 in a comment, and
`docs/COVERAGE.md` names the cell: an implementor overriding a JAX-RS
interface method with its own `@Produces` (or any other non-httpMethod
JAX-RS annotation) but no HTTP-verb annotation of its own has that override
silently ignored for every attribute Quarkus reads — the interface's
declaration governs entirely.

## Verdict

1. Row 1 confirms R1's gate is unchanged at 3.39.4.
2. Row 2 gives `hint_annotations` in priority order:
   `@RestStreamElementType` before `@RestSseElementType`.
3. Row 3 gives `quarkus-rest.yml`'s `excludes` addition: the three Vert.x
   context types, added by the deployment processor's own static set, on top
   of `jakarta-jaxrs.yml`'s JAX-RS `@Context` list.
4. Row 4 confirms the parameter-resolution order (context → container → path
   name → body) with the message text, and gives the container-detection rule
   and its full annotation set for `implicit_bindings`.
5. Row 5 gives the exact relocation boundary: 3.9.0, both `detect.coordinates`
   entries can now cite an exact version rather than "recent".
6. **Row 6 is FALSE as the all-or-nothing §3.6 hypothesis:** Quarkus REST's
   own mechanism is neither §3.6 nor a per-annotation merge; it is a
   whole-ancestor-member selection driven by which hierarchy level first
   carries the httpMethod annotation being searched, and that same member's
   declaration is used for every other JAX-RS annotation on the endpoint. This
   must be recorded as a Quarkus-specific divergence, not modelled as §3.6.

`measured: 2026-09-18` for every row above.
