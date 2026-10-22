# A merged value with a common root — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Status: BUILT 2026-10-21** — ruled "take your partial approach"; all four tasks done; the
measured result (68 of 68 on `apollo-portal`) is in the spec's §7 BUILT block and `OI-143` is closed.

**Goal:** `OI-143`. Apollo's wrapper reassigns `path` on one branch, the extractor collapses
the merge to a sourceless `unresolved`, and 68 outgoing calls with their paths written at the
call publish as two unknown destinations. After this: the extractor writes the merge's
candidates; the walk resolves a merge whose candidates share a root to the root's answers,
marked inexact; the rows publish at `partial`.

**The deliverable is the document**: `apollo-portal`'s outbound section carrying the 68 calls'
own addresses (32–68 rows at `partial`, measured), not a fact kind.

**Spec:** `docs/superpowers/specs/2026-10-21-merged-values-design.md` — §3b is the rule, §3c
is what was dropped and must not creep back (no method is ever modelled), §4 the limits.

## Global Constraints

- **Nothing is evaluated and no method is named.** The root check reads two facts (a
  candidate, and the call site another candidate came from); it never asks what the call
  does. A `substring`, `trim` or `replace` entry anywhere is a violation of ruling 3.
- **Ruling 1 unchanged:** a merge with no root is `unresolved(non_enumerable)`.
- **Every row this produces is `partial`.** A consumer that would need exactness (a channel)
  refuses an inexact answer.
- **Framework words stay out of `resolve/`** (`test_source_rules`, `test_language_confinement`).
- **Fixtures with JDK 21.** Gate `JAVA_HOME=/opt/homebrew/opt/openjdk@21 bash scripts/check.sh`;
  `scripts/check.sh --guards`; `python scripts/field_check.py`.
- **Branch `spec/merged-values`** from `main` after PR #58.
- Match the surrounding style; do not refactor adjacent code.

## File Structure

| file | responsibility |
|---|---|
| `extractor-jvm/.../MethodFlow.java` | `argumentJson` renders a multi-producer value as `{kind: merge, candidates: [...]}` |
| `extractor-jvm/.../Capabilities.java` | `merge_candidates` (9.19) |
| `scripts/probes/cp41_merge_candidates/` | the probe: javac's frame merge at a reassignment, on the fixture class and Apollo's |
| `src/sextant/domain/facts.py` | `CallArgument.kind` gains `merge`; `candidates` |
| `src/sextant/application/resolve/values.py` | `Answer.inexact`; the `merge` branch and the root check; `_joined` accepts inexact |
| `src/sextant/application/resolve/shapes/arguments.py` | `url_of_answer` publishes inexact at `partial`; `channel_of_answer` refuses it |
| `fixtures/orders-service/.../clients/NormalisingBillingClient.java` | the wrapper shape, with callers whose literals differ by a leading slash |
| `docs/components/D00-fact-schema.md`, `M03-scanner.md` | the kind and the capability as built |
| `docs/open-issues.md`, `docs/COVERAGE.md`, `CHANGELOG.md` | close-out |

---

## Task 1 — the extractor writes the candidates · **DONE**

- [x] `MethodFlow.argumentJson`: a value with more than one producer renders each producer
      through the existing single-producer body (factored out, not duplicated) and emits
      `{kind: merge, candidates: [...]}`, identical candidates folded to one. A merge of one
      distinct candidate is that candidate.
- [x] `Capabilities`: `merge_candidates`, sorted; the capability pin in `test_asm_scanner`.
- [x] `ClassScannerTest`: a sample method reassigning a parameter on one branch; the argument
      at the consuming call is a `merge` whose candidates are the parameter and the call's
      result, in that order.
- [x] Probe `cp41_merge_candidates`: §5.4 provenance (JDK from the installation's own
      `release`), measured on the fixture class and on `RetryableRestTemplate#execute`.
- [x] `CallArgument` accepts the kind and `candidates`; D00 §5a row and prose; M03 row.
- [x] Gate.

## Task 2 — the walk resolves a rooted merge, inexactly · **DONE**

- [x] `Answer.inexact: bool = False`, carried through every hop like `yields`.
- [x] `_entry`: `kind == "merge"` → the root check (spec §3b) over the index's `sites`
      (receiver, `receiver_parameter`, arguments); root found → `_entry(root, …)` with every
      answer marked inexact; none → `unresolved(non_enumerable)`.
- [x] `_joined`: an inexact string literal fills its hole; `whole` is false when any filler
      is inexact, so the result is an `expression`.
- [x] `url_of_answer`: an inexact literal publishes through the `expression` path at
      `partial`; `channel_of_answer` refuses it with the reason an expression gets.
- [x] ~~`shadow.record_value_resolutions` records inexact answers distinguishably~~ — not
      done: the table's columns are fixed and the inexact answer records as the literal it
      is; the fact stream carries the merge, which is where a reader looks. Noted, not hidden.
- [x] `single_call` mints `(verb, destination)` pairs per binding, so a verb that is a
      parameter is read through the same walk as the path (found on Apollo: 51 of 61 rows
      had no verb; now 68 of 68 do).
- [x] Unit tests on hand-built facts (`test_values.py`): the rooted merge resolves; an
      unrooted merge is `non_enumerable`; two identical literals resolve exactly; the
      multiplicity through a parameter root; the channel refusal.
- [x] Gate.

## Task 3 — the fixture, the document, the guards · **DONE**

- [x] `NormalisingBillingClient` in `orders-service`: `if (path.startsWith("/")) path =
      path.substring(1); restTemplate.exchange(baseUrl + path, …)` with callers passing
      `"/billing/ledger"` and `"billing/ledger/{id}"`; the e2e pin: rows at `partial` with
      each caller's literal, and the document's outbound section showing them.
- [x] Every moved pin (document count, reach, dispatch, origins) re-pinned with its cause.
- [x] Guards: the candidates are written; a rooted merge resolves; an unrooted one does not;
      inexact never reaches `resolved`; a channel refuses inexact.
- [x] Gate, guards.

## Task 4 — measured close-out · **DONE**

- [x] `apollo-portal` through `analyze`: the outbound rows, counted and listed; the spec's
      §7 prediction checked.
- [x] Across every pinned corpus: merges that gained a root vs none (from the fact stream and
      a shadow run), recorded in the spec.
- [x] Field pins re-run; moved expectations re-recorded with cause.
- [x] `OI-143` closed or re-measured; the value-resolution spec's §1 amended; COVERAGE's
      outbound rows; CHANGELOG.
- [x] Full gate, full guard sweep, six field pins.
