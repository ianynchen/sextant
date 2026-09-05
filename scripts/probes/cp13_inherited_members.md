# CP-13 — what three frameworks do with an INHERITED member

**Question.** `docs/principles-sweep-2026-09-05.md` records three Class A
Majors that encode the same invented rule — **a type's members are the ones it
DECLARES** — and grades all three `read`, with the framework half explicitly
unverified in each:

| finding | the rule that was encoded | what this probe asks |
|---|---|---|
| `A-M13` | `derived_resource._methods` keys on `enclosing`, so a repository's query methods are the ones it declares | which methods Spring Data enumerates as a repository's own |
| `A-M14` | CRUD exclusion is `if name in crud_methods`, a bare identifier | how Spring Data decides a method IS one of the base contract's |
| `A-M15` | `members: public_methods` joins `gate_types` on `s.enclosing` | which members the JAX-WS reference implementation exposes as operations |

**The language half was never in doubt** — JLS 8.2 (a class inherits its
superclass's members), 9.2 and 9.4.1 (an interface inherits its
superinterfaces'), and 8.4.2 (a method's signature is its name AND its
parameter types in order). What needed measuring is whether each FRAMEWORK acts
on it, and that turns out to be answerable from bytecode without deploying
anything: in every case the question reduces to **which reflective enumeration
the framework calls** — `Class.getMethods()`, which includes inherited public
methods, or `getDeclaredMethods()`, which does not — and **what it then filters
out of the result**. Both are instructions.

**What this probe does not settle, and the verdict must not be read past it.**
Nothing here was deployed. It records the enumeration and the filters; it does
not observe a served `/search/` route or a published WSDL operation. A live run
stays rank 2 and rank 11 of the sweep's own probe backlog, and `A-M14` is left
OPEN on the strength of what this measured rather than closed by it.

**Extended, 2026-09-05, by the round-1 review's two Criticals.** Both are
fabrications the round-1b fix pass introduced, and both have the same cause:
this probe measured the ENUMERATION and left half the FILTER unopened, and the
implementer reasoned about the other half rather than measuring it (§5.4).
Questions 5, 6 and 7 close exactly the halves that were reasoned about.

| finding | what was reasoned about rather than measured | which question closes it |
|---|---|---|
| CRITICAL 1 (`A-M15`) | what `Class.getMethods()` returns for an OVERRIDE — the walk enumerates one row per declaration where the enumeration yields one per SIGNATURE | Q5 |
| CRITICAL 2 (`A-M13`) | `isCustomMethod`, recorded by NAME in row 1 and never opened — Spring Data REST does not serve a custom-fragment method | Q6, Q7 |

**Version scope (§5.4).** Read against **spring-data-commons 3.2.5 and 4.1.1,
and jaxws-rt 4.0.2**, plus — for Q5 alone, which is the JDK's own behaviour
rather than a framework's — **the JDK the probe process itself reported**
(`java.version`, printed into the table's own version column rather than taken
from the `javac` on PATH). Two spring-data-commons minors rather than one for CP-12's
reason: an enumeration is a version-scoped fact and one reading cannot say
whether it is stable. 3.2.5 is what `fixtures/orders-service` resolves through
Boot 3.x; 4.1.1 is the current generation. jaxws-rt 4.0.2 is the Jakarta EE 10
reference implementation — the one `jakarta-jws.yml` claims to have been
"verified against BOTH reference implementations" without naming either
(`A-Mi7`); this probe names one and measures it. **The Apache CXF half stays
unmeasured**, and `A-Mi7` stays open for it.

**How to run.** `bash scripts/probes/cp13_inherited_members/run.sh`. It resolves
each artifact through Maven (network on the first run only, cached in `~/.m2`
afterwards) and asks `javap -p -c` six of the seven questions. Q5 is the one
that cannot be answered by reading bytecode — the answer is the JDK's runtime
behaviour rather than an instruction — so it compiles the override pair with
`javac` into a temporary directory and runs it. Needs a JDK and Maven. Not a
test: nothing in the suite runs it, and NFR-1's no-network rule governs the
suite rather than evidence gathering.

## Expectation table

| # | Under test | Expected |
|---|---|---|
| 1 | Spring Data's query-method enumeration | `Class.getMethods()` — inherited interface methods included — then `ClassUtils.getMostSpecificMethod`, then a filter excluding base-class and custom methods |
| 2 | Spring Data's base-method lookup | a comparison on the method's NAME, its parameter COUNT and its parameter TYPES — a signature, not an identifier |
| 3 | JAX-WS's exposed-member enumeration | `Class.getMethods()` on the implementor class — inherited public methods included — with `getDeclaringClass()` used to drop `java.lang.Object`'s, then `isWebMethodBySpec` |
| 4 | JAX-WS's per-method test | `static` and `final` excluded, plus the declaring-class check row 3 uses |
| 5 | what `Class.getMethods()` returns for an override pair | ONE entry for the overridden signature, declared by the OVERRIDING class, beside the inherited method that is not overridden |
| 6 | what makes a Spring Data method CUSTOM | resolution through the FRAGMENT composition — a method a fragment supplies is a custom method and therefore not a query method |
| 7 | which superinterfaces become fragments | the repository interface's own direct superinterfaces, filtered to those NOT carrying `@NoRepositoryBean` |

## Observations

Verbatim from `run.sh`'s generated tables (`probe.py` prints them; nothing here
is typed by hand). **Every column header of the first table is a version the JAR
itself reported, and not the version the coordinate list asked for** — out of
each manifest's `Implementation-Version`. `probe.py` reads the value out of the
archive it opened and ABORTS the whole run when it disagrees with the coordinate
that resolved the jar, rather than filling a mislabelled column; that is CP-5's
failure, which printed a version it believed beside output from a version it had
not run.

Rows 1 and 2 are scanned over the WHOLE class rather than one method body, and
that is stated because it bounds them: a framework predicate is not always in
the method that names it — `calculateQueryMethods` at 3.2.5 puts its filter in a
lambda, and `RepositoryAwareMethodLookup`'s comparisons are spread across
several one-line private methods. The filter that survives is narrow enough for
the cell to be an answer rather than a dump: only `java/lang/Class` and
`java/lang/reflect` calls and the named framework predicates, which is exactly
the set that decides membership. Row 7 is scanned whole for the same reason:
`getFragmentInterfaces` puts its predicate in `isCandidate`, reached through a
lambda.

Row 5 is not an instruction sequence at all — it is what the compiled pair
PRINTED. `AbstractBilling` declares `refund(String)` and `reconcile(String)`;
`BillingWebService extends AbstractBilling` declares `refund(String)` and
nothing else; the cell is every `getMethods()` entry not declared by
`java.lang.Object`, as `declaringClass#name`, sorted. Its version column is
`java.version` as the running process reported it.

| what the run read | 3.2.5 | 4.0.2 | 4.1.1 |
|---|---|---|---|
| artifacts reporting this version | spring-data-commons | jaxws-rt | spring-data-commons |
| identity read from the archive itself | yes | yes | yes |

| # | question | artifact | version | observed |
|---|---|---|---|---|
| 1a | `RepositoryInformationSupport.calculateQueryMethods` | `spring-data-commons` | 3.2.5 | `invokestatic Method java/lang/reflect/Modifier.isStatic:(I)Z ; invokevirtual Method isCustomMethod:(Ljava/lang/reflect/Method;)Z ; invokevirtual Method isBaseClassMethod:(Ljava/lang/reflect/Method;)Z ; invokevirtual Method java/lang/Class.getMethods:()[Ljava/lang/reflect/Method; ; invokestatic Method org/springframework/util/ClassUtils.getMostSpecificMethod:(Ljava/lang/reflect/Method;Ljava/lang/Class;)Ljava/lang/reflect/Method;` |
| 1b | `RepositoryInformationSupport.calculateQueryMethods` | `spring-data-commons` | 4.1.1 | `invokevirtual Method org/springframework/data/repository/core/RepositoryInformationSupport$DefaultQueryMethods.isQueryMethod:(Ljava/lang/reflect/Method;)Z ; invokestatic Method java/lang/reflect/Modifier.isStatic:(I)Z ; invokevirtual Method isCustomMethod:(Ljava/lang/reflect/Method;)Z ; invokevirtual Method isBaseClassMethod:(Ljava/lang/reflect/Method;)Z ; invokevirtual Method java/lang/Class.getMethods:()[Ljava/lang/reflect/Method; ; invokestatic Method org/springframework/util/ClassUtils.getMostSpecificMethod:(Ljava/lang/reflect/Method;Ljava/lang/Class;)Ljava/lang/reflect/Method; ; invokevirtual Method isQueryMethodCandidate:(Ljava/lang/reflect/Method;)Z` |
| 2a | `MethodLookups$RepositoryAwareMethodLookup` | `spring-data-commons` | 3.2.5 | `invokevirtual Method java/lang/reflect/Method.getParameterTypes:()[Ljava/lang/Class; ; invokevirtual Method java/lang/reflect/Method.getParameterCount:()I ; invokevirtual Method java/lang/reflect/Method.getName:()Ljava/lang/String;` |
| 2b | `MethodLookups$RepositoryAwareMethodLookup` | `spring-data-commons` | 4.1.1 | `invokevirtual Method java/lang/reflect/Method.getParameterTypes:()[Ljava/lang/Class; ; invokevirtual Method java/lang/reflect/Method.getParameterCount:()I ; invokevirtual Method java/lang/reflect/Method.getName:()Ljava/lang/String;` |
| 3 | `RuntimeModeler.processClass` | `jaxws-rt` | 4.0.2 | `invokevirtual Method java/lang/Class.getMethods:()[Ljava/lang/reflect/Method; ; invokevirtual Method java/lang/reflect/Method.getDeclaringClass:()Ljava/lang/Class; ; invokevirtual Method isWebMethodBySpec:(Ljava/lang/reflect/Method;Ljava/lang/Class;)Z` |
| 4 | `RuntimeModeler.isWebMethodBySpec` | `jaxws-rt` | 4.0.2 | `invokestatic Method java/lang/reflect/Modifier.isStatic:(I)Z ; invokestatic Method java/lang/reflect/Modifier.isFinal:(I)Z ; invokevirtual Method java/lang/reflect/Method.getDeclaringClass:()Ljava/lang/Class;` |
| 5 | `Class.getMethods()` over an override pair | `java.lang.Class` | 26.0.2.1 | `AbstractBilling#reconcile ; BillingWebService#refund` |
| 6a | `DefaultRepositoryInformation.isCustomMethod` | `spring-data-commons` | 3.2.5 | `invokevirtual Method org/springframework/data/repository/core/support/RepositoryComposition.getMethod:(Ljava/lang/reflect/Method;)Ljava/lang/reflect/Method;` |
| 6b | `DefaultRepositoryInformation.isCustomMethod` | `spring-data-commons` | 4.1.1 | `invokevirtual Method org/springframework/data/repository/core/support/RepositoryComposition.getMethod:(Ljava/lang/reflect/Method;)Ljava/lang/reflect/Method;` |
| 7a | `FragmentMetadata` (`getFragmentInterfaces`/`isCandidate`) | `spring-data-commons` | 3.2.5 | `invokeinterface InterfaceMethod org/springframework/core/type/ClassMetadata.getInterfaceNames:()[Ljava/lang/String; ; ldc class org/springframework/data/repository/NoRepositoryBean ; invokeinterface InterfaceMethod org/springframework/core/type/AnnotationMetadata.hasAnnotation:(Ljava/lang/String;)Z` |
| 7b | `FragmentMetadata` (`getFragmentInterfaces`/`isCandidate`) | `spring-data-commons` | 4.1.1 | `invokeinterface InterfaceMethod org/springframework/core/type/ClassMetadata.getInterfaceNames:()[Ljava/lang/String; ; ldc class org/springframework/data/repository/NoRepositoryBean ; invokeinterface InterfaceMethod org/springframework/core/type/AnnotationMetadata.hasAnnotation:(Ljava/lang/String;)Z` |

## Verdict

1. **`A-M13` is confirmed and its fix is a mirror — of BOTH halves, since
   2026-09-05.** Spring Data enumerates `getRepositoryInterface().getMethods()`
   at both measured minors, so an inherited query method IS one of the
   repository's own. But `getMethods()` is only the enumeration: row 1 also
   records `isCustomMethod` in the filter, and the first fix read the
   enumeration and stopped. **Rows 6 and 7 open the filter.** A method the
   FRAGMENT composition resolves is a custom method (6), and the fragments are
   the repository interface's own direct superinterfaces minus those carrying
   `@NoRepositoryBean` (7) — identical bytecode at 3.2.5 and 4.1.1. So
   `interface OrderRepository extends CrudRepository<Order, Long>,
   OrderRepositoryCustom` serves NO `/search/` route for
   `OrderRepositoryCustom`'s methods, while a `@NoRepositoryBean` base's query
   methods ARE served. `derived_resource` now crosses a module-local
   superinterface only where it carries that annotation.
2. **`A-M14` is confirmed and NOT fixed.** The base-method lookup compares a
   name, a parameter count and parameter types — a signature (JLS 8.4.2) —
   where `spring-data-rest.yml`'s `crud_methods` is 25 bare identifiers. So a
   derived query method named `findAll(String tenantId)` is a query method to
   the framework and is dropped by us. Closing it needs `crud_methods` to carry
   parameter types per contract per store AND the type-variable resolution the
   framework does through `getMostSpecificMethod`, neither of which the fact
   stream supports today. Stated in `docs/COVERAGE.md` rather than half-built
   (§8.1 rule 4).
3. **`A-M15` is confirmed.** The JAX-WS RI walks the implementor class's
   `getMethods()` — inherited public methods included — drops only those
   declared by `java.lang.Object`, and then applies `isWebMethodBySpec`, which
   excludes `static` and `final`. Our SQL joins the gate on `s.enclosing` and
   excludes `static` and `synthetic`. **Two divergences, not one**: the
   inherited members are absent, and a `final` public method is exposed by us
   and not by the RI.
4. **An OVERRIDE is one member, not two, and that is now measured too (Q5).**
   `getMethods()` — the enumeration rows 1 and 3 both record — returns exactly
   one entry per SIGNATURE, declared by the overriding class. The first
   `A-M15` fix widened the walk to every ancestor's declared members and
   published one row per declaration, so an overridden operation shipped twice
   and an override carrying `@WebMethod(exclude = true)` withdrew only its own
   row while the base's went out under the same name. `derive_endpoints.sql`
   now keeps the nearest declaration of each `(name, parameter types)` and
   applies the exclusions and the annotation anti-join to that one.

   **Its boundary.** Q5 is the JDK's behaviour, not JAX-WS's, and it was
   measured on ONE JDK — the version in the table. It stops being evidence for
   this repository the day the enumeration `RuntimeModeler.processClass` calls
   stops being `Class.getMethods()`, which row 3 is what re-checks.
5. **The RI is one implementation.** Apache CXF is the other and is not
   measured here, so every row above is scoped to jaxws-rt 4.0.2 and says so.
