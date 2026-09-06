# GUIDELINES  

Operating guidelines for AI coding agents and human contributors.  

Sections 1–4 govern **how to work** on any change. Sections 5–12 govern **how the project is shaped**, standards, and delivery. Section 13 governs **agent-session discipline** (model use, checkpoints, explicit uncertainty). Re-read 1–4 before each task; 5–12 before structural decisions; 13 when working as an autonomous agent.  

---  

## 1. Think & Ask  
- State assumptions explicitly. If uncertain or multiple interpretations exist, ask—never pick silently.  
- If a simpler approach exists, push back and suggest it.  
- Simplicity (§2) does not override the duty to surface ambiguity. Resolve ambiguity first.  

### 1.1 The spec and plan are a contract — no unilateral deviations  

The design spec (`docs/components/*`, and REQUIREMENTS) and the phase plans (`docs/superpowers/plans/*`) exist so work is **trackable against an agreed contract** — NOT as a starting suggestion the agent edits and reports afterward. **Decide-then-inform is a violation.** Before acting, STOP and get explicit approval for any of:  

- **Scope changes** — deferring, descoping, or dropping anything in the plan/requirements (even "I'll do it in a later sub-phase"); adding scope not in the plan.  
- **Spec deviations** — a module layout, identifier grammar, table/schema shape, fact-stream contract, node/edge/catalog form, or construct set that differs from what the spec states (including "extending" a set the spec calls *closed*).  
- **Design choices not pre-decided** in the plan's decisions, the spec, or this document's defaults.  
- **Plan/spec edits themselves** — changing a decision, marking scope done/deferred, or amending a `docs/components/*` file.  

Allowed without asking: reading anything; running tests/linters/builds; writing tests; **implementing exactly what the plan/spec specifies**. When the spec is silent or wrong, do not pick — follow §6 (propose amendment with rationale, then proceed *once confirmed*; never code around a doc without updating it first, per §5).  

**Declare deviations explicitly; silence is not a declaration.** Every task report and hand-off states either `Deviations: none` or an enumerated list — a report that simply does not mention a descope has violated this section, not satisfied it. The same applies to a numbered step in a brief: each is completed or explicitly reported as not completed. Skipping one without saying so is the same failure as descoping without asking.  

**Pre-commit gate:** before committing or merging, confirm the change contains **zero un-approved deviations** from the spec/plan. If a deviation was necessary, it must already be an approved doc amendment. List any deviation in the message only after it was approved — never as a fait accompli.  

---  

## 2. Simplicity First  
- Minimum code to solve the exact request. Zero speculative features, abstractions, or unrequested config.  
- No error handling for impossible scenarios.  
- Rewrite 200 lines if it can be done in 50. (Test: Would a senior engineer call this overcomplicated?)  
- **One feature fully done beats ten half-baked.** *(User principle, 2026-09-05.)* "Done" means the mechanism exists, a consumer reads it, a test proves it, and the documents describing it are true. A feature that is designed, documented and partly wired is not 40% delivered — it is a **liability**, because every reader downstream treats the document as a description of what runs. Half-baked is not a lesser form of shipped; it is a debt with interest, and the interest is paid by whoever believes the doc.  

  The corollary, which is where this bites in practice: **a document describing an unbuilt mechanism is itself a half-baked feature.** Either finish it or retire the claim — but "retire the claim" is a decision to be taken deliberately and recorded, never a quiet deletion, and never a reason to leave the debt unaddressed. See §5.3, and `docs/documented-not-implemented.md`, which is the register this rule keeps.  

---  

## 3. Surgical Changes  
- Touch only what you must. Match existing style.  
- Do not "improve" or refactor adjacent code, comments, or formatting.  
- Delete unused imports/variables/functions created *by your change*. Do not touch pre-existing dead code; mention it instead.  
- Test: Every changed line traces directly to the user's request.  

---  

## 4. Goal-Driven Execution  

**Define success criteria. Loop until verified.**  

Transform tasks into verifiable goals:  

- "Add validation" → write tests for invalid inputs, then make them pass.  
- "Fix the bug" → write a test that reproduces it, then make it pass.  
- "Refactor X" → ensure tests pass before and after.  

For multi-step tasks, state a brief plan:  

```  
1. [step] → verify: [check]  
2. [step] → verify: [check]  
```  

AI agents additionally checkpoint after each significant step per §13.4.  

---  

## 5. Source of Truth  

Authoritative when documents disagree, in this order (initialize these under the `docs/` folder on first use if they do not exist):  

1. **[REQUIREMENTS.md](docs/REQUIREMENTS.md)** — functional and non-functional requirements.  
2. **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** — design decisions, technology choices, extension points, C4 diagrams. Must be consistent with REQUIREMENTS.md.  
3. **[PROJECT.md](docs/PROJECT.md)** — delivery status only (`planned | in-progress | delivered | deferred | cancelled`), each entry linking to a requirement. Create on first use if missing.  
4. **[RUNBOOK.md](docs/RUNBOOK.md)** - lessons learned throughout current project. To be reviewed before a task is being performed to avoid past mistakes.  

**CHANGELOG.md** follows [Keep a Changelog](https://keepachangelog.com/) and [SemVer](https://semver.org/). Every merge to main adds an `## [Unreleased]` entry; tagging rolls it into a versioned section.  

Reference across documents; never duplicate. Any change that alters behaviour or design **updates REQUIREMENTS.md and/or ARCHITECTURE.md in the same commit**.  

### 5.1 Schema changes update every schema-describing file  

The schema contract can described in several files at once; they must never drift apart. **When the schema changes** — update **all** of these in the **same commit**:  

- The affected **data definitions** under `docs/components/` (`D00`–`D06`) — these *are* the schema — and any other touched component spec.  
- **REQUIREMENTS.md / ARCHITECTURE.md** where the contract (FR-3 endpoint catalog, NFR-5 construct set, ARCHITECTURE §5 fact model) is stated.  
- **REQUIREMENTS.md § Traceability**, if a requirement gained or lost a realising component.  
- `CHANGELOG.md`.  

### 5.2 Architectural Changes

Architectural change should not take place silently. Always ask for approval before making an architectural change, and always record such changes as ADRs after approval. Clearly state what's replaced in the ADRs. Always apply architectural unit tests to ensure there is no authorized architectural changes. Exact architectural test framework is to be specified in ARCHITECTURE.md file.

### 5.3 Documents are authoritative for intent; code is authoritative for existence  

§5's ordering settles what the system **should** do. It does not establish what is **built**. Before any spec, plan, or review cites a mechanism as shipped — a catalog key, a fact kind, an engine style or capability, a table, a column, a detector — **verify it in `src/` and record the `file:line` that proves it**. A mechanism named only under `docs/` is a proposal until the code says otherwise.  

This is not a hypothetical risk. [docs/documented-not-implemented.md](docs/documented-not-implemented.md) is the register of mechanisms this repository documents and never built — including a catalog key declared by **every shipped catalog** and, when this was written, ignored by the loader (2O Task 6 made it real for two styles; the entry stays open, narrowed), two fact types defined and never constructed, and a fact kind D00 specifies with no producer anywhere. Phase 2O's design was written against two of them as though they were shipped.  

**Why this rule is a grep and not another review round:** four rounds of adversarial spec review did not catch those two, because the reviewer read the same documents the author did and cited the same lines back. A premise the author and reviewer share is invisible to review. It is visible to a grep, in minutes.  

**Cite the consumer, not the declaration.** The `file:line` that satisfies this rule is where the mechanism is READ, called, or acted upon — never where its name appears. `detect:` is declared by every shipped catalog — 41 when this was written, 55 today — so a grep finds it and a citation of any of those lines would satisfy a weaker rule; **nothing read it at all, and that was the entire defect**. A name existing is not a mechanism existing. *Updated 2026-09-05: 2O Task 6 made the key real, and the update is itself the rule's second form. `detect.coordinates` is now read — but only by `resolve/dependencies.py`, only for the two styles in its `DEPENDENCY_GATED` set, and so only for four of the 55 catalogs; the loader validates the coordinate SHAPE for all 55, which is a read a grep finds and a gate it is not. Cite `dependencies.py:108-137`, not the validation, and say which catalogs it reaches.*  

The same trap has a second form, which costs more because the grep succeeds honestly: a mechanism that IS read, but is **gated, scoped, or answers differently than assumed**. Four of this phase's spec errors were that shape — an inheritance walk that runs only for catalogs declaring a type-level gate; a catalog model that holds one style/protocol/direction triple, not three; a build probe that emits one boolean where plugin ids were assumed; a framework conditional whose second branch its own dependencies make unreachable. So verify what the mechanism DOES at the point of use, and for a conditional, name the circumstances under which it does not hold.  

Two corollaries:  

- **When a document and the code disagree about what exists, the code wins and the document is wrong** — fix it under §6 rather than building on it. (This is narrower than §6's conflict rule, which governs *behaviour*; this one governs *existence*.)  
- **Where a document deliberately describes something ahead of its implementation, it must say so in the document**, in words a reader cannot mistake for a shipped feature — `default_produces`'s own "specified here, not yet used" is the model. Silence is the failure mode, not intent.  

Prefer making this mechanical over remembering it: an architecture test that asserts every catalog key `D02` declares is read by the loader, and every fact field `D00` declares exists on its model, enforces §5.3 the way §8 requires rules to be enforced rather than aspirational.  

### 5.4 Empirical evidence is bounded by what it measured  

A checkpoint, probe, or experiment establishes its verdict **only for the configuration it ran against**. Extending it further needs either new evidence or an explicit statement that the wider scope is assumed and unverified — written where the verdict is written, so a later reader inherits the boundary along with the result. A recorded verdict otherwise reads as universal.  

Two failures this prevents, both from Phase 2O. A path-normalisation rule was measured against one framework's **server** side and then applied to every catalog sharing that protocol, including a client library whose relative-path semantics differ — so it rewrote addresses instead of normalising spellings. And a checkpoint was written with two branches for a framework conditional whose second branch is unreachable, because the framework's own non-optional dependency pins the antecedent true; implementing the unreachable branch would have produced a wrong address on every module of one build system.  

**Record identity from the run's own output, never from the parameter you passed in.** A probe that builds with `-Dversion=4.1.1` and then labels its results "4.1.1" has recorded an *intention*. It is evidence only if the running process said so itself — the banner it printed, the artifact it resolved, the version it reported. CP-5 in Phase 2O passed `-Dboot.version=4.1.1`, rebuilt without `clean`, ran the previous version's jar twice, and recorded eight observation cells for a configuration that never executed. Every claim in that table was independently true; none of it was measured where it said.  

Two consequences follow, and both are cheap:  

- **Generate the evidence table from the run; do not write it.** A hand-written table can drift from the run silently. A generated one can only be wrong if somebody edits it, which a diff shows.  
- **Make the mismatch fatal.** If the recorded identity and the observed identity disagree, the harness aborts. An advisory echo that nobody reads is not a check — CP-5's first version printed the version it *believed* alongside output from the version it *ran*, and the two disagreed in plain sight for a full review cycle.  

Hence, before writing a checkpoint with branches, ask **which branches are reachable**. That is a dependency-tree question, not a code-reading one, and it is cheap to answer before a spec is written and expensive to discover during implementation.  

---  

## 6. Conflict Resolution  

When code or evidence conflicts with the source of truth, **stop and surface the conflict before implementing**. Resolutions, in order of preference:  

1. Propose a doc amendment with rationale, proceed once confirmed.  
2. Propose an alternative that fits the existing design.  
3. Flag and ask.  

Never resolve a conflict by editing code in a way that contradicts the documents without updating them first.  

When **two patterns in the codebase contradict**, do not blend or split the difference — that produces the worst kind of change: it satisfies neither rule and obscures the inconsistency. Pick one (prefer the more recent or better-tested path), state why, implement consistently, and flag the other pattern for cleanup in a follow-up.  

---  

## 7. Agent Scope  

**Out of scope without explicit instruction:**  

- CI/CD config, build scripts, infrastructure-as-code.  
- Adding, upgrading, or removing dependencies.  
- Database migrations.  
- Disabling, skipping, or weakening existing tests.  
- Public APIs, wire formats, persisted schemas.  
- New global or static mutable state.  
- Bulk reformatting outside the requested change.  

**Always in scope:** reading any file for context; running tests, linters, formatters, and architecture checks; proposing follow-up work as separate items.  

---  

## 8. Design Principles  

Non-negotiable defaults. Deviations require justification in ARCHITECTURE.md.  

- **Single responsibility.** If a unit needs "and" to describe its purpose, split it.  
- **Composition over inheritance.** Inheritance permitted only for: framework integration, sealed type hierarchies, or exception hierarchies — all documented in ARCHITECTURE.md.  
- **Business rules in domain or application services**, never in controllers or transport-layer code.  
- **Dependencies flow inward** toward the domain.  
- **Extension points are explicit interfaces**, with documented contracts.  
- **No new global or static mutable state.** Immutability by default; mutation is a deliberate choice with a stated reason. Side effects at the edges.  
- **Never assert what the evidence does not support.** A derived record must be justified by evidence specific to what it claims: absent evidence, produce nothing; ambiguous evidence, produce nothing. Where a value cannot be read, record it as unresolved with its expression verbatim — *unresolved is an answer, invention is not*. (ARCHITECTURE states this as "the failure mode is fabrication, not imprecision"; it is repeated here because it is a design rule, not only a design note.)  
- **Exclude only on proof, never on inference.** A decision NOT to analyse, index, or report something is an assertion like any other and needs evidence just as specific. "This module publishes an artifact" does not establish "this module has no endpoints" — the second is knowable only by looking. Exclude where something is *provably* absent (Maven's own `<packaging>pom</packaging>` states the module produces no jar, so there is nothing to scan); never where a signal merely correlates with absence. The asymmetry is decisive: analysing something uninteresting costs a little time, while excluding something interesting removes it from the output entirely, and a reader of the result cannot tell it was ever there. This is the anti-fabrication rule above, applied to a negative claim — and it is easier to violate, because an omission leaves no wrong row to notice.  
- **Architecture rules are enforceable, not aspirational.** Layering, dependency direction, and naming conventions are encoded as automated architecture tests (tooling chosen in ARCHITECTURE.md). An untested rule is already being violated.  

### 8.1 Modelling a framework, library, or language  

Every catalog, engine, detector and rule that claims to know what a framework does is bound by these four. They exist because a derived record about someone else's framework is only ever as true as our model of it, and a wrong model is indistinguishable from a right one to every consumer downstream.  

1. **Mirror the framework's own rule; never substitute an approximation.** Read what the framework actually does under the exact circumstances, and encode *its* predicate — not a simplification that happens to fit the examples in front of you. Spring's server-side handler test is `AnnotatedElementUtils.hasAnnotation(beanType, Controller.class)` — **measured**, `spring-webmvc 6.2.15`, and unchanged across 6.1.6-7.0.9 — which is meta-annotation and type-hierarchy aware, so a custom stereotype meta-annotated `@Controller` or a `@Controller` base class passes it, and a check for a literal annotation name rejects both. *This sentence previously read "accepts `@Controller` **or** a type-level `@RequestMapping`" — that disjunct is an older Spring's rule and is absent from every version this repo targets. The example teaching "never assert a framework's rule from memory" was itself asserted from memory and shipped wrong for a month; it is corrected here from `javap` output, and `docs/principles-sweep-2026-09-05.md` carries the finding as `A-C7`.* Where the framework's rule is conditional, encode the condition, not the common case.  

2. **A valid usage must never be misinterpreted, and never error out.** Deriving nothing for a shape we cannot see is acceptable — provided rule 3 is honoured. Deriving the *wrong* answer is not, and raising on valid input is worse than both: this phase shipped a renderer that raised on a question kind the same phase had added, so a real module would have crashed at render.  

3. **Raise what the framework supports and we cannot see; never drop it silently.** A shape the framework serves and we miss gets a COVERAGE row naming the shape and why it is invisible. Under-reporting a stated boundary is honest; under-reporting an unstated one is a defect. **Where the escape is a USER ACTION, saying so in COVERAGE is not enough — it belongs in user-facing documentation.** COVERAGE records what we can see; the usage docs are where the person who can actually change the outcome will look. Supplying a dependency's bytecode is the user's responsibility; telling them plainly that a contract living in a dependency jar is invisible until they opt in via `extract_libraries`, and how, is ours.  

4. **Never add behaviour the framework does not have under the exact circumstances.** The test is not "would this be reasonable" but "does the framework do this, here, under these conditions". A class implementing an `@HttpExchange` interface is served only when it is a controller bean; deriving an inbound route for a plain `@Service` implementation invents an endpoint nothing serves.  

**A language's rules bind exactly as a framework's do.** The four rules above say "framework" throughout; a language is the same discipline with a stricter source. Java identifies a method by **name and parameter types in order** — arity is a consequence of that list, never the rule — so a catalog matching a call by name and argument COUNT has invented a rule the language does not use, and two overloads sharing a count are then indistinguishable. That is not a framework quirk to be probed; it is in the language specification, and mirroring it is not optional. The same holds for any language construct we key on: read the rule, encode the rule.  

**Operationally:** the framework's rule must be **measured before it is built on** (§5.4) — a rule taken from memory, from a reviewer's citation, or from documentation is a *prediction*, and two of Phase 2O's checkpoints falsified exactly such predictions. State the versions measured, because a framework's rule is version-scoped, and a rule verified on one version is evidence about that version only.  

**Diagrams:** Use Mermaid for L1/L2 in docs; L3 only if non-obvious. Use ASCII art for L2, class, and sequence diagrams during chat conversations. A lying diagram is worse than none.  

### 8.2 Code is truth; anything a deployment can overwrite is a possibility  

Sort every fact by whether it can change **without rebuilding the artifact**.  

**Truth:** source and compiled bytecode. A class, a method, an annotation and its arguments are what they are in the jar we read.  

**A declared default:** in-repo configuration. `application.yml`, `.properties`, and every value like them are the *lowest*-precedence source at runtime — an OS environment variable, a Kubernetes ConfigMap, a Helm value, `SPRING_APPLICATION_JSON`, a command-line argument or an external config location all beat them, and none of those is visible from a repository. So in-repo config is truth about **what the repository declares**, never about what runs.  

The rule this yields is asymmetric, and the asymmetry is the point:  

- **Never gate on an overridable value.** Excluding a row because the packaged config would disable it is excluding on inference, which §8 forbids. Gate only where the *code path does not exist* — an absent dependency, an unimplemented interface.  
- **Never assert one as a property of the running system.** "This endpoint is exposed" is not derivable; "this endpoint is declared and registered" is.  
- **Report the code fact, and name the dependency.** A row that depends on deployment says so, in COVERAGE and in the catalog.  

**The decision procedure**, because recognising the category is harder than running the test: before gating, ask *"what is the smallest change that makes this row appear at runtime?"* If the answer is a redeploy with different configuration, it is not a gate. If it is adding a dependency or writing code, it is. A writer does not need to know Spring's precedence table to answer that.  

**The direction it is violated:** both shipped instances suppressed a real code fact because a default said it was off. Neither fabricated by trusting config positively. A reviewer should look for the *missing* row, not the wrong one.  

Two rulings came from this before it was written: Spring Boot Actuator endpoints (`management.endpoints.web.exposure.include`, whose default is `health` alone and which any deployment routinely overrides) and servlet `TRACE` handlers (Tomcat's connector `allowTrace`, default false). Both were briefly treated as absent because the in-repo default said so. Contrast Spring Data REST, which we **do** gate: absent that dependency, no code path exists to serve those routes at all.  

**Its §8.3 audit list, run the day this was written — clean, and structurally so.** Every gating decision in the pipeline is one of two, both in `resolve/dependencies.py` and `resolve/capabilities.py`: the build declares a coordinate, or the scan produced the fact kinds a catalog needs. Neither reads configuration. `config_entries` is read in exactly one place, `resolve/config.py`, and only to **derive** `resolved_config` rows — a derivation, never an existence decision. Every catalog `when:` clause keys on a code fact (`implements`, an argument's value), none on a property. The four catalogs that name a config property are the two rulings above plus Spring Data REST, which gates on the dependency.  

So the rule holds today by construction rather than by discipline, and the invariant is the enforceable form: **no gating or exclusion decision may read `config_entries` or `resolved_config`.** The condition that would falsify this audit is a catalog gaining a gate keyed on a property — at which point the allowlist §8.3 requires starts at one.  

### 8.3 A new principle ships with its retroactive audit list  

Every rule in §5.3, §5.4, §8, §8.1, §8.2, §9 and §10 was written **after** the code it governs, because each was derived from a failure. That is the normal way a rule is earned — and it means writing one is a claim that *other places are broken the same way*.  

So a principle does not ship as prose alone. It ships with **every existing site the rule now governs, enumerated as a failing allowlist that must shrink**. An allowlist entry is a deliberate edit with a reason; an omission is a test failure.  

The cost of skipping this is measurable. §8.1's language rule says Java identifies a method by name and parameter types in order. It landed as prose and audited **zero** existing sites — while twenty-three shipped catalog rows were matching calls by argument count, three of which were publishing a message payload as a wire destination. The rule was right, and it reached nothing. The descriptor ratchet that followed (`tests/architecture/test_catalog_descriptor_coverage.py`) is what the rule should have shipped with.  

**A principle that audits nothing on the day it lands is a note, not a rule.** This is §8's "architecture rules are enforceable, not aspirational" applied to the moment of writing rather than to the rule's steady state — and it is the harder half, because a new rule is exactly when the backlog is invisible and the author is thinking about the defect in front of them.  


---  

## 9. Coding Standards  

### Documentation  

Every public symbol documents: **purpose**, **parameters and return** (meaning, units, ranges, nullability), **failure modes**, and **concurrency guarantees** when relevant.  

**Extension points** additionally document: required invariants, ordering and idempotency expectations, what the framework will and will not do, and examples when the contract is subtle.  

**Non-obvious decisions** document: alternatives considered, tradeoff accepted, and conditions to revisit. Prefer one comment explaining *why* over five restating *what*.  

**A comment justifying an omission states the condition that would make it wrong**, in the same sentence. "We do not X because Y" is a claim about the present that a later change can silently falsify — write "we do not X because Y, which holds as long as Z". A rationale that has quietly become false is worse than no comment, because the next reader trusts it.  

### Naming and style  

- Names describe intent at the call site, not implementation.  
- Booleans read as predicates (`isReady`, `hasExpired`).  
- Avoid abbreviations except established domain terms.  
- Formatter and linter configs are committed and run in CI; the agent runs them locally before proposing a change. Tooling named in ARCHITECTURE.md.  

### Errors  

- Typed errors or exceptions, not strings — callers can branch on them.  
- Messages name the failed operation, the inputs that mattered (no secrets), and the likely cause when known.  
- No silent catches without a comment explaining why.  

### Logging and observability  

- Log at boundaries (request, external call, state transition), not in tight loops.  
- Structured logging with stable field names; no string concatenation of values into messages.  
- Never log secrets, tokens, full PII, or full user-data payloads.  

---  

## 10. Testing  

GUIDELINES.md states *what tests must cover and how they behave*. ARCHITECTURE.md names the framework, assertion library, mocking library, and integration harness.  

### Coverage  

Every public method on a domain or application service has tests for the **happy path**, each **documented failure mode**, and **boundary conditions** (empty, absent, max, zero, negative, duplicate, concurrent if relevant).  

**Anything that detects, matches, or classifies is tested on near-miss input that must NOT match** — and the assertion is that *nothing* was produced, not that something different was. A suite where every fixture demonstrates the rule firing cannot tell you the rule declines correctly; it only tells you it is capable of firing. Derive the near-miss from the rule's own conditions: for each conjunct, an input satisfying every other one. This is distinct from the boundary conditions above, which vary a *value*; this varies whether the thing is *the kind of thing at all*.  

**And the near-miss needs a positive PAIRED with it: any rule or catalog key precise enough to be silently wrong needs a test proving the row still FIRES.** The near-miss proves the rule declines; the paired positive proves it still fires. A rule carrying only the first can rot into permanent silence and look correct all the way down — every near-miss still passes, because a rule that matches nothing declines everything.  

The concrete instance is `single_call`'s `descriptor:` key, added in Phase 2O to stop an overload's PAYLOAD being published as a destination. It is validated for well-formedness at load (`application/resolve/engines/single_call.py:601`, which refuses a value not opening with `(`), and it is matched verbatim against the call site's own `target.descriptor` (`:502`). A descriptor that is well-formed and WRONG — one character off, or the source-level signature rather than the erased one — passes the load check, matches nothing, and CLAIMS its arity anyway (`:504`), so the whole overload set derives nothing. Silently: no error, no COVERAGE row, and every test that asserts absence still passes. Each of the three shipped `descriptor:` rows therefore has such a pair — `spring-rabbit-template.yml`'s arity 3 and arity 2, and `spring-jms-template.yml`'s arity 2, each with a near-miss that derives nothing beside a positive that still resolves.  

The test for whether a key needs the pair: could a change to it be WRONG without being INVALID? A verbatim-compared string, an exact arity, a fully-qualified annotation name and a package coordinate all answer yes.  

Branch and condition coverage are diagnostics, not targets. Coverage drops require justification; coverage increases driven by trivial tests are equally suspect. Bug fixes ship with a regression test that fails before the fix.  

### Behaviour  

- Tests describe behaviour, not implementation; renaming a private method must not break tests.  
- Tests should encode **why** the behaviour matters (invariants, risks), not only snapshots of outputs — see §13.3 for the agent-facing bar.  
- Test names read as specifications (exact convention in ARCHITECTURE.md).  
- Each test is independent — no shared mutable state, no ordering dependencies.  
- No sleeps for synchronisation; use awaitility/polling primitives or deterministic clocks.  
- Flaky tests are bugs: quarantine immediately, fix or delete within a defined window. Never re-run until green.  

### Test types  

- **Unit** — fast, isolated, no I/O. Bulk of the suite.  
- **Integration** — real adapters against test doubles, in-memory implementations, or testcontainers. Mocks acceptable at boundaries with systems the team does not own.  
- **Architecture** — enforce §8 in CI alongside unit tests.  
- **Contract** — for services consumed by or consuming other services, when applicable.  

### Don't test  

Framework behaviour, trivial accessors, generated code, or implementation details that exist only to make a test pass.  

---  

## 11. Version Control  

**Conventional Commits**: `type(scope): summary`. Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `build`, `ci`, `perf`. Breaking changes use `!` and a `BREAKING CHANGE:` footer.  

**PR description** states what changed and why (linking REQUIREMENTS.md), any deviation from ARCHITECTURE.md with justification, risk and rollback notes for non-trivial changes, and new dependencies with rationale.  

### Versioning  

The package version in `pyproject.toml` follows [SemVer](https://semver.org/) and is bumped **on every change that alters shipped behaviour**:  

- **patch** (`0.0.x`) — bug fixes (no behaviour/API addition).  
- **minor** (`0.x.0`) — backward-compatible enhancements / new features.  
- **major** (`x.0.0`) — breaking changes. Pre-1.0, a breaking change may ride a minor bump but must be called out with `!` / a `BREAKING CHANGE:` footer.  

Pure docs, chore, test, or behaviour-preserving refactor changes do **not** bump. **Propose the exact bump and get explicit confirmation before applying it — never bump silently.** A change may span several commits; bump once, on the commit where the behaviour lands.  

### Definition of Done  

- [ ] Compiles cleanly; all tests pass locally.  
- [ ] Run linter before commit code.  
- [ ] New behaviour has tests per §10.  
- [ ] Architecture tests pass.  
- [ ] Formatter and linter clean.  
- [ ] REQUIREMENTS.md / ARCHITECTURE.md updated in the same commit if behaviour or design changed.  
- [ ] Schema change? All schema-describing files updated together.
- [ ] PROJECT.md status updated.  
- [ ] CHANGELOG.md `Unreleased` updated for user-visible changes.  
- [ ] Package version bumped per SemVer (§ Versioning) if behaviour changed — proposed and confirmed before applying.  
- [ ] RUNBOOK.md updated with lessons learned.  
- [ ] Conventional Commits format.
- [ ] Push request created if remote git repository is setup.

---  

## 12. When in Doubt  

Ask before assuming. Prefer the option that is easier to undo, easier to read six months from now, and — if equivalent — smaller.  

---  

## 13. Agent discipline  

Rules in this section apply to **AI coding agents** in addition to §1–§12. They operationalize judgment and honesty defaults that plain "be careful" guidance does not nail down.  

### 13.1 Use the model only for judgment calls  

Use the language model for: classification, drafting, summarization, extraction from unstructured text.  

Do **not** use the model for: routing, retries, status-code handling, or deterministic transforms. If a status code or a short piece of plain code already answers the question, code answers the question.  

### 13.2 Read before you write  

Before adding code in a file: read that file's public surface (exports, primary types), the immediate caller, and obvious shared utilities. If the reason for the existing structure is unclear, ask before extending it. "Looks orthogonal to me" is a warning sign, not a green light.  

### 13.3 Tests encode intent, not only behaviour  

Every test should make **why** the behaviour matters obvious — not only **what** happens. A test that would still pass when business rules change but only fixtures were renamed is weak. Prefer assertions and names tied to the requirement or invariant. (Aligns with §10; this section states the bar explicitly for agents.)  

### 13.4 Checkpoint after every significant step  

After each meaningful step in a multi-step task: briefly state what was done, what was verified, and what remains. Do not continue from a state you cannot describe back to the requester. If continuity is lost, stop and restate the plan from evidence (files, test output), not from memory alone.  

### 13.5 Match the codebase's conventions, even if you disagree  

Conformance beats personal taste inside the repo: naming, file layout, patterns (e.g. class vs hooks, snake_case vs other styles) follow what is already established. If a convention appears harmful, surface it explicitly and propose a separate change — do not fork style silently in one patch.  

### 13.6 Fail loud  

If something might not have worked, say so. Do not claim "migration completed" when rows were skipped without calling that out; do not claim "tests pass" when any were skipped; do not claim "feature works" when an agreed edge case was not checked. Default to surfacing uncertainty and partial results over confident understatement.  

### 13.7 New definition-model fields default to `None`  

New definition-model fields default to `None` — non-None defaults change the canonical snapshot dump and cause universal false drift.  

### 13.8 The second occurrence is a diagnosis; the third is a stop  

When the same class of error happens **twice**, record it — in the working ledger during a task, in [RUNBOOK.md](docs/RUNBOOK.md) across tasks. **The record is the mechanism, not the bookkeeping.** Without it the third occurrence looks like the first, which is how six instances of one defect can each feel novel in the moment.  

**Then do the diagnosis, at the second — not the third.** Recording is not enough, because "stay alert" is not an action anyone takes. At the second occurrence:  

1. **State the cause**, not the two symptoms. Why did this happen — what wrong assumption, missing fact, or misleading document produced both?  
2. **Test the cause against the principles that already exist.** Read §5.3, §5.4, §8, §8.1, §8.2, §9 and §10 and ask whether the cause is something one of them already forbids.  
3. **If it violates an existing principle, stop and raise it.** Do not fix the instance and continue. A rule we already wrote, already agreed, and still broke twice is not an implementer's slip — it is a rule with no reach, and the fix is a mechanism, not another correction. Bring it to your human partner and settle the mechanism before resuming.  
4. **If no existing principle covers it, the missing principle is the finding.** Write it, with the audit list §8.3 requires.  

The difference between 3 and 4 matters. A *new* rule needs the backlog it now governs. A *broken* rule needs enforcement — a test, a ratchet, a review instruction — because prose has already been tried on this exact cause and lost.  

**The worked example is this rule's own second occurrence, and it is uncomfortable.** A deployment default was read as a code fact twice: Spring Boot Actuator's `management.endpoints.web.exposure.include`, then Tomcat's connector `allowTrace`. The RUNBOOK entry recorded the second correctly, generalised it correctly, and even *named the principle it violated* — "§8's 'exclude only on proof, never on inference' is the same rule read from the other end" — and then the work continued. The analysis was right, written down, and inert. §8.2 exists because a human raised it afterwards, not because the record did. **Naming the violated principle IS the trigger; it is not the conclusion.**  

On the **third**, stop and raise it with your human partner. Do not fix it and continue. A defect class recurring three times is evidence of a systemic cause — a wrong assumption, a missing rule, a misleading document — and **fixing instances is what prevents you from finding it**. Each individual fix is correct, feels like progress, and leaves the cause untouched.  

**Count by cause, not by symptom.** "Cited a mechanism that does not exist" and "assumed a mechanism's behaviour from its name" look like two bugs and are one cause — treating documentation as evidence about code. Counted separately, both stay below the threshold forever.  

Phase 2O is the worked example, twice over:  

- **Six phantom mechanisms.** `detect.coordinates`, the `constant` fact kind and the routing-ambiguity detector were each corrected individually before anyone asked why they kept appearing. The answer became §5.3 — a rule which, written at the third occurrence rather than the sixth, would have preceded the spec that four of them went on to break.  
- **Four fabrications, four frameworks.** A gRPC endpoint minted from an ordinary `extends` pair; a module excluded because it published an artifact; an endpoint derived with an empty name; a message payload published as part of a destination. One cause: a rule matches on SHAPE and then publishes a specific MEANING, with nothing checking that the shape entails the meaning. Four separate fixes found it; one upstream question would have.  

**Its §8.3 audit list — every recurring class recorded to date, re-read against step 3.** Two of the three had no existing principle to violate: "documentation as evidence about code" (six occurrences) produced §5.3, and the four fabrications produced §8's anti-fabrication and exclusion rules — in both cases the correct outcome was a new rule written late, which is step 4. **One is a real hit.** "A deployment default read as a code fact" reached its second occurrence *after* §8's "exclude only on proof, never on inference" was already written and while the entry recording it cited that very rule. Under this amendment it stops there. That is the only entry in the list, and the list is short because the record only began in Phase 2O — which is itself the argument for keeping it.  

---

### 13.9 One writer per branch; everyone else reads or uses the scratchpad  

Agents and the controller share **one working tree and one git index**. Only ONE agent may do write-related work on a branch at a time. Every other agent working that branch is **read-only**, and anything it needs to create — probe scripts, scratch fixtures, throwaway harnesses — goes to the session scratchpad, **never into the repository**.  

This applies most sharply to reviewers. A review verifies by execution, which means writing probes; those belong in the scratchpad, because a reviewer that leaves files in `tests/` has changed the tree it was asked to judge.  

**Why a shared tree is not survivable without this rule**, from three occurrences of one class in Phase 2O: an implementer's unformatted in-flight file blocked an unrelated docs commit, because the pre-commit hook validates the WHOLE tree rather than the staged paths; a second agent's bare `git commit` swept a first agent's staged files into its own commit; and a read-only reviewer's probe files blocked the controller's commit the same way as the first. Explicit pathspecs (`git commit -- <paths>`) stop the contamination but not the blocking — the tree is shared whether or not your commit is scoped.  

Isolated worktrees would also solve it and are deliberately NOT the answer here: the merge cost of several trees exceeds the coordination cost of one writer.  
