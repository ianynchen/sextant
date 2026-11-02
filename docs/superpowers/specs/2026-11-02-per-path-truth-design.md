# Per-path truth: follow hand-offs, never merge paths

Status: approved 2026-11-02 (the user: "we should tell the truth … as long as we have the code,
we have the call graph and can trace"; "Yes, build it"). Branch `fix/per-path-truth`, cut from
`cov/vertx` (PR #88).

## 1. The defect

A value Sextant publishes at `resolved` must be true on every path that reaches it. Two readers
break that today.

**A. The walk ignores a hand-off.** `values.py`'s `escapes` window counts only calls made ON a
value. A value handed to another method as an ARGUMENT is ignored, a narrowing stated in
`_through`'s docstring ("a value handed to another method as an ARGUMENT can be mutated too …
Counting every hand-off would make the commonest readable shape … unresolved"). So:

```java
WebClientOptions o = new WebClientOptions().setDefaultHost("search");
configure(o);                                   // sets the port to 9090
WebClient client = WebClient.create(vertx, o);
client.get("/q").send();                        // Vert.x sends to search:9090
```

publishes peer `search`, `resolved`. The same narrowing applies to every reader of the walk.

**B. The Vert.x options reader merges paths.** `client_base._Options.defaults_of` and `parts_of`
merge the parts every path read (`_agreed`): a part two paths read differently is "set and not
read", and a part one path does not set is ABSENT, as if no path set it. With two factories, one
setting port 8080 and one setting none, the row is `search`, `resolved` — wrong for the first.
An options object Sextant could not read at all (an unlisted factory overload, an unrooted chain,
`new WebClientOptions(json)`) is also read as "nothing set", so `client.get("search", "/q")`
publishes `search` while its port is unknown.

## 2. The rules

1. **A hand-off into code we have is followed.** Between the call that produced a value and the
   call that uses it (the `escapes` window), a call that hands the value to a parameter of a body
   `call_edges` resolves — a method of this module, or of a jar named in `.sextant.yml`
   `extract_libraries` — is walked into. Inside that body, the calls made on the parameter
   (`receiver_parameter`) are read by the same window rule, in their order, at the hand-off's
   position in the caller's order; a further hand-off of the parameter is followed the same way
   (a cycle is `cycle`). A call with several resolved callees is several paths. A method's OWN
   parameter is a value produced when the method is entered: its window runs from the entry to
   the use, so `send(o) { configure(o); create(vertx, o); }` reads the hand-off inside `send`
   (fix round 1, C1).
2. **A hand-off into code we do not have is unknown.** A callee `call_edges` leaves NULL (the JDK,
   a library not named, another module), a write of the value into a field, a call that reaches
   the value below the top level of an argument (an array element, a merge candidate), an
   instance call on the value's own type whose receiver the facts cannot name (a parameter
   reassigned on a branch), and a call through a type a lambda or method reference in the
   module implements (`dispatch` lists no such body) end the path with `escapes`. Never
   "nothing happened".

   **A lambda capture** (a `dynamic` site) is followed through the capture fold (OI-150/OI-266,
   `value_index`), which DOES say which parameter of which body a capture lands on — this rule
   first said the facts do not, which was stale. A body that does nothing to that parameter (no
   call on it, no hand-off of it, no field write) cannot change the value, so the capture is
   not a hand-off. A body that does anything is `escapes`: when the body runs is not known, so
   what it does cannot be placed in the window. A capture the fold does not map is `escapes`
   (fix round 1, M6).
3. **An immutable value cannot be changed by a hand-off.** A hand-off whose parameter type (read
   off the site's own descriptor) is a primitive, `java.lang.String`, or a boxed primitive is not
   a hand-off for this rule; nor is any hand-off of, or call on, a value whose OWN type the facts
   state is one of those (its producer's declared return, a concat's `String`, a construction's
   type, a parameter's declared type) — SLF4J's `info(String, Object)` types a logged `String`
   `Object` (fix round 1, M1). **A compiler's null checks are not hand-offs either** — ruled
   by the user on 2026-11-02: a call to `kotlin.jvm.internal.Intrinsics`
   (`checkNotNullParameter`, `checkNotNullExpressionValue`, `checkNotNull`,
   `checkParameterIsNotNull`, `checkExpressionValueIsNotNull`) takes the value without
   handing it off, because the compiler, not the author, inserts these and they only check
   for null and throw. Recognised by the owner class alone, declared as catalog data
   (`value-models/compiler-null-checks.yml`, D02 §1f's `not_hand_offs`), since the walk names
   no language. This is a property of the JVM type, not of any method, so it is one
   structural rule (OI-143's ruling allows it), and it keeps `log.info(url)` before
   `client.get(url)` resolved.
4. **Paths are never merged into one answer.** Each path composes its own address; paths giving
   the same address are one row, different addresses one row each (enumerable is exact). A path
   whose part is unread or unknown gives its own row with peer NULL, path kept, `partial`; other
   paths keep their rows.
5. **A framework default is used only where it is proven.** On a path whose options object was
   built by the no-argument constructor and whose every call (rules 1-2) was read, a part no call
   set is the framework's own default, declared in the client model (`unset`; Vert.x: host
   `localhost`, port `80`, CP-56 row 132). Anywhere else the part is unknown. This reverses the
   Vert.x spec's §2a/item 23 ("unset defaults are never published"), a ruling made under the
   delegation, not the user's.
6. **A setter whose own argument has several values is unread** (`_Options._value`, unchanged):
   pairing two independent setters' candidates would publish combinations no path makes.
7. **A hand-off to a call a catalog declares takes its effect from the catalog** [ruled by the
   user, 2026-11-02: "predict the framework's behavior exactly, including its errors", DR-6].
   A catalog-declared call is not code we do not have: the catalog is the measured statement of
   what it does, and every row that passes through it rests on that same statement — never one
   row on the statement and the next on "unknown". The catalog states, per declared call and
   argument, what the call does to the value (measured with `javap`, cited to a probe row): which
   parts it changes, and when it refuses. A declared call whose effect the catalog does not state
   is unknown (rule 2). A call the framework refuses gives its row marked refused, never dropped
   and never repaired.

   Quartz, `QuartzScheduler.scheduleJob(JobDetail, Trigger)`, measured (CP-55 section (g),
   rows 24-48: `javap` of 2.5.1, the version the catalog lists, and the outcomes on an
   in-memory scheduler created and never started; 2.3.2 read by hand, the same): it checks
   both non-null; where the trigger names no job it binds it (`setJobKey(job.getKey())`);
   where it names a job with another key it throws "Trigger does not reference given job!";
   it calls `computeFirstFireTime` (the next fire time, not the schedule); it stores both.
   Two jobs built with no `withIdentity` never share a key. So one trigger scheduled with
   `BJob` then `CJob` is `BJob @ c2` resolved and `CJob @ c2` resolved and refused. The
   collection forms re-bind every trigger with no check, and every job store in the Quartz
   jar refuses a second store of one job or trigger key unless told to replace; both are
   measured and stated in the probe, and neither is built: the collection forms reach a
   trigger only through a collection, and which store a module runs is configuration (the
   user, 2026-11-02: "that decision comes later").

   **How a refused row is marked** [ruled by the user, 2026-11-02: "B: refused column"]:
   `scheduled_work` gains a nullable `refused`, the framework's reason as text, NULL on every
   row the framework accepts. `resolution` keeps its meaning, how sure the read is, so a
   refused row keeps the resolution it was read at and may also be `partial`. A refused row's
   handler is not a root: the job never runs on that schedule. Every reader that lists
   schedules shows the refusal. The route table and Vert.x's refused routes are not changed
   here (a separate item).

   **As built.** The effect is the catalog key `hand_off_effects` (D02 §1f, in
   `value-models/quartz-scheduler.yml`): per declared call and argument, `binds: {part, to}`
   and `refuses: bound_elsewhere`, each citing its probe row. The walk reads a hand-off one
   states as a step of its path, not `escapes`, so the parts it does not bind stay as they
   were (`values._Walk._handed_to`, `Path.stated`). The Quartz reader takes the trigger's
   binding as its FIRST bind on the path — the builder's `forJob(…)` (every overload) where
   there is one, else the first stated call that binds it — and marks a later call refused
   where its job's key is not the bound one (`scheduled_chain._refusal`): `forJob(X)` then
   `scheduleJob(Y, t)` marks Y refused (CP-55 row 44). After review 2 (2026-11-02): an
   earlier stated call inside a helper is read through the call that ENTERED the helper, so
   two calls of one helper are two executions (C1); one `build()` site is one job only in one
   execution (C2); a job `forJob` names takes the refusal where every call that would store
   the trigger on the path is refused — nothing is stored, so it never runs (M1), unless a
   call the reader does not pair may store it; a listener or capture body re-entered while it
   is read is `cycle` (M2); and a path ending `cycle` keeps its row as `escapes` does (M3).
   That an earlier call runs before a later one rests on the window alone today
   (`scheduled_chain._ran_before`), pending the user's ruling on control flow (review 2, C3,
   M4).

   **The job argument** [ruled by the user, 2026-11-02, "option B"]: measured in 2.5.1 and
   2.3.2 (CP-55 rows 27, 32, 35, 49-73), Quartz's own code reads the job and never changes
   it, and hands it to `SchedulerListener.jobAdded` on every registered listener. The catalog
   states that (`arg0`, `hands_to`). A listener the module implements is code we have, read as
   a lambda's capture is (rule 2): a body that does nothing to the job leaves it stated; one
   that does anything, or bodies that cannot be listed, make it `escapes`. So one job
   scheduled twice with one trigger is ONE row, `resolved`. The second call is NOT marked
   refused: the job store's refusal of a second store of one key is not built, since which
   store a module runs is configuration. Where a job's key cannot be read, whether it is refused is
   not decided, and the row is no surer than `partial`.

8. **Identity is not content** [ruled by the user, 2026-11-02]. A reader asking
   WHICH object or constant a value is (an `HttpMethod` constant, a class, the call that built
   it) is unaffected by a hand-off: Java hands a method a copy of the reference, so no callee can
   make the caller's variable another object. Rules 1-3 apply to readers of an object's CONTENTS.
   As built (`values._Walk._identities_past`): a window path that ends `escapes` or `cycle`
   still answers where the walk reads the value as a declaration (a `symbol` answer: an enum
   constant, a class, the type a value was built from); every other answer on that path keeps
   the reason. Only `symbol`: a string an identity arm reads off a constructor is the
   object's contents, and a `String` value already has an empty window (rule 3). The case it
   restores is apollo-portal's `doExecute(HttpMethod method, …)`, which runs
   `HttpMethod.GET.equals(method)` before `exchange(…, method, …)`.

## 3. Not changed

- The Ktor block ladder (`_Ladder.base_of`) answers `non_enumerable` for two bases (ruling M-1).
  It does not lie, so it stays.
- A value written into a field and changed later through that field by another method is out of
  the window this rule reads; logged as an issue, not built.

## 4. Done when

- Each rule has a test that fails before the change, on `fixtures/orders-vertx-web` where it is a
  Vert.x shape and on a unit fixture where it is the walk.
- The full gate passes, and `scripts/field_check.py` is run: every moved count is explained per
  module, never re-pinned silently.
- D02 (the options `client_base`, `unset`), the Vert.x spec (§2a, §3d, item 23), the client
  model and COVERAGE's WebClient row say the new rules.
