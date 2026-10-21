# A merged value with a common root — design

**Status: RULED 2026-10-21.** The user ruled "take your partial approach" after rejecting the
first draft's decisions 2 and 3 — see §3 for what was dropped and why. The plan beside it
(`../plans/2026-10-21-merged-values.md`) sequences the work.

**Goal.** Close `OI-143`: Apollo's own HTTP client wrapper funnels every outgoing call through
one `restTemplate.exchange(parseHost(service) + path, …)`, and the document publishes that
module's outbound side as eight calls to half-known destinations and two to none — when the
code states **68 call sites with the verb and the path written at the call**. The inbound
side of the same module is 411 of 411. This is the largest remaining falsehood on a pinned
Spring Boot repository.

---

## 1. What is published today, and what the code states

Measured on `examples/apollo` at the pinned commit `ea35677`, `apollo-portal`:

| | rows | with a path |
|---|---|---|
| published outbound rows | 10 | 8, at `partial` (`<host>/health`, `<host>/services/admin`, `<host>/services/config`, `<host>`) |
| the wrapper's own two rows (`exchangeGet`, `doExecute`) | 2 | **0** — `path` NULL, `unresolved` |
| call sites of the wrapper in the module's main sources | **68** | 68 — `restTemplate.get(env, "apps/{appId}/clusters/{clusterName}/namespaces", …)` |
| distinct verb + path pairs among them | **32** | |

The eight pathful rows are calls a controller makes on `restTemplate` directly; they are
evidence that `partial` works (spec `2026-10-18-partly-known-addresses-design.md`), not that
the 68 are read. The two addressless rows are the funnel, and every one of the 68 ends in
them.

### 1a. What the walk itself recorded, from a shadow run

`sextant module analyze examples/apollo/apollo-portal --shadow` (2026-10-21) wrote 20,613
`value_resolutions` rows. The one catalog that matters here, `spring-resttemplate`, asked
1,303 positions: 958 `would_resolve`, 345 `unresolved`. Of every `not_readable` answer in the
module, **297 sit in `RetryableRestTemplate`** — more than any other class — and the `url`
slot of `doExecute`'s `exchange` answers the expression `{}{path}`: a hole for the host (the
discovered service, decision 6) and a hole for the path, which is the merge. So the walk gets
to the wall and names it; §2 is what the wall is made of.

## 2. The cause, exactly

The four causes the 2026-10-18 spec fixed got a partly-known address as far as the wrapper.
The fifth, found by building them, is below the walk:

```java
private <T> T execute(HttpMethod method, Env env, String path, …) {
  if (path.startsWith("/")) {
    path = path.substring(1);                       // ← one of two producers now
  }
  …
  doExecute(method, extraHeaders, serviceDTO, path, request, responseType, uriVariables);
```

```java
// doExecute
restTemplate.exchange(parseHost(service) + path, method, entity, responseType, uriVariables)
// parseHost: homepageUrl.endsWith("/") ? homepageUrl : homepageUrl + "/"
```

At the `doExecute` call, `path` is a MERGE of two producers — the parameter as it arrived,
and `substring(1)`'s result. The extractor's `MethodFlow.singleSource` reports a value with
exactly one producer and nothing otherwise, so the argument is written as
`{"kind": "unresolved"}` with **no `source` at all**, and the walk (`values.py`, "source is
None → `not_readable`") has nothing to follow. The 68 literals are one hop behind a wall the
fact stream put there.

That collapse was a ruling, not an accident: the Phase 2G checkpoint and ruling 1 of the
value-resolution design (2026-09-22) say a branch-merged value is `unresolved` — *"picking
one of them would be a fact about code that may never run"*. This design keeps that.

## 3. The design — two parts, and what was dropped

### 3a. The extractor reports a merge's candidates instead of collapsing them

A value with several producers is written as

```json
{"kind": "merge", "candidates": [{"kind": "parameter", "value": 2},
                                 {"kind": "unresolved", "source": 41}]}
```

— each candidate rendered through the same argument grammar a single producer is (D00 §5a),
so a literal, a parameter, a concat and a call result all appear as themselves. Nothing is
chosen; the fact says "one of these", which is more than `unresolved` says and exactly as
true. Capability `merge_candidates` (9.19) with a probe: javac's frame merge at an `if`
reassignment, measured on the fixture's compiled class and on
`RetryableRestTemplate#execute`.

Cost: `SourceValue.insns` already holds the producer set; the collapse is the one line that
drops it. Candidates are bounded by producers, which are bounded by the method's
instructions. Two identical candidates (the same literal on both branches) are one.

### 3b. A merge whose candidates share a ROOT resolves to the root's answers, inexactly

Look at what the facts say about the two candidates **without knowing what `substring`
does**: candidate 2 is call site 41, and call site 41's own fact says its receiver is
parameter 2 — candidate 1. The merge is `x` or `f(x)` for the same `x` and an unknown `f`.
Both branches are the same value, possibly re-rendered. That is a structural fact read off
two existing facts, not an interpretation of any method.

**Rule.** A merge has a root `x` when every candidate is either `x` itself or a call whose
receiver or argument is `x`. Such a merge resolves to `x`'s answers — through every edge the
walk already has, so a parameter root crosses `bound_to_parameter` to all 68 call sites and
ruling 1's multiplicity gives 68 answers — **marked inexact**: "an address derived from this
value was sent; its exact rendering was not read." A merge with no root is
`unresolved(non_enumerable)`, exactly as ruled; its candidates stay in the fact for a reader.

**What inexact does downstream.** An inexact literal fills a concat hole like an exact one
and makes the join's result an `expression`; `url_of_answer` publishes an inexact address at
**`partial`** — the word the resolution set already has for "part of this address was read",
and what the eight existing wrapper rows carry; `channel_of_answer` refuses it, because a
broker resolves a destination it is given and a re-rendered topic name is not one. Nothing
new in the closed sets.

For Apollo: `GET <host>/apps/{appId}`, `POST <host>/apps/{appId}/clusters/{clusterName}/namespaces`,
… at `partial`, peer NULL (the authority is a discovered service — decision 6 of
2026-10-19, refused, stands). The leading slash the wrapper strips is covered honestly: the
row carries the literal the developer wrote and says the rendering is not exact, rather than
asserting either spelling.

**The verb rides the same binding.** Found by building it: Apollo's `exchange(parseHost +
path, method, …)` takes its VERB as a parameter too, and `single_call` read that argument
verbatim — so the first run published the 68 with their paths and 51 of them with no verb
(`unresolved`, since a declared verb capture had failed). The walk resolves every slot of a
site per binding, so the verb's answer sits in the same binding as the path's: the enum the
wrapper's own `post()`/`put()`/`delete()` handed to `execute`, on the same calling path as
the literal. The engine now mints `(verb, destination)` pairs from the bindings instead of
one verb for every destination. No new mechanism — the same walk, one more slot read.

### 3c. Dropped, on the user's reasoning

The first draft proposed (2) judging agreement between candidates as a *path* (leading `/`,
`//`) and (3) a value-model entry modelling `String#substring(int)` on literals. The user
rejected both: the candidates never agree textually because the branch exists to change the
text, so (2) was a workaround; and (3) is a parser for one line of one project — every other
string manipulation (`trim`, `replace`, `toLowerCase`, `URLEncoder.encode`, a project's own
helper) would want its own entry, an open set nobody can enumerate, and each one is an
interpreter in disguise. §3b is one rule for all of them: it never asks what `f` does.

## 4. What it does NOT do

* **Does not pick a branch.** No root → `unresolved`, as ruled. Ruling 1 is unchanged.
* **Does not evaluate or model any method.** `substring` is never named anywhere.
* **Does not read the guard.** `if (path.startsWith("/"))` is not consulted.
* **Does not read the authority.** `<host>` stays `<host>`.
* **Does not claim exactness.** Every row this produces is `partial`. Where the branch
  did `path = prefix + path`, the candidates are `x` and `concat(prefix, x)` — a call whose
  argument is `x` — so the rule fires and publishes `x`'s literal, under-reporting the
  prefix; still derived from that literal, still `partial`. Named here so nobody reads
  `partial` as "almost resolved".
* **No new engine, no catalog change, no value-model entry.**

## 5. Performance (§8.7)

Measured before building. Sourceless `unresolved` arguments — the upper bound on merges that
gain candidates — are 457 of `apollo-portal`'s 15,172 (3%), 741 of 25,015 on
`yudao-module-system`, 41 of 37,667 on `mall-admin`. The walk visits candidates only at a
position a catalog asked about (1,303 on `apollo-portal` for the one catalog that reaches the
wrapper), so the cost is `candidates ×` today's per-position cost there and nowhere else. The
root check is two dictionary reads per candidate against indexes the walk already holds. A
fan-out the data shows to matter arrives as a reason word with the measurement behind it
(ruling 2), never as a number chosen now.

## 6. Decisions, as ruled 2026-10-21

| # | decision | ruling |
|---|---|---|
| 1 | the extractor reports a merge's candidates (`kind: merge`); a merge with no common root stays `unresolved`, candidates in the fact | **agreed** |
| 2 | a merge of `x` and calls-on-`x` resolves to `x`'s answers at `partial`; nothing is evaluated, no method is modelled | **agreed** — "take your partial approach" |
| 3 | a `substring` transform or identity entry | **dropped** — one parser per string manipulation is not enumerable |

## 7. What it closes, predicted and to be checked at the end

> **BUILT 2026-10-21 (Tasks 1–2), measured through `analyze` on `apollo-portal`:** the two
> addressless wrapper rows became **68 rows, every one at `partial` with its verb** — GET 39,
> POST 14, DELETE 8, PUT 7; 65 distinct verb + path pairs. `OI-143`'s own falsifier was
> "`apollo-portal` publishing the 64 call sites' own paths"; at this commit the module has 68
> and publishes 68. The first build published 61 with 51 verbs missing, which is how §3b's
> last paragraph was found. Full corpus measurement and the pins are Task 4.

`apollo-portal`: the two addressless wrapper rows become the 68 call sites' own addresses at
`partial`, one row per (caller, verb, path) as `single_call` dedups — between 32 and 68,
measured not predicted. The plan's measurement task also counts, across every pinned corpus,
how many merges gain a root and how many have none, so the rule's reach is a number rather
than Apollo alone. Amendments on completion: D00 §5a (the `merge` kind), M03 (capability
9.19), the value-resolution spec's §1 (a merge with a root), `OI-143` closed or re-measured.
