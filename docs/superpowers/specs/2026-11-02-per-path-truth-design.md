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
   The first binder is the first stated call in RUN order: the walk meets frames backward,
   so a frame it crosses out to or descends into ran before the one met before it (re-review
   N1, `scheduled_chain._first_binder`); a pairing call the walk reads no pairing from leaves
   a `forJob` row undecided (N3). That an earlier call runs before a later one rests on the
   window alone today (`_first_binder`, `_ran_before`, the two places order is decided),
   pending the user's ruling on control flow (review 2, C3, M4).

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

9. **A call on a branch is not a call on every path** [option A ruled by the user,
   2026-11-02: "A: fact per call"; the exact fact below approved by the user 2026-11-02: "Approve, build it";
   `post_dominator` ruled 2026-11-03: "A: add post_dominator"; several splits ruled 2026-11-03:
   "A: every row partial"; `reaches_return` ruled 2026-11-03: option A; `loop_group` ruled
   2026-11-03: option A for review 3's M1; published parts ruled 2026-11-03: option A].
   The facts today give each call its `ordinal` (instruction order) and nothing else, so
   `a; b;` and `if (x) a; else b;` are the same facts (review 2, C3), and
   `if (tls) o.setDefaultPort(443); client.get(…)` publishes port 443 `resolved` — false
   when `tls` is false (review 2, M4). D00 reserved this as "an enrichment of this same field
   in a later phase".

   **The fact.** Each `call_site` gains five fields, computed by the extractor from the
   method's control-flow graph (ASM's `Analyzer`, exception-handler edges included):
   - `dominator`: the `ordinal` of the nearest call site in the same method that runs
     before this call on EVERY path from the method's entry to this call; absent where none
     does. Following `dominator` from a call lists every call that always runs before it.
   - `on_every_exit`: true where this call runs on every path from the entry to a normal
     return. An exception that leaves the method is not a normal return: the value it carried
     is never used.
   - `post_dominator` (ruled 2026-11-03): the `ordinal` of the nearest call site in the same
     method that runs after this call on EVERY path from it to a normal return; absent where
     none does. A path that ends in a throw reaches no normal return and constrains nothing,
     so a call from which every path throws has none.
   - `reaches_return` (ruled 2026-11-03, option A): true where every path from the call ends
     at a normal return; false where any path ends in a throw or loops forever. Absent
     `post_dominator` alone cannot tell "no call follows" from "no return follows"; this does.
   - `loop_group` (ruled 2026-11-03, option A for review 3's M1): the loop a call is in — the
     non-trivial strongly connected component of the method's instruction graph, exception
     edges included — identified by the lowest call ordinal in it; absent where the call is in
     no cycle. Two calls with one group can each run again after the other; without a shared
     group, neither reaches back. Exact for nested loops: an inner loop lies in the outer
     loop's component.

   **The readers.** Both sit in the one place each reader decides order (`_ran_before`, the
   walk's window):
   - *Before, in one method.* Call `a` ran before call `b` on every path exactly when `a`
     is on `b`'s `dominator` chain.
   - *Before, across a hand-off.* A call `s` inside a callee ran before the caller's later
     call `c` exactly when `s` is `on_every_exit` in the callee and the hand-off call is on
     `c`'s chain. Anything else is undecided.
   - *Quartz (C3).* A pairing call is refused only where the binding call ran before it on
     every path. Where it is undecided, the row is `partial`, unmarked.
   - *A configuring call (M4).* A call between a value's producer and its use that is not
     on every path to the use splits the path: one path where it ran, one where it did not.
     Each path composes its own row (rule 4). Not being on every path to the use proves only
     that a run reaches the use WITHOUT the call; it does not prove a run reaches it WITH the
     call — `if (tls) { o.setPort(443); return; } client.connect(o);` has no run that connects
     with 443 (corrected 2026-11-03; this paragraph first said the fact proved both). So the
     row with the call is `resolved` only where the use is on the call's `post_dominator`
     chain (ruled 2026-11-03), and `partial` otherwise; the row without it is `resolved`.
     `if (tls) o.setDefaultPort(443); client.get(…)` gives `search:443` and `search:80`, both
     `resolved`. A call inside a callee that is not `on_every_exit` splits in the same way;
     across frames the call's chain must reach the call that leads on to the use, or the
     method's normal exit where the use is in a caller. A RETURN of the value counts as the
     use.

   **Not claimed.** The fact does not say WHICH branch a call is on. Where two or more
   calls on branches are in one window (`if (x) setPort(1); else setPort(2);`, or
   `if (x) useTls(o); else usePlain(o);`), the split gives every combination, including
   ones no run makes (neither, both) and an order no run has. **Every row from such a split
   is `partial`, whichever PUBLISHED parts the calls set** [ruled by the user 2026-11-03, "A:
   every row partial"; narrowed the same day, option A: "whatever parts they set" became
   "whatever published parts they set"]: different parts give fabricated combinations too, but
   **a call on a branch that sets no part the reader's row publishes is no split for that
   row**. Each reader states the parts its rows publish as capture names (the forward chain
   walk's `fluent` reader, `PUBLISHED_PARTS`), read against the catalog step and capture
   names a call's step declares (`values.counts_split`); a reader that states none counts
   every split, the conservative default. Branch structure (option B) is a later enrichment of the same
   field.

   **As built** (2026-11-03).
   - *The extractor* (`MethodFlow.FlowGraph`) records every normal and exception-handler edge
     ASM's `Analyzer` follows and computes both trees with Cooper, Harvey and Kennedy's
     iterative algorithm over two nodes per instruction (before it runs, after it completed);
     a handler edge leaves the BEFORE node, so a call that may have thrown dominates nothing
     in its catch and is skipped by it for `post_dominator`. The post-dominator tree is the
     same algorithm on the reversed edges, rooted at a normal-exit node every reached
     `*RETURN` feeds. `reaches_return` marks every node that cannot reach that exit (every
     path throws or loops forever) and propagates the mark backwards to every predecessor; a
     reached `ATHROW` leads nowhere, so even a throw a handler covers counts as one that may
     leave (handler types are not compared — the answer errs towards false). All four fields
     are written on throw sites too. An unreachable invoke, and a body the analyser cannot
     walk, emit no site at all.
   - *The walk* (`values._Walk._window`, `_reaches_use`, `_windowed`): a split records the
     choice on the trail (`_SPLIT`); a call made on a configuring call's result is skipped
     with it. The side WITH the call is proven where the use (a call in the same frame) is on
     its `post_dominator` chain; where the window runs to the end of an entered body, where
     a normal return follows the call — any `post_dominator`, or `reaches_return` true (ruled
     2026-11-03, option A), which is what a setter with no call after it has; where the use
     is a RETURN, where that holds and every return of the method hands the value back (the
     side without the call needs the latter too). `Options make(tls) { o = new; if (tls)
     o.setSsl(true); return o; }` gives both rows `resolved`; a setter every path from which
     throws stays `partial`. A call on the way to a body this workspace read that has no
     normal return (`boom()` that always throws) is a throw the method's own facts cannot see:
     no run with the split call gets past it, so that side is `partial` (review 3, m2).
   - *Several splits are counted per PATH* (review 3, C1): two or more calls on branches
     anywhere on the path from the producer to the use — in one window, or one in a helper's
     window and one in its caller's, or one in a factory and one in the code using what it
     returns — make every row of the path `partial` (`values._unsure`).
   - *A call after the use in its loop* (ruled 2026-11-03, `loop_group`, review 3's M1): the
     window takes a call after the use by ordinal where it shares the use's `loop_group` — it
     can run before a later run of the use — as a call on a branch (it is never on the use's
     `dominator` chain), so it splits and counts toward the several-splits rule; not where the
     value was produced in that same loop (a new object each time round), and not in another
     loop. `for (…) { Client.of(o); o.setPort(443); }` gives two rows: port unset `resolved`
     (the first time round, which the facts prove a run makes) and port 443 `partial`. The
     same holds where the use is in a callee called from the loop: the call that leads on to
     it is the use the caller's window reads. **Fix round 2 (review 3 re-review):**
     - *A path that ran a loop-later call is never `resolved`* (C-A). The window gathers its
       calls in ordinal order, which is not the run order across the back edge, so no proof
       read off it — the `post_dominator` chain included — holds:
       `while (true) { o.setPort(80); use(o); if (flag()) return; o.setPort(443); }` has the use
       on the later setter's chain, yet every use sees 80. The other proofs read no ordinal
       order: `dominator`, `post_dominator` and `reaches_return` are facts about the graph,
       the path without the call is a first time round the facts prove, and the several-splits
       count counts contexts, not order.
     - *Even where the value is produced in the use's loop group* (M-A): nested loops are one
       group, so a producer in the outer loop shares it with an inner loop whose later call
       reaches the next use on the same object. The five facts cannot tell that from a value
       built afresh before every use (`fresh` and `nestedProducer` have the same facts), so the
       call stays in the window and its row is `partial`; nothing is dropped.
   - *The path bound* (review 3, M2): a window with two or more splits records one mark
     instead of each choice, so paths that gather the same calls are one; a window whose paths
     still pass 256 is one path ending `non_enumerable`, its parts unknown, stated. Twenty
     guarded setters on one object were a million paths, 32 s and 2.16 GB; now one row, under
     0.1 s and 0.1 GB. The cap counts the WHOLE path across frames too (fix round 2, m-B):
     `_windowed` stops enumerating once its answers pass 256, so eight guarded setters in a
     caller and eight in its callee (65,536 paths) are one `non_enumerable` row.
   - *The forward chain walk reads branches by the same rule* (fix round 3): `values.Flow` holds
     the split and proof both walks call; a statement-style call the walk folds into a chain
     forks it where it is not on every path to the fork it carries on to; the path cap counts
     every split on the path, across chained forks, continuations and the walk back. Only the
     splits that set a published part count toward the several-splits rule (ruled 2026-11-03,
     option A). Ktor's inline `setBody` is two `setBody` calls on two branches, and the body is
     a published part (`request_shape`), so a Ktor request with a body is `partial`.
   - *The forward walk follows hand-offs, and counts what it cannot see* (fix round 4, review
     3 re-review 2). Rules 1 and 2 hold in the forward chain walk, by the value walk's own code
     (`values.HandOffs`, `_Walk._handed_events`): a hand-off of the chain's value before its
     terminal into a body we have folds the calls the body makes on its parameter, in order, at
     the hand-off's place, each path through the body its own by the body's own positions
     (`on_every_exit`, `reaches_return`); inside the body a call configures the value as in the
     chain's own method (void, or `returns_receiver`), and any other call on it is `escapes`. A
     hand-off into code we do not have, a call reaching the value below an argument's top level
     and a call through a receiver the facts cannot name leave every part a step of the catalog
     sets unknown on that path, its row no surer than `partial` (an address not read is
     `unresolved` by `fluent`'s own rule). A call the catalog itself reads (a root, a step, a
     terminal, a join's consumer) is read by its words, not as a hand-off. The enumeration —
     split, proof, the skipped-parent rule, the several-splits collapse and the path cap — is
     written once (`values.Flow.paths`) and both walks call it; the forward walk's cap counts the
     paths it already holds (`width`), with a walk back's. **A split is counted by what its paths
     set** (`values._counted`): a path ending at a reason (`escapes`, `cycle`, the cap) sets
     parts not known, so it counts; a branched hand-off into a body counts where a call the body
     makes sets a published part. **A call on a configuring call's result that is on that
     call's `post_dominator` chain is no split of its own**: it runs on every path that call's
     run takes to a return, so `if (x) b.setUri("/b").setUri("/c")` is one split (`/a`, `/c`,
     both `resolved`), in both walks — the `post_dominator` fact read as the side-proof already
     reads it. M-1 (a builder handed to a module method that builds and sends it) already kept
     its row through the walk back (ruling 5) once `call_edges` are derived, as the pipeline
     derives them; the review's probe had not derived them.
   - *Rows of one identity* (fix round 4, m-2; rule 4). The published table holds one row per
     identity (protocol, direction, verb, path, and caller and peer, or handler inbound), its
     metadata keyed to it, so two chains that differ only in a published column or in metadata
     (a header put on one branch) cannot be two rows without a schema change: the one row is
     no surer than `partial`. Two chains equal in every published column and metadata are one
     request, and the row keeps the more exact resolution of the two (`fluent._Kept`).
   - *Readers keep every row* (fix round 2, M-B; rule 4): the rootless walk-back
     (`chains._walk_back`) keeps a producer it cannot call exact, its row no surer than
     `partial` (`ChainEnd.inexact`, read by `fluent` and the Quartz reader), and a walk back
     past the cap keeps the terminal's row with its parts unread. Quartz keeps a capped
     walk's row as it keeps an `escapes` one (`_UNREAD_ENDS`, m-A). An unproven side's answers are inexact (`partial`), as is
     every path of a window with two or more splits. A fact with no `on_every_exit` is
     undecided: every call in its window splits, unproven.
   - *Quartz* (`scheduled_chain._ran_before`, `values.Path.ran_before`): in one method, on
     the consumer's `dominator` chain; inside an entered body, `on_every_exit` there at each
     level; in a caller the path crossed out to, on the chain of the call that entered the
     use's method or one enclosing it; inside a callee whose return the path read,
     `on_every_exit` there and that call ran before. Anything else is undecided.
   - *Cost*, measured: the extractor on `spring-core-7.0.9.jar` (29,432 call sites), 5 runs
     each: 1.00-1.11 s before, 1.18-1.27 s with three fields, 1.17-1.25 s with four (0.99-1.08 s
     before in the same runs), and 1.21-1.27 s with all five (1.18-1.24 s with four in the same
     runs),
     JVM start included; the facts are strictly additive. `mall-admin`, the largest field corpus: scan 1.3-1.5 s
     before and 1.4 s after, resolve 3.9 s before and 3.9-4.0 s after. Per window, the worst
     seen on eleven corpora is 4 split calls and 5 paths (`yudao-module-infra`); no cap is
     set. Every published table on the six pinned and five unpinned corpora is identical
     before and after.
   - *Not proven, so `partial`*: a setter from which some path throws or never ends and
     which no call follows on every path to a return; a setter before one of several returns
     that hand back different values; and every row of a window with two or more splits.

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
- Rule 9: D00 gains `dominator`, `on_every_exit` and `post_dominator` on `call_site`, and the fact schema
  version goes from 5 to 6 (every workspace is re-extracted; every fixture is rebuilt with
  JDK 21). The extractor has a unit test for each shape: straight line, `if`, `if/else`,
  early return, loop, `try/catch`. C3 and M4 each have a test with the review's shape.
