# W63 — Apache CXF's implementor rule, measured against the JAX-WS RI's

**Corrected 2026-09-12, same day as the first pass.** The first version of
this probe concluded CXF diverges from the RI on inherited operations. That
conclusion compared CXF's bytecode to a SENTENCE from `cp13_inherited_members.md`
("`RuntimeModeler.processClass` ... drops only those declared by
`java.lang.Object`") rather than to the RI's own bytecode. That sentence
describes `processClass`'s enumeration filter, not what the per-method
predicate it calls next — `isWebMethodBySpec` — does with a method that
carries no `@WebMethod` of its own. Reading `isWebMethodBySpec` directly (this
probe's own `javap`, below) shows it makes the IDENTICAL declaring-class
`@WebService` check CXF's `hasWebServiceAnnotation` makes. A live run of BOTH
runtimes over the identical fixture (below) confirms it: same five methods in,
same one method out, for both. **The corrected verdict is: CXF agrees with the
RI on all three axes.**

**Question.** `jakarta-jws.yml`'s `members: public_methods` rule derives a
`@WebService` class's operations by walking `Class.getMethods()` (inherited
public methods included), excluding `static` and `final` methods, and honouring
`@WebMethod(exclude = true)`. That rule was measured against ONE JAX-WS
implementation — jaxws-rt 4.0.2, the reference implementation,
`cp13_inherited_members.md` Q3/Q4 — and the catalog's own comment (`A-Mi7`) has
said since 2026-09-05 that **"Apache CXF is not measured"**, carrying
`apache-cxf` on the SOAP row of the delivery register as "version-scoped, not
settled". This task measures it: does CXF's JAX-WS frontend decide operation
membership the same way, for the same three questions — inheritance,
`static`/`final`, `@WebMethod(exclude = true)` — or does it diverge?

CXF's own answer lives in
`org.apache.cxf.jaxws.support.JaxWsServiceConfiguration.isOperation(Method)`
(and its `JaxWsImplementorInfo` collaborator), which the task brief says
delegates to `org.apache.cxf.service.factory.ReflectionServiceFactoryBean` /
`AbstractServiceConfiguration`. `cxf-core` DOES carry an
`org/apache/cxf/service/factory/` package (`AbstractServiceFactoryBean` and
five siblings — `unzip -l` confirms it) — but not these two specific classes.
They resolve to a different package at 4.0.5 than the brief assumed; see
"Where the brief's two class names actually live" below.

**Version scope (§5.4).** Read against **cxf-rt-frontend-jaxws 4.0.5 and
cxf-core 4.0.5** — the two coordinates the task brief names — plus
**cxf-rt-wsdl 4.0.5**, where `ReflectionServiceFactoryBean` and
`AbstractServiceConfiguration` actually live at this version, **jakarta.jws-api
3.0.0**, the annotation types every `isOperation`/`isWebMethodBySpec` path
reads (`@WebMethod`'s `exclude` attribute, `@WebService`), and **jaxws-rt
4.0.2** — the reference implementation itself, resolved here directly (not
just cited from `cp13_inherited_members.md`) so its `isWebMethodBySpec`
bytecode and its live service model can be read side by side with CXF's. All
five are resolved `-Dtransitive=false` for the `javap` half; the live
cross-checks need each runtime's full transitive runtime and resolve that
separately through `fixture/pom.xml` (CXF) and `fixture/pom-ri.xml` (the RI).

**How to run.** `bash scripts/probes/w63_cxf_web_method_rule/run.sh`. Resolves
the five artifacts through Maven (network on the first run only, cached in
`~/.m2` afterwards), reads the version each jar states for itself, `javap -p -c`
every method under test, and — as an independent check — compiles and runs
`scripts/probes/w63_cxf_web_method_rule/fixture/*.java` against BOTH a real
`JaxWsServiceFactoryBean` (CXF) and the RI's own model (through
`DatabindingFactory`, the SPI `jakarta.xml.ws.Endpoint.create` uses) to read
what each runtime's service model actually derives, over the identical two
fixture classes. Needs a JDK and Maven; the live halves each need network
access to their runtime's full transitive dependency set the first time they
run.

## Expectation table

| # | If | then |
|---|---|---|
| 1 | CXF's per-method test invokes `Modifier.isStatic` **and** `Modifier.isFinal` | same rule as the RI on this axis; a necessary condition for shipping the CXF `measured:` row |
| 2 | CXF's per-method test does NOT invoke `Modifier.isFinal` | CXF exposes `final` methods; the catalog's exclusion is RI-only and needs a per-catalog switch — record as a spec item |
| 3 | An operation with no `@WebMethod` of its own, whose declaring class does NOT carry `@WebService`, is excluded THE SAME WAY by both runtimes (whether that declaring class is the implementor itself or a plain ancestor it inherited the method from) | same rule as the RI on this axis too; combined with row 1, ships the CXF `measured:` row |
| 4 | The two runtimes decide that case differently | a genuine cross-implementation divergence; the catalog's rule is RI-only — record as a spec item, not a catalog change |

Rows 3/4 are not in the task brief's own two-row table (brief only names the
`static`/`final` axis), but the task's own opening question names all three —
inheritance, `static`/`final`, `exclude` — as what is being measured. Row 3 is
phrased carefully after the correction below: the decisive fact is not
"inherited vs. declared directly" but "does the declaring class of record carry
`@WebService`" — and BOTH runtimes read that off the same class (the method's
own declaring class when no `@WebMethod` is present), so both exclude an
operation inherited from a plain, unannotated superclass. That is not a
Sextant-vs-catalog gap on the CXF side; it is a gap between what BOTH runtimes
actually do and what `jakarta-jws.yml`'s `gate_ancestry` walk currently derives
(recorded separately below, as a new blocker).

## Observations

Verbatim from `scripts/probes/w63_cxf_web_method_rule/run.sh`, which runs
`sweep.py`. **Every version in the table below is the one the JAR itself
reported** — out of its own `META-INF/maven/.../pom.properties` —
and **not the version the coordinate list asked for**; `checked` compares
the two and ABORTS the whole run when they disagree.

| what the run read | 4.0.5 | 3.0.0 | 4.0.2 |
|---|---|---|---|
| artifacts reporting this version | cxf-rt-frontend-jaxws, cxf-core, cxf-rt-wsdl | jakarta.jws-api | jaxws-rt |
| where the jar states it | pom.properties | pom.properties | pom.properties |

### Where the brief's two class names actually live at 4.0.5

The task brief names `org.apache.cxf.service.factory.ReflectionServiceFactoryBean`
/ `AbstractServiceConfiguration` inside `cxf-core`. `cxf-core` DOES carry an
`org/apache/cxf/service/factory/` package — `unzip -l` shows
`AbstractServiceFactoryBean` and five siblings living there — but NOT these two
classes. `mvn dependency:tree` off `cxf-rt-frontend-jaxws:4.0.5` finds both one hop
further, repackaged as `org.apache.cxf.wsdl.service.factory.*` inside `cxf-rt-wsdl`
— pulled in transitively through `cxf-rt-bindings-soap`, not through `cxf-core`.

| class | brief's assumed location | actual 4.0.5 location |
|---|---|---|
| `ReflectionServiceFactoryBean` | `cxf-core` / `org.apache.cxf.service.factory` | `cxf-rt-wsdl` / `org.apache.cxf.wsdl.service.factory` |
| `AbstractServiceConfiguration` | `cxf-core` / `org.apache.cxf.service.factory` | `cxf-rt-wsdl` / `org.apache.cxf.wsdl.service.factory` |

### Every inspected method's `invokestatic`/`invokevirtual`/`invokeinterface`
### targets, in bytecode order

| class | method | calls, in order |
|---|---|---|
| `AbstractServiceConfiguration` | `isOperation` | *(calls nothing — `aconst_null; areturn`)* |
| `JaxWsServiceConfiguration` | `isOperation` | invokevirtual Method java/lang/reflect/Method.getDeclaringClass:()Ljava/lang/Class; ; invokevirtual Method java/lang/Object.equals:(Ljava/lang/Object;)Z ; invokestatic Method java/lang/Boolean.valueOf:(Z)Ljava/lang/Boolean; ; invokevirtual Method java/lang/reflect/Method.getDeclaringClass:()Ljava/lang/Class; ; invokevirtual Method org/apache/cxf/jaxws/support/JaxWsImplementorInfo.getSEIClass:()Ljava/lang/Class; ; invokevirtual Method java/lang/reflect/Method.getAnnotation:(Ljava/lang/Class;)Ljava/lang/annotation/Annotation; ; invokeinterface InterfaceMethod jakarta/jws/WebMethod.exclude:()Z ; invokevirtual Method java/lang/reflect/Method.getName:()Ljava/lang/String; ; invokespecial Method org/apache/cxf/common/i18n/Message."<init>":(Ljava/lang/String;Ljava/util/logging/Logger;[Ljava/lang/Object;)V ; invokespecial Method org/apache/cxf/jaxws/JaxWsConfigurationException."<init>":(Lorg/apache/cxf/common/i18n/Message;)V ; invokevirtual Method org/apache/cxf/jaxws/support/JaxWsImplementorInfo.getImplementorClass:()Ljava/lang/Class; ; invokevirtual Method getDeclaredMethod:(Ljava/lang/Class;Ljava/lang/reflect/Method;)Ljava/lang/reflect/Method; ; invokevirtual Method java/lang/reflect/Method.getAnnotation:(Ljava/lang/Class;)Ljava/lang/annotation/Annotation; ; invokeinterface InterfaceMethod jakarta/jws/WebMethod.exclude:()Z ; invokevirtual Method isWebMethod:(Ljava/lang/reflect/Method;)Ljava/lang/Boolean; ; invokevirtual Method java/lang/Boolean.booleanValue:()Z ; invokestatic Method java/lang/Boolean.valueOf:(Z)Ljava/lang/Boolean; ; invokevirtual Method getDeclaredMethod:(Ljava/lang/reflect/Method;)Ljava/lang/reflect/Method; ; invokevirtual Method isWebMethod:(Ljava/lang/reflect/Method;)Ljava/lang/Boolean; |
| `JaxWsServiceConfiguration` | `isWebMethod(Method)` | invokevirtual Method java/lang/reflect/Method.getReturnType:()Ljava/lang/Class; ; invokevirtual Method java/lang/Object.equals:(Ljava/lang/Object;)Z ; invokevirtual Method java/lang/reflect/Method.getReturnType:()Ljava/lang/Class; ; invokevirtual Method java/lang/Object.equals:(Ljava/lang/Object;)Z ; invokevirtual Method java/lang/reflect/Method.isSynthetic:()Z ; invokevirtual Method java/lang/reflect/Method.getAnnotation:(Ljava/lang/Class;)Ljava/lang/annotation/Annotation; ; invokevirtual Method java/lang/reflect/Method.getDeclaringClass:()Ljava/lang/Class; ; invokeinterface InterfaceMethod jakarta/jws/WebMethod.exclude:()Z ; invokeinterface InterfaceMethod jakarta/jws/WebMethod.exclude:()Z ; invokevirtual Method org/apache/cxf/jaxws/support/JaxWsImplementorInfo.getSEIClass:()Ljava/lang/Class; ; invokevirtual Method java/lang/Class.isInterface:()Z ; invokevirtual Method org/apache/cxf/jaxws/support/JaxWsImplementorInfo.getSEIClass:()Ljava/lang/Class; ; invokevirtual Method java/lang/Class.isAssignableFrom:(Ljava/lang/Class;)Z ; invokevirtual Method java/lang/reflect/Method.getDeclaringClass:()Ljava/lang/Class; ; invokevirtual Method java/lang/Class.isInterface:()Z ; invokevirtual Method hasWebServiceAnnotation:(Ljava/lang/reflect/Method;)Z ; invokestatic Method java/lang/Boolean.valueOf:(Z)Ljava/lang/Boolean; ; invokevirtual Method org/apache/cxf/jaxws/support/JaxWsImplementorInfo.getSEIClass:()Ljava/lang/Class; ; invokevirtual Method hasWebServiceAnnotation:(Ljava/lang/reflect/Method;)Z ; invokevirtual Method java/lang/reflect/Method.getModifiers:()I ; invokestatic Method java/lang/reflect/Modifier.isFinal:(I)Z ; invokevirtual Method java/lang/reflect/Method.getModifiers:()I ; invokestatic Method java/lang/reflect/Modifier.isStatic:(I)Z ; invokestatic Method java/lang/Boolean.valueOf:(Z)Ljava/lang/Boolean; ; invokevirtual Method org/apache/cxf/jaxws/support/JaxWsImplementorInfo.getSEIClass:()Ljava/lang/Class; ; invokevirtual Method java/lang/reflect/Method.getDeclaringClass:()Ljava/lang/Class; ; invokevirtual Method java/lang/Class.isAssignableFrom:(Ljava/lang/Class;)Z ; invokestatic Method java/lang/Boolean.valueOf:(Z)Ljava/lang/Boolean; |
| `JaxWsServiceConfiguration` | `hasWebServiceAnnotation` | invokevirtual Method java/lang/reflect/Method.getDeclaringClass:()Ljava/lang/Class; ; invokevirtual Method java/lang/Class.getAnnotation:(Ljava/lang/Class;)Ljava/lang/annotation/Annotation; |
| `JaxWsServiceConfiguration` | `getDeclaredMethod(Class, Method)` | invokevirtual Method java/lang/reflect/Method.getDeclaringClass:()Ljava/lang/Class; ; invokevirtual Method java/lang/Object.equals:(Ljava/lang/Object;)Z ; invokevirtual Method java/lang/reflect/Method.getName:()Ljava/lang/String; ; invokevirtual Method java/lang/reflect/Method.getParameterTypes:()[Ljava/lang/Class; ; invokevirtual Method java/lang/Class.getMethod:(Ljava/lang/String;[Ljava/lang/Class;)Ljava/lang/reflect/Method; ; invokespecial Method org/apache/cxf/service/factory/ServiceConstructionException."<init>":(Ljava/lang/Throwable;)V ; invokevirtual Method isWebMethod:(Ljava/lang/reflect/Method;)Ljava/lang/Boolean; ; invokevirtual Method java/lang/Boolean.booleanValue:()Z |
| `ReflectionServiceFactoryBean` | `isValidMethod` | invokeinterface InterfaceMethod java/util/List.iterator:()Ljava/util/Iterator; ; invokeinterface InterfaceMethod java/util/Iterator.hasNext:()Z ; invokeinterface InterfaceMethod java/util/Iterator.next:()Ljava/lang/Object; ; invokevirtual Method org/apache/cxf/wsdl/service/factory/AbstractServiceConfiguration.isOperation:(Ljava/lang/reflect/Method;)Ljava/lang/Boolean; ; invokevirtual Method java/lang/Boolean.booleanValue:()Z |
| `ReflectionServiceFactoryBean` | `createInterface` | invokevirtual Method getInterfaceName:()Ljavax/xml/namespace/QName; ; invokespecial Method org/apache/cxf/service/model/InterfaceInfo."<init>":(Lorg/apache/cxf/service/model/ServiceInfo;Ljavax/xml/namespace/QName;)V ; invokevirtual Method getServiceClass:()Ljava/lang/Class; ; invokevirtual Method java/lang/Class.getMethods:()[Ljava/lang/reflect/Method; ; invokespecial Method org/apache/cxf/wsdl/service/factory/MethodComparator."<init>":()V ; invokestatic Method java/util/Arrays.sort:([Ljava/lang/Object;Ljava/util/Comparator;)V ; invokevirtual Method isValidMethod:(Ljava/lang/reflect/Method;)Z ; invokevirtual Method createOperation:(Lorg/apache/cxf/service/model/ServiceInfo;Lorg/apache/cxf/service/model/InterfaceInfo;Ljava/lang/reflect/Method;)Lorg/apache/cxf/service/model/OperationInfo; ; invokevirtual Method getServiceClass:()Ljava/lang/Class; ; invokevirtual Method sendEvent:(Lorg/apache/cxf/service/factory/FactoryBeanListener$Event;[Ljava/lang/Object;)V |
| `RuntimeModeler` | `isWebMethodBySpec` | invokevirtual Method java/lang/reflect/Method.getModifiers:()I ; invokestatic Method java/lang/reflect/Modifier.isStatic:(I)Z ; invokestatic Method java/lang/reflect/Modifier.isFinal:(I)Z ; invokestatic Method java/lang/reflect/Modifier.isPublic:(I)Z ; invokespecial Method java/lang/AssertionError."<init>":()V ; invokevirtual Method java/lang/Class.isInterface:()Z ; invokespecial Method java/lang/AssertionError."<init>":()V ; invokevirtual Method getAnnotation:(Ljava/lang/reflect/Method;Ljava/lang/Class;)Ljava/lang/annotation/Annotation; ; invokeinterface InterfaceMethod jakarta/jws/WebMethod.exclude:()Z ; invokestatic Method com/sun/xml/ws/resources/ModelerMessages.localizableRUNTIME_MODELER_WEBMETHOD_MUST_BE_NONSTATICFINAL:(Ljava/lang/Object;)Lcom/sun/istack/localization/Localizable; ; invokespecial Method com/sun/xml/ws/model/RuntimeModelerException."<init>":(Lcom/sun/istack/localization/Localizable;)V ; invokevirtual Method java/lang/reflect/Method.getDeclaringClass:()Ljava/lang/Class; ; invokevirtual Method getAnnotation:(Ljava/lang/Class;Ljava/lang/Class;)Ljava/lang/annotation/Annotation; |

### The declaring-class `@WebService` check, raw — CXF and the RI side by side

The compressed invoke-only table above loses the control flow (`ldc`, `aload`,
`ifeq`/`ifnull`) that actually decides which branch runs. Raw excerpts, both
read off the same `javap -p -c` output the table above parses:

**`JaxWsServiceConfiguration.hasWebServiceAnnotation` — the whole method, which
carries the `ldc class jakarta/jws/WebService` line:**

```
0: aload_1
1: invokevirtual #128                // Method java/lang/reflect/Method.getDeclaringClass:()Ljava/lang/Class;
4: ldc           #198                // class jakarta/jws/WebService
6: invokevirtual #200                // Method java/lang/Class.getAnnotation:(Ljava/lang/Class;)Ljava/lang/annotation/Annotation;
9: ifnull        16
12: iconst_1
13: goto          17
16: iconst_0
17: ireturn
```

**`JaxWsServiceConfiguration.isWebMethod`, offsets 138-176 — the branch reached
when there is no separate SEI (`implInfo.getSEIClass()` null) and the declaring
class is not an interface: `hasWebServiceAnnotation` gates `Modifier.isFinal`/
`isStatic`, in that order:**

```
138: aload_0
139: getfield      #42                 // Field implInfo:Lorg/apache/cxf/jaxws/support/JaxWsImplementorInfo;
142: invokevirtual #134                // Method org/apache/cxf/jaxws/support/JaxWsImplementorInfo.getSEIClass:()Ljava/lang/Class;
145: ifnonnull     185
148: aload_0
149: aload_1
150: invokevirtual #149                // Method hasWebServiceAnnotation:(Ljava/lang/reflect/Method;)Z
153: ifeq          180
156: aload_1
157: invokevirtual #157                // Method java/lang/reflect/Method.getModifiers:()I
160: invokestatic  #160                // Method java/lang/reflect/Modifier.isFinal:(I)Z
163: ifne          180
166: aload_1
167: invokevirtual #157                // Method java/lang/reflect/Method.getModifiers:()I
170: invokestatic  #166                // Method java/lang/reflect/Modifier.isStatic:(I)Z
173: ifne          180
176: iconst_1
```

**`RuntimeModeler.isWebMethodBySpec`, offsets 117-147 — the branch reached when the
method carries no `@WebMethod` of its own and is not `static`/`final`: reads
`@WebService` off the method's OWN declaring class (`ldc_w class jakarta/jws/
WebService`), the same read CXF's `hasWebServiceAnnotation` makes:**

```
117: iload         4
119: ifeq          124
122: iconst_0
123: ireturn
124: aload_1
125: invokevirtual #468                // Method java/lang/reflect/Method.getDeclaringClass:()Ljava/lang/Class;
128: astore        6
130: aload_0
131: aload         6
133: ldc_w         #281                // class jakarta/jws/WebService
136: invokevirtual #150                // Method getAnnotation:(Ljava/lang/Class;Ljava/lang/Class;)Ljava/lang/annotation/Annotation;
139: ifnull        146
142: iconst_1
143: goto          147
146: iconst_0
147: ireturn
```

### Live cross-check: what EACH runtime's own service model derives

`fixture/BillingWebService.java` reproduces `jakarta-jws.yml`'s own scenario:
`@WebService` on the implementor class (no separate SEI), one ordinary
operation (`charge`), one operation INHERITED from a plain, unannotated
superclass (`refund`, from `fixture/AbstractBilling.java`), one `final`
operation (`reconcile`), one `static` method (`staticHelper`) and one
`@WebMethod(exclude = true)` method (`internalOnly`). `fixture/CxfLiveProbe.java`
boots a real `org.apache.cxf.jaxws.support.JaxWsServiceFactoryBean`;
`fixture/RiLiveProbe.java` boots the RI's own model through
`com.oracle.webservices.api.databinding.DatabindingFactory` (the same SPI
`jakarta.xml.ws.Endpoint.create` uses) — both over the IDENTICAL two fixture
classes, each built and run by `_run_live_probe()` off a classpath
`dependency:build-classpath` resolves from `fixture/pom.xml` (CXF) and
`fixture/pom-ri.xml` (the RI), the full runtime rather than just the `javap`
coordinates.

| method on `BillingWebService`/`AbstractBilling` | CXF derives it | RI derives it |
|---|---|---|
| `charge` | yes | yes |
| `refund` | no | no |
| `reconcile` | no | no |
| `staticHelper` | no | no |
| `internalOnly` | no | no |

Raw operation names CXF produced: charge

Raw operation names the RI produced: charge

## Verdict

**CXF agrees with the RI on all three axes.** Every sentence below cites a
table row or a bytecode excerpt above.

1. **`static`/`final` exclusion agrees.** The `JaxWsServiceConfiguration#isWebMethod`
   excerpt (offsets 156-173) invokes `Modifier.isFinal:(I)Z` then
   `Modifier.isStatic:(I)Z`, each gating the `false` branch. `RuntimeModeler#isWebMethodBySpec`
   (offsets 5-16 of its own body, in the invoke-sequence table) invokes the
   identical pair, at offsets 6 (`Modifier.isStatic`) and 13
   (`Modifier.isFinal`) of its own body. The live table confirms it:
   `reconcile` (`final`) and `staticHelper` (`static`) derive `no` under BOTH
   runtimes.
2. **`@WebMethod(exclude = true)` is honoured by both, identically.**
   `JaxWsServiceConfiguration#isOperation`'s own row invokes `WebMethod.exclude:()Z`
   directly (and even throws `JaxWsConfigurationException` if `exclude = true`
   is declared on a method the SEI itself owns — stricter than the RI's silent
   withdrawal, but the *derivation* outcome agrees). `RuntimeModeler#isWebMethodBySpec`'s
   own row invokes `WebMethod.exclude:()Z` too (offset 88 of its body) and, on
   an explicit `@WebMethod` naming a `static`/`final` method, throws
   `RuntimeModelerException` via `RUNTIME_MODELER_WEBMETHOD_MUST_BE_NONSTATICFINAL`
   — the SAME "illegal combination, not a silent withdrawal" reaction CXF has.
   The live table confirms it: `internalOnly` derives `no` under both.
3. **The declaring-class `@WebService` read agrees — this is the axis the
   first pass of this probe got backwards.** `JaxWsServiceConfiguration#hasWebServiceAnnotation`
   (raw excerpt above) is `method.getDeclaringClass().getAnnotation(WebService.class) != null`.
   `RuntimeModeler#isWebMethodBySpec`'s offsets 117-147 (raw excerpt above) —
   reached precisely when the method carries no `@WebMethod` and is not
   `static`/`final` — is the SAME read: `method.getDeclaringClass()` then
   `getAnnotation(WebService.class)`, `ifnull` → not an operation. Both runtimes
   read the annotation off the method's OWN declaring class, never off the
   implementor class they were configured with. For `refund()` — declared only
   in `AbstractBilling`, which carries no `@WebService`, and inherited without
   being overridden by `@WebService class BillingWebService extends
   AbstractBilling` — `getDeclaringClass()` returns `AbstractBilling` under
   BOTH runtimes, so both exclude it. The live table is the direct
   confirmation: `refund` derives `no` under CXF AND under the RI, off the
   IDENTICAL two fixture classes.

**Net: CXF's `isOperation` rule agrees with the JAX-WS RI's on inheritance,
`static`/`final` exclusion, and `@WebMethod(exclude = true)`.** The
`measured:` row is added to `jakarta-jws.yml` per the task's first branch.

## A real finding, found while correcting this one

Both runtimes reject `refund()` — a public method inherited from a plain,
unannotated superclass — because NEITHER treats an inherited method as if its
declaring class were the `@WebService` implementor. `jakarta-jws.yml`'s own
`gate_ancestry` walk (`derive_endpoints.sql`, `A-M15`) does the opposite: it
walks the transitive superclass closure and publishes every public method
found there as an operation of the `@WebService` class, regardless of whether
that ancestor itself carries `@WebService` or the method carries its own
`@WebMethod`. So for the fixture's own `BillingWebService extends
AbstractBilling`, Sextant derives `refund` as an operation — a row NEITHER
runtime would ever serve. This is a fabrication, not an omission, and is
recorded as a new blocker (`jaxws-inherited-unannotated`) rather than fixed in
this task — fixing `gate_ancestry` or its pinning test is explicitly out of
scope here (next task).
