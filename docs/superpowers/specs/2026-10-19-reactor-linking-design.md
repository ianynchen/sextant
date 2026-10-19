# Reactor linking — design

**Status: PROPOSAL. Six decisions below need the user's approval before Task 1** (GUIDELINES
§1.1). Nothing here amends `docs/components/*`; §7 lists the amendments this design would
need, to be applied only once approved.

**Goal.** Close the reactor case of `GAP-2`: Sextant reads that one module calls
`POST /owners/{ownerId}/pets` at `customers-service` and that another module serves exactly
that, and **nothing joins the two facts**. `FR-8` is unbuilt and `M05`/`M06` are `planned`.

---

## 1. What it closes, measured before it is built

Read from the workspaces `analyze` already wrote, over three real multi-module systems. No
code was changed to produce this table — it is what a matcher running `M06` steps 1, 2 and 4
would publish today.

| system | modules | outbound rows | endpoint links | participant links | narrowed | unmatched |
|---|---|---|---|---|---|---|
| `spring-petclinic-microservices` | 8 | 10 | **6** | 4 | 0 | 0 |
| `mall-swarm` | 6 | 12 | **7** | 5 | 0 | 0 |
| `apollo` | 5 | 10 | **5** | 0 | 1 | 4 |

**27 of 32 outbound rows gain a link.** Two things in that measurement are worth stating
because neither was predicted:

**`M06`'s claim that uniqueness needs no threshold holds on real code.** Zero narrowed links
on two of the three systems, one on the third. The spec says *"uniqueness across the system
does the work, and there is no parameter to tune"*; this is that claim measured rather than
reasoned.

**Apollo links by path alone, once the unread authority is dropped.** `apollo-portal` calls
`<host>/services/admin`; `apollo-configservice` serves `/services/admin`, uniquely in the
reactor. Five of Apollo's ten rows are this shape, and they are the dependency its document
is missing. See decision 6 — this is the one key built on an address half nobody read.

---

## 2. The participant set is the reactor

`M06` takes a `ParticipantSet` from `M05`, which reads `system.yml` and `system.state.json`
and fetches bundles produced by earlier, separate runs. None of that exists, and building it
is a phase: `M05`, `M01`, `D05`'s second half and two `D01` tables, with the value landing
only at the end.

**A Maven reactor is already a participant set that needs no manifest to discover.** All
three systems measured above are single reactors; `analyze` at a reactor root walks every
aggregator's `<modules>` breadth-first (`OI-139`) and writes one workspace per module. The
participant set is those modules.

```
sextant system analyze examples/spring-petclinic-microservices --environment default
```

**Participants are read from BUNDLES, not from workspaces**, which keeps `D01`'s storage
claim intact: the system workspace holds two native tables and federates the rest as views
over the bundles' Parquet. A module whose bundle is missing is a participant marked
`absent` with that reason, and `M06`'s rule applies — an unmatched call into an absent
participant is attributed to the gap, not reported as an architectural finding.

So `system analyze` requires `module export` to have run per module. That is `M05`'s own
division of labour said in one reactor's terms: *it fetches, it does not build*.

---

## 3. The filter chain, step by step

### Step 0 — environment

**Not a no-op, and an earlier draft of this design had it wrong.** A module's bundle declares
its environments (`petclinic`'s are `default` and `docker`) and `resolved_config` carries an
`environment` column. `--environment` selects one, defaulting to `default`, and every
comparison uses the values resolved for it. `M06`'s rule is untouched: *expression → this
environment's value → compare values*, never expression text.

Measured on `petclinic`: the gateway's eight route keys are identical under both
environments, so this changes no link there today. The flag exists because the mechanism is
real, not because this corpus exercises it.

### Step 1 — protocol

Equality. `http` to `http`, `soap` to `soap`.

### Step 2 — wire identity, three keys

| key | what it compares | measured yield |
|---|---|---|
| the discovery name the client states | `peer` against each participant's module name | the 4 + 5 participant links (gateway forwards) |
| verb and path template | `(protocol, method, path)` | the 6 + 7 endpoint links |
| path alone, unread authority dropped | `path` with a leading `<host>` removed | Apollo's 5 (decision 6) |

Path templates match by string equality in this slice, not by shape. `M06` specifies shape
matching — *"`/v1/orders/42` matches `/v1/orders/{id}`"* — and every one of the 18 endpoint
links measured above matches on the string, because both sides derive the template rather
than a concrete address. **Shape matching is therefore not in this slice** and is decision 3.

### Step 3 — structural compatibility

**Not in this slice.** Decision 2. On this corpus it would change nothing: all 18 endpoint
links are already unique on wire identity, so there is no candidate for a payload test to
discriminate between. It also carries `M06`'s open decision 4 (shapes across serialisation
formats), which this design does not settle.

### Step 4 — uniqueness decides the tier

`M06`'s table unchanged: one survivor is `resolved`/`name_match`, several is `narrowed` with
all candidates listed, none is unmatched with a reason.

---

## 4. A gateway route is a PATH PREFIX

Not a new concept and not a rewrite engine. A class-level `@RequestMapping("/owners")` in
front of a method's `@GetMapping("/{ownerId}")` makes `/owners/{ownerId}`; `setPathPrefixes`
does the same per package (`OI-148` §4). A gateway route is that shape with the two halves in
**two modules**:

```yaml
# the gateway declares
- id: customers-service
  uri: lb://customers-service
  predicates: [ Path=/api/customer/** ]
  filters:    [ StripPrefix=2 ]
```

```
customers-service serves      GET /owners/{ownerId}
full address                  GET /api/customer/owners/{ownerId}
         prefix from the route ───┘       └── path from the other module
```

So the link joins the gateway's wildcard row to each inbound row of the service the route
names, and the full address is the route's literal prefix plus that row's own path.

**`StripPrefix` is a GATE on that join, never a rewrite.** `/api/customer` is two segments
and the filter says `StripPrefix=2`; where those two numbers agree, prefix plus service path
is the gateway's address. Where they disagree the composition is wrong and the route keeps
its participant link with no endpoint links. Measured across the whole corpus:

| | |
|---|---|
| route path predicates | `Path=` — 9 of 9 |
| path-rewriting filters | `StripPrefix=N` — 9 of 9 |
| routes where `N` equals the prefix's segment count | **9 of 9** |
| other filters | `CircuitBreaker` ×1, which rewrites no path |

**One framework fact has to be measured, and only one** (GUIDELINES §5.4): what `StripPrefix`
removes from a path. CP probe, read off `spring-cloud-gateway-server-webflux`'s own class,
version stated. A route carrying `RewritePath`, `SetPath` or `PrefixPath` — none appears in
the corpus — publishes the participant link only, because there the gateway's address is not
the prefix plus the service's path.

### These links are `resolved`, not `narrowed`

`/api/customer/**` reaches all eight of `customers-service`'s endpoints, and **every one of
them genuinely is reachable** — a `GET /api/customer/owners/7` does reach
`GET /owners/{ownerId}`, and `GET /api/customer/petTypes` does reach `GET /petTypes`. Each
pair is individually certain, so each is its own `resolved` link.

`narrowed` means a set one of whose members is the real answer and we cannot say which, which
is `M06`'s own path-template example:

```
client calls      GET /v1/orders/42
server serves     GET /v1/orders/{id}     <- one of these handles it
server serves     GET /v1/orders/42       <- and we cannot say which
```

An earlier draft of this design proposed a `D01` vocabulary addition for the gateway case.
**That was wrong**, on a misreading of `narrowed`: eight certain links are not one uncertain
link, and the existing word set covers both situations.

---

## 5. Honesty obligations

`M06`'s list, minus what the deferred steps cannot answer:

- unmatched outbound endpoints and uncalled inbound endpoints, **separately**;
- unmatched calls into an `absent` participant, kept apart from real findings;
- every `narrowed` link with all candidates and the evidence that produced them;
- every route whose `StripPrefix` gate refused the composition, with the two numbers.

There is no `findings` table and none is planned (`D01`, W51): Sextant publishes the rows a
consumer derives judgements from.

---

## 6. Cost (GUIDELINES §8.7)

Counted before building, per `system analyze` over a reactor of `M` modules:

| | |
|---|---|
| bundle manifests read | `M` |
| federated `endpoints` view | one view over `M` Parquet files, one scan per matching pass |
| `resolved_config` read | one scan, filtered to the selected environment |
| matching | one pass over outbound rows, indexed by `(protocol, method, path)` and by participant name — no per-candidate query |
| writes | one insert into `participants`, one into `links` |

No read is per candidate and none is per module-pair. The largest reactor measured is
`mall-swarm` at 6 modules and 298 rows; `ruoyi-vue-pro` is the scale case at 7,244 files and
will be measured in Task 1 before the matcher is written.

---

## 7. Decisions needing approval, and the amendments each implies

| # | decision | amendment if approved |
|---|---|---|
| 1 | **The participant set may be a reactor**, discovered from `<modules>`, not only `M05`'s manifest | `M05` Inputs, `M06` Inputs, `M00`'s `system analyze` |
| 2 | **Step 3 (structural compatibility) is not in this slice** | `M06` Behaviour — a note that steps 1–2 and 4 ship first |
| 3 | **Path templates match by STRING, not by shape, in this slice** | `M06` step 2 — the shape rule stays specified, unbuilt |
| 4 | **No `proposals.yml`**; a `narrowed` link is recorded in `links` with its candidates and nowhere else | `M06` "Ambiguity goes to a person" — blocked on `D03`/`M01` |
| 5 | **No external participants**; a call matching nothing is unmatched, not a link to a declared external host | `M06` External participants — blocked on `system.yml` |
| 6 | **An unread authority may still match by path alone.** `<host>/services/admin` links to the one module serving `/services/admin`. It is `name_match` and `M06` permits path-only matching, but it is the one key built on an address half nobody read — and it is worth 5 of Apollo's 10 rows, 0 elsewhere | `M06` step 2 — a fourth row in the key table |

**Decision 6 is the one I am least sure of and it is a false-positive risk**, so it is stated
rather than folded in: the real target of a call whose host went unread may be a service
outside the reactor, and uniqueness inside the reactor cannot see that. For Apollo it is
correct — the portal does ask the meta service for config-service addresses — which is
evidence for it and not proof of it. Approving 1–5 and refusing 6 costs the five Apollo links
and nothing else.
