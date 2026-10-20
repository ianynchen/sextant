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

**Participants are read from the module WORKSPACES `analyze` already wrote** (the user's
choice, 2026-10-19), not from exported bundles. A module whose workspace is missing is a
participant marked `absent` with that reason, and `M06`'s rule applies — an unmatched call
into an absent participant is attributed to the gap, not reported as an architectural
finding.

**This is a deviation from `D01` and it is declared rather than reasoned around.** `D01`'s
system-scope rule says the estate's graphs are *"views over the bundles"* and that federating
Parquet *"cannot drift from the bundle, because it IS the bundle"*. Reading workspaces keeps
the half of that rule which matters — **the system workspace still copies nothing**, it holds
two native tables and reads the module workspaces through a view — and gives up the
anti-drift half.

Why that trade is right HERE and nowhere else: a reactor is one build, so every module
workspace comes from the same run, and there is no second artefact for one to drift from.
Requiring bundles instead would add a `module export` per module before `system analyze`
could say anything, for an anti-drift guarantee that a single build already provides. When
`M05` arrives and participants come from separate runs of separate repositories, the bundle
rule is the right one and this one does not generalise — which is exactly what the `D01`
amendment must say.

---

## 3. The filter chain, step by step

### Step 0 — environment

**An addition to the approved scope, declared.** The scope the user approved said *"no
environments"*, and that was right about `system.yml`'s single-environment declaration, which
this slice does not build. It is wrong about the mechanism: a module's manifest declares its
environments (`petclinic`'s are `default` and `docker`) and `resolved_config` carries an
`environment` column, so a comparison that ignored it would be comparing values from whatever
environment happened to be in the row.

So `--environment` selects one, defaulting to `default`, and every comparison uses the values
resolved for it — `M06`'s rule untouched: *expression → this environment's value → compare
values*, never expression text.

**APPROVED by the user, 2026-10-19: the flag**, with a refusal underneath it.

**It costs nothing either way on this corpus, measured.** 119 keys resolve to different
values per environment across the estate — `apollo-portal` 24, `apollo-configservice` 19,
`mall-admin` 23, `spring-petclinic-rest` 12, the seven `petclinic` modules 0 — and **not one
of them is a wire identity**. They are datasource URLs, Nacos server addresses, LDAP
attribute mappings, log levels and Eureka flags. The two places an environment could move a
link were counted and both are zero:

| | |
|---|---|
| gateway routes built on a placeholder (`uri: lb://${…}`, `Path=${…}/**`) | 0 |
| outbound rows whose `peer` or `path` is still a `${…}` | 0 |

So no link in the corpus moves. The flag is here for the shape that is one edit away from
real — `uri: lb://${service.customers}` with that key differing between `dev` and `prod` —
where a matcher ignoring the column would publish one link and could be silently wrong.

**And the refusal lives underneath the flag rather than instead of it** (the user's ruling,
both halves): where the SELECTED environment leaves a key unresolved, that route gets no
endpoint link and a recorded reason — never a fall back to another environment's value. A
stated environment, and no silent substitution.

**A participant answers to its artifactId AND to the name it registers** (built 2026-10-19,
Task 2, after the first matcher scored ZERO on `petclinic`). A build coordinate is not a
service name: the artifactId is `spring-petclinic-customers-service` and every client in that
system states `customers-service`. `D01`'s `participants.aliases` and `M05`'s "alias index"
both specify this and **this spec omitted the column**, which is how the gap reached a running
matcher. Counting the distinct names clients state:

| | names stated | matched by the registered name | matched by the artifactId |
|---|---|---|---|
| `spring-petclinic-microservices` | 4 | **4** | 0 |
| `mall-swarm` | 5 | 0 | **5** |

Neither source alone covers both systems. The key holding the registered name is framework
knowledge, so a CATALOG declares it (`participant_name_key`, on the family's base catalog
where `config_model` and `terminals` live for the same reason) and the matcher only ever asks
"what is this participant's registered name?". Approved by the user as decision 8.

**And it makes `--environment` load-bearing rather than undemonstrated**: the registered name
is read per environment, so step 0 now decides something on this corpus after all.

### Step 1 — protocol

Equality. `http` to `http`, `soap` to `soap`.

### Step 2 — wire identity, three keys

| key | what it compares | measured yield |
|---|---|---|
| the discovery name the client states | `peer`, and a gateway's `lb://name`, against every name a participant ANSWERS TO | the 4 + 5 participant links, and every petclinic link |
| verb and path template | `(protocol, method, path)` | the 6 + 7 endpoint links |
| path alone, unread authority dropped | `path` with a leading `<host>` removed | Apollo's 5 (decision 6) |

Path templates match by string equality in this slice, not by shape. `M06` specifies shape
matching — *"`/v1/orders/42` matches `/v1/orders/{id}`"* — and every one of the 13 endpoint
links measured above matches on the string, because both sides derive the template rather
than a concrete address. **Shape matching is therefore not in this slice** and is decision 3.

### Step 3 — structural compatibility

**Not in this slice.** Decision 2. On this corpus it would change nothing: all 13 endpoint
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

No read is per candidate and none is per module-pair.

**MEASURED 2026-10-19, Task 1, before the matcher was written** — DuckDB `ATTACH` per module
workspace, one `UNION ALL` view over their `endpoints` tables, one scan:

| reactor | modules | workspace on disk | attach | create view | one scan |
|---|---|---|---|---|---|
| `ruoyi-vue-pro` | 18 | 432 MB | 45 ms | 0.5 ms | **2.0 ms** (484 rows) |
| `mall-swarm` | 6 | 160 MB | 14 ms | 0.2 ms | 1.6 ms (298 rows) |
| `petclinic` | 8 | 80 MB | 17 ms | 0.2 ms | 1.5 ms (59 rows) |

`ATTACH` is lazy — it reads a header, not a database — which is why 432 MB across 18 files
costs 45 ms and not seconds. The whole federated read on the scale case is **under 50 ms**,
so nothing here needs lazy materialisation, caching or a narrowed view. This replaces the
estimate this section originally carried, which guessed rather than counted.

---

## 7. Decisions needing approval, and the amendments each implies

| # | decision | amendment if approved |
|---|---|---|
| 1 | **APPROVED.** The participant set may be a reactor, discovered from `<modules>`, not only `M05`'s manifest — and read from the module **workspaces** of that one build, not from bundles | `M05` Inputs, `M06` Inputs, `M00`'s `system analyze`, and `D01`'s system-scope rule (§2 states what the workspace reading gives up and why it does not generalise past one build) |
| 2 | **Step 3 (structural compatibility) is not in this slice** | `M06` Behaviour — a note that steps 1–2 and 4 ship first |
| 3 | **Path templates match by STRING, not by shape, in this slice** | `M06` step 2 — the shape rule stays specified, unbuilt |
| 4 | **No `proposals.yml`**; a `narrowed` link is recorded in `links` with its candidates and nowhere else | `M06` "Ambiguity goes to a person" — blocked on `D03`/`M01` |
| 5 | **No external participants**; a call matching nothing is unmatched, not a link to a declared external host | `M06` External participants — blocked on `system.yml` |
| 6 | **An unread authority may still match by path alone.** `<host>/services/admin` links to the one module serving `/services/admin`. It is `name_match` and `M06` permits path-only matching, but it is the one key built on an address half nobody read — and it is worth 5 of Apollo's 10 rows, 0 elsewhere | `M06` step 2 — a fourth row in the key table |

**Decision 6 was REFUSED by the user, 2026-10-19.** A call whose authority went unread is not
linked by path alone: the real target may be a service outside the reactor, and uniqueness
inside the reactor cannot see that. For Apollo the link would have been correct — the portal
does ask the meta service for config-service addresses — which is evidence for the rule and
not proof of it, and `M06` calls a wrong link fabrication rather than imprecision.

**So the third key in §3's table is NOT built**, and Apollo's five rows stay unmatched with
their reason. The yield this design is measured against is therefore **22 links, not 27**:
13 endpoint links and 9 participant links across `petclinic` and `mall-swarm`, and 0 on
`apollo`. The §1 table's Apollo row records what refusing costs, which is the point of
keeping it.

**Decisions 2–5 were approved as scope statements**, each blocked on a component that does
not exist; the user's chosen scope named steps 1–2 and 4 explicitly.

**Decision 7 (added during review, approved 2026-10-19): `--environment NAME`, default
`default`**, with no fall back to another environment's value where the selected one leaves a
key unresolved. §3 step 0 carries the measurement and the reasoning.
