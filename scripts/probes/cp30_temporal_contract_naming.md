# CP-30 — Temporal's naming rules: which member names a workflow method, the activity name's empty-string test and title-casing, the two qualification predicates, the Spring Boot starter annotations, argument-0 naming on the client, and the task queue's declaration sites

**Question.** `docs/superpowers/specs/2026-09-22-temporal-and-eventbus-design.md` §0a states
eight framework facts (M1–M5, M10) that the Temporal catalogs Tasks 3, 5, 8 and 9 build on,
each asserted from a `javap` read the spec's own table cites by offset but that no probe in
this repository had yet reproduced as a generated, re-runnable table (GUIDELINES §5.4, §8.1
rule 1 — "measured before it is built on", not taken from a table someone typed by hand).
`.superpowers/sdd/2026-09-22-temporal-and-eventbus/task-2-brief.md` asks this probe to
answer eight of those questions and no others: Q1 which name
`POJOWorkflowMethodMetadata`'s constructor takes on the `WORKFLOW` branch versus every other
kind (M1); Q2/Q3 `POJOActivityMethodMetadata`'s empty-name test and the prefix it guards, and
`getActivityNameFromMethod`'s title-casing (M2, M3); Q4/Q5 the two interfaces'
`validateAndQualifiedFor*Method` predicates, side by side (M4); Q6 the three Spring Boot
starter annotations' attributes (M5's annotation half); Q7
`WorkflowClient.newUntypedWorkflowStub` and `WorkflowStub.signal`/`query`/`update`'s
argument-0 naming (M10); Q8 the task queue's declaration sites across `WorkerFactory` and
every `*Options$Builder` class the SDK ships (M5's builder half). The brief is explicit that
the expected column beside each question is a prediction to check, not an assumption to
encode: "make the probe produce them, not assume them."

**Two of the eight rows came back different from what M4 and M5 state, and this is the
headline finding, not a footnote.** See the two starred verdicts (Q5, Q8) below.

**What this probe does not settle.** Nothing was run; every cell is a `javap` read of a
class file in one of two jars. It measures the compiled `1.27.0` surface, not the Java
source or the reference documentation. Q1–Q5 dump a method's FULL instruction body rather
than a hand-picked excerpt, so nothing that disagreed with the brief's prediction could have
been filtered out before a reader sees it. The fixture row Task 6 adds — the owners a
compiled Temporal workflow/activity pair actually names at its call sites, the way CP-27's
row 16 does for Spring Integration — is not in this probe yet; `run.sh`'s `specs` array ends
after the two jars, with a comment marking exactly where Task 6's fixture spec goes. Nothing
here measures the resolve-layer rules the spec specifies, or Nexus service naming beyond
`NexusServiceImpl`'s two attributes (Q6).

**Version scope (§5.4).** `io.temporal:temporal-sdk` and
`io.temporal:temporal-spring-boot-autoconfigure` at Maven coordinate **1.27.0** — the version
`run.sh`'s `ARTIFACTS` array requested and Maven resolved from Maven Central into `~/.m2`.
**Neither jar's own bytes state that version anywhere**: this is a genuine departure from
every probe CP-27 through CP-29 ran, all of which read `Implementation-Version` off the
jar's manifest and aborted when it disagreed. `temporal-sdk-1.27.0.jar`'s manifest carries
only `Manifest-Version: 1.0` and `Multi-Release: true`; `temporal-spring-boot-autoconfigure-1.27.0.jar`'s
carries only `Manifest-Version: 1.0`. Neither ships a `META-INF/maven/*/pom.properties`, and
no class in either jar's constant pool holds the literal string `1.27.0` (checked
exhaustively over every `.class` entry). So the column below is the version `run.sh`'s
`ARTIFACTS` parameter requested, not the version either archive's own bytes state — the one
fact §5.4 asks a probe to read off the run's own output simply is not present in these two
jars. What `probe.py` CAN read off the archive's own bytes is its SHA-1, which it recomputes
from the jar it opened and checks against the `.jar.sha1` sidecar Maven wrote beside it when
`mvn dependency:get` resolved this exact coordinate from Maven Central — and aborts if they
disagree, the same "fail loud on a mismatch" shape §5.4 asks for, applied to the one
self-stated fact that exists. Every verdict below is bounded by those two archives.

**How to run.** `JAVA_HOME=<jdk> PATH=$JAVA_HOME/bin:$PATH bash
scripts/probes/cp30_temporal_contract_naming/run.sh`. It resolves the two jars into `~/.m2`
(Maven and network only if either is missing — both were already present from Task 1's
environment) then runs `probe.py`, which reads each jar's `Implementation-Version` off its
manifest where one exists, falls back to a SHA-1 check against Maven's own sidecar where it
does not, and prints the table below. Needs a JDK for `javap` and Maven for the
`dependency:get` fallback. Not a test: nothing in the suite runs it.

## Observations

Verbatim from `run.sh`'s generated table (`probe.py` prints it; nothing here is typed by
hand). **The column header is not the version either archive's own manifest reports** — it
is the version `run.sh`'s `ARTIFACTS` parameter requested — because unlike CP-27's jars,
neither `temporal-sdk-1.27.0.jar` nor `temporal-spring-boot-autoconfigure-1.27.0.jar`
reports an `Implementation-Version` at all, so `probe.py` cannot abort on a manifest
mismatch here; it
aborts instead on a SHA-1 mismatch against Maven's own `.jar.sha1` sidecar, which the second
observation row states as "verified" for both jars. Every cell in the second table is a
`javap -p -s`/`-c` read of the named class or classes in the named artifact.

```
| what the run read | 1.27.0 |
|---|---|
| artifacts reporting this version | io.temporal:temporal-sdk, io.temporal:temporal-spring-boot-autoconfigure |
| identity read from the archive itself (`Implementation-Version`) | NO |
| SHA-1 verified against `mvn`'s own `.jar.sha1` sidecar (used only where the manifest reports no version) | verified, verified |

| # | question | artifact | version | observed |
|---|---|---|---|---|
| 1 | `POJOWorkflowMethodMetadata`'s constructor: which name each branch takes | `io.temporal:temporal-sdk` | 1.27.0 | `0: aload_0 ; 1: invokespecial Method java/lang/Object."<init>":()V ; 4: aload_0 ; 5: aload_1 ; 6: invokestatic Method java/util/Objects.requireNonNull:(Ljava/lang/Object;)Ljava/lang/Object; ; 9: checkcast class io/temporal/common/metadata/POJOWorkflowMethod ; 12: putfield Field workflowMethod:Lio/temporal/common/metadata/POJOWorkflowMethod; ; 15: aload_0 ; 16: getfield Field workflowMethod:Lio/temporal/common/metadata/POJOWorkflowMethod; ; 19: invokevirtual Method io/temporal/common/metadata/POJOWorkflowMethod.getType:()Lio/temporal/common/metadata/WorkflowMethodType; ; 22: getstatic Field io/temporal/common/metadata/WorkflowMethodType.NONE:Lio/temporal/common/metadata/WorkflowMethodType; ; 25: if_acmpne ; 28: new class java/lang/IllegalArgumentException ; 31: dup ; 32: new class java/lang/StringBuilder ; 35: dup ; 36: invokespecial Method java/lang/StringBuilder."<init>":()V ; 39: ldc String Method \" ; 41: invokevirtual Method java/lang/StringBuilder.append:(Ljava/lang/String;)Ljava/lang/StringBuilder; ; 44: aload_1 ; 45: invokevirtual Method io/temporal/common/metadata/POJOWorkflowMethod.getMethod:()Ljava/lang/reflect/Method; ; 48: invokevirtual Method java/lang/reflect/Method.getName:()Ljava/lang/String; ; 51: invokevirtual Method java/lang/StringBuilder.append:(Ljava/lang/String;)Ljava/lang/StringBuilder; ; 54: ldc String \" is not annotated with @WorkflowMethod, @SignalMethod @QueryMethod, @UpdateMethod, or @UpdateValidatorMethod ; 56: invokevirtual Method java/lang/StringBuilder.append:(Ljava/lang/String;)Ljava/lang/StringBuilder; ; 59: invokevirtual Method java/lang/StringBuilder.toString:()Ljava/lang/String; ; 62: invokespecial Method java/lang/IllegalArgumentException."<init>":(Ljava/lang/String;)V ; 65: athrow ; 66: aload_0 ; 67: aload_2 ; 68: invokestatic Method java/util/Objects.requireNonNull:(Ljava/lang/Object;)Ljava/lang/Object; ; 71: checkcast class java/lang/Class ; 74: putfield Field workflowInterface:Ljava/lang/Class; ; 77: aload_0 ; 78: getfield Field workflowMethod:Lio/temporal/common/metadata/POJOWorkflowMethod; ; 81: invokevirtual Method io/temporal/common/metadata/POJOWorkflowMethod.getNameFromAnnotation:()Ljava/util/Optional; ; 84: astore_3 ; 85: aload_0 ; 86: getfield Field workflowMethod:Lio/temporal/common/metadata/POJOWorkflowMethod; ; 89: invokevirtual Method io/temporal/common/metadata/POJOWorkflowMethod.getType:()Lio/temporal/common/metadata/WorkflowMethodType; ; 92: getstatic Field io/temporal/common/metadata/WorkflowMethodType.WORKFLOW:Lio/temporal/common/metadata/WorkflowMethodType; ; 95: if_acmpne ; 98: aload_0 ; 99: aload_3 ; 100: aload_2 ; 101: invokevirtual Method java/lang/Class.getSimpleName:()Ljava/lang/String; ; 104: invokevirtual Method java/util/Optional.orElse:(Ljava/lang/Object;)Ljava/lang/Object; ; 107: checkcast class java/lang/String ; 110: putfield Field name:Ljava/lang/String; ; 113: goto ; 116: aload_0 ; 117: aload_3 ; 118: aload_1 ; 119: invokevirtual Method io/temporal/common/metadata/POJOWorkflowMethod.getMethod:()Ljava/lang/reflect/Method; ; 122: invokevirtual Method java/lang/reflect/Method.getName:()Ljava/lang/String; ; 125: invokevirtual Method java/util/Optional.orElse:(Ljava/lang/Object;)Ljava/lang/Object; ; 128: checkcast class java/lang/String ; 131: putfield Field name:Ljava/lang/String; ; 134: aload_0 ; 135: aload_0 ; 136: getfield Field workflowMethod:Lio/temporal/common/metadata/POJOWorkflowMethod; ; 139: invokevirtual Method io/temporal/common/metadata/POJOWorkflowMethod.getDescriptionFromAnnotation:()Ljava/util/Optional; ; 142: ldc String ; 144: invokevirtual Method java/util/Optional.orElse:(Ljava/lang/Object;)Ljava/lang/Object; ; 147: checkcast class java/lang/String ; 150: putfield Field description:Ljava/lang/String; ; 153: return` |
| 2 | `POJOActivityMethodMetadata`'s constructor: the empty-name test and the prefix composition it guards | `io.temporal:temporal-sdk` | 1.27.0 | `0: aload_0 ; 1: invokespecial Method java/lang/Object."<init>":()V ; 4: aload_0 ; 5: aload_1 ; 6: invokestatic Method java/util/Objects.requireNonNull:(Ljava/lang/Object;)Ljava/lang/Object; ; 9: checkcast class java/lang/reflect/Method ; 12: putfield Field method:Ljava/lang/reflect/Method; ; 15: aload_0 ; 16: aload_2 ; 17: invokestatic Method java/util/Objects.requireNonNull:(Ljava/lang/Object;)Ljava/lang/Object; ; 20: checkcast class java/lang/Class ; 23: putfield Field interfaceType:Ljava/lang/Class; ; 26: aload_1 ; 27: ldc class io/temporal/activity/ActivityMethod ; 29: invokevirtual Method java/lang/reflect/Method.getAnnotation:(Ljava/lang/Class;)Ljava/lang/annotation/Annotation; ; 32: checkcast class io/temporal/activity/ActivityMethod ; 35: astore ; 37: aload_0 ; 38: aload ; 40: ifnull ; 43: aload ; 45: invokeinterface InterfaceMethod io/temporal/activity/ActivityMethod.name:()Ljava/lang/String; ; 50: invokevirtual Method java/lang/String.isEmpty:()Z ; 53: ifne ; 56: aload ; 58: invokeinterface InterfaceMethod io/temporal/activity/ActivityMethod.name:()Ljava/lang/String; ; 63: goto ; 66: new class java/lang/StringBuilder ; 69: dup ; 70: invokespecial Method java/lang/StringBuilder."<init>":()V ; 73: aload_3 ; 74: invokeinterface InterfaceMethod io/temporal/activity/ActivityInterface.namePrefix:()Ljava/lang/String; ; 79: invokevirtual Method java/lang/StringBuilder.append:(Ljava/lang/String;)Ljava/lang/StringBuilder; ; 82: aload_1 ; 83: invokestatic Method getActivityNameFromMethod:(Ljava/lang/reflect/Method;)Ljava/lang/String; ; 86: invokevirtual Method java/lang/StringBuilder.append:(Ljava/lang/String;)Ljava/lang/StringBuilder; ; 89: invokevirtual Method java/lang/StringBuilder.toString:()Ljava/lang/String; ; 92: putfield Field name:Ljava/lang/String; ; 95: return` |
| 3 | `POJOActivityMethodMetadata.getActivityNameFromMethod` | `io.temporal:temporal-sdk` | 1.27.0 | `0: aload_0 ; 1: invokevirtual Method java/lang/reflect/Method.getName:()Ljava/lang/String; ; 4: astore_1 ; 5: new class java/lang/StringBuilder ; 8: dup ; 9: invokespecial Method java/lang/StringBuilder."<init>":()V ; 12: aload_1 ; 13: iconst_0 ; 14: iconst_1 ; 15: invokevirtual Method java/lang/String.substring:(II)Ljava/lang/String; ; 18: invokevirtual Method java/lang/String.toUpperCase:()Ljava/lang/String; ; 21: invokevirtual Method java/lang/StringBuilder.append:(Ljava/lang/String;)Ljava/lang/StringBuilder; ; 24: aload_1 ; 25: iconst_1 ; 26: invokevirtual Method java/lang/String.substring:(I)Ljava/lang/String; ; 29: invokevirtual Method java/lang/StringBuilder.append:(Ljava/lang/String;)Ljava/lang/StringBuilder; ; 32: invokevirtual Method java/lang/StringBuilder.toString:()Ljava/lang/String; ; 35: areturn` |
| 4 | `POJOActivityInterfaceMetadata.validateAndQualifiedForActivityMethod` | `io.temporal:temporal-sdk` | 1.27.0 | `0: aload_0 ; 1: ldc class io/temporal/activity/ActivityMethod ; 3: invokevirtual Method java/lang/reflect/Method.getAnnotation:(Ljava/lang/Class;)Ljava/lang/annotation/Annotation; ; 6: ifnull ; 9: iconst_1 ; 10: goto ; 13: iconst_0 ; 14: istore_1 ; 15: aload_0 ; 16: invokevirtual Method java/lang/reflect/Method.getModifiers:()I ; 19: invokestatic Method java/lang/reflect/Modifier.isStatic:(I)Z ; 22: ifeq ; 25: iload_1 ; 26: ifeq ; 29: new class java/lang/IllegalArgumentException ; 32: dup ; 33: new class java/lang/StringBuilder ; 36: dup ; 37: invokespecial Method java/lang/StringBuilder."<init>":()V ; 40: ldc String Method with @ActivityMethod annotation can\'t be static: ; 42: invokevirtual Method java/lang/StringBuilder.append:(Ljava/lang/String;)Ljava/lang/StringBuilder; ; 45: aload_0 ; 46: invokevirtual Method java/lang/StringBuilder.append:(Ljava/lang/Object;)Ljava/lang/StringBuilder; ; 49: invokevirtual Method java/lang/StringBuilder.toString:()Ljava/lang/String; ; 52: invokespecial Method java/lang/IllegalArgumentException."<init>":(Ljava/lang/String;)V ; 55: athrow ; 56: iconst_0 ; 57: ireturn ; 58: iload_1 ; 59: ifeq ; 62: iconst_1 ; 63: ireturn ; 64: aload_0 ; 65: invokevirtual Method java/lang/reflect/Method.isSynthetic:()Z ; 68: ifeq ; 71: iconst_0 ; 72: ireturn ; 73: iconst_1 ; 74: ireturn` |
| 5 | `POJOWorkflowInterfaceMetadata.validateAndQualifiedForWorkflowMethod` | `io.temporal:temporal-sdk` | 1.27.0 | `0: aload_0 ; 1: invokevirtual Method io/temporal/common/metadata/POJOWorkflowMethod.getMethod:()Ljava/lang/reflect/Method; ; 4: astore_1 ; 5: aload_0 ; 6: invokevirtual Method io/temporal/common/metadata/POJOWorkflowMethod.getType:()Lio/temporal/common/metadata/WorkflowMethodType; ; 9: getstatic Field io/temporal/common/metadata/WorkflowMethodType.NONE:Lio/temporal/common/metadata/WorkflowMethodType; ; 12: invokevirtual Method io/temporal/common/metadata/WorkflowMethodType.equals:(Ljava/lang/Object;)Z ; 15: ifne ; 18: iconst_1 ; 19: goto ; 22: iconst_0 ; 23: istore_2 ; 24: aload_1 ; 25: invokevirtual Method java/lang/reflect/Method.getModifiers:()I ; 28: invokestatic Method java/lang/reflect/Modifier.isStatic:(I)Z ; 31: ifeq ; 34: iload_2 ; 35: ifeq ; 38: new class java/lang/IllegalArgumentException ; 41: dup ; 42: new class java/lang/StringBuilder ; 45: dup ; 46: invokespecial Method java/lang/StringBuilder."<init>":()V ; 49: ldc String Workflow Method can\'t be static: ; 51: invokevirtual Method java/lang/StringBuilder.append:(Ljava/lang/String;)Ljava/lang/StringBuilder; ; 54: aload_1 ; 55: invokevirtual Method java/lang/StringBuilder.append:(Ljava/lang/Object;)Ljava/lang/StringBuilder; ; 58: invokevirtual Method java/lang/StringBuilder.toString:()Ljava/lang/String; ; 61: invokespecial Method java/lang/IllegalArgumentException."<init>":(Ljava/lang/String;)V ; 64: athrow ; 65: iconst_0 ; 66: ireturn ; 67: iload_2 ; 68: ifeq ; 71: iconst_1 ; 72: ireturn ; 73: aload_1 ; 74: invokevirtual Method java/lang/reflect/Method.isSynthetic:()Z ; 77: ifeq ; 80: iconst_0 ; 81: ireturn ; 82: iconst_1 ; 83: ireturn` |
| 6 | `WorkflowImpl`/`ActivityImpl`/`NexusServiceImpl`'s declared attributes | `io.temporal:temporal-spring-boot-autoconfigure` | 1.27.0 | `WorkflowImpl: public abstract java.lang.String[] workers(), public abstract java.lang.String[] taskQueues() ; ActivityImpl: public abstract java.lang.String[] workers(), public abstract java.lang.String[] taskQueues() ; NexusServiceImpl: public abstract java.lang.String[] workers(), public abstract java.lang.String[] taskQueues()` |
| 7 | `WorkflowClient.newUntypedWorkflowStub`; `WorkflowStub.signal`/`query`/`update` | `io.temporal:temporal-sdk` | 1.27.0 | `WorkflowClient.newUntypedWorkflowStub ×4 ; newUntypedWorkflowStub(Ljava/lang/String;)Lio/temporal/client/WorkflowStub; ; newUntypedWorkflowStub(Ljava/lang/String;Lio/temporal/client/WorkflowOptions;)Lio/temporal/client/WorkflowStub; ; newUntypedWorkflowStub(Ljava/lang/String;Ljava/util/Optional;Ljava/util/Optional;)Lio/temporal/client/WorkflowStub; ; newUntypedWorkflowStub(Lio/temporal/api/common/v1/WorkflowExecution;Ljava/util/Optional;)Lio/temporal/client/WorkflowStub; ; WorkflowStub.signal(Ljava/lang/String;[Ljava/lang/Object;)V ; WorkflowStub.query(Ljava/lang/String;Ljava/lang/Class;[Ljava/lang/Object;)Ljava/lang/Object; ; WorkflowStub.query(Ljava/lang/String;Ljava/lang/Class;Ljava/lang/reflect/Type;[Ljava/lang/Object;)Ljava/lang/Object; ; WorkflowStub.update(Ljava/lang/String;Ljava/lang/Class;[Ljava/lang/Object;)Ljava/lang/Object; ; WorkflowStub.signalWithStart(Ljava/lang/String;[Ljava/lang/Object;[Ljava/lang/Object;)Lio/temporal/api/common/v1/WorkflowExecution; (not asked; recorded for completeness) ; WorkflowStub.startUpdate(Ljava/lang/String;Lio/temporal/client/WorkflowUpdateStage;Ljava/lang/Class;[Ljava/lang/Object;)Lio/temporal/client/WorkflowUpdateHandle; (not asked; recorded for completeness) ; WorkflowStub.startUpdate(Lio/temporal/client/UpdateOptions;[Ljava/lang/Object;)Lio/temporal/client/WorkflowUpdateHandle; (not asked; recorded for completeness) ; WorkflowStub.startUpdateWithStart(Lio/temporal/client/UpdateOptions;[Ljava/lang/Object;[Ljava/lang/Object;)Lio/temporal/client/WorkflowUpdateHandle; (not asked; recorded for completeness) ; WorkflowStub.getUpdateHandle(Ljava/lang/String;Ljava/lang/Class;)Lio/temporal/client/WorkflowUpdateHandle; (not asked; recorded for completeness) ; WorkflowStub.getUpdateHandle(Ljava/lang/String;Ljava/lang/Class;Ljava/lang/reflect/Type;)Lio/temporal/client/WorkflowUpdateHandle; (not asked; recorded for completeness)` |
| 8 | the task queue's declaration sites: `WorkerFactory.newWorker` and every `*Options$Builder` class | `io.temporal:temporal-sdk` | 1.27.0 | `scanned 21 `*Options$Builder` classes; 4 declare public setTaskQueue ; ActivityOptions$Builder: (Ljava/lang/String;)Lio/temporal/activity/ActivityOptions$Builder; ; WorkflowOptions$Builder: (Ljava/lang/String;)Lio/temporal/client/WorkflowOptions$Builder; ; ChildWorkflowOptions$Builder: (Ljava/lang/String;)Lio/temporal/workflow/ChildWorkflowOptions$Builder; ; ContinueAsNewOptions$Builder: (Ljava/lang/String;)Lio/temporal/workflow/ContinueAsNewOptions$Builder; ; WorkerFactory.newWorker ×2 ; newWorker(Ljava/lang/String;)Lio/temporal/worker/Worker; ; newWorker(Ljava/lang/String;Lio/temporal/worker/WorkerOptions;)Lio/temporal/worker/Worker;` |
```

## Verdicts

**Q1 — confirmed exactly (M1).** `POJOWorkflowMethodMetadata`'s constructor compares
`workflowMethod.getType()` against `WorkflowMethodType.WORKFLOW` at offset 92
(`if_acmpne 116`); the taken (equal) branch calls `Class.getSimpleName()` on the interface
argument at **offset 101**, the not-equal branch falls to offset 116 and calls
`Method.getMethod().getName()` at **offset 122** — the reflected method's own name. Both
values are wrapped in `Optional.orElse(...)` against the annotation's own declared name
(`getNameFromAnnotation()`, read at offset 81, before either branch), so an explicit
`@WorkflowMethod(name = "X")`/`@SignalMethod(name = "X")`/etc. always wins; the branch this
row measures is the FALLBACK only. M1's claim matches the bytecode exactly, offset for
offset.

**Q2/Q3 — confirmed exactly (M2, M3).** `POJOActivityMethodMetadata`'s constructor calls
`ActivityMethod.name()` twice: once at offset 45 to test `.isEmpty()` (offset 50,
`ifne 66` — jumps to the prefix-composition branch when the name IS empty), and again at
offset 58 to return the annotation's own value verbatim when it is not. The prefix
(`namePrefix()` at 74, `getActivityNameFromMethod(...)` at 83, concatenated by a
`StringBuilder`) is built ONLY inside the offset-66 branch, i.e. only when `name()` was
empty — an explicitly named member never reaches it, exactly as M2 states.
`getActivityNameFromMethod` is `substring(0, 1).toUpperCase()` (offsets 15, 18) appended to
`substring(1)` (offset 26) — M3's title-casing rule, confirmed offset for offset.

**Q4 — confirmed exactly (M4, activity half).** `validateAndQualifiedForActivityMethod`
computes `annotated = getAnnotation(ActivityMethod.class) != null` (offsets 1–14), then: a
static+annotated method throws (`Method with @ActivityMethod annotation can't be static`,
offsets 29–55); a static+unannotated method returns `false` at offset 56; a
non-static+annotated method returns `true` at offset 62; and a non-static+unannotated method
checks `isSynthetic()` (offset 65) and returns `true` at **offset 73** when it is not
synthetic, `false` at offset 71 when it is. M4's claim — "true at offset 73 for an
unannotated method; false only for static or synthetic" — matches exactly.

**Q5 ★ — M4's stated "workflow half" does not match the bytecode.** The spec's own table
(line 45) reads: *"A workflow interface is the opposite — an unannotated method qualifies
for nothing."* `validateAndQualifiedForWorkflowMethod`'s actual bytecode is **structurally
identical to Q4's**, not its opposite: it computes `qualified = (getType() != NONE)`
(offsets 5–23, the equivalent of Q4's "annotated" flag, since `getType()` was already
computed from the annotation scan by the time this predicate runs), then follows the exact
same four-way branch as the activity method — static+qualified throws, static+unqualified
returns `false` (offset 65), non-static+qualified returns `true` (offset 71), and
**non-static+UNqualified (i.e. unannotated) checks `isSynthetic()` and returns `true` at
offset 82 when it is not synthetic** — the same shape as Q4's offset 73, not "qualifies for
nothing." Tracing the caller (`newInstanceInternal`, offsets 140–145) confirms why:
`validateAndQualifiedForWorkflowMethod`'s `true` only gates whether the method is added to a
STRUCTURAL candidate set (every non-static, non-synthetic method, annotated or not); the
actual "only annotated methods become workflow-contract members" filtering happens
SEPARATELY, later in that same caller, by comparing `getType() == WorkflowMethodType.NONE`
(offsets 204–212) before a `POJOWorkflowMethodMetadata` is ever constructed for it — an
unannotated method is added to the candidate set (by THIS predicate returning `true`) and
then skipped one step later (by a DIFFERENT check this probe's question did not name).
**The one-sentence rule "an unannotated method qualifies for nothing" is true of the
overall framework behaviour but false of the specific predicate M4 cites** — the exclusion
is not in `validateAndQualifiedForWorkflowMethod` at all. §2c's `declared_type_methods`
fence (spec line 205, "M4 is why the activity catalogs need a member type annotation
directly") should key on `getType() != NONE`, not on this predicate, if it means to
reproduce M4's actual boundary for workflows. **This is a spec correction, not a probe
question to re-ask**: the spec's plain-language claim about workflow behaviour stands (only
annotated methods are workflow-contract members), but its citation of
`validateAndQualifiedForWorkflowMethod` as where that boundary lives is wrong, and any code
that keys the workflow/activity asymmetry off this predicate's return value alone will treat
every plain method of a `@WorkflowInterface` as a candidate, same as an activity.

**Q6 — confirmed exactly (M5, annotation half).** `WorkflowImpl`, `ActivityImpl` and
`NexusServiceImpl` each declare exactly `String[] workers()` and `String[] taskQueues()` and
nothing else — no name-bearing attribute, matching M5's "never on an SDK annotation."

**Q7 — confirmed for the forms M10 names; one overload is a narrower case worth
recording.** `WorkflowStub.signal(String, Object...)`, `query(String, Class, Object...)`,
`query(String, Class, Type, Object...)` and `update(String, Class, Object...)` all take the
member name as a bare `String` at argument 0, with no workflow type anywhere in the
descriptor — M10's "name a member at argument 0 with no workflow type at the call site",
confirmed. Three of `WorkflowClient.newUntypedWorkflowStub`'s four overloads take the
workflow type as a bare `String` at argument 0 (`(String)`, `(String, WorkflowOptions)`,
`(String, Optional<String>, Optional<String>)`); the fourth,
`newUntypedWorkflowStub(WorkflowExecution, Optional<String>)`, takes a `WorkflowExecution`
(a running instance identity) at argument 0 instead, with the type name only optionally
present in the `Optional<String>` at argument 1 — M10 does not claim this holds for every
overload, so this is a narrowing worth recording (a catalog keying strictly on "argument 0
is the workflow type" for this factory needs the three-argument-0-is-String overloads, not
all four). Recorded but not asked: `WorkflowStub` also declares `signalWithStart`,
`startUpdate` (two overloads), `startUpdateWithStart` and `getUpdateHandle` — the first and
last still name a member at argument 0 the way M10 describes; the two `UpdateOptions`-taking
overloads take that options object at argument 0 instead, the same shape as the client's
fourth `newUntypedWorkflowStub` overload.

**Q8 ★ — four `*Options$Builder` classes declare `setTaskQueue`, not three.** M5 states
"the three options builders' `setTaskQueue(String)`" without naming them. This probe javaps
all 21 classes in the SDK jar matching `*Options$Builder` (not a hand-picked subset) and
finds `setTaskQueue(String)` publicly declared on exactly four:
`ActivityOptions$Builder`, `WorkflowOptions$Builder`, `ChildWorkflowOptions$Builder` and
**`ContinueAsNewOptions$Builder`**. The first three match the natural reading of "the three"
(the task queue for an activity call, a new top-level workflow, and a child workflow); the
fourth is the queue a workflow continues itself onto — a real, public, ordinarily-declared
setter (verified: not deprecated, not package-private, not inherited from a shared base) that
M5's "three" leaves uncounted. `WorkerFactory.newWorker(String)` and
`newWorker(String, WorkerOptions)` are unaffected — the queue a worker POLLS is named on
`WorkerFactory` alone, at argument 0 in both overloads, exactly as M5 states. **This is a
spec correction**: §2d's `metadata_from` (spec line 46) should list four builder classes,
not three, or explicitly say why `ContinueAsNewOptions$Builder` is out of scope for the
catalogs Tasks 3/5/8/9 build (it may simply be irrelevant to those catalogs' surface, since
continue-as-new is invoked from inside the running workflow rather than dispatched by a
caller the catalog models) — but the CLAIM as written ("the three") undercounts what the
jar declares.

`measured: 2026-09-22`, all eight rows, on the two archives the scope names. The fixture row
(the owners a compiled Temporal flow actually names at its call sites, mirroring CP-27's row
16) is **pending — Task 6 adds it** once the fixture module exists; `run.sh`'s `specs` array
carries a comment marking exactly where that third spec line goes.
