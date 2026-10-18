# Partly-known addresses: publish the half we read

**Status:** design. Written 2026-10-18 after `apolloconfig/apollo` was run through the
pipeline, which is what found the gap. Not yet planned.

**What it closes:** **nothing outright, and that is a correction to this spec's own first
draft.** It was written to close `OI-143` — a project's own HTTP client wrapper derives
nothing — and `OI-143` stays OPEN, narrowed: the four causes below are real and fixed, and
a fifth one nobody had looked for (§1a) still blocks the 64 rows that motivated the work.
The implementation measured it; the spec had predicted otherwise, one item in a one-item
closure list written specifically to avoid the previous spec's four false entries
(`2026-09-22-value-resolution-design.md`'s withdrawal block). Predicting closure is the
part that keeps failing, so §8 now records what the change DID move, measured.

**What it is not:** a way to guess a host. No hole is ever filled with anything but a value
the code states, and a hole nothing states stays a hole in the published text.

---

## 0. The measurement this exists for

`apolloconfig/apollo`, 530 non-test Java files, 8 modules, built at `ea35677`:

| | rows | resolved |
|---|---|---|
| inbound | **411** | **411 — all** |
| outbound | 8 | **0** |

The module makes **64** outgoing calls whose verb and path are both literals at the call
site:

```java
restTemplate.get(env, "apps/{appId}/clusters/{clusterName}/namespaces", ...)
restTemplate.delete(env, "/apps/{appId}?operator={operator}", appId, operator)
```

`restTemplate` is Apollo's own `RetryableRestTemplate`, not Spring's. Every call funnels
into one framework call site:

```java
restTemplate.exchange(parseHost(service) + path, method, entity, responseType, uriVariables)
```

whose url argument the facts record as `{kind: concat, value: "{}{}", source: 88}` — two
holes and no literal text. Hole 1 is a call on a parameter and does not resolve.

**Hole 2 is `parameter 3`, and this spec first said `bound_to_parameter` crosses it to the
64 callers. It does not.** Measured 2026-10-18 after the implementation left the row
addressless: the crossing reaches `execute`, one frame up, and stops there, because
`execute` REASSIGNS the local before the call —

```java
private <T> T execute(HttpMethod method, Env env, String path, …) {
  if (path.startsWith("/")) {
    path = path.substring(1);          // ← the value at the call is a MERGE
  }
  …
  doExecute(method, extraHeaders, serviceDTO, path, request, responseType, uriVariables);
```

— so the fact for that argument is a bare `{kind: unresolved}` with no `source` at all:
one of two producers, and the walk has nothing to follow. §1a carries it as the fifth
cause.

**So the document reports calls to unknown destinations where there are 64 to known
paths**, and after this change it reports 8 of them with a real path and 2 without (§8).
The verb is known too — the wrapper's method name is the verb — but that half is out of
scope here (§6).

---

## 1. The four causes, each probed separately

Stated as four because a fix for fewer than all four changes nothing, which a probe
confirmed: partial fill plus the product, without causes 1 and 4, left the module at 8 rows
and 0 paths.

| # | cause | where |
|---|---|---|
| 1 | the walk is consulted only where a catalog declares a hop | `single_call`, `elif "channel_via" in method:` |
| 2 | a join is all-or-nothing, so one unresolvable hole discards the rest | `values._joined` |
| 3 | several answers for one hole refuse the join rather than multiplying | `values._joined` |
| 4 | a partly-known address cannot be published | `shapes/arguments.url_of` |

### 1a. The fifth cause, found by implementing the other four

| # | cause | where |
|---|---|---|
| 5 | a local REASSIGNED between the literal and the call reaches the call as a merge of two producers, which no edge follows | the fact stream: `{kind: unresolved}` with no `source` |

**Not fixed here, and not a hole in the walk.** `path = path.substring(1)` means the value
at the call came from one of two places, and the honest answer for a merge is the one the
Phase 2G checkpoint already ruled: `unresolved`. Closing it needs one of two things that
are each their own piece of work — the extractor reporting a merge's CANDIDATES rather than
collapsing them, or a transform model that knows `String#substring` returns a substring of
its receiver. Neither is designed, and guessing either from here is how a wrong address
gets published at `resolved`.

**It is why `OI-143` stays open**, and why the four causes below are stated as a mechanism
rather than as a closure: they are what lets a partly-known address exist at all, and
Apollo's own 64 need the fifth as well.

**Cause 1 is a carried-over miss, not a new finding.** The identical hole was found and
fixed in `fluent` on 2026-10-17, and that file states the argument: *"An ASSEMBLED address
is not a hop, so it needs no `url_via`. `url_via` declares that the address lives on some
OTHER call's argument … A concat is neither: the catalog already pointed at THIS
position."* The question was never carried to the other two engines.

---

## 2. An assembled address is the catalog's own position, in every engine

Where a declared url or channel argument is not a plain string literal **and is a
`concat`**, the engine resolves that position through the walk. No `channel_via`/`url_via`
declaration is required, because none is being used: the catalog already named the
position, and the operands are the concat site's own arguments.

**With NO identity entries**, exactly as `fluent` does, and the reason is the one recorded
there on 2026-10-18: an `identified_by` entry says what a value STANDS FOR while a join
publishes text as an ADDRESS, and those part company — `String.valueOf(x)` is
`x.toString()`, so for a messaging destination whose identity is `"orders"` the rendering is
a vendor debug string. Consulting no identity holds the join to text the code states.

`interface_implementation` already consults the walk unconditionally and needs no change on
this axis.

---

## 3. A join fills the holes it can and leaves the rest as holes

Today `_joined` returns a complete `literal` or nothing. Three outcomes replace that:

| what resolved | answer | kind |
|---|---|---|
| every hole | the complete address | `literal`, `literal_kind: string` |
| **some holes** | **the template with those filled, `{}` for the rest** | **`expression`** |
| no hole | the template unchanged | `expression` |

**`expression` and not `literal` for the middle row, which is the whole safety of it.** A
partly-filled template is not a value the code states; it is a statement about part of one.
`channel_of_answer` refuses an expression as a destination, so **every messaging catalog is
unaffected by this change** — a Kafka topic assembled from a parameter stays `unresolved`
exactly as today, because a broker resolves a destination it is GIVEN and half of one is
not a destination.

**What makes it honest:** no hole is filled with anything but a `string` literal the walk
reached, and a hole nothing reached is printed as `{}` rather than dropped. `{}apps/{appId}`
says "something, then `apps/{appId}`", which is true and strictly more than `{}{}` says.

**And `{}{}` itself is NOT a partly-known address** (added 2026-10-18 from the first
measurement, where it reached the document as one). A template whose every piece is empty
carries nothing the code states — two runtime values and no text — so publishing it at
`partial` claims a read that did not happen. `url_of` requires text to survive removing the
holes; Apollo's `parseHost(service) + path` is exactly this row and stays `unresolved` with
`path` NULL, which is what it has always been.

§8.2 is untouched: a `${…}` operand answers `expression`, so it can never be one of the
filled holes.

---

## 4. Several answers for one hole are several addresses

Ruling 1 (multiplicity), already the rule for a single position, applied across operands:
one answer per combination, each on its own path, paths merged by `_combine`'s coherence
rule and incoherent combinations dropped.

For Apollo this is 1 × 64 = 64 answers, which the engine then dedups to distinct
destinations — and `caller` is already in `single_call`'s dedup key, so a second caller
reaching one path is a second row rather than a dropped one (F5 §6.1, W27's fix).

**A cap is NOT declared here, and that mirrors §3a's own ruling** (*no cap in v1, measure
first*): the product is over HOLES, and the hole count is the recipe's `\u0001` count — small
— while the answers per hole are what can be large. The plan measures the distribution over
all corpora **plus Apollo** before deciding, and a cap, if the data demands one, arrives as a
reason word with that measurement behind it rather than as a number chosen now.

---

## 5. A partly-known address publishes at `partial`

`url_of` accepts an `expression` answer and returns `(peer, path, Resolution.PARTIAL)`.
`PARTIAL` is already a member of D00 §4's closed resolution set, so no schema changes.

**Why a third value rather than `resolved` or `unresolved`.** `resolved` would claim an
address we do not have; `unresolved` is what the row says today and is what made 64 known
paths invisible. `partial` says what is true — part of this address was read — and it is the
word the set already has for exactly that.

**The peer.** `split_url` runs on the filled template as it does on a literal, with one
rule: **a peer is taken only when the authority it would come from contains no hole.**
`http://host/{}/x` yields peer `host`; `{}apps/{appId}` yields peer NULL, because an
authority half-read is not an authority. This is the same refusal `carries_expression`
already makes for `https://${billing.host}/orders`, one notation over.

**What a consumer must not do with it**, stated because the linking tier is not written yet:
a `path` containing `{}` is not an exact address and must not be matched as one. It is a
statement that part of the address was read, and a stitcher that treats it as literal text
would join two rows on a `{}` they share.

---

## 6. Out of scope, named so the closure list stays honest

- **The verb.** Apollo's wrapper carries it in the method name (`get`/`post`/`put`/
  `delete`), so the 64 rows would publish the verb of the framework call (`exchange`'s
  `method` parameter) rather than the caller's. Reading a verb through a wrapper is its own
  question and is not touched here.
- **The caller attribution.** The rows are attributed to the method making the framework
  call (`doExecute`), not to the 64 application methods behind it. Honest, and a reachability
  question rather than an endpoint one.
- **The host half of Apollo's address.** `parseHost(service)` where `service` is a
  discovered `ServiceDTO` stays a hole. 64 rows with a real path and no peer are the point;
  `OI-142` is where the peer half lives.
- **`OI-141`** (a binding's literal value as a fact) and **`OI-142`** (identity vs rendering)
  are untouched and stay open.

## 7. Standing requirements

- **No false positives.** Every hole is filled from a `string` literal the walk reached, or
  printed as a hole. The danger here is the inverse of the usual one: this converts blanks
  into assertions about a real system, so every conversion is a new claim.
- **Existing output moves in the step that says so**, and the pins that fix it move there
  too. Expected movers: any row whose address is a concat with at least one resolvable hole.
  Messaging rows do not move (§3).
- **Re-run `scripts/measure_value_walk.py`** — §3a's no-cap ruling was measured before
  `_joined` resolved holes at all, and §4 widens what one position costs.
- **Apollo joins the field corpus**, pinned, so this cannot regress and the next yield
  figure is measured on a corpus that contains the shape
  (`nothing-in-the-corpus-is-about-the-corpus`).

---

## 8. What it moved, measured

Built on branch `field/apollo`, 2026-10-18. Every figure here is a run, not a prediction —
§0's own prediction about the 64 callers was wrong, and that is what this section exists for.

**`apollo-portal`, the same commit before and after:**

| | outbound rows | carrying a path |
|---|---|---|
| before | 8 | **0** |
| after | 10 | **8, at `partial`** |

The eight: `{}/health` ×2, `{}/services/admin` ×3, `{}/services/config` ×2,
`{}?env={env}` — each a `parseHost(service) + "/literal"` whose host is a discovered
service address. The row count rises by two because
`PortalManagementController#getServerAddress` and `SystemInfoController#getServerAddress`
each make TWO calls that were indistinguishable while both paths were NULL. Two rows stay
addressless (`doExecute`, `exchangeGet`) and they are the 64's funnel, blocked by §1a.

**Nothing else in the estate moved.** All five field pins agree on endpoint counts and route
sets. (Three fail on `terminal_kinds`, identically at HEAD: the pins were never re-recorded
after the `throws` terminal kind landed, which is older than this branch and is its own
item.)

**The walk's cost** (`scripts/measure_value_walk.py`, re-run per §7): unchanged on the 27
corpora — estate maximum 11 paths, 38 visits. Apollo, measured for the first time, reaches
**685 paths and 3,365 visits** at one position (`PortalMetaDomainService#getMetaServerAddress`,
depth 18) and still walks in 0.05s. Apollo now joins that harness's corpora, since it is the
only module in the estate that reaches the product at all.

**The product, §4's open question** (`scripts/probes/cp37_join_product.md`): across 31
corpora the product enumerates at most **2** combinations, in `apollo-portal`, the same
corpus as the 685-path position. A path is not a candidate — a hole that reached no `string`
literal contributes one candidate, itself — so §4's stated reason holds on the data.
**No cap, and the number behind that is 2.**

**Guards.** 162 killed / 0 survived before; two added for the rules this change invented —
`arguments.a-template-with-no-read-text-is-not-partly-known` and
`arguments.an-authority-holding-a-hole-is-not-a-peer` — both killed by the test that names
them.
