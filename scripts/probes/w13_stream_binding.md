# W13 — Spring Cloud Stream: cardinality, and the protocol default (F2 §3.4)

**Question.** `spring-cloud-stream.yml` states two rules in prose that nothing had
checked against the framework:

1. **"Absent — every candidate binds, the framework's own default."** When
   `spring.cloud.function.definition` names nobody, this catalog binds every
   function bean it found. Is that what Spring Cloud Function does?
2. **"A name absent from `binder_protocols` leaves the row on this catalog's own
   declared protocol — a gap to grow this map from, never a guessed protocol."**
   The parenthetical is the claim to test: is a defaulted protocol a gap, or is it
   a guess?

The second question is the one worth the most care, and not because it is the more
likely. `protocol` is IDENTITY: DR-5 gates linking on protocol equality, so a row
published on the wrong protocol does not merely under-report inside this bundle —
it merges, or fails to merge, in **another consumer's** graph, against rows this
analysis never saw.

**Version scope (§5.4).** Read against **spring-cloud-function-context 4.1.2**,
whose `SimpleFunctionRegistry` carries the default-selection rule. The binding rule
is framework behaviour and can change between releases; widening the scope means
adding a coordinate to `scripts/probes/w13_stream_binding/run.sh` and re-running.
The Sextant side is read against the shipped `spring-cloud-stream.yml` at this
commit.

## Expectation table

| # | If | then |
|---|---|---|
| 1 | the framework defaults the definition only when exactly ONE function is eligible | two or more beans with no definition bind NOTHING, and a catalog binding all of them fabricates one row per bean |
| 1b | the candidate set counted HERE is not the set the framework counts | a suppression here is not evidence the framework suppressed, so it must be visible rather than silent |
| 2 | a binder name is absent from `binder_protocols` | the protocol is unknown, so no row can be published on any protocol — and the honest output is an open question |
| 3 | the catalog is dependency-gated | a run without the build declaration measures nothing, and must say so rather than reporting zeros |

## Observations

Verbatim from `scripts/probes/w13_stream_binding/run.sh`, which runs `sweep.py`. **The version below is the one the JAR itself reported** — and **not the version the coordinate list asked for**; `sweep.py` compares the two and ABORTS when they disagree, rather than printing a version it did not read.

| what the run read | 4.1.2 |
|---|---|
| artifact reporting this version | spring-cloud-function-context |
| where the jar states that version | pom.properties |
| class the rule was read from | `SimpleFunctionRegistry.java` |

### 1. The framework's own rule, verbatim

| what decides the default function | the code |
|---|---|
| `normalizeFunctionDefinition` | `if (eligibleFunction.size() == 1 && !eligibleFunction.get(0).equals(functionDefinition) && !functionDefinition.contains("|") && !eligibleFunction.get(0).startsWith("&")) { functionDefinition = eligibleFunction.get(0); }` |

### 2. What Sextant derives, per shape (`spring-cloud-stream.yml`)

| function beans | `spring.cloud.function.definition` | binder | rows | paths | questions |
|---|---|---|---|---|---|
| `orders` | — | `kafka` | 1 | `kafka:orders.topic` | 0 |
| `orders`, `payments` | — | `kafka` | 0 | — | 2 |
| `orders`, `payments` | `orders` | `kafka` | 1 | `kafka:orders.topic` | 0 |
| `orders` | — | `rocketmq` | 0 | — | 1 |

## Verdict

**1. The framework binds a function by default only when there is exactly ONE, and
this catalog binds all of them.** Section 1 is `normalizeFunctionDefinition`'s own
`if`, verbatim: the guard opens with **`eligibleFunction.size() == 1`**. With two
eligible functions and no `spring.cloud.function.definition`, the definition is
left as it was — empty — and nothing binds.

Section 2, row 2 is what Sextant does with that shape: **two rows**,
`kafka:orders.topic` and `kafka:payments.topic`, for an application that binds
neither. Row 3 is the control — the same two beans WITH a definition naming one
derive exactly that one — so the fabrication is the cardinality rule and not the
bean reading.

The catalog's sentence, "every candidate binds, the framework's own default", is
false. It is not a paraphrase that drifted: it names the framework as its
authority, and the framework's own code says the opposite.

**2. An unmapped binder is published on the catalog's declared protocol, and that
is a guess wearing a default.** Section 2, row 4: a module whose binder is
`rocketmq` — a real Spring Cloud Stream binder, absent from `binder_protocols` —
derives a row on **`kafka`**, with **zero** open questions. Nothing anywhere says
the protocol was not read.

The catalog calls this "a gap to grow this map from, never a guessed protocol". A
gap produces no row or an unresolved one; this produces a row that is complete,
confident, and wrong in the one column D01 uses as identity. Under DR-5 a consumer
links rows across bundles on protocol equality, so this row will link to Kafka
endpoints in some other service's graph that this module never speaks to, and will
fail to link to the RocketMQ ones it does.

**3. Both are the same defect wearing two faces**, which is why §3.4 pairs them: a
rule that cannot be answered is being answered anyway, once from a cardinality the
framework does not use and once from a default the catalog supplies. In both cases
the honest output is fewer rows and an open question.

**4. The cardinality rule cannot be mirrored exactly, and section 2 row 2 shows the
compromise.** The framework counts registered BEANS; `config_join._candidates` counts
every declared method whose return type is one of the declared interfaces, with no
`@Bean` conjunct (`docs/COVERAGE.md` records the over-count, and §8.1 forbids
inventing the conjunct without measuring which registration forms the framework
binds).

Those are different sets, so a count taken here is not the count the framework takes.
The first version of this rule suppressed silently on the reasoning that "the
framework binds nothing, so no row is the complete answer" — which needed the two
counts to be EQUAL. Measured: one real `Consumer` bean beside one ordinary helper
returning `Function` derived nothing at all, where the framework binds the bean. That
traded a known over-report for an unknown SILENT under-report, which §8 ranks worse:
an absent row nothing explains cannot be told from a module with no such boundary.

So `sole` files one `unselected_binding` question per candidate — row 2's two
questions. Not a guess, not a fabricated row, and not silence. The real fix is the
`@Bean` conjunct, and it is a measurement this repository has not made.

## What this probe deliberately did not measure

- **Whether a running Spring Cloud Stream application actually refuses to bind.**
  Finding 1 reads the selection code, which is where the rule lives; what a running
  binder then does with an unbound function is not established here.
- **The other conjuncts around the same `if`, described precisely.** The routing-function
  exclusion is in the `.filter()` chain ABOVE the guard, not in it, so it narrows the
  eligible set rather than the branch. `!functionDefinition.contains("|")` tests the
  definition STRING, not a bean. `!eligibleFunction.get(0).startsWith("&")` can suppress
  the default even for a lone candidate — a FactoryBean-dereference edge — so it is not
  purely an eligibility narrowing either. None of the three changes the answer for an
  EMPTY definition, which is the case this probe is about, and that is why they are
  listed here rather than measured. *An earlier version of this bullet described all
  three as narrowing which beans are eligible, which is true of only one.*
- **Every binder name.** `rocketmq` stands for "a name the map does not carry".
  Which names Spring Cloud Stream ships binders for is a different question, and a
  longer map would not change what an unmapped name should do.
- **Composed definitions** (`a|b`), which bind one endpoint from two beans. The
  catalog declares a `composition_separator` and that path is untouched here.

## How the verdict is consumed

**W13 acted on both findings, and the tables above are the POST-fix run** — which is
why section 2 now reads 0 rows for the two-bean shape and 0 rows plus 1 question for
the unmapped binder. That is deliberate, and it is the same choice
`scripts/probes/w11_javax_jakarta.md` states: a probe whose generated table shows the
broken state stops being re-runnable the moment the break is fixed, and a verdict
quoting numbers no current run produces is the CP-5 shape this harness exists to
avoid. What the tables prove today is that the fix HOLDS; each failure is one revert
away from being shown again:

| revert | the row that changes |
|---|---|
| `unselected_binds: sole` → `all` in `spring-cloud-stream.yml` | row 2 → **2 rows**, one fabricated endpoint per bean |
| `_protocol_of`'s `return None` → the catalog default, **and** `gaps`'s `_bean_name_questions` branch | row 4 → **1 row on `kafka`**, 0 questions |

*The second revert names two edits because one is not enough, and the table said one
until a review performed it: reverting `_protocol_of` alone gives 1 row and **1
question**, since `gaps` still finds the unmapped binder. A revert table exists so the
pre-fix numbers stay reproducible, and a table that does not reproduce them is worse
than none — it reads as verified.*

- The cardinality conjunct is `mapping`-level catalog data (`unselected_binds`), so a
  framework that DOES bind every candidate says `all` and nothing about this engine
  changes. The default is `all`, which is what the engine did before the conjunct
  existed.
- The binder rule is not a conjunct at all — it is the removal of a fallback. An
  unmapped name returns no protocol, the row is dropped, and `gaps` files a
  `binder_protocol` question carrying the binding and the configured name.
- **Only the binder case earns a question, and the asymmetry is the point.** With two
  or more candidates the framework binds nothing, so "no row" is the complete answer;
  there is nothing unanswered. With an unmapped binder the module binds something and
  the wire is unread. The first is knowledge, the second is a question — which is why
  this added one kind to `open_questions.QUESTIONS` rather than two.

**The ratchet hole §3.4 names in the same breath is closed by a guard, not by the
offline audit.** `tests/architecture/test_defaulted_identity_values.py` reads shipped
CATALOGS, and nothing in the data was wrong — `protocol: kafka` is a correct
declaration and `binder_protocols` a correct map; the default was in the engine's
fallback. `scripts/guard_check.py`'s `config_join.unmapped-binder-derives-no-row` and
`config_join.unselected-cardinality` break each line and require a named test to fail.
That file's own docstring now records the blind spot, so the next reader does not
conclude the offline audit covers every defaulted identity value.
