# RUNBOOK

Lessons learned on this project. Read before starting a task; add to it when something
costs time that a note would have saved.

One entry per lesson. State what went wrong, and what to do instead.

---

## Documentation and diagrams

### Mermaid reserves `graph` as an identifier

A node named `graph` fails to parse:

```
    store[(Derived graph)]     ← works
    graph[(Derived graph)]     ← Parse error … got 'GRAPH'
```

`end`, `subgraph`, `class` and `click` are also reserved. Prefer a short unambiguous
identifier and put the words in the label.

### Verify Mermaid by rendering it, not by reading it

Two diagram bugs reached a file in this project because they looked correct. Render before
claiming a diagram works:

```bash
npx @mermaid-js/mermaid-cli -i diagram.mmd -o out.svg
```

Puppeteer ships no browser here. Point it at the installed one:

```bash
export PUPPETEER_EXECUTABLE_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
```

### Keep Mermaid labels plain

Quoted labels, `<br/>`, quoted subgraph titles and parallelogram shapes with quotes inside
are all rejected by some renderers. Plain unquoted labels using only letters, digits, spaces
and hyphens, with `[]` and `[()]` shapes, work everywhere.

### VS Code does not render Mermaid on its own

Its built-in Markdown preview shows nothing. It needs an extension:

```bash
code --install-extension bierner.markdown-mermaid
```

Check this before debugging diagram syntax. GitHub renders Mermaid natively.

---

## Design discipline

### Derive the fact set from the deliverables, never the other way round

A graph built facts-first ends up with **most of its edges having no consumer at all** —
produced because they seemed natural, read by nothing. The cause is always the same: facts
produced first, consumers assumed to arrive later. They do not arrive.

Before adding a fact kind or an edge kind, name the requirement that consumes it. This is
NFR-6, and it is why the four type-reference edge kinds are kept while `imports` and field
access are not.

### Separate what is certain from what produced it from who wins

"Confidence" means three different things and therefore none of them. One field grading
extractor quality cannot also express "one of these four".
Keep `resolution`, `evidence` and `precedence` separate — see
[ARCHITECTURE.md](ARCHITECTURE.md) DR-3.

### Two producers for one file means reconciling them forever

A two-tier extraction design pays for itself in reconciliation clauses accumulating in the
stitcher — typically to recover facts that **no deliverable reads**. One producer per file. Where a language genuinely needs two readers, the
adapter owning that language merges them internally and the pipeline sees one stream.

### Bulk load. Never per-row.

Per-row insertion runs **orders of magnitude** slower than bulk load — minutes against
seconds on a real fact set — and a per-row loader left as a placeholder is never revisited.

### A stale cache is a correctness bug wearing an efficiency costume

Include every input that could change the result in the cache key: content hash, scanner
identity, scanner version, catalog hash, redaction pattern set. Omit one — the mapper
version, say — and stale facts get served until someone forces a cold rebuild by hand.

### A stored value that is a pure function of another field is policy leaking into data

`precedence` was stored on every fact, yet it was entirely determined by `evidence` —
human 90, model 10, code 50. Storing it made illegal states representable and froze the
rank table into published bundles, so a policy change would have required re-extracting the
estate. The test: *could two rows with the same source field ever legitimately differ?* If
not, derive it at use time and never store it.

### A table whose rows are copies of another table is a query

Materialised traces duplicated every shared subtree once per endpoint that reached it — a
validator on 150 endpoints' paths appeared 150 times, and the copies would have dwarfed the
`edges` table they came from. Everything in a trace except membership and the cycle marker
was already in other tables. The fix: a named query (`trace_of`) plus one slim summary
table for the numbers findings need. Before materialising a derivation, ask what it
contains that its inputs do not.

### An arbitrary bound truncates the wrong thing

A depth limit on a trace spends its budget on accessors and stops before the call that
mattered. Remove the noise instead of capping the depth. Where termination genuinely needs a
stop, use cycle detection, which is a correctness requirement rather than a limit.

Path enumeration is the exception that proves it: routes between two symbols grow
exponentially, so return the union subgraph of all routes rather than a truncated list.

### A type's wire answer belongs to the extractor or to a catalog — never to the resolver

`OrderView.class` and `String.class` arrive as call arguments carrying a bare symbol and
nothing else: [D00](components/D00-fact-schema.md) §5's argument grammar has no room for the
wire projection a type *reference* carries, so the payload rooting had to invent one, and
invented `object` for every argument — a shape claim about `String`, about `Void`, and about
an array.

The obvious repair — a small table of JDK scalars in the resolver — is forbidden, and
rightly: [ARCHITECTURE](ARCHITECTURE.md) §10 confines language names to
`ingress/extract/jvm`, two architecture tests enforce it, and a table like that is a
language branch waiting to happen. The two legitimate homes are the extractor's own
projection and a catalog's `known_types` ([D02](components/D02-catalog-schema.md) §2g). The
fix used the second, declaring the boxes, `String` and `Void` with exactly the wire types
and formats the extractor emits, so the two halves cannot answer differently.

Before writing a type name in the language-blind half, ask which of the two owns the
answer. If neither can be made to, the fact schema is what needs the change.

---

## Working practice

### A library earns its place by absorbing mechanics, never by setting policy

The tool-capability audit ran four dependency decisions through one test. `jsonref` was
taken for pointer mechanics — but remote-fetch policy, cycle semantics and gap reporting
stayed in our loader, because the library's defaults did all three wrong. The Gradle
Tooling API was *rejected* because its hard part (an injected model builder) was ours to
write anyway, leaving only a dependency and a version matrix. `click` and `rich` were taken
without hesitation because a CLI router and a status display carry zero policy. Ask first:
which part is mechanics, which part is policy? Take the tool for the first, never let it
decide the second.

### Verify, then claim

Three defects in this project were found by running something rather than reading it: two
Mermaid parse errors, and a broken cross-reference. Cheap checks that have already paid for
themselves:

```bash
# every markdown link resolves
for f in **/*.md; do grep -oE '\]\([^)#][^)]*\.md' "$f" | ...; done
```

Per `GUIDELINES.md` §13.6, "the diagrams are written but I have not rendered them" is the
honest statement when a check has not been run. Better to run the check.

### The specification is a contract

`GUIDELINES.md` §1.1. A decomposition, a dependency choice, a schema shape — none of these
are agent decisions, even when they look obvious. Proposing a component breakdown before
writing seventeen documents against it saved rewriting all of them.

---

## Implementation

### An explicit `read_json` column spec silently nulls out NDJSON

`read_json(path, columns={'json': 'JSON'})` looks for a field literally named `json` in
every record. A newline-delimited fact file has no such field, so every row still loads —
row counts look right — and every column comes back `NULL`. Nothing errors. `read_ndjson_objects(path)`
is the form that actually reads one-JSON-object-per-line files; see `load_facts` in
`workspace.py`. The lesson is not "use this one function" — it's that an ingestion path can
fail by going silently null instead of loudly wrong, and a passing row count does not rule
that out. Spot-check a value, not just a count.

### "Ruff clean" is a claim, not a result

Two implementers reported the lint gate clean while `ruff` was in fact reporting an error.
The controller only caught it by running the linters itself rather than trusting the report.
Reported gate output is not gate output — run it yourself before believing it.

### A test asserting on a return code needs `check=False`

`subprocess.run(..., check=True)` raises before a test gets to assert on
`result.returncode` — the assertion never runs, and a red test looks like a crash instead.
Pass `check=False` explicitly whenever the return code itself is under test; the linter
that insists on an explicit `check=` argument is catching a real bug here, not
bikeshedding.

### Shadow's classic plugin ID doesn't work under Gradle 9

`com.github.johnrengelman.shadow` fails on Gradle 9 with an opaque `MissingPropertyException`
that points nowhere near the real cause. The maintained coordinates are
`com.gradleup.shadow` — that's what `extractor-jvm/build.gradle.kts` declares.

### Pre-declare a table that only a derivation creates

`derive_endpoints.sql` runs only when a catalog's required capabilities are met, and every
catalog can legitimately be skipped — capability gating exists precisely so a weaker
scanner degrades instead of failing. But the named `endpoints` query didn't know that:
with no catalog run, the table never existed, and the query crashed on exactly the path
whose entire purpose is to report rather than fail. Fix: `schema.sql` pre-declares an empty
`endpoints` table with `CREATE TABLE IF NOT EXISTS`; `derive_endpoints.sql` replaces it
whole with `CREATE OR REPLACE TABLE` whenever at least one catalog runs. A named query
against a sometimes-created table needs the table declared unconditionally, not just
populated conditionally.

### `IS NOT NULL` binds tighter than `->>` in DuckDB

`payload ->> 'origin' IS NOT NULL` parses as `payload ->> ('origin' IS NOT NULL)` — a
boolean subscript — and fails at run time with `Failed to cast value to numerical`,
naming the whole JSON payload and pointing at a caret in the WHERE clause. Nothing about
the message says "precedence". Parenthesise the extraction: `(payload ->> 'origin') IS NOT
NULL`. A JSON extraction in a projection needs no parentheses, because nothing follows the
operator there — which is why every named query written before this one was fine.

### `mvn install` is not available offline in this environment

`maven-jar-plugin` is absent from `~/.m2`, and `install:install-file` cannot resolve its
own dependencies offline either. A fixture library that must be installable therefore does
the three steps by hand: `mvn -o compile` (the compiler plugin IS present), assemble the
jar, and lay it into `~/.m2/repository` at Maven's own layout path together with a minimal
`.pom` — offline resolution reads the POM, and a jar laid down without one is refused.
Assembling the jar with Python's `zipfile` rather than the JDK's `jar` keeps entry order
under the test's control, so the artifact is byte-identical between machines.

### DuckDB's Python scalar UDFs require numpy

`connection.create_function(...)` raises `Invalid Input Error: 'numpy' is required for this
operation, but it wasn't installed` — before it ever calls the function, and with nothing in
the message about UDFs being optional. numpy is not a Sextant dependency and adding one to
mask a column would be a poor trade. So the export projections that mask
(`resolved_config.value`, `endpoints.path`/`peer`) compute their masked strings **in
Python**, stage the ones that actually change in a temp table, and `LEFT JOIN ... coalesce`
against it. That keeps one redactor — restating its rules as SQL would be a second copy
drifting beside `domain/redaction.py` — and leaves every unmatched value byte-identical.

### A `domain` module cannot reuse an `application` one — move the rule down, don't copy it

2K's redactor lives in `domain` and needs the relaxed config-key binding rule that had lived
in `application/resolve/config.py` since 2F. The layering contract forbids the import, and
the tempting alternative — three lines of `lower().replace(...)` copied into the redactor —
is exactly the drift this codebase spends comments preventing. The move is `normalize_key`
into `domain/config_keys.py`, with both former callers repointed. When a second layer needs
a pure rule, the rule was in the wrong layer.

### Re-serializing JSON to mask one leaf moves bytes that had no reason to move

The bundle exit masks string leaves inside `call_sites.arguments`, `annotations.args` and
`config_entry` payloads. The obvious implementation — parse, map, `json.dumps` — rewrites
whitespace and escaping for **every** document it touches, including the overwhelming
majority nothing matched, and NFR-1's byte-identity claim then rests on Python's serializer
agreeing with DuckDB's forever. `Redactor.redact_json` returns the input string unchanged
when the mapped structure compares equal to the parsed original, so only genuinely masked
documents are re-serialized and staged. Same rule for the fact payloads. When a projection
is "mostly identity", make the identity path return the input, not an equal-looking copy.

### A live "excluded, so absent from resolved_config" pin needs a filename Spring would resolve

2K Task 2's fixture decoy had to prove `.sextantignore` keeps a file's config keys out of
`resolved_config` specifically — not merely out of the raw fact tree. `resolve_config`
only considers documents matching one of `config_model.sources`'s own filename patterns
(`application{-profile}.yml`, `bootstrap{-profile}.yml`); a file named something else
never reaches `resolved_config` regardless of whether it is ignored, so a decoy named
arbitrarily (`ignored-secrets.yml`) would pass the pin whether or not the ignore wiring
worked at all. The fixture decoy is `application-secret.yml` instead — a real, Spring-
recognised profile variant — so ignoring it is what makes its `secret` environment and
its key absent, and removing `.sextantignore` (checked by hand, not left to inference)
makes the same test fail.

### `.sextantignore` was designed once, before 2K, and drifted from what shipped

`docs/components/D04-config-and-exclusion.md` §3 already existed (per-directory
cascading ignore files, a JVM class-to-source resolution step, a different built-in
pattern list that explicitly excluded `.env` from ever being built in) — written before
2K's actual design (root-level only, no JVM resolution, `.env` IS built in) existed. Two
sections of one component doc had gone stale in different directions before either was
implemented. Amended in place with the same append-don't-rewrite pattern 2K Task 1 used
for §4 — caught by reading the component doc before writing the matcher, not after.

### `pathspec`'s `gitwildmatch` factory is deprecated in the pinned version, kept anyway

`pathspec==1.1.1` warns `GitWildMatchPattern ('gitwildmatch') is deprecated. Use
'gitignore' instead` at every `PathSpec.from_lines` call. The binding decision for this
task named `gitwildmatch` specifically (mirroring git's own wildmatch semantics is the
point DR-6 cares about), so the deprecated factory is used as instructed rather than
swapped for `gitignore` on this agent's own judgment — a factory-name substitution is
exactly the kind of unrequested deviation §1.1 rules against. The warning is harmless
(non-fatal, no `filterwarnings=error` in this suite) and worth revisiting the day
`gitwildmatch` is actually removed rather than merely deprecated.

### A document naming a mechanism is not evidence the mechanism exists

Phase 2O's spec called `detect.coordinates` "the SHIPPED jar-presence mechanism"
and had a task read a `constant` fact kind's value. Neither exists: `detect:` is
declared by every one of the 41 shipped catalogs and read by nothing, and D00's
`constant` kind has no producer at all. Nine such mechanisms are now registered
in [documented-not-implemented.md](documented-not-implemented.md), one of which
(a routing-ambiguity "collision detector" that D01 describes as a *property* of
identity, not a component) reached an implementation task's dispatch before a
grep caught it.

**What did not work:** four rounds of adversarial spec review. The reviewer read
the same documents the author did and cited the same lines back — a premise both
share is invisible to review.

**What worked, in minutes:** grepping `src/` for every mechanism the remaining
tasks named. Before writing a spec section or dispatching a task that depends on
a mechanism, verify it in the code and cite the `file:line`. GUIDELINES §5.3 now
requires this.

**The tell to watch for:** a doc sentence that reads as description ("that
collision is a routing-ambiguity finding", "the shipped jar-presence mechanism")
rather than as specification. Descriptive prose about a design's *consequences*
is easy to promote into a component that was never built.

### A column that exists is not a column that answers

2O Task 7b's brief said, of servlet handlers being `protected`: *"Is `protected`
visibility recorded? (It is — `workspace.py:163-168` projects it — confirm
rather than assume.)"* The projection is real, the citation is correct, and the
answer is still no: D00 §5a's `visibility` is TWO-VALUED, so a `protected`
member is recorded as `other` and the column cannot say which. A design built on
"widen the selector from `public` to `protected`" would have had nothing to
widen it to.

This is §5.3's second form — a mechanism that IS read but answers differently
than assumed — and it cost nothing here only because the brief said "confirm
rather than assume" and the probe printed the literal value. **The cheap check is
to read the VALUE the mechanism produces, not the line that produces it.** A
grep proves existence; only a value proves the answer.

(The design survived intact, for a reason worth keeping: the language forbids an
override from narrowing visibility, so the column was never needed. A rule that
mirrors the language rather than the fact stream had one fewer thing to get
wrong.)

### The rule that matters most was the one not written down

Phase 2O shipped an engine that minted a gRPC endpoint from `NightlyJob extends
AbstractJob` — plain Java inheritance, zero gRPC evidence anywhere. The match
required only "extends something in this module" plus "overrides a public
method"; the gRPC-specific marker was read *afterwards*, and only chose
resolved-vs-unresolved.

The uncomfortable part is that **no guideline was broken.** §8's design
principles were structural — single responsibility, dependency direction,
immutability — and the change satisfied every one. The project's actual central
invariant, "the failure mode is fabrication, not imprecision", lived in
ARCHITECTURE prose rather than in the rules document CLAUDE.md calls
non-negotiable. It is now a §8 bullet.

**The two fabrication shapes seen in practice**, worth recognising by sight:

- **Generic match, specific label.** A rule keys on structure any codebase has
  (an `extends` pair, a public override) and then labels the result with a
  meaning only some codebases have. The give-away: the framework-specific
  evidence is read *after* the match, to decorate it, rather than *as* the match.
- **Ambiguity emitted as certainty.** A lookup that cannot separate two
  candidates emits BOTH rather than neither — two rows, both `resolved`, sharing
  one handler symbol, at least one of them false.

Two supporting gaps found the same phase:

- **Every fixture demonstrated detection working; none demonstrated it
  declining.** The reviewer's own words were that the golden fixture missed the
  fabrication "by luck" — its single subclass happens to override nothing. §10
  now requires near-miss input that must NOT match, asserting *nothing* is
  produced.
- **A rationale comment went stale and nobody noticed.** `# No stamp — the row
  already carries its own response_shape` was true while one engine minted that
  identity and false the moment a second did; the merged row silently lost both
  contracts and the streaming detail that rides one of them. §9 now requires
  such a comment to state the condition that would make it wrong.

**The generalisable lesson:** when a review finds something the guidelines do
not forbid, the guidelines are the defect. Check whether the violated principle
is written down before concluding the implementer was careless.

### Two error classes that recurred, and what they cost before anyone counted

GUIDELINES §13.8 exists because of these. Both are recorded here so a later
reader inherits the count rather than starting it again — which is the whole
mechanism: without a record, the third occurrence looks like the first.

**Class 1 — treating documentation as evidence about code. Six occurrences.**
`detect.coordinates` (declared by all 41 catalogs, read by nothing), D00's
`constant` fact kind (no producer), a routing-ambiguity "collision detector"
(no findings mechanism exists at all), `root_kind`, `trace_of`, and project
catalogs (whose config key does not merely fail — it aborts the analysis).
Each was corrected on its own. The rule that would have prevented the rest is
§5.3, and writing it at the third occurrence instead of the sixth would have
put it in front of the spec that four of them went on to break.

**Class 2 — a rule matching on SHAPE and publishing a specific MEANING.
Four occurrences, four unrelated frameworks.** A gRPC endpoint minted from an
ordinary `extends` pair plus one overridden method. A module excluded from
analysis entirely because it applied `maven-publish`. An endpoint derived with
an empty name at `resolved`/`compiler`. A String payload published as part of an
AMQP destination because overloads collide on arity.

The give-away in every case: **the specific evidence is read AFTER the match, to
decorate it, rather than being the match.** `supertype_derived` matched any
subclass and then looked for a gRPC marker; the Gradle detector matched a
publishing plugin and then asserted "no endpoints"; `single_call` matched a name
and arity and then published whatever was in the slot. Four separate fixes found
that; one upstream question would have.

**The lesson is not "be more careful."** Every individual fix was correct, and
correctness at the instance level is precisely what hides the cause — each fix
feels like progress and leaves the generator running.

### A shared working tree is a shared failure surface

Three occurrences in one phase, one cause (GUIDELINES §13.9): agents and the
controller share one working tree AND one git index, and the pre-commit hook
validates the whole tree rather than the staged paths.

1. An implementer's unformatted in-flight file blocked an unrelated docs commit.
2. A second agent's bare `git commit` swept a first agent's staged files into
   its own commit — caught only because that agent ran `git show --stat`
   afterwards and recognised files it had not written.
3. A **read-only reviewer**'s probe files, created under `tests/`, blocked the
   controller's commit exactly as (1) did.

**Explicit pathspecs stop contamination, not blocking.** After (2) the rule was
"commit with `git commit -- <paths>`", which correctly prevents sweeping someone
else's staged work — and (3) happened anyway, because the tree is shared whether
or not your commit is scoped.

**The tell for (3) specifically:** a reviewer is asked to verify by execution,
execution means writing probes, and nothing in the brief said where to put them.
A reviewer that leaves files in the repository has modified the tree it was asked
to judge — which is a correctness problem before it is a hygiene one.

Isolated worktrees would also solve this and were rejected on cost: several trees
to merge is worse than one writer at a time.

### A deployment default is not a code fact — and this is the second time

2O Task 7 settled it for Actuator: `management.endpoints.web.exposure.include`
defaults to `health` alone, so a custom `@Endpoint` is a 404 out of the box —
and the endpoint still ships, because exposure is configuration any deployment
overrides and no repository can see. We report code and state the dependency.

Task 7b then measured TRACE as a 405 *even with `doTrace` explicitly
overridden*, concluded the address was unserved, and dropped `doTrace` from the
verb map. Same shape, opposite answer: Tomcat's `allowTrace` is connector
configuration, exactly as overridable and exactly as invisible. The 405 was a
fact about the probe's connector, not about the servlet. Re-measured over a
connector with `allowTrace="true"`, `service()` dispatches TRACE to `doTrace`
like any other verb, on all three containers.

**The tell is a probe that answers the same for the class that declares the
handler and the class that does not.** Rows 10 and 13 were both 405 — the
overriding class and the bare one, indistinguishable — which means the thing
being measured was upstream of the code under test. When a probe cannot tell
your two cases apart, it is measuring something else; change the configuration
that might be doing the masking and probe again, rather than recording the
answer.

The generalisation: before a measured absence becomes an exclusion, ask **who
can turn this on, and can we see them do it**. If the answer is "the deployment,
and no" — derive the row and state the dependency. §8's "exclude only on proof,
never on inference" is the same rule read from the other end.

**Outcome, and why §13.8 was amended because of this entry.** Naming §8 here was
the correct diagnosis and it changed nothing: the entry was written, the work
continued, and §8.2 exists only because a human raised it afterwards. §13.8 now
makes the SECOND occurrence the diagnosis point — state the cause, test it
against the principles that already exist, and where it violates one, stop and
settle the mechanism rather than recording the finding and moving on. A rule
already written and broken twice needs enforcement, not another correction. This
entry is the worked example in §13.8 and the sole hit in its audit list.

---

## A test that describes a module which cannot exist (principles sweep round 1a)

Four gates were added to catalogs this round, each mirroring what a framework
measurably does: a WebSocket endpoint is a class carrying `@ServerEndpoint`, a
STOMP handler lives on a `@Controller`, a Retrofit or `@HttpExchange` client is
an interface, a Spring Cloud Stream binding needs Spring Cloud Stream on the
build. **Every one of the four found a shipped test or fixture that had been
describing something the framework would never serve**, and each went red the
moment the gate landed:

- a Retrofit-shaped fact set whose docstring said "interface method" while its
  own `construct_kind` said `class`;
- a STOMP handler on a class carrying no stereotype at all;
- `fixtures/orders-service`, which has modelled a Spring Cloud Stream module
  since 2F — functional beans, `spring.cloud.function.definition`,
  `spring.cloud.stream.bindings.*` — while its POM declared no Spring Cloud
  Stream, a module with no binder and therefore no bindings.

None of these was caught by review, and none could have been: they are all
*plausible*, and the pipeline derived rows from them happily because nothing
encoded the framework's own precondition. **A synthetic fact set is a claim
about a module, and an unfalsifiable one is where a wrong rule hides.** The
practical form: when a fixture is built by hand, write down which real
declaration it is standing in for, and when a gate lands, expect the fixtures to
tell you which of them were fiction. The gate going red is the cheapest audit of
the fixture set anybody runs.

**And a mechanical one, learned the annoying way.** Recording a commit SHA in a
document and then `git commit --amend`ing that commit invalidates every SHA
written into it. Stamp the identifier after the commit is final, or in a
separate commit — the same "record identity from the run's own output" rule
§5.4 states for probes, applied to git.

## A marker declaring coverage is not coverage (principles sweep round 1b)

`@pytest.mark.declines("<catalog>")` made §10's near-miss rule countable, and
`test_catalog_near_miss_coverage.py` said in its own docstring what it could not
do: *"the marker is a DECLARATION by the test's author, not a proof."* Nothing
checked that the marked body discriminates, so a near-miss could pass because
its synthetic input was broken in some unrelated way — the guard it named
deletable, the test still green, and the catalog counted as covered.

**It shipped twice, and the second time it was the fix pass that wrote it.**
Sweep 1 found three non-discriminating markers by hand; the round correcting
them produced three more, `A-M2`'s servlet `bypassed_by` near-misses, whose
input declares no `doXxx` at all — the shape the branch *below* the bypass
already declines, so the bypass changes no outcome. §13.8 step 3 applies
exactly: a rule we had already written (§10) and still broke twice is a rule
with no reach, and the answer is enforcement, not another correction.

The enforcement is `scripts/guard_check.py` (`scripts/check.sh --guards`): a
test names the guard it pins with a second marker, the harness disables that one
guard in a COPY of the tree and reruns only the tests naming it, and a test that
still passes is a failure. Its first run measured all 28 declining tests in 41
seconds and found six that measure nothing — four predicted, two new.

Three things about it generalise beyond this one harness:

- **Disabling a guard is not deleting a line; it is writing the specific mistake
  the line exists to prevent.** Two of the servlet guards are no-ops when simply
  deleted (the loop they protect iterates zero times either way), and a run that
  counted a no-op mutation would have manufactured findings against tests that
  are fine.
- **A mutation harness needs a positive control more than the suite it
  measures.** The first run reported all 28 tests as unmeasurable, because the
  copied tree was missing one fixture. Without the control it would have printed
  "28 killed" and been believed — the harness's own version of the defect it
  exists to find.
- **Name the guard from the test's docstring, then check the name against the
  code.** Two guard names in the first registry were false — one pointed at a
  `declared_on` conjunct the catalog does not declare at all — and both were
  caught only by the run.


## Half a measured rule is a prediction (principles sweep, round-1 review)

**Twice in one fix pass, a probe measured half a framework rule and the
implementer reasoned about the other half. Both halves published a fabrication
where the code had previously derived nothing** — the only two places in the
whole sweep where the fix pass left the project worse than it found it.

- **`A-M15`.** CP-13 Q3 measured that the JAX-WS RI walks the implementor's
  `Class.getMethods()`. The fix widened the member rule to the superclass
  closure — correct — and enumerated one row per DECLARATION, where the
  enumeration it was mirroring returns one per SIGNATURE. An overridden SOAP
  operation shipped twice, the second attributed to a base the RI never
  exposes; and an override carrying `@WebMethod(exclude = true)` withdrew only
  its own row while the base's identical declaration published the withdrawn
  operation at `resolved`/`compiler`.
- **`A-M13`.** CP-13 Q1 recorded `calculateQueryMethods`' filter and named
  `isCustomMethod` inside it. The fix read the enumeration beside that name and
  stopped. The walk crossed every module-local superinterface, so a
  custom-fragment method — whose body lives in a hand-written `…Impl` — was
  published as `GET /orders/search/searchByFullText`, a route Spring Data REST
  does not serve.

**The cause is one, and no new principle is missing.** §5.4 says a verdict is
bounded by the configuration it measured. §8.1 rule 4 says never add behaviour
the framework does not have under the exact circumstances. Both were written,
both were agreed, and both were broken twice in one round — which §13.8 step 3
calls a rule with no reach, whose answer is a mechanism rather than another
correction. **That mechanism has not been built, and it is the thing to settle
before the next probe-backed fix**, not something this round closed.

Three things that generalise while it is unsettled:

- **A probe row that names a predicate has not opened it.** Q1's cell contained
  the literal string `isCustomMethod` and the fix pass read past it. A recorded
  instruction sequence is a list of questions as much as a list of answers, and
  the ones it names by symbol are exactly the ones nobody has looked at.
- **Extending the probe is cheaper than the argument about whether to.** Q5, Q6
  and Q7 took under an hour between them, jars already cached, and CP-9's rows
  41-46 needed one new probe servlet and one new fact reader. Both rounds that
  got this wrong had budget for the measurement and spent it on reasoning
  instead.
- **A generalisation can run in either direction, and the second is harder to
  see.** `A-M2` was found deriving nothing for a configuration a probe had not
  covered; the fix then derived SOMETHING for a different configuration the
  same probe had not covered. Reviewers looked for the first shape and found
  it. Ask of every verdict: which configurations does it now decide, and which
  of those did the run touch?

## A brief's premise can be stale in the direction that hides the defect (2O Task 10)

Task 10's brief opened: "a locally-implemented `@HttpExchange` interface derives
an **outbound** row — the module reported calling a service it actually serves —
and its inbound routes are missed entirely. Both errors in the same rows."

The first half had already been closed, by a different pass. `A-C1` gave
`spring-http-interface.yml` `declared_on: interface`, which on an outbound
catalog also engages the SEI fence, and the fence subtracts every interface the
module implements. So the shipped behaviour on the day the task started was not
a fabrication and silence — it was **silence alone**: no outbound row, no
inbound row, a whole HTTP surface absent from the export. `docs/documented-not-implemented.md`
still described the fabrication too, in the present tense.

Two things generalise, and the second is the uncomfortable one.

- **Check the defect the brief describes before fixing it.** It cost one query
  to find out, and it changed the implementation: the brief's Step 2 said "do
  NOT also add `declared_on: interface`", which reads as advice about a key that
  is not there and is in fact a warning about one that is. Had it been followed
  literally — flip added, fence untouched — the fence would have subtracted
  exactly the rows the flip flips and **no inbound row would have shipped at
  all**, which is the cancellation the spec warned of, reached from the other
  side. The fix was to make the fence YIELD to the flip, which nothing in the
  brief could have said.
- **A fix that converts a wrong row into a missing row moves the entry down the
  severity list and out of everyone's attention.** The fabrication was the
  reason #5 was called "the only entry where shipped output is actively false".
  Closing that half quietly demoted the entry to an under-report while its
  register text still claimed the worse failure — so the register overstated the
  problem and the estate understated it, at the same time. When a pass narrows a
  known defect rather than closing it, the register entry is part of the change.

### A fixture spelled in a simpler coordinate space cannot see a coordinate-space bug

Most synthetic fixtures in `tests/application/test_endpoints.py` write BARE
descriptors (`com/acme/api/OrderApi#`) where a real fact writes a
module-prefixed symbol (`sextant-jvm maven com.acme/orders-service 1.0.0
com/acme/api/OrderApi#`). That is harmless for a rule comparing two values from
the same space, and it is not harmless for a rule that crosses one.

Task 10's flip crosses one: it joins a declaring method to the method
implementing it, and an interface scanned out of an opted-in dependency jar
carries that jar's coordinates while the class implementing it carries the
module's. So every comparison is on the bare descriptor and the published symbol
is the prefixed one. The first version keyed its handler map on the **prefixed**
declaration and joined it against a **bare** one — which cannot match, so on
every real module the handler would silently have fallen back to the interface's
own method. Six tests passed, because in a bare fixture the two spellings are
the same string.

**The rule: a fixture for a rule that crosses a coordinate boundary must be
written in the coordinate space the facts actually use.** It costs one constant.
`test_effective_annotations.py`'s `_MODULE` prefix is the precedent, and it is
there for exactly this reason.
