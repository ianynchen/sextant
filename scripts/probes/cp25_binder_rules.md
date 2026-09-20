# CP-25 — binder rules; row 1: Javalin's `ApiBuilder` guard

**Question.** Spec 2026-09-19 §4a lets `javalin-apibuilder.yml` declare `follow_calls:
all` on the `apiBuilder` entry and the `path` prefix — an origin-less body whose
module-local helper calls the combinator follows — on the argument that `ApiBuilder`'s
static verbs register on a THREAD-LOCAL instance the builder refuses to hand out when no
block is open, so a helper that reaches a verb can only ever have been called from inside
one. Row 1 records that argument off the jar: what `ApiBuilder.staticInstance()` reads,
what it throws when the thread-local is empty (the exception class and the message
literal), and a verb's first instruction showing every static verb goes through it.
**Rows 2+ are added by the request-requirements work** (spec §5b–§5d, plan Task 12): the
binder predicates of spring-web 6.1.6, micronaut-http 4.7.6, RESTEasy Reactive,
quarkus-reactive-routes, Javalin's `Validator.get()` and `jakarta.servlet`'s
`getParameter`/`getHeader`, plus `HeadersRequestCondition` dropping `Accept`/`Content-Type`
(A4). This file and `probe.py` are their home; each joins as one more `q<N>_…` function
and one more row, under the same identity discipline.

**What this probe does not settle.** Nothing was run; the cell is a `javap -c -p` read of
one class file. It shows the guard and that ONE verb (`get(String, Handler)`) opens by
calling it; the other twenty-three verb overloads were read by hand for the catalog
comment (each opens with `invokestatic staticInstance`) and are not in the table. It does
not show what `path(String, EndpointGroup)` does to the thread-local prefix stack — that
is `w61_javalin_surface.md`'s `prefixPath` read. And it says nothing about a helper
called from OUTSIDE a block: such a helper throws at runtime and registers nothing, which
is exactly why following the call from inside a block invents no route, but the probe
does not exercise the throw.

**Version scope (§5.4).** `io.javalin:javalin` at Maven coordinate `6.4.0` — and, as the
identity the harness files the cell under, the `Implementation-Version` the jar's own
`META-INF/MANIFEST.MF` reports, read as **6.4.0**. The harness aborts when the archive
reports a version other than the one the run expected. The verdict below is bounded by
that one archive.

**How to run.** `JAVA_HOME=<jdk> PATH=$JAVA_HOME/bin:$PATH bash
scripts/probes/cp25_binder_rules/run.sh`. It resolves the jar into `~/.m2` (Maven and
network on the first run only), then runs `probe.py`, which reads the jar's
`Implementation-Version` off its manifest before it measures anything and prints the
table below. Needs a JDK for `javap`. Not a test: nothing in the suite runs it.

## Observations

Verbatim from `run.sh`'s generated table (`probe.py` prints it; nothing here is typed by
hand). **The column header is the version the jar REPORTED in its own manifest's
`Implementation-Version`, not the version the harness's artifact list asked for.**
`probe.py` reads it off the archive's bytes before it measures anything and ABORTS the
whole run when it disagrees with the version the run expected, rather than filling a
mislabelled column.

```
| what the run read | 6.4.0 |
|---|---|
| artifacts reporting this version | io.javalin:javalin |
| identity read from the archive itself (`Implementation-Version`) | yes |

| # | question | artifact | version | observed |
|---|---|---|---|---|
| 1 | ApiBuilder.staticInstance(): the thread-local field, what it throws with no block open, and a verb's first instruction | `io.javalin:javalin` | 6.4.0 | `field: private static final java.lang.ThreadLocal<io.javalin.router.JavalinDefaultRoutingApi<?>> staticJavalin; ; staticInstance(): getstatic Field staticJavalin:Ljava/lang/ThreadLocal; ; invokevirtual Method java/lang/ThreadLocal.get:()Ljava/lang/Object; ; checkcast class io/javalin/router/JavalinDefaultRoutingApi ; astore_0 ; aload_0 ; ifnonnull ; new class java/lang/IllegalStateException ; dup ; ldc String The static API can only be used within a routes() call. ; invokespecial Method java/lang/IllegalStateException."<init>":(Ljava/lang/String;)V ; athrow ; aload_0 ; areturn ; get(String, Handler) opens with: invokestatic Method staticInstance:()Lio/javalin/router/JavalinDefaultRoutingApi;` |
```

## Verdicts

**Q1 — `follow_calls: all` on `javalin-apibuilder.yml` (§4a).** `ApiBuilder` keeps the
current instance in `private static final ThreadLocal<JavalinDefaultRoutingApi<?>>
staticJavalin`; `staticInstance()` reads it, and when it is `null` — no `apiBuilder { }`
block open on this thread — throws `java.lang.IllegalStateException("The static API can
only be used within a routes() call.")`; `get(String, Handler)` opens with `invokestatic
staticInstance`, and so does every other verb overload (read by hand, see the boundary
above). Therefore a module-local helper whose body reaches an `ApiBuilder` verb can only
have run inside a block — outside one it throws before registering anything — and the
combinator following the CALL from inside the block, with no origin to check because
there is none, attaches only routes Javalin itself registers. That is the one condition
under which origin-less following is honest (A1 excludes it for the Spring router's
`Supplier` bodies, which hand a value back and have no such guard), and it is the fact
the catalog's two `follow_calls: all` declarations cite.

`measured: 2026-09-20`, row 1, on the one archive the scope names.
