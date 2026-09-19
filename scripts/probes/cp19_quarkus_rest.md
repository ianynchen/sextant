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

**Version scope (§5.4).** `io.quarkus:quarkus-rest`, `quarkus-rest-deployment`,
`io.quarkus.resteasy.reactive:resteasy-reactive-common` and
`resteasy-reactive-common-processor` at **3.39.4** for every source/bytecode
row, and again at **3.17.5** (one generation before the 3.9.0 relocation row 5
finds) for rows 1, 2, 3 and 4 — the harness resolves and reads both, so those
rows are measured at both generations rather than asserted stable across them.
Row 6 (`AnnotationStore`/`collectEndpoints`) is scoped to 3.39.4 alone; the
harness does not re-derive it at 3.17.5. The relocation question (row 5) is
read against Maven Central's own metadata for both `io.quarkus:quarkus-rest`
and `io.quarkus:quarkus-resteasy-reactive`, unscoped by version because it
asks which versions of the COORDINATE exist, not a single jar's behaviour.
Every source-code verdict below is bounded to 3.39.4 and 3.17.5.

## Environment

The design review staged `ResteasyReactiveScanner.java`, `EndpointIndexer.java`,
`ResteasyReactiveDotNames.java` and `ParamContainerScanner.java` (=
`ResteasyReactiveParameterContainerScanner.java`) in a session scratchpad, and
Rows 1–6 below were first read against those files. The committed harness does
NOT depend on that scratchpad — it turns out
`io.quarkus.resteasy.reactive:resteasy-reactive-common-processor` publishes a
`-sources` classifier on Maven Central at the SAME coordinate as its bytecode,
so `run.sh` resolves `resteasy-reactive-common-processor-3.39.4-sources.jar`
(and the 3.17.5 generation) the same way it resolves every other jar, and
`probe.py` reads the four `.java` files out of that archive — confirmed
byte-for-byte identical to the scratchpad's copies before the harness was
trusted. This is simpler and more robust than the raw-GitHub-fetch approach
the task brief anticipated for when no sources jar exists: the identity is the
same resolved Maven coordinate as the bytecode, not a URL tag a later run
could silently fetch a different revision of.

**How to run.** `bash scripts/probes/cp19_quarkus_rest/run.sh`. It resolves
`quarkus-rest`, `quarkus-rest-deployment`, `resteasy-reactive-common` and
`resteasy-reactive-common-processor` (plus its `-sources` classifier) at both
3.39.4 and 3.17.5 through Maven (network on the first run only, cached in
`~/.m2` afterwards), and reads Maven Central's plain metadata XML for row 5 on
every run — that IS the question row 5 asks, not a resolution step. Needs a
JDK and Maven. Not a test: nothing in the suite runs it, and NFR-1's no-network
rule governs the suite rather than evidence gathering.

## Observations

Verbatim from `run.sh`'s generated table (`probe.py` prints it; nothing here
is typed by hand). **Every column header of the first table is a version the
JAR itself REPORTED, and not the version the coordinate list asked for** — out
of each manifest's `Implementation-Version`. `probe.py` reads the value out of
the archive it opened and ABORTS the whole run when it disagrees with the
coordinate that resolved the jar, rather than filling a mislabelled column;
that is CP-5's failure, which printed a version it believed beside output from
a version it had not run.

```
| what the run read | 3.17.5 | 3.39.4 |
|---|---|---|
| artifacts reporting this version | io.quarkus.resteasy.reactive:resteasy-reactive-common, io.quarkus.resteasy.reactive:resteasy-reactive-common-processor, io.quarkus:quarkus-rest, io.quarkus:quarkus-rest-deployment | io.quarkus.resteasy.reactive:resteasy-reactive-common, io.quarkus.resteasy.reactive:resteasy-reactive-common-processor, io.quarkus:quarkus-rest, io.quarkus:quarkus-rest-deployment |
| identity read from the archive itself | yes | yes |

| # | question | artifact | version | observed |
|---|---|---|---|---|
| 1a | root-resource gate: class-level @Path | `io.quarkus.resteasy.reactive:resteasy-reactive-common-processor` | 3.39.4 | `if (annotation.target().kind() == AnnotationTarget.Kind.CLASS) { ClassInfo clazz = annotation.target().asClass(); if (!Modifier.isInterface(clazz.flags())) { scannedResources.put(clazz.name(), clazz); scannedResourcePaths.put(clazz.name(), annotation.value().asString()); } else { pathInterfaces.put(clazz.name(), annotation.value().asString()); } MethodInfo ctor = hasJaxRsCtorParams(clazz); if (ctor != null) { resourcesThatNeedCustomProducer.put(clazz.name(), ctor); } if (hasJaxRsFieldInjection(clazz, index)) { requestScopedResources.add(clazz.name()); } List<AnnotationInstance> exceptionMapperAnnotationInstances = clazz.annotationsMap() .get(ResteasyReactiveDotNames.SERVER_EXCEPTION_MAPPER); if (exceptionMapperAnnotationInstances != null) { for (AnnotationInstance instance : exceptionMapperAnnotationInstances) { if (instance.target().kind() != AnnotationTarget.Kind.METHOD) { continue; } methodExceptionMappers.add(instance.target().asMethod()); } } } else if (annotation.target().kind() == AnnotationTarget.Kind.METHOD) { ClassInfo clazz = annotation.target().asMethod().declaringClass(); if (Modifier.isInterface(clazz.flags())) { interfacesWithPathOnMethods.add(clazz.name()); } }` |
| 1b | root-resource gate: @Path-interface implementors | `io.quarkus.resteasy.reactive:resteasy-reactive-common-processor` | 3.39.4 | `for (ClassInfo clazz : index.getAllKnownImplementors(i.getKey())) { if (!Modifier.isAbstract(clazz.flags())) { if ((clazz.enclosingClass() == null || Modifier.isStatic(clazz.flags())) && clazz.enclosingMethod() == null) { if (!scannedResources.containsKey(clazz.name())) { scannedResources.put(clazz.name(), clazz); scannedResourcePaths.put(clazz.name(), i.getValue()); // check for server exception mapper method in implementation class of the interface. List<AnnotationInstance> exceptionMapperAnnotationInstances = clazz.annotationsMap() .get(ResteasyReactiveDotNames.SERVER_EXCEPTION_MAPPER); if (exceptionMapperAnnotationInstances != null) { for (AnnotationInstance instance : exceptionMapperAnnotationInstances) { if (instance.target().kind() != AnnotationTarget.Kind.METHOD) { continue; } methodExceptionMappers.add(instance.target().asMethod()); } } } } } }` |
| 1c | root-resource gate: HTTP-verb-only clientInterfaces/subResources | `io.quarkus.resteasy.reactive:resteasy-reactive-common-processor` | 3.39.4 | `// for clients, it is also enough to only have @GET, @POST, etc on methods and no PATH whatsoever Set<DotName> methodAnnotations = httpAnnotationToMethod.keySet(); for (DotName methodAnnotation : methodAnnotations) { for (AnnotationInstance methodAnnotationInstance : index.getAnnotations(methodAnnotation)) { if (methodAnnotationInstance.target().kind() == AnnotationTarget.Kind.METHOD) { MethodInfo annotatedMethod = methodAnnotationInstance.target().asMethod(); ClassInfo classWithJaxrsMethod = annotatedMethod.declaringClass(); if (Modifier.isAbstract(annotatedMethod.flags()) && Modifier.isInterface(classWithJaxrsMethod.flags()) && !clientInterfaces.containsKey(classWithJaxrsMethod.name())) { clientInterfaces.put(classWithJaxrsMethod.name(), ""); } } } } //now index possible sub resources. These are all classes that have method annotations //that are not annotated @Path Deque<ClassInfo> toScan = new ArrayDeque<>(); for (DotName methodAnnotation : httpAnnotationToMethod.keySet()) { for (AnnotationInstance instance : index.getAnnotations(methodAnnotation)) { MethodInfo method = instance.target().asMethod(); ClassInfo classInfo = method.declaringClass(); toScan.add(classInfo); } } //sub resources can also have just a path annotation //if they are 'intermediate' sub resources for (AnnotationInstance instance : index.getAnnotations(ResteasyReactiveDotNames.PATH)) { if (instance.target().kind() == AnnotationTarget.Kind.METHOD) { MethodInfo method = instance.target().asMethod(); ClassInfo classInfo = method.declaringClass(); toScan.add(classInfo); } } Map<DotName, ClassInfo> possibleSubResources = new HashMap<>();` |
| 2a | SSE default-produces: the @Produces/stream-type resolution | `io.quarkus.resteasy.reactive:resteasy-reactive-common-processor` | 3.39.4 | `String[] produces = extractProducesConsumesValues(getAnnotationStore().getAnnotation(currentMethodInfo, PRODUCES)); if (((produces == null) || (produces.length == 0)) && (streamElementType != null)) { // when @RestStreamElementType is used, we automatically determine SSE as the @Produces MediaType produces = new String[] { MediaType.SERVER_SENT_EVENTS }; } else if (produces == null || produces.length == 0) { // use the @Produces annotation at class level if exists produces = basicResourceClassInfo.getProduces(); }` |
| 2b | SSE default-produces: getStreamAnnotationValue | `io.quarkus.resteasy.reactive:resteasy-reactive-common-processor` | 3.39.4 | `private String getStreamAnnotationValue(AnnotationTarget target) { String value = getAnnotationValueAsString(target, REST_STREAM_ELEMENT_TYPE); if (value == null) { value = getAnnotationValueAsString(target, REST_SSE_ELEMENT_TYPE); } return value; }` |
| 3a | DEFAULT_CONTEXT_TYPES (source) | `io.quarkus.resteasy.reactive:resteasy-reactive-common-processor` | 3.39.4 | `private static final Set<DotName> DEFAULT_CONTEXT_TYPES = Set.of(URI_INFO, HTTP_HEADERS, REQUEST, SECURITY_CONTEXT, PROVIDERS, RESOURCE_CONTEXT, CONFIGURATION, SSE, SSE_EVENT_SINK, // extras SERVER_REQUEST_CONTEXT, DotName.createSimple("org.jboss.resteasy.reactive.server.SimpleResourceInfo"), //TODO: fixme RESOURCE_INFO);` |
| 3b | addContextTypes caller + Vert.x CONTEXT_TYPES (bytecode) | `io.quarkus:quarkus-rest-deployment` | 3.39.4 | `caller: invokevirtual Method io/quarkus/resteasy/reactive/server/deployment/QuarkusServerEndpointIndexer$Builder.addContextTypes:(Ljava/util/Collection;)Lorg/jboss/resteasy/reactive/common/processor/EndpointIndexer$Builder; ; static init: ldc_w String io.quarkus.resteasy.reactive.server ; invokestatic Method org/jboss/logging/Logger.getLogger:(Ljava/lang/String;)Lorg/jboss/logging/Logger; ; putstatic Field log:Lorg/jboss/logging/Logger; ; invokedynamic InvokeDynamic #59:test:()Ljava/util/function/Predicate; ; putstatic Field isEmpty:Ljava/util/function/Predicate; ; ldc_w class io/vertx/core/http/HttpServerRequest ; invokevirtual Method java/lang/Class.getName:()Ljava/lang/String; ; invokestatic Method org/jboss/jandex/DotName.createSimple:(Ljava/lang/String;)Lorg/jboss/jandex/DotName; ; ldc_w class io/vertx/core/http/HttpServerResponse ; invokevirtual Method java/lang/Class.getName:()Ljava/lang/String; ; invokestatic Method org/jboss/jandex/DotName.createSimple:(Ljava/lang/String;)Lorg/jboss/jandex/DotName; ; ldc_w class io/vertx/ext/web/RoutingContext ; invokevirtual Method java/lang/Class.getName:()Ljava/lang/String; ; invokestatic Method org/jboss/jandex/DotName.createSimple:(Ljava/lang/String;)Lorg/jboss/jandex/DotName; ; invokestatic InterfaceMethod java/util/Set.of:(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/Set; ; putstatic Field CONTEXT_TYPES:Ljava/util/Set;` |
| 4a | parameter-resolution order: context -> container -> path-name -> body | `io.quarkus.resteasy.reactive:resteasy-reactive-common-processor` | 3.39.4 | `// auto context parameters if (!field && paramType.kind() == Kind.CLASS && isContextType(paramType.asClassType())) { // no name required builder.setType(ParameterType.CONTEXT); } else if (!field && paramType.kind() == Kind.CLASS && isParameterContainerType(paramType.asClassType())) { // auto @BeanParam/@MultipartForm parameters builder.setType(ParameterType.BEAN); } else if (!field && pathParameters.contains(sourceName)) { builder.setName(sourceName); builder.setType(ParameterType.PATH); builder.setErrorLocation(builder.getRawErrorLocation() + " (this parameter name matches the @Path parameter name, so it has been implicitly assumed to be an @PathParam and not the request body)", builder.getErrorLocationParameters()); convertible = true; } else if (!field && paramType.name().equals(MULTI_PART_DATA_INPUT)) { builder.setType(ParameterType.MULTI_PART_DATA_INPUT); builder.setSingle(true); return builder; } else { //un-annotated field //just ignore it if (field) { return builder; } builder.setName(sourceName); builder.setType(ParameterType.BODY); } }` |
| 4b | ParamContainerScanner.scanParameterContainers | `io.quarkus.resteasy.reactive:resteasy-reactive-common-processor` | 3.39.4 | `public static Set<DotName> scanParameterContainers(IndexView index, ApplicationScanningResult result) { Set<DotName> res = new HashSet<DotName>(); // FIXME: this should discover parameter-containers containing parameter-containers // NOTE: we used to call result.keepClass but the TCK doesn't list bean parameters in their Application.getClasses // and the docs says this applies to resource, provider or feature which I don't think apply to bean params for (DotName fieldAnnotation : ResteasyReactiveDotNames.JAX_RS_ANNOTATIONS_FOR_FIELDS) { for (AnnotationInstance annotationInstance : index.getAnnotations(fieldAnnotation)) { // these annotations can be on fields or properties if (annotationInstance.target().kind() == Kind.FIELD) { ClassInfo klass = annotationInstance.target().asField().declaringClass(); res.add(klass.name()); } else if (annotationInstance.target().kind() == Kind.METHOD) { ClassInfo klass = annotationInstance.target().asMethod().declaringClass(); res.add(klass.name()); } } } return res; }` |
| 4c | JAX_RS_ANNOTATIONS_FOR_FIELDS | `io.quarkus.resteasy.reactive:resteasy-reactive-common-processor` | 3.39.4 | `public static final Set<DotName> JAX_RS_ANNOTATIONS_FOR_FIELDS = new HashSet<>( Arrays.asList(BEAN_PARAM, MULTI_PART_FORM_PARAM, PATH_PARAM, QUERY_PARAM, HEADER_PARAM, FORM_PARAM, MATRIX_PARAM, COOKIE_PARAM, REST_PATH_PARAM, REST_QUERY_PARAM, REST_HEADER_PARAM, REST_FORM_PARAM, REST_MATRIX_PARAM, REST_COOKIE_PARAM, CONTEXT, DEFAULT_VALUE, SUSPENDED));` |
| 1a | root-resource gate: class-level @Path | `io.quarkus.resteasy.reactive:resteasy-reactive-common-processor` | 3.17.5 | `if (annotation.target().kind() == AnnotationTarget.Kind.CLASS) { ClassInfo clazz = annotation.target().asClass(); if (!Modifier.isInterface(clazz.flags())) { scannedResources.put(clazz.name(), clazz); scannedResourcePaths.put(clazz.name(), annotation.value().asString()); } else { pathInterfaces.put(clazz.name(), annotation.value().asString()); } MethodInfo ctor = hasJaxRsCtorParams(clazz); if (ctor != null) { resourcesThatNeedCustomProducer.put(clazz.name(), ctor); } List<AnnotationInstance> exceptionMapperAnnotationInstances = clazz.annotationsMap() .get(ResteasyReactiveDotNames.SERVER_EXCEPTION_MAPPER); if (exceptionMapperAnnotationInstances != null) { for (AnnotationInstance instance : exceptionMapperAnnotationInstances) { if (instance.target().kind() != AnnotationTarget.Kind.METHOD) { continue; } methodExceptionMappers.add(instance.target().asMethod()); } } } else if (annotation.target().kind() == AnnotationTarget.Kind.METHOD) { ClassInfo clazz = annotation.target().asMethod().declaringClass(); if (Modifier.isInterface(clazz.flags())) { interfacesWithPathOnMethods.add(clazz.name()); } }` |
| 1b | root-resource gate: @Path-interface implementors | `io.quarkus.resteasy.reactive:resteasy-reactive-common-processor` | 3.17.5 | `for (ClassInfo clazz : index.getAllKnownImplementors(i.getKey())) { if (!Modifier.isAbstract(clazz.flags())) { if ((clazz.enclosingClass() == null || Modifier.isStatic(clazz.flags())) && clazz.enclosingMethod() == null) { if (!scannedResources.containsKey(clazz.name())) { scannedResources.put(clazz.name(), clazz); scannedResourcePaths.put(clazz.name(), i.getValue()); // check for server exception mapper method in implementation class of the interface. List<AnnotationInstance> exceptionMapperAnnotationInstances = clazz.annotationsMap() .get(ResteasyReactiveDotNames.SERVER_EXCEPTION_MAPPER); if (exceptionMapperAnnotationInstances != null) { for (AnnotationInstance instance : exceptionMapperAnnotationInstances) { if (instance.target().kind() != AnnotationTarget.Kind.METHOD) { continue; } methodExceptionMappers.add(instance.target().asMethod()); } } } } } }` |
| 1c | root-resource gate: HTTP-verb-only clientInterfaces/subResources | `io.quarkus.resteasy.reactive:resteasy-reactive-common-processor` | 3.17.5 | `// for clients, it is also enough to only have @GET, @POST, etc on methods and no PATH whatsoever Set<DotName> methodAnnotations = httpAnnotationToMethod.keySet(); for (DotName methodAnnotation : methodAnnotations) { for (AnnotationInstance methodAnnotationInstance : index.getAnnotations(methodAnnotation)) { if (methodAnnotationInstance.target().kind() == AnnotationTarget.Kind.METHOD) { MethodInfo annotatedMethod = methodAnnotationInstance.target().asMethod(); ClassInfo classWithJaxrsMethod = annotatedMethod.declaringClass(); if (Modifier.isAbstract(annotatedMethod.flags()) && Modifier.isInterface(classWithJaxrsMethod.flags()) && !clientInterfaces.containsKey(classWithJaxrsMethod.name())) { clientInterfaces.put(classWithJaxrsMethod.name(), ""); } } } } //now index possible sub resources. These are all classes that have method annotations //that are not annotated @Path Deque<ClassInfo> toScan = new ArrayDeque<>(); for (DotName methodAnnotation : httpAnnotationToMethod.keySet()) { for (AnnotationInstance instance : index.getAnnotations(methodAnnotation)) { MethodInfo method = instance.target().asMethod(); ClassInfo classInfo = method.declaringClass(); toScan.add(classInfo); } } //sub resources can also have just a path annotation //if they are 'intermediate' sub resources for (AnnotationInstance instance : index.getAnnotations(ResteasyReactiveDotNames.PATH)) { if (instance.target().kind() == AnnotationTarget.Kind.METHOD) { MethodInfo method = instance.target().asMethod(); ClassInfo classInfo = method.declaringClass(); toScan.add(classInfo); } } Map<DotName, ClassInfo> possibleSubResources = new HashMap<>();` |
| 2a | SSE default-produces: the @Produces/stream-type resolution | `io.quarkus.resteasy.reactive:resteasy-reactive-common-processor` | 3.17.5 | `String[] produces = extractProducesConsumesValues(getAnnotationStore().getAnnotation(currentMethodInfo, PRODUCES)); if (((produces == null) || (produces.length == 0)) && (streamElementType != null)) { // when @RestStreamElementType is used, we automatically determine SSE as the @Produces MediaType produces = new String[] { MediaType.SERVER_SENT_EVENTS }; } else if (produces == null || produces.length == 0) { // use the @Produces annotation at class level if exists produces = basicResourceClassInfo.getProduces(); }` |
| 2b | SSE default-produces: getStreamAnnotationValue | `io.quarkus.resteasy.reactive:resteasy-reactive-common-processor` | 3.17.5 | `private String getStreamAnnotationValue(AnnotationTarget target) { String value = getAnnotationValueAsString(target, REST_STREAM_ELEMENT_TYPE); if (value == null) { value = getAnnotationValueAsString(target, REST_SSE_ELEMENT_TYPE); } return value; }` |
| 3a | DEFAULT_CONTEXT_TYPES (source) | `io.quarkus.resteasy.reactive:resteasy-reactive-common-processor` | 3.17.5 | `private static final Set<DotName> DEFAULT_CONTEXT_TYPES = Set.of(URI_INFO, HTTP_HEADERS, REQUEST, SECURITY_CONTEXT, PROVIDERS, RESOURCE_CONTEXT, CONFIGURATION, SSE, SSE_EVENT_SINK, // extras SERVER_REQUEST_CONTEXT, DotName.createSimple("org.jboss.resteasy.reactive.server.SimpleResourceInfo"), //TODO: fixme RESOURCE_INFO);` |
| 3b | addContextTypes caller + Vert.x CONTEXT_TYPES (bytecode) | `io.quarkus:quarkus-rest-deployment` | 3.17.5 | `caller: invokevirtual Method io/quarkus/resteasy/reactive/server/deployment/QuarkusServerEndpointIndexer$Builder.addContextTypes:(Ljava/util/Collection;)Lorg/jboss/resteasy/reactive/common/processor/EndpointIndexer$Builder; ; static init: ldc_w String io.quarkus.resteasy.reactive.server ; invokestatic Method org/jboss/logging/Logger.getLogger:(Ljava/lang/String;)Lorg/jboss/logging/Logger; ; putstatic Field log:Lorg/jboss/logging/Logger; ; invokedynamic InvokeDynamic #59:test:()Ljava/util/function/Predicate; ; putstatic Field isEmpty:Ljava/util/function/Predicate; ; ldc_w class io/vertx/core/http/HttpServerRequest ; invokevirtual Method java/lang/Class.getName:()Ljava/lang/String; ; invokestatic Method org/jboss/jandex/DotName.createSimple:(Ljava/lang/String;)Lorg/jboss/jandex/DotName; ; ldc_w class io/vertx/core/http/HttpServerResponse ; invokevirtual Method java/lang/Class.getName:()Ljava/lang/String; ; invokestatic Method org/jboss/jandex/DotName.createSimple:(Ljava/lang/String;)Lorg/jboss/jandex/DotName; ; ldc_w class io/vertx/ext/web/RoutingContext ; invokevirtual Method java/lang/Class.getName:()Ljava/lang/String; ; invokestatic Method org/jboss/jandex/DotName.createSimple:(Ljava/lang/String;)Lorg/jboss/jandex/DotName; ; invokestatic InterfaceMethod java/util/Set.of:(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/Set; ; putstatic Field CONTEXT_TYPES:Ljava/util/Set;` |
| 4a | parameter-resolution order: context -> container -> path-name -> body | `io.quarkus.resteasy.reactive:resteasy-reactive-common-processor` | 3.17.5 | `// auto context parameters if (!field && paramType.kind() == Kind.CLASS && isContextType(paramType.asClassType())) { // no name required builder.setType(ParameterType.CONTEXT); } else if (!field && paramType.kind() == Kind.CLASS && isParameterContainerType(paramType.asClassType())) { // auto @BeanParam/@MultipartForm parameters builder.setType(ParameterType.BEAN); } else if (!field && pathParameters.contains(sourceName)) { builder.setName(sourceName); builder.setType(ParameterType.PATH); builder.setErrorLocation(builder.getRawErrorLocation() + " (this parameter name matches the @Path parameter name, so it has been implicitly assumed to be an @PathParam and not the request body)", builder.getErrorLocationParameters()); convertible = true; } else if (!field && paramType.name().equals(MULTI_PART_DATA_INPUT)) { builder.setType(ParameterType.MULTI_PART_DATA_INPUT); builder.setSingle(true); return builder; } else { //un-annotated field //just ignore it if (field) { return builder; } builder.setName(sourceName); builder.setType(ParameterType.BODY); } }` |
| 4b | ParamContainerScanner.scanParameterContainers | `io.quarkus.resteasy.reactive:resteasy-reactive-common-processor` | 3.17.5 | `public static Set<DotName> scanParameterContainers(IndexView index, ApplicationScanningResult result) { Set<DotName> res = new HashSet<DotName>(); // FIXME: this should discover parameter-containers containing parameter-containers // NOTE: we used to call result.keepClass but the TCK doesn't list bean parameters in their Application.getClasses // and the docs says this applies to resource, provider or feature which I don't think apply to bean params for (DotName fieldAnnotation : ResteasyReactiveDotNames.JAX_RS_ANNOTATIONS_FOR_FIELDS) { for (AnnotationInstance annotationInstance : index.getAnnotations(fieldAnnotation)) { // these annotations can be on fields or properties if (annotationInstance.target().kind() == Kind.FIELD) { ClassInfo klass = annotationInstance.target().asField().declaringClass(); res.add(klass.name()); } else if (annotationInstance.target().kind() == Kind.METHOD) { ClassInfo klass = annotationInstance.target().asMethod().declaringClass(); res.add(klass.name()); } } } return res; }` |
| 4c | JAX_RS_ANNOTATIONS_FOR_FIELDS | `io.quarkus.resteasy.reactive:resteasy-reactive-common-processor` | 3.17.5 | `public static final Set<DotName> JAX_RS_ANNOTATIONS_FOR_FIELDS = new HashSet<>( Arrays.asList(BEAN_PARAM, MULTI_PART_FORM_PARAM, PATH_PARAM, QUERY_PARAM, HEADER_PARAM, FORM_PARAM, MATRIX_PARAM, COOKIE_PARAM, REST_PATH_PARAM, REST_QUERY_PARAM, REST_HEADER_PARAM, REST_FORM_PARAM, REST_MATRIX_PARAM, REST_COOKIE_PARAM, CONTEXT, DEFAULT_VALUE, SUSPENDED));` |
| 5a | relocation: quarkus-rest earliest GA versions (Maven Central metadata) | `io.quarkus:quarkus-rest` | n/a | `quarkus-rest earliest GA versions: 3.9.0, 3.9.1, 3.9.2` |
| 5b | relocation: quarkus-resteasy-reactive last versions (Maven Central metadata) | `io.quarkus:quarkus-rest` | n/a | `quarkus-resteasy-reactive last versions: 3.15.1, 3.15.2, 3.15.3.1, 3.15.3, 3.15.4, 3.15.5, 3.15.6.1, 3.15.6.2, 3.15.6, 3.15.7` |
| 6a | AnnotationStore.getAnnotation (bytecode, no hierarchy walk) | `io.quarkus.resteasy.reactive:resteasy-reactive-common-processor` | 3.39.4 | `AnnotationStore.getAnnotation: aload_0 ; getfield Field delegate:Lorg/jboss/jandex/AnnotationOverlay; ; aload_1 ; invokeinterface InterfaceMethod org/jboss/jandex/AnnotationTarget.asDeclaration:()Lorg/jboss/jandex/Declaration; ; aload_2 ; invokeinterface InterfaceMethod org/jboss/jandex/AnnotationOverlay.annotation:(Lorg/jboss/jandex/Declaration;Lorg/jboss/jandex/DotName;)Lorg/jboss/jandex/AnnotationInstance; ; areturn` |
| 6b | EndpointIndexer.collectEndpoints, full body (source) | `io.quarkus.resteasy.reactive:resteasy-reactive-common-processor` | 3.39.4 | `private static List<FoundEndpoint> collectEndpoints(ClassInfo currentClassInfo, ClassInfo actualEndpointInfo, Set<String> seenMethods, Set<String> existingClassNameBindings, boolean considerApplication, Map<DotName, String> httpAnnotationToMethod, IndexView index, ApplicationScanningResult applicationScanningResult, AnnotationStore annotationStore) { if (considerApplication && applicationScanningResult != null && !applicationScanningResult.keepClass(actualEndpointInfo.name().toString())) { return Collections.emptyList(); } // $$CDIWrapper suffix is used to generate CDI beans from interfaces, we don't want to create endpoints for them: if (currentClassInfo.name().toString().endsWith(CDI_WRAPPER_SUFFIX)) { return Collections.emptyList(); } List<FoundEndpoint> ret = new ArrayList<>(); Set<String> classNameBindings = NameBindingUtil.nameBindingNames(index, currentClassInfo); if (classNameBindings.isEmpty()) { classNameBindings = existingClassNameBindings; } for (DotName httpMethod : httpAnnotationToMethod.keySet().stream().sorted().toList()) { List<MethodInfo> methods = currentClassInfo.methods(); for (MethodInfo info : methods) { AnnotationInstance annotation = annotationStore.getAnnotation(info, httpMethod); if (annotation != null) { if (!hasProperModifiers(info)) { continue; } String descriptor = methodDescriptor(info); if (seenMethods.contains(descriptor)) { continue; } seenMethods.add(descriptor); ret.add(new FoundEndpoint(currentClassInfo, classNameBindings, info, httpMethod)); } } } //now resource locator methods List<MethodInfo> methods = currentClassInfo.methods(); for (MethodInfo info : methods) { AnnotationInstance annotation = annotationStore.getAnnotation(info, PATH); if (annotation != null) { if (!hasProperModifiers(info)) { continue; } String descriptor = methodDescriptor(info); if (seenMethods.contains(descriptor)) { continue; } seenMethods.add(descriptor); ret.add(new FoundEndpoint(currentClassInfo, classNameBindings, info, null)); } } DotName superClassName = currentClassInfo.superName(); if (superClassName != null && !superClassName.equals(OBJECT)) { ClassInfo superClass = index.getClassByName(superClassName); if (superClass != null) { ret.addAll(collectEndpoints(superClass, actualEndpointInfo, seenMethods, classNameBindings, considerApplication, httpAnnotationToMethod, index, applicationScanningResult, annotationStore)); } } List<DotName> interfaces = currentClassInfo.interfaceNames(); for (DotName i : interfaces) { ClassInfo superClass = index.getClassByName(i); if (superClass != null) { ret.addAll(collectEndpoints(superClass, actualEndpointInfo, seenMethods, classNameBindings, considerApplication, httpAnnotationToMethod, index, applicationScanningResult, annotationStore)); } } return ret; }` |
| 6c | EndpointIndexer.getInheritableAnnotation, full body (source) | `io.quarkus.resteasy.reactive:resteasy-reactive-common-processor` | 3.39.4 | `private Map.Entry<AnnotationTarget, AnnotationInstance> getInheritableAnnotation(MethodInfo info, DotName name) { // try method first, class second AnnotationInstance annotation = getAnnotationStore().getAnnotation(info, name); AnnotationTarget target = info; if (annotation == null) { annotation = getAnnotationStore().getAnnotation(info.declaringClass(), name); target = info.declaringClass(); } return annotation != null ? new AbstractMap.SimpleEntry<>(target, annotation) : null; }` |
| 6d | getInheritableAnnotation's only callers | `io.quarkus.resteasy.reactive:resteasy-reactive-common-processor` | 3.39.4 | `getInheritableAnnotation is called only for: BLOCKING, NON_BLOCKING, RUN_ON_VIRTUAL_THREAD` |
```

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
355               }
356           }
357       }
358   }
359
360   //now index possible sub resources. These are all classes that have method annotations
361   //that are not annotated @Path
362   Deque<ClassInfo> toScan = new ArrayDeque<>();
363   for (DotName methodAnnotation : httpAnnotationToMethod.keySet()) {
364       for (AnnotationInstance instance : index.getAnnotations(methodAnnotation)) {
365           MethodInfo method = instance.target().asMethod();
366           ClassInfo classInfo = method.declaringClass();
367           toScan.add(classInfo);
368       }
369   }
370   //sub resources can also have just a path annotation
371   //if they are 'intermediate' sub resources
372   for (AnnotationInstance instance : index.getAnnotations(ResteasyReactiveDotNames.PATH)) {
373       if (instance.target().kind() == AnnotationTarget.Kind.METHOD) {
374           MethodInfo method = instance.target().asMethod();
375           ClassInfo classInfo = method.declaringClass();
376           toScan.add(classInfo);
377       }
378   }
379   Map<DotName, ClassInfo> possibleSubResources = new HashMap<>();
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
17: ldc_w  #2199  // class io/vertx/core/http/HttpServerRequest
20: invokevirtual #67    // Method java/lang/Class.getName:()Ljava/lang/String;
23: invokestatic  #865   // Method org/jboss/jandex/DotName.createSimple:(Ljava/lang/String;)Lorg/jboss/jandex/DotName;
26: ldc_w  #2201  // class io/vertx/core/http/HttpServerResponse
29: invokevirtual #67    // Method java/lang/Class.getName:()Ljava/lang/String;
32: invokestatic  #865   // Method org/jboss/jandex/DotName.createSimple:(Ljava/lang/String;)Lorg/jboss/jandex/DotName;
35: ldc_w  #2203  // class io/vertx/ext/web/RoutingContext
38: invokevirtual #67    // Method java/lang/Class.getName:()Ljava/lang/String;
41: invokestatic  #865   // Method org/jboss/jandex/DotName.createSimple:(Ljava/lang/String;)Lorg/jboss/jandex/DotName;
44: invokestatic  #262   // InterfaceMethod java/util/Set.of:(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)Ljava/util/Set;
47: putstatic     #1074  // Field CONTEXT_TYPES:Ljava/util/Set;
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
1380  // no name required
1381  builder.setType(ParameterType.ASYNC_RESPONSE);
1382  builder.setSuspended(true);
1383  } else {
1384      // auto context parameters
1385      if (!field
1386              && paramType.kind() == Kind.CLASS
1387              && isContextType(paramType.asClassType())) {
1388          // no name required
1389          builder.setType(ParameterType.CONTEXT);
1390      } else if (!field
1391              && paramType.kind() == Kind.CLASS
1392              && isParameterContainerType(paramType.asClassType())) {
1393          // auto @BeanParam/@MultipartForm parameters
1394          builder.setType(ParameterType.BEAN);
1395      } else if (!field && pathParameters.contains(sourceName)) {
1396          builder.setName(sourceName);
1397          builder.setType(ParameterType.PATH);
1398          builder.setErrorLocation(builder.getRawErrorLocation()
1399              + " (this parameter name matches the @Path parameter name, so it has been implicitly assumed to be an @PathParam and not the request body)",
1400              builder.getErrorLocationParameters());
1401          convertible = true;
1402      } else if (!field && paramType.name().equals(MULTI_PART_DATA_INPUT)) {
1403          builder.setType(ParameterType.MULTI_PART_DATA_INPUT);
1404          builder.setSingle(true);
1405          return builder;
1406      } else {
1407          //un-annotated field
1408          //just ignore it
1409          if (field) {
1410              return builder;
1411          }
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
268                  REST_COOKIE_PARAM, CONTEXT, DEFAULT_VALUE, SUSPENDED));
```

**Claim.** Once no explicit binding annotation applies, a parameter is
resolved in this order: **context type → container (bean-param) type →
path-variable name match → body** (1384–1414), confirming the order the spec
names, with the message quoted verbatim at 1398–1400. `ParamContainerScanner`
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
curl -s https://repo1.maven.org/maven2/io/quarkus/quarkus-resteasy-reactive/maven-metadata.xml | grep -o '<version>3\.[0-9]*\.[0-9]*</version>' | tail -10
cat <scratchpad>/quarkus-resteasy-reactive-3.15.7.pom
```

**Output.**
```
quarkus-rest earliest versions: 3.9.0.CR1, 3.9.0.CR2, 3.9.0
quarkus-resteasy-reactive last versions: 3.14.3, 3.14.4, 3.15.0, 3.15.1, 3.15.2, 3.15.3, 3.15.4, 3.15.5, 3.15.6, 3.15.7
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
public org.jboss.jandex.AnnotationInstance getAnnotation(org.jboss.jandex.AnnotationTarget, org.jboss.jandex.DotName);
    Code:
         0: aload_0
         1: getfield      #23                 // Field delegate:Lorg/jboss/jandex/AnnotationOverlay;
         4: aload_1
         5: invokeinterface #29,  1           // InterfaceMethod org/jboss/jandex/AnnotationTarget.asDeclaration:()Lorg/jboss/jandex/Declaration;
        10: aload_2
        11: invokeinterface #39,  3           // InterfaceMethod org/jboss/jandex/AnnotationOverlay.annotation:(Lorg/jboss/jandex/Declaration;Lorg/jboss/jandex/DotName;)Lorg/jboss/jandex/AnnotationInstance;
        16: areturn
```
`getAnnotation(target, name)` looks up the annotation declared on THAT
declaration alone via the Jandex `AnnotationOverlay` — no class-hierarchy walk
happens inside `AnnotationStore` itself.

**Output — `EndpointIndexer.collectEndpoints`, the actual hierarchy walk, full
method body, line numbers from the file (`private static List<FoundEndpoint>
collectEndpoints(…)`, signature at 456–459 omitted from the excerpt below for
space; every line of the body from the first statement to the closing brace
is included).**
```
461         if (considerApplication && applicationScanningResult != null
462                 && !applicationScanningResult.keepClass(actualEndpointInfo.name().toString())) {
463             return Collections.emptyList();
464         }
465
466         // $$CDIWrapper suffix is used to generate CDI beans from interfaces, we don't want to create endpoints for them:
467         if (currentClassInfo.name().toString().endsWith(CDI_WRAPPER_SUFFIX)) {
468             return Collections.emptyList();
469         }
470
471         List<FoundEndpoint> ret = new ArrayList<>();
472         Set<String> classNameBindings = NameBindingUtil.nameBindingNames(index, currentClassInfo);
473         if (classNameBindings.isEmpty()) {
474             classNameBindings = existingClassNameBindings;
475         }
476
477         for (DotName httpMethod : httpAnnotationToMethod.keySet().stream().sorted().toList()) {
478             List<MethodInfo> methods = currentClassInfo.methods();
479             for (MethodInfo info : methods) {
480                 AnnotationInstance annotation = annotationStore.getAnnotation(info, httpMethod);
481                 if (annotation != null) {
482                     if (!hasProperModifiers(info)) {
483                         continue;
484                     }
485                     String descriptor = methodDescriptor(info);
486                     if (seenMethods.contains(descriptor)) {
487                         continue;
488                     }
489                     seenMethods.add(descriptor);
490                     ret.add(new FoundEndpoint(currentClassInfo, classNameBindings, info, httpMethod));
491                 }
492             }
493         }
494
495         //now resource locator methods
496         List<MethodInfo> methods = currentClassInfo.methods();
497         for (MethodInfo info : methods) {
498             AnnotationInstance annotation = annotationStore.getAnnotation(info, PATH);
499             if (annotation != null) {
500                 if (!hasProperModifiers(info)) {
501                     continue;
502                 }
503                 String descriptor = methodDescriptor(info);
504                 if (seenMethods.contains(descriptor)) {
505                     continue;
506                 }
507                 seenMethods.add(descriptor);
508                 ret.add(new FoundEndpoint(currentClassInfo, classNameBindings, info, null));
509             }
510         }
511
512         DotName superClassName = currentClassInfo.superName();
513         if (superClassName != null && !superClassName.equals(OBJECT)) {
514             ClassInfo superClass = index.getClassByName(superClassName);
515             if (superClass != null) {
516                 ret.addAll(collectEndpoints(superClass, actualEndpointInfo, seenMethods, classNameBindings, considerApplication,
517                         httpAnnotationToMethod, index, applicationScanningResult, annotationStore));
518             }
519         }
520         List<DotName> interfaces = currentClassInfo.interfaceNames();
521         for (DotName i : interfaces) {
522             ClassInfo superClass = index.getClassByName(i);
523             if (superClass != null) {
524                 ret.addAll(collectEndpoints(superClass, actualEndpointInfo, seenMethods, classNameBindings, considerApplication,
525                         httpAnnotationToMethod, index, applicationScanningResult, annotationStore));
526             }
527         }
528         return ret;
529     }
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
