# W63 — Apache CXF's implementor rule, measured against the JAX-WS RI's

**Question.** `jakarta-jws.yml`'s `members: public_methods` rule derives a
`@WebService` class's operations by walking `Class.getMethods()` (inherited
public methods included), excluding `static` and `final` methods, and honouring
`@WebMethod(exclude = true)`. That rule was measured against ONE JAX-WS
implementation — jaxws-rt 4.0.2, the reference implementation, `cp13_inherited_members.md`
Q3/Q4 — and the catalog's own comment (`A-Mi7`) has said since 2026-09-05 that
**"Apache CXF is not measured"**, carrying `apache-cxf` on the SOAP row of the
delivery register as "version-scoped, not settled". This task measures it: does
CXF's JAX-WS frontend decide operation membership the same way, for the same
three questions — inheritance, `static`/`final`, `@WebMethod(exclude = true)` —
or does it diverge?

CXF's own answer lives in
`org.apache.cxf.jaxws.support.JaxWsServiceConfiguration.isOperation(Method)`
(and its `JaxWsImplementorInfo` collaborator), which the task brief says
delegates to `org.apache.cxf.service.factory.ReflectionServiceFactoryBean` /
`AbstractServiceConfiguration`. Both class names resolve to a DIFFERENT package
than the brief assumed at 4.0.5 — see "Where the brief's two class names
actually live" below, the first thing this probe found.

**Version scope (§5.4).** Read against **cxf-rt-frontend-jaxws 4.0.5 and
cxf-core 4.0.5** — the two coordinates the task brief names — plus
**cxf-rt-wsdl 4.0.5**, where `ReflectionServiceFactoryBean` and
`AbstractServiceConfiguration` actually live at this version, and
**jakarta.jws-api 3.0.0**, the annotation types both `isOperation` paths read
(`@WebMethod`'s `exclude` attribute, `@WebService`). All four are resolved
`-Dtransitive=false` for the `javap` half; the live cross-check below needs
CXF's full transitive runtime and resolves that separately through
`fixture/pom.xml`.

**How to run.** `bash scripts/probes/w63_cxf_web_method_rule/run.sh`. Resolves
the four artifacts through Maven (network on the first run only, cached in
`~/.m2` afterwards), reads the version each jar states for itself, `javap -p -c`
every method under test, and — as a second, independent check — compiles and
runs `scripts/probes/w63_cxf_web_method_rule/fixture/*.java` against a real
`JaxWsServiceFactoryBean` to read what CXF's own service model actually
derives. Needs a JDK and Maven; the live half needs network access to CXF's
full transitive dependency set (`dependency:build-classpath`) the first time
it runs.

## Expectation table

| # | If | then |
|---|---|---|
| 1 | CXF's per-method test invokes `Modifier.isStatic` **and** `Modifier.isFinal` | same rule as the RI on this axis; a necessary condition for shipping the CXF `measured:` row |
| 2 | CXF's per-method test does NOT invoke `Modifier.isFinal` | CXF exposes `final` methods; the catalog's exclusion is RI-only and needs a per-catalog switch — record as a spec item |
| 3 | An operation inherited from a PLAIN (unannotated) superclass is exposed the same as one declared directly on the `@WebService` class | same rule as the RI on this axis too; combined with row 1, ships the CXF `measured:` row |
| 4 | Such an inherited operation is NOT exposed | CXF's rule diverges from the RI on inheritance; the catalog's `gate_ancestry` walk is RI-only — record as a spec item, not a catalog change |

Rows 3/4 are not in the task brief's own two-row table (brief only names the
`static`/`final` axis), but the task's own opening question names all three —
inheritance, `static`/`final`, `exclude` — as what is being measured, and the
catalog's own comment (`jakarta-jws.yml:137-148`) calls the inheritance rule
"the sharper half". A verdict that checked only `static`/`final` and skipped
inheritance would leave exactly the axis the catalog itself flags as sharpest
unmeasured.

## Observations

Verbatim from `scripts/probes/w63_cxf_web_method_rule/run.sh`, which runs
`sweep.py`. **Every version in the table below is the one the JAR itself
reported** — out of its own `META-INF/maven/.../pom.properties` —
and **not the version the coordinate list asked for**; `checked` compares
the two and ABORTS the whole run when they disagree.

| what the run read | 4.0.5 | 3.0.0 |
|---|---|---|
| artifacts reporting this version | cxf-rt-frontend-jaxws, cxf-core, cxf-rt-wsdl | jakarta.jws-api |
| where the jar states it | pom.properties | pom.properties |

### Where the brief's two class names actually live at 4.0.5

The task brief names `org.apache.cxf.service.factory.ReflectionServiceFactoryBean`
/ `AbstractServiceConfiguration` inside `cxf-core`. `unzip -l` on
`cxf-core-4.0.5.jar` carries no such package. `mvn dependency:tree` off
`cxf-rt-frontend-jaxws:4.0.5` finds both classes one hop further, repackaged
as `org.apache.cxf.wsdl.service.factory.*` inside `cxf-rt-wsdl` — pulled in
transitively through `cxf-rt-bindings-soap`, not through `cxf-core` at all.

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

### Live cross-check: what CXF's own service model derives

`fixture/BillingWebService.java` reproduces `jakarta-jws.yml`'s own scenario:
`@WebService` on the implementor class (no separate SEI), one ordinary
operation (`charge`), one operation INHERITED from a plain, unannotated
superclass (`refund`, from `fixture/AbstractBilling.java`), one `final`
operation (`reconcile`), one `static` method (`staticHelper`) and one
`@WebMethod(exclude = true)` method (`internalOnly`). `fixture/LiveProbe.java`
boots a real `org.apache.cxf.jaxws.support.JaxWsServiceFactoryBean` over it and
prints every operation name CXF's own `ServiceInfo` carries — built and run by
`live_operations()` off a classpath `dependency:build-classpath` resolves from
`fixture/pom.xml` (the full CXF runtime, not just the two `javap` coordinates).

| method on `BillingWebService`/`AbstractBilling` | CXF derived it as an operation |
|---|---|
| `charge` | yes |
| `refund` | no |
| `reconcile` | no |
| `staticHelper` | no |
| `internalOnly` | no |

Raw operation QNames CXF produced: {http://soap.example.com/}charge

## Verdict

**Two of the three axes agree with the RI; the third — inheritance — diverges,
and it is the one the catalog itself calls "the sharper half".**

1. **`static`/`final` exclusion agrees (expectation row 1).** The
   `JaxWsServiceConfiguration#isWebMethod(Method)` row above invokes
   `Modifier.isFinal:(I)Z` and `Modifier.isStatic:(I)Z` back to back, both
   gating the `true` branch — the identical pair `RuntimeModeler.isWebMethodBySpec`
   invokes at jaxws-rt 4.0.2 (`cp13_inherited_members.md` row 4). The live table
   confirms it: `reconcile` (`final`) and `staticHelper` (`static`) both derive
   `no`.
2. **`@WebMethod(exclude = true)` is honoured, in fact checked TWICE (expectation
   row 1's neighbour, not its own numbered row but the same axis the task names).**
   `JaxWsServiceConfiguration#isOperation`'s own row invokes
   `WebMethod.exclude:()Z` directly (and even THROWS
   `JaxWsConfigurationException` if `exclude = true` is declared on a method the
   SEI itself owns — CXF treats that combination as a configuration error, a
   stricter reaction than the RI's silent withdrawal, but the *derivation*
   outcome — no operation — agrees). `isWebMethod` invokes `WebMethod.exclude:()Z`
   a second time for the general path. The live table confirms it: `internalOnly`
   derives `no`.
3. **Inheritance from a plain superclass DIVERGES (expectation row 4, not row
   3).** `JaxWsServiceConfiguration#hasWebServiceAnnotation` — the predicate
   `isWebMethod` calls before it will ever reach the `static`/`final` check —
   invokes `Method.getDeclaringClass()` and then `Class.getAnnotation(WebService.class)`
   on THAT class, not on the implementor class CXF was configured with. For a
   method inherited from a plain superclass (`AbstractBilling`, which carries no
   `@WebService`), `getDeclaringClass()` returns `AbstractBilling`, whose
   `@WebService` annotation is absent — so `hasWebServiceAnnotation` returns
   `false`, and `isWebMethod` falls straight to its `false` branch without ever
   reaching the `Modifier` checks. The live table is the direct confirmation:
   `refund` — declared only in `AbstractBilling`, inherited by
   `BillingWebService` without being overridden — derives `no`, while `charge`,
   declared directly on the annotated class, derives `yes`. **The JAX-WS RI does
   the opposite** (CP-13 Q3: `RuntimeModeler.processClass` walks
   `Class.getMethods()` on the implementor and drops only methods
   `java.lang.Object` declares — it never re-checks which class carries
   `@WebService`). So a `@WebService public class BillingWebService extends
   AbstractBilling` publishes `refund` under jaxws-rt and silently drops it
   under CXF: the exact silent-omission failure mode `A-M15`'s own fix
   description warns about, now shown to recur on the OTHER implementation this
   catalog claims to cover.

**Net: CXF diverges.** Two axes agree, but the task's own opening line names
all three as what a `measured:` claim for CXF would have to cover, and the
third does not hold. No catalog row is added; the divergence is recorded in
`docs/COVERAGE.md` §5.3 and `docs/java-kotlin-delivery-list.md` instead of a
`measured:` entry, per the task's own second branch.
