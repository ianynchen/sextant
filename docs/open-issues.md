# Open issues — the standing register

**What this is.** One place for every known defect that is open, and every defect
this project introduces as it works. Created 2026-09-06 on the user's
instruction: *"Do record all new issues that are introduced, and I mean record
them in files in this repo, not in your memory file."*

**The rule.** A defect found or introduced during a task is entered here **in the
same commit group that found it**, with an id, its evidence, what it costs, and
what closes it. An issue leaves this file only when its fix ships, and the row
moves to CLOSED with the commit that closed it. A register that lies about its
own state is the defect it exists to catch.

**Relationship to the other registers.** `docs/principles-sweep-2026-09-05.md` is
the triage of one audit and stays frozen as that audit's record.
`docs/documented-not-implemented.md` holds one class — mechanisms documents
describe that code does not implement. `docs/COVERAGE.md` states BOUNDARIES: what
we cannot see and say so. **This file holds what is WRONG**, whether or not it is
also stated elsewhere.

Severity: **Critical** = publishes a wrong row a reader would act on ·
**Major** = wrong under a realistic input, or a silent drop · **Minor** = stale
prose or a latent shape with no live consequence.

---

## OPEN

### OI-2 — a DISABLED scheduled job is reported as live work
**Major · introduced 2026-09-06 by 2O Task 8 (`35fa4d5..4e51317`) · COVERAGE.md:1922**

`spring-scheduling.yml` treats no cron value as the framework's "never schedule
this" sentinel, because no probe has measured which value the framework so reads
and encoding one from memory is what §8.1 forbids. So a schedule the framework
will never run publishes a `scheduled_work` row saying it does.

**This is not the Actuator case.** A disable sentinel is not deployment-
overridable — it is a code fact we are misreading, so §8.2 does not excuse it.
The implementer chose correctly under "measure or do not encode", but the honest
close is a probe, and it is among the cheapest on the list.
**Closes by** one probe question and one catalog key. **Falsified by** a disabled
schedule appearing in an export.

### OI-3 — the multi-path WebSocket rule is documentation, not measurement
**Minor · introduced 2026-09-06 by 2O Task 13 (`2a1c918`)**

`channels_of` derives one row per registered WebSocket path. The behaviour rests
on Spring's documented registration semantics, **not on a live scan** — no pom in
this repository depends on `spring-websocket`, so nothing measured it. §8.1: a
rule taken from documentation is a prediction, and two of 2O's checkpoints
falsified exactly such predictions.
**Closes by** a fixture or probe that depends on `spring-websocket` and measures
the registration. **Falsified by** a real multi-path registration behaving
otherwise.

### OI-4 — one identity, two string spellings, and nothing enforces which you hold
**Major · SECOND OCCURRENCE (§13.8) · found 2026-09-06**

A symbol fact carries the full SCIP spelling
(`sextant-jvm maven com.acme/orders-service 1.0.0 com/acme/orders/X#m(sig_…).`)
while a call target carries the bare one (`com/acme/orders/X#m`). A join across
the two matches nothing.

- **Occurrence 1:** round 1 `F6` — the member selector compared raw parameter
  symbols against a normalised supertype.
- **Occurrence 2:** 2O Task 10 — the handler map was keyed module-prefixed and
  joined against bare descriptors. **No match on any real module, six green
  tests**, because the fixture spelled every symbol bare.

**Root cause:** synthetic fixtures are not in the same coordinate space as real
extraction, so a cross-space join bug is invisible to any test built on them —
which is most of our tests. It is a type-safety problem expressed as strings.
**Closes by** making the two spellings distinct types so mypy refuses the
comparison, or by fixture builders emitting module-prefixed symbols so tests
exercise the real space. §13.8 says diagnose at the second occurrence rather than
fix the instance twice — this row IS that diagnosis.

### OI-5 — MicroProfile GraphQL publishes a wrong address
**Major · pre-existing (`A-Mi9`) · stated, not closed**

`microprofile-graphql.yml`'s `path_fallback: construct_name` is a prediction: MP
GraphQL likely strips a `get`/`is` prefix, so `@Query List<Order> getOrders()`
would be served as `orders` while we publish `getOrders`. **A wrong address, not
an under-report** — the highest-value item in the probe backlog.
**Closes by** a live SmallRye run.

### OI-6 — 8 Class A Minors remain open
**Minor · pre-existing · `docs/principles-sweep-2026-09-05.md` §13**

`A-Mi4` (needs a D02 schema field — the `measured:` block), `A-Mi8` (writing an
unmeasured version would repeat CP-5's own mistake), `A-Mi17/18/19/20/21`
(extractor, engine and ratchet code rather than text), `A-Mi22` (a published
contract column, waiting on the serializer question). **None is a fabrication.**

---

## CLOSED

### OI-1 — every Spring Integration channel question was filed under `amqp`
**Major · introduced 2026-09-06 by 2O Task 9 (`bd61663`) · CLOSED 2026-09-06 by
`947102f` · COVERAGE.md:1933**

`spring-integration.yml` declared `protocol: amqp` and stamped it on **every**
`channel_destination` question it filed, a Kafka- or JMS-fed channel's included.
Closed by option (a), the rule Task 8 already agreed read one level finer:
`resolve/endpoints.py`'s check is keyed on whether the CATALOG derives endpoint
rows rather than on whether its style is nominally a wire one, so a catalog that
mints none declares neither `protocol` nor `direction`, and the question's column
is empty instead of guessed.

**A second defect fell out of it, fixed in the same commit.**
`config_join.derives_rows` answered "derives" for any catalog with an
`address_from_config` block, which is wrong by its own docstring: with no `key`
the engine asks configuration nothing and answers no channel. That wrong answer
is exactly what demanded a protocol of a file that mints nothing. Its other
reader is the engine ordering, where a catalog writing no rows may sort anywhere
— so the ordering half was harmless and the wire-identity half was not.

**Two shipped catalogs are governed** (§8.3's audit list, checked by
`test_call_engines`'s whole-estate run): `spring-integration.yml` and
`spring-kafka-media.yml`, whose top-level `direction: inbound` sat beside one
inbound and one outbound stamping rule.

**Not closed by this, and it is not a defect:** which broker feeds a channel is
still unread. That is the Stage 4 adapter split, and it stays in `COVERAGE.md`
as an ABSENCE — the honest state — rather than here as a wrong value.
