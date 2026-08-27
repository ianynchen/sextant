# M01 — Overlay

## Purpose

Turn overlay files into claims that can be trusted, ranked and refused.

It has three consumers — [M04](M04-resolver.md) applies fact overlays,
[M06](M06-stitcher.md) applies curated links, [M07](M07-renderer.md) applies component and
view overlays — and one precedence-and-validation contract. Duplicating that three times is
how three subtly different answers to the same question appear.

## Interface

```
validate(files, lookup)      -> ValidationResult
claims(files, slot)          -> [Claim]
resolve([Claim])             -> (winner, [OpenQuestion])
```

`lookup` is a function from an identifier to existence. **The module never queries the
workspace itself** — that would make it depend on the Resolver, which depends on it.
Passing the lookup in keeps the dependency one-way and makes the module testable with a
dictionary.

## Inputs

Overlay files ([D03](D03-overlay-schema.md)) and a lookup function supplied by the caller.

## Output

Validated claims, a resolved winner per slot, and open questions.

## Behaviour

### Validation comes first, and it is absolute

> **An overlay may name only symbols, endpoints, shapes and modules that already exist.**

A file naming anything else is **rejected whole**, not partially applied. This is not a
lint pass. It is the reason invention is structurally impossible rather than caught
afterwards — an unvalidated model stage will eventually report boundaries that exist in no
code, and only a check that runs by construction cannot be forgotten.

Two rules beyond existence, both from [D03](D03-overlay-schema.md):

- A `view` overlay may **never hide a terminal of kind `unresolved` or `cycle`**. Those are
  the places a person has to look, and no overlay can suppress them.
- A grouped dispatch must place every candidate in exactly one group, or the rendered
  diagram must state how many were not shown.

### Resolution is per slot, never by application order

A **slot** is one field of one entity — endpoint `ep_7c1a`'s request shape, or the target
of link `ln_3f8b`.

```
collect every claim for the slot
winner = the highest precedence
every losing claim that DIFFERS from the winner -> an open question
two claims at equal precedence that differ      -> an open question, and no winner
```

Order-independence is what makes the result byte-identical across runs (NFR-1). Applying
overlays in sequence and letting the last one win would make output depend on file
ordering.

### Precedence

**Computed here, never read from a stored field.** The rank is a pure function of a claim's
evidence, held as a fixed table in `domain/`:

| Rank | Evidence |
|---|---|
| 90 | `human` — curation |
| 50 | Everything code-derived |
| 10 | `llm` — **attach only, never overrides a fact** |

Facts do not carry a precedence column ([D00](D00-fact-schema.md) §3): the rank is policy,
and policy is applied at the moment of conflict, not baked into data at extraction time.

A rank-10 claim that contradicts a fact does not win and does not silently lose either: it
is dropped and recorded.

The specification and library tiers that a comparable design carried are absent here. A
contract artifact is either a build input, in which case its facts *are* code-derived, or it
is documentation and produces no facts at all — see [ARCHITECTURE.md](../ARCHITECTURE.md)
DR-4. Library references are matched by symbol coordinates, so no rank is involved.

### A curation that disagrees still wins, and is still recorded

If a person asserts a link whose payloads are structurally incompatible, the link is created
at rank 90 **and** an open question is written. Both readings are interesting: there may be
a gateway transforming payloads, which the architecture should say; or the curation names
the wrong endpoint. Accepting it silently hides a typo forever.

### Fact overlays and presentation overlays are applied at different times

| Kind | Applied during | Because |
|---|---|---|
| `curation` | `analyze` | It must change what `endpoint match` and `symbol impact` return |
| `components`, `view` | `render` | It changes how things are drawn and adds no facts |

Applying a curation at render time would make the documents and the queries disagree.

## What it must not do

- **No workspace access.** Existence arrives as a lookup function.
- **No repair.** An overlay naming a renamed symbol is rejected, never remapped by
  similarity.
- **No writing.** It produces claims; callers write.
- **No silent drop.** A claim that loses is either identical to the winner, or an open
  question.

## Honesty obligations

- A rejected overlay names every identifier that did not exist, not just the first.
- Every open question records both claims, their sources and their ranks.
- `overlay list` shows each file, its rank, and how many claims it makes — so "why does the
  document say this?" is answerable.

## Open decisions

| Decision | Blocks |
|---|---|
| Whether a curation may assert an endpoint no code declares, for a service Sextant cannot analyse | [D03](D03-overlay-schema.md), M06 |
| Whether a rejected overlay fails the run or is skipped with a loud report | M00 |
| How a curation survives a symbol being renamed | The curation lifecycle |
