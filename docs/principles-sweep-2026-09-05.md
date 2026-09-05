# The principles sweep — 2026-09-05

## 1. What this is

Six read-only audits, run against the whole tree on 2026-09-05 on branch
`feat/phase-2o-spring-surface` (`src`/`tests` at `fc0e570`; the intervening commits touch
`docs/` and `GUIDELINES.md` only). They are the six sweeps
`docs/superpowers/plans/2026-08-28-phase-2-roadmap.md:82-168` names: near-miss coverage
(§10), fabrication and negative claims (§8), mechanism existence and behaviour (§5.3),
framework fidelity (§8.1), stale rationale (§9), and invented language rules (§8.1's
language rule). Their six scratchpad reports do not survive the session; this file is their
durable form. Nothing here is new analysis of the code — it is consolidation, de-duplication
and triage of what those six reports found, plus the corrections listed in §7 and the four
facts in §8 that the session controller verified directly.

The sweeps were **pulled forward** from their scheduled slot between 2O and 2P
(roadmap `:84`). The reason is `single_call`'s arity defect: `_matching_method` selected a
catalog row by method name and **argument count**, a rule the Java Language Specification
does not have, and published a message payload as an AMQP destination, a JMS destination and
a SOAP service address. It was found **by luck**, during an unrelated review of Task 7, five
days after it shipped and after four earlier reviews had passed the file. Nothing was looking
for it, because §8.1's language rule did not exist when the code was written and a new rule
reaches backwards through nothing (§8.3).

**The verdict.** The sweep cost six parallel read-only audits, a paused 2O (resuming at Task
8 after the fix pass), and a documentation-debt checkpoint now scheduled between 2O and 2P.
It bought a number in place of a guess. **48 Class A findings — 9 Critical, 16 Major, 23
Minor — are shipped behaviour that fabricates a row or silently drops a real one**, and one
of them (`A-C4`) is the same invented-language-rule shape as the arity defect, living in a
second engine, undetected for the same reason. **34 Class B rows — 7 Critical, 18 Major, 9
Minor — are component documents describing a system that was never built**, of which 33 are
findings and one (`B-M10`) is scheduled work this document declines to count (§7.1); the
roadmap's own measurement is that D01 documents twelve-plus base tables against six that
exist, M00 documents 25 CLI verbs against four, and D00 documents fifteen fact kinds of which
eight have a producer.

Of the 25 Class A Criticals and Majors, **five were reproduced end to end from real
bytecode**, three more were driven through the shipped derivation with hand-built facts, two
were proven by calling the shipped function on real extracted facts, eight rest on a
measurement of the framework's own behaviour with our divergence read rather than run, and
seven are traced through source only. Every row says which (§3's `proof` column). The arity
defect was not unique, it was not the worst, and it was not the last: five Class A Criticals
assert something no evidence supports — a verb, an address, a wire type, or a boundary's
existence — and §4 shows four of them share one cause.

---

## 2. The Class A / Class B split

This split is the document's spine. Every later section respects it.

**Class A — wrong output.** Shipped behaviour that fabricates a row or silently drops a real
one — Sextant's cardinal sin and its second. Drawn from sweeps 1, 2, 4, 5 and 6, plus three
findings lifted out of sweep 3 (below). **These are fixed in the sweep fix pass**, before 2O
resumes at Task 8.

Class A is the fix pass's lane, and the lane is defined by *where the fix lands* — in shipped
source, catalogs, SQL or the extractor — not by severity. Not every Class A row produces a
wrong row today: sweep 5's seven findings are stale comments with **no live derivation
consequence**, and sweep 5 says so itself. They are Class A because the correction is to
source, not to a document describing an unbuilt mechanism. They are recorded at the severity
their auditor gave them (Minor) and are not inflated.

**Class B — documents describing an unbuilt system.** Drawn from sweep 3. Per GUIDELINES §2
these are **tech debt to be addressed, not dropped**: *"one feature fully done beats ten
half-baked"*, and its corollary, *"a document describing an unbuilt mechanism is itself a
half-baked feature. Either finish it or retire the claim — but 'retire the claim' is a
decision to be taken deliberately and recorded, never a quiet deletion."* They are settled at
the **documentation-debt checkpoint immediately after 2O, before 2P**
(roadmap `:208-248`). **Retire-and-mark is the expected outcome for most of them**, taken
deliberately and recorded in `docs/documented-not-implemented.md`.

### The three sweep-3 findings that are Class A, not Class B

Three of sweep 3's findings are operational rather than documentary and do not wait for the
checkpoint (roadmap `:227-242`):

| Class A id | Sweep 3 id | Why it is operational |
|---|---|---|
| `A-C8` | CRIT-3 | `ARCHITECTURE.md:341` claims redaction happens during extraction. It does not — the workspace holds verbatim values. The consequence is outside correctness: a reader would believe a workspace is safe to hand over. |
| `A-C9` | CRIT-2 | Neither documented config file is ever opened, and writing their keys into the file that *is* read aborts every command. A user following D04 §2 is not degraded — they are stopped. |
| `A-M16` | MAJ-12 | `.sextantignore` loads at the module root rather than the repository root, so a reactor's ignore file reaches no submodule. |

Two further sweep-3 rows moved lanes for the same reason — they are comments in `src/`, not
documents: **MIN-7** duplicates sweep 5's F1 and is merged into `A-Mi10`; **MIN-8** is a stale
"not yet shipped" comment in shipped rendering code and becomes `A-Mi23`. One sweep-6 row
moved the other way: finding 14 (`ConstructKind.RECORD` declared with no producer) is a
register entry by that sweep's own instruction and becomes `B-Mi9`.

---

## 3. Class A — the findings

Ranked by severity, then by blast radius. Blast radius here means, in order: how many
catalogs or modules the defect reaches; whether the wrong value is published at
`resolved`/`compiler` (the top tier the system can assert, where nothing downstream can tell
it from an observation); and whether the failure is a fabricated row or a silent drop — a
fabrication outranks a drop of the same reach, because a drop leaves no wrong row to notice
and a fabrication is read as fact.

**Proof vocabulary**, used in every table and subsection. It is the auditor's own claim about
what they executed, not a re-verification by this document.

| tier | means |
|---|---|
| **E2E** | Real Java compiled with `javac --release 21`, run through the shipped extractor jar, then through the full `resolve()` against the shipped catalogs. |
| **derivation** | Shipped catalog plus hand-built facts driven through the shipped derivation path. Real catalog, synthetic facts. |
| **unit** | Real extracted facts, with the shipped Python function called directly. |
| **framework** | The framework's own behaviour measured (`javap`, `javap -v`, or a compiled probe against the real jar); our divergence from it read, not run. |
| **read** | Traced through source and greps; nothing executed. |

### 3.1 The table

| id | sev | sweep | file:line | summary |
|---|---|---|---|---|
| `A-C1` | Critical | 1 + 4 | `catalogs/jakarta-websocket.yml:12-48`, `spring-stomp.yml`, `spring-http-interface.yml`; `storage/duckdb/derive_endpoints.sql:812` | A lone method annotation mints a `resolved`/`compiler` endpoint at the empty address in three catalogs; on `jakarta-websocket` a WebSocket *client* is published as an inbound server endpoint. |
| `A-C2` | Critical | 2 | `catalogs/okhttp.yml:17`, `:26-31` | `Request.Builder.method("DELETE", body)` publishes `http_method: GET` at `resolved`/`compiler`; the catalog comment calls the gap "not silently guessed". |
| `A-C3` | Critical | 2 | `catalogs/spring-mvc.yml:75-79` + 8 siblings; `extractor-jvm/.../WireTypes.java:65` | `ResponseEntity<Void>` publishes an `object` response shape and files `java/lang/Void#` as an unexpanded type, in nine catalogs, polluting the global `shapes` table. |
| `A-C4` | Critical | 6 | `application/resolve/effective_annotations.py:220`, `:473-497` | A class inherits its superclass's annotations only when the superclass is **generic**, so a controller on a plain `extends` base publishes `/{id}` where Spring serves `/api/orders/{id}`. |
| `A-C5` | Critical | 1 + 4 | `application/resolve/engines/config_join.py:215-262`, `:305-332`; `catalogs/spring-cloud-stream.yml:26-70` | Three ordinary `java.util.function`-returning methods on a plain class, on a module with **no Spring Cloud Stream dependency and no config**, assert four Kafka boundaries. |
| `A-C6` | Critical | 1 | `catalogs/retrofit.yml` (no `declared_on`) | A `@retrofit2.http.GET` method on a **concrete class** derives a `resolved`/`compiler` outbound HTTP row; Retrofit only ever proxies interfaces. |
| `A-C7` | Critical | 4 | `catalogs/spring-web.yml:13`, `spring-mvc.yml:13`, `spring-graphql.yml`; `derive_endpoints.sql:204-208` | The Spring handler gate is string equality against one FQN where Spring's rule is a meta-annotation- and hierarchy-aware predicate; a module-local custom stereotype deletes its controller's **entire** HTTP surface. |
| `A-C8` | Critical | 3 | `docs/ARCHITECTURE.md:341` | "Redaction happens during extraction" is false; redaction runs at the render and export exits and the workspace stays verbatim. A confidentiality claim (NFR-8) that is wrong in the first document a reader opens. |
| `A-C9` | Critical | 3 | `docs/components/D04-config-and-exclusion.md:26-70`; `ingress/detect/sextant_config.py:38`, `:42`, `:103-108` | Neither `~/.sextant/config.yml` nor repo-root `sextant.yml` is ever opened, and writing any of their documented keys into the per-module `.sextant.yml` — one character away — raises `SextantConfigError` and aborts every command. |
| `A-M1` | Major | 2 | `engines/interface_implementation.py:186-196`, `:172` | A prefix first-match over `ORDER BY symbol` picks the wrong overload as an inbound subscription's `handler`, at `evidence: compiler`. |
| `A-M2` | Major | 2 | `catalogs/jakarta-servlet.yml:113-127`; `engines/supertype_dispatch.py:55-62`, `:154-155` | A servlet that overrides `service()` to wrap and delegate loses its **whole** surface — address, verbs and handlers — on a bypass rule generalised from a probe configuration that never had `doXxx` methods. |
| `A-M3` | Major | 4 | `catalogs/spring-webclient.yml:12-18`, `spring-restclient.yml:12-18` | Five of eight request-starting methods are declared; `head()`, `options()` and `method(HttpMethod)` chains derive nothing, unstated. |
| `A-M4` | Major | 4 | `catalogs/spring-webclient.yml` (`terminal`) | `exchangeToMono`/`exchangeToFlux` — the only exchange terminals from Spring 7 and the recommended ones since 5.3 — are absent, and `exchange` is declared and does not exist at Spring 7. No version is recorded anywhere in the file. |
| `A-M5` | Major | 4 | `catalogs/retrofit.yml:22-28` | Six of Retrofit's eight request-method annotations; `@OPTIONS` and `@HTTP` derive nothing, unstated. |
| `A-M6` | Major | 4 | `catalogs/kafka-clients.yml:12-17`, `kafka-consumer.yml:12-28`, `spring-kafka-template.yml:12-30` | The callback and rebalance-listener overloads — the idiomatic async producer call and the idiomatic consumer-group call — derive nothing, and COVERAGE lists them "✅ shipped" without arity qualification. |
| `A-M7` | Major | 4 | `catalogs/jakarta-jms.yml:12-40` | One of `jakarta.jms.Session`'s eleven consumer factories is modelled; every selector, durable and shared subscription derives nothing. |
| `A-M8` | Major | 4 | `catalogs/spring-sqs.yml:19-21` | `path_from: [value]` reads one half of an `@AliasFor` pair; `@SqsListener(queueNames = …)`, the spelling AWS's own documentation uses, reads as absent. |
| `A-M9` | Major | 4 | `catalogs/spring-webflux-router.yml:20-75` | The verb vocabulary is exactly the fixture's verb vocabulary — GET/POST/HEAD in Java, GET/POST in Kotlin, against seven each in the framework. §8.1 rule 1's own failure shape. |
| `A-M10` | Major | 6 | `extractor-jvm/.../TypeRefs.java:29-35`, `:161-165` | `Type#getElementType` returns an array's **innermost** element type, so `String[][]` and `String[]` produce byte-identical facts; a DR-5 contract comparison of the two reads equal. |
| `A-M11` | Major | 6 | `application/resolve/effective_annotations.py:500-518` | An ancestor's module-prefixed symbol is recoverable only if the ancestor declares a method, so an abstract base whose only purpose is to carry a type-level `@RequestMapping` inherits nothing. |
| `A-M12` | Major | 6 | `application/resolve/shapes/parse_binding.py:573-586`, `:262-285` | `A-C4`'s invented rule in a second engine: the ancestry walk reads `supertypes` + `implementations` and never `superclasses`, so a payload whose only route to a protobuf marker is a plain `extends` binds nothing. |
| `A-M13` | Major | 6 | `engines/derived_resource.py:656-682`, `:474-528` | A repository's query methods are taken to be the ones it *declares*; a repository extending a user-declared base interface loses every inherited query route. |
| `A-M14` | Major | 6 | `engines/derived_resource.py:517-518`; `catalogs/spring-data-rest.yml:105-135` | CRUD exclusion matches on the bare method **name**, so a derived query method named `findAll(String)` is dropped. |
| `A-M15` | Major | 6 | `storage/duckdb/derive_endpoints.sql:357-387`, `:380`; `catalogs/jakarta-jws.yml:109` | `members: public_methods` joins on `enclosing`, so a `@WebService` class's **inherited** public operations are absent from the SOAP surface. |
| `A-M16` | Major | 3 | `application/stages/analyze.py:284`; `api.py:593-596` | `.sextantignore` is loaded at `module.root`; for a reactor that is not the repository root, so the file reaches no submodule. |
| `A-Mi1` | Minor | 2 | `resolve/shapes/arguments.py:688-691` | "The scanner never unpacks an array argument" is false since capability 9.15. No live consequence. |
| `A-Mi2` | Minor | 2 | `catalogs/spring-web.yml:209-210` | The protobuf-lite premise ("reaches none of these") contradicts item 4 of the list it sits under. **Premise unverified**; conclusion safe either way. |
| `A-Mi3` | Minor | 2 | `engines/derived_resource.py:398-404` | "Ordinary names always pass" is `str.isidentifier()`; a legal Java type name containing `$` fails it. Latent, under-report direction. |
| `A-Mi4` | Minor | 4 | `docs/components/D02-catalog-schema.md:15-45` | D02 has no field for the version a rule was measured against, which is why 32 of 52 catalogs are silent about it. Structural. |
| `A-Mi5` | Minor | 4 | `scripts/probes/cp10_catalog_descriptors.md`; `tests/architecture/test_catalog_descriptors.py` | CP-10 proves every declared descriptor exists and never asks the converse. Its `0 NOT DECLARED` row reads as completeness. |
| `A-Mi6` | Minor | 4 | `catalogs/spring-actuator.yml` | The four sibling registration annotations derive nothing. **Correctly stated** (COVERAGE:799); noted only for its shape. `@WebEndpoint`'s meta-annotation status **unverified**. |
| `A-Mi7` | Minor | 4 | `catalogs/jakarta-jws.yml:85` | "Verified against BOTH reference implementations" names neither, with no version and no committed probe. Unauditable. |
| `A-Mi8` | Minor | 4 | `catalogs/spring-sqs.yml` | The modern `@SqsListener` catalog names no version where its legacy sibling names two. |
| `A-Mi9` | Minor | 4 | `catalogs/microprofile-graphql.yml` (`path_fallback: construct_name`) | **Prediction, not measured**: MP GraphQL likely strips a `get`/`is` prefix, so `@Query List<Order> getOrders()` would be served as `orders` while we publish `getOrders` — a *wrong* address. The highest-value item in the probe backlog. |
| `A-Mi10` | Minor | 5 (+3 MIN-7) | `application/ports/catalogs.py:46-49` | "Only Task 9's wrapper unwrapping reads `wrappers`, the rest wait on Tasks 10 and 11" — all four blocks are read today. |
| `A-Mi11` | Minor | 5 | `derive_endpoints.sql:688-691`; `catalogs/spring-actuator.yml:34-37` | "Only two readers of `resolved_config`" — five call sites in three files. Wrong when written; the operative claim survives. |
| `A-Mi12` | Minor | 5 | `application/resolve/open_questions.py:23-25` | "Both the renderer and the export switch on it" — only the renderer does. Overstates the cost of adding a kind. |
| `A-Mi13` | Minor | 5 | `engines/single_call.py:469-476` | "The shipped 2C catalogs (none of which declare `arity`)" — all 57 shipped `methods:` rows now declare both `arity` and `descriptor`. |
| `A-Mi14` | Minor | 5 | `catalogs/google-pubsub-client.yml:31-33` | "Matches by name+arity alone" in a row that now carries a `descriptor`. |
| `A-Mi15` | Minor | 5 | `ingress/catalogs/yaml_source.py:94-97` | "All 41 shipped catalogs" — 52 ship. GUIDELINES §5.3 repeats the 41. |
| `A-Mi16` | Minor | 5 | `application/stages/analyze.py:155-159` | "Nothing passed it" — the same commit (`ca66b73`) added the CLI flag that passes it. Wrong when written. |
| `A-Mi17` | Minor | 6 | `extractor-jvm/.../ClassScanner.java:642` | A `protected` nested type is recorded `public`, because the `InnerClasses` attribute is never read. Its one consumer would export a `protected` nested repository the framework does not: a fabricated route set, on a rare shape. |
| `A-Mi18` | Minor | 6 | `shapes/parse_binding.py:557-570`, `:596-601` | `callee_of` matches a call by owner, name and **argument count** — the arity defect's own rule, one module from the catalog rows that were fixed for it. Returns `None` on a collision, so it under-reports rather than choosing wrongly. |
| `A-Mi19` | Minor | 6 | `engines/fluent.py:582-611`; `combinator.py:407-475`; +6 grammars | 93 catalog call-matching entries key on owner+name; `test_catalog_descriptor_coverage.py` scans `methods:` lists only, so the descriptor ratchet reaches one of the six grammars that exist. |
| `A-Mi20` | Minor | 6 | `domain/symbols.py:44-58` | `outer_type_of` splits on the first `$`; JLS 3.8 permits `$` in an identifier and JVMS 4.7.6 makes `InnerClasses` the authority. **Latent** — every shipped consumer is fenced to protoc-generated names. |
| `A-Mi21` | Minor | 6 | `domain/symbols.py:88-108` | `type_descriptor` treats every `.` as a package separator, so `com.foo.Outer.Inner` yields a symbol the extractor never emits. **Latent** — every shipped catalog already writes `$`, and no architecture test refuses the dotted spelling. |
| `A-Mi22` | Minor | 6 | `extractor-jvm/.../WireTypes.java:22`, `:56-57` | `char` projects to `wire_type: integer`. Right as JLS 4.2.1, wrong as a wire projection for every JSON serializer in the estate. **Noted, not asserted** — a serialization question. |
| `A-Mi23` | Minor | 3 (MIN-8) | `egress/render/document.py:699-700` | "Not yet shipped" for `environment_divergence`, which ships (`engines/derived_resource.py:224`, wired at `resolve/pipeline.py:86`). |

**Sweep 1's coverage findings are not in this table.** MAJOR-1 through MAJOR-6, MODERATE-1
through MODERATE-3 and MINOR-1 are defects in the *test suite* — guards with no test, markers
on tests that do not discriminate, near-misses that pass vacuously. They produce no wrong
row, so they are not Class A; they are carried with their mutation evidence in §6.3. They are
not re-scored.

### 3.2 Critical findings

---

#### `A-C4` — a class inherits from its superclass only when the superclass is generic

**Sweep 6, finding 1. Merges nothing. Proof: unit** (real extracted facts, `inherited_rows`
called directly). The SQL composition that turns it into a wrong address is **read**-verified;
sweep 6 states it did not run the DuckDB pipeline to observe the literal column.

**Sites.** `application/resolve/effective_annotations.py:220` and `:473-497` (`_supertype_of`),
fed by `engines/annotation_driven.py:716-723` (`_supertype_rows`, reading
`workspace.query("supertypes")`).

**The invented rule.** A class has a superclass edge only where a `supertype` fact exists, and
that fact is emitted only when the superclass carries type **arguments**
(`TypeRefs.genericSuperclassFromSignature`, D00 §5a's parameterised-type-reference carrier).
`class Child extends Base` therefore produces no inheritance edge at all.

**The JLS rule it should have been.** JLS 8.1.4 / 8.2: a class has exactly one direct
superclass and inherits its members, generic or not. The class file always states it (JVMS 4.1
`super_class`), and capability 9.13 already emits it as the `superclass` field —
`workspace.query("superclasses")` exists at `storage/duckdb/workspace.py:137-142` and is
already module-prefixed on both sides. This is §8.1's tell exactly: the walk reached for the
field that happened to be in the row rather than for the sentence in the specification.

**Triggering input.** Two controllers differing only in whether the base is generic:

```java
@RequestMapping("/api/orders")  public abstract class PrefixBase         { public void helper() {} }
@RequestMapping("/api/items")   public abstract class GenericPrefixBase<T>{ public void helper() {} }
public class OrderController extends PrefixBase              { @GetMapping("/{id}") public String get(){…} }
public class ItemController  extends GenericPrefixBase<String>{ @GetMapping("/{id}") public String get(){…} }
```

Extracted facts: `app/OrderController#` carries `superclass = …app/PrefixBase#` and **no**
`supertype`; `app/ItemController#` carries both. `inherited_rows(...)`, called with those facts
and spring-mvc's own `mapping_fqns`/`prefix_annotation`, returns the `ItemController` prefix
row and nothing for `OrderController`.

**The wrong output.** `derive_endpoints.sql:723` is
`LEFT JOIN prefixes p ON p.type_symbol = s.enclosing`, so an absent prefix composes as `''`.
`OrderController#get` publishes **`path: /{id}`**, `resolution: resolved`,
`evidence: compiler`, where Spring serves `/api/orders/{id}`. That is a confidently wrong
address — the class `$path_fallback` and `$canonical_path` exist to close — reached by a route
neither of them guards. The second half of the same probe is the other direction: a
non-generic abstract `BaseController` carrying `@GetMapping("/ping")` on a method
`PlainChild` overrides synthesizes nothing, so the whole `GET /base/ping` row is dropped,
while the identical generic pair synthesizes both.

**Fix.** Pass `workspace.query("superclasses")` into `inherited_rows` as the class-inheritance
edge and keep `supertypes` for what it is. Both sides are already module-prefixed, so
`_supertype_of`'s `_prefixed_types` lookback is not needed for the new edge — which also
closes `A-M11`. §10's paired test is the generic and non-generic bases side by side.

---

#### `A-C7` — the Spring handler gate is a literal annotation name where Spring's rule is a predicate

**Sweep 4, F-2. Proof: framework** — the framework side is measured across seven jars and one
compiled probe; our divergence is read from the SQL and the pre-pass, not run.

**Severity note, recorded rather than re-scored.** Sweep 4 graded this Critical "because it
silently deletes a module's entire HTTP surface rather than merely narrowing one row, and
because §8.1 rule 3 requires a COVERAGE row for it and there is none", and added its own
hedge: *"If the grading is strictly 'fabricates a row', it is Major."* The grade here is the
auditor's. This document did not re-score it.

**Sites.** `catalogs/spring-web.yml:13`, `spring-mvc.yml:13`, `spring-graphql.yml`
(`type_annotation: org.springframework.stereotype.Controller`), consumed at
`derive_endpoints.sql:204-208` as `WHERE annotation = $type_annotation`.

**What the framework does (measured).** `javap -p -c` on spring-webmvc 6.1.6, 6.2.15, 7.0.2,
7.0.8, 7.0.9 and spring-webflux 6.1.6, 7.0.2 — all seven jars — give the identical
four-instruction `isHandler` body: `aload_1`, `ldc Controller`,
`invokestatic AnnotatedElementUtils.hasAnnotation`, `ireturn`. `spring-graphql` 1.2.6 does the
same at `AnnotatedControllerConfigurer.findHandlerMethods`. A compiled probe against
spring-core/spring-web/spring-context 6.1.6 reports `isHandler = true` for `@RestController`,
`@Controller`, a custom `@MyApi` meta-annotated `@RestController`, a custom `@MyStereotype`
meta-annotated `@Controller`, a **subclass** of an `@Controller` base and a class
**implementing** an `@Controller` interface; `false` for a `@RequestMapping`-only class and
for a plain class.

**What we encode.** String equality against one FQN over the type's own direct annotations.
`annotations_effective` (`derive_endpoints.sql:194-201`) unions in the composition pre-pass,
but `effective_annotations.py:41-47` widens only `mapping_fqns` — the **method**-level
annotations, as its own docstring says. The type gate is never widened, and Task 7's
inheritance walk carries mappings onto an implementer, never the stereotype.

**The wrong output, three divergences.** (1) A module-local custom stereotype: Spring serves
every mapping on the controller; we derive nothing, and **every endpoint of that controller
disappears from the export**. `docs/COVERAGE.md:802` claims meta-annotations "✅ shipped" with
no qualification, so a reader cannot tell only the method half is shipped. (2) A stereotype
inherited from a base class or an interface: measured `true`, we derive nothing. (3) The stale
half — see §8, third bullet: GUIDELINES §8.1 rule 1's own worked example is itself wrong.

**Fix.** Make the type gate a hierarchy-and-composition search: widen the composition pre-pass
to `type_annotation`, and walk `supertypes`/`implementations` for it — both edges exist and
Task 7 already uses them, and `A-C4`'s `superclasses` edge is the third. Until then, three
COVERAGE rows, one per divergence. Correct the §8.1 worked example, and pin `isHandler`'s body
with a committed probe.

**Not settled.** Whether Spring's component scan admits a subclass of an `@Controller` base as
a *bean* was not measured; it bounds how universal the superclass case is and does not touch
the composed-stereotype or interface cases.

---

#### `A-C1` — three catalogs mint an empty-address endpoint from one method annotation

**Merges sweep 1 CRITICAL-1 and sweep 4 F-1, credited to both.** Sweep 4 found the defect on
`jakarta-websocket` and named the direction inversion; sweep 1 found the same structural shape
on two further shipped catalogs and measured all three. **Proof: derivation** for the three
empty-address rows (shipped catalogs, hand-built facts, script re-run independently at
`v2.py`); **read** for sweep 4's `@ClientEndpoint` variant, which sweep 4 explicitly declines
to call run-verified.

**Sites.** `catalogs/jakarta-websocket.yml:12-24` and `:44-48`, `spring-stomp.yml`,
`spring-http-interface.yml`; the generic defence at `derive_endpoints.sql:812`.

**The mechanism.** All three are `annotation_driven` catalogs with **no type-level gate**, so
`derive_endpoints.sql:725` (`WHERE ($type_annotation IS NULL OR c.type_symbol IS NOT NULL)`) is
a no-op and a single method annotation mints a declaration. The prefix seam
(`:617-620`) leaves an absent prefix as `''`. The one generic defence against the resulting
empty address is `:812`, `WHERE NOT ($path_separator IS NULL AND d.path = '')` — which fires
**only when the catalog declares no `path_separator`**. All three declare `path_separator: "/"`,
which disables it. `jakarta-websocket.yml:12-17` cites the `spring-kafka`/`@KafkaHandler`
precedent as its reason for having no type gate, and then at `:44-48` declares the separator
that voids the only thing protecting that precedent, calling it "inert in practice". It is not
inert; it is the difference between declining and fabricating.

**Triggering input and wrong output.** Measured against the shipped catalogs:

| catalog | input | derived today | paired positive |
|---|---|---|---|
| `jakarta-websocket` | method `@jakarta.websocket.OnMessage` (no args), enclosing class carries no `@ServerEndpoint` | `(websocket, inbound, method=NULL, path='', resolved, compiler)` | class `@ServerEndpoint("/live")` → `path='/live'` |
| `spring-stomp` | method `@…messaging.handler.annotation.MessageMapping` (no args), class carries none | `(websocket, inbound, NULL, '', resolved, compiler)` | `@MessageMapping({"/place"})` → `/place` |
| `spring-stomp` | method `@…messaging.simp.annotation.SubscribeMapping` (no args) | `(websocket, inbound, NULL, '', resolved, compiler)` | class `@MessageMapping({"/app"})` + bare method → `/app` |
| `spring-http-interface` | method `@…web.service.annotation.GetExchange` (no args), no class `@HttpExchange` | `(http, **outbound**, GET, '', resolved, compiler)` | class `@HttpExchange("/base")` → `/base` |

The `spring-http-interface` row is the worst of the three because it is **outbound**: it claims
the module calls a service at the empty address.

**The direction inversion (sweep 4, read-verified).** `jakarta.websocket.OnMessage` is
`@Target(METHOD)`, declares exactly one attribute (`maxMessageSize()`), carries no address, and
ships in the **client** API jar — measured by `javap -v` on
`jakarta.websocket-client-api-2.2.0.jar` and `jakarta.websocket-api-2.2.0.jar`. It is the
message callback for both `@ServerEndpoint` and `@ClientEndpoint` classes, and a class is a
served endpoint only by virtue of `@ServerEndpoint`. So a `@ClientEndpoint` class with an
`@OnMessage` handler — a class that *dials out* — is published as an **inbound** WebSocket
endpoint at the empty address. Direction inverted and address invented in one row.
`docs/COVERAGE.md:1211-1216` identifies precisely this failure mode as the reason the `javax`
spelling is left detection-only; the same hazard is live on the `jakarta` path and is nowhere
stated.

**Second half of the same divergence, silent.** A `@ServerEndpoint` class whose only lifecycle
method is `@OnOpen`/`@OnClose` is a real served endpoint and derives nothing. No COVERAGE row
names it.

**Fix.** Add `type_annotation: jakarta.websocket.server.ServerEndpoint` so the class gate is the
framework's own predicate rather than the prefix's side effect, and the equivalent type gate or
`declared_on` for the other two. Add `declines` tests for a `@ClientEndpoint` + `@OnMessage`
class and for each row above. State the `@OnOpen`-only under-report in COVERAGE. Then probe
`jakarta-websocket`: it rests today on a fact-stream note from a fixture, not on any measurement
of what a container serves. Note also that `A-C1` is closed by §4's mechanism without any of
these catalog edits — the catalog edits are what restores the *correct* rows.

**Related, and not merged.** `spring-stomp` carries a second hazard sweep 1 raises and does not
verify: `org.springframework.messaging.handler.annotation.MessageMapping` is
`spring-messaging`'s annotation, and is **the** routing annotation for Spring RSocket
controllers. An RSocket handler in a scanned module would be published by this catalog as a
`websocket` endpoint — a wrong-protocol fabrication rather than an empty-address one. The FQN
identity is certain; the derived output for a real RSocket controller is **unverified**.

---

#### `A-C3` — `ResponseEntity<Void>` publishes an unexpandable `object` shape in nine catalogs

**Sweep 2, C-2. Proof: E2E** — a Spring MVC controller compiled `--release 21`, run through the
shipped extractor jar and the full `resolve()` against the shipped `spring-mvc` catalog.

**Sites.** `catalogs/spring-mvc.yml:75-79` and eight siblings — `spring-web.yml`,
`spring-webflux-router.yml`, `spring-http-interface.yml`, `spring-cloud-openfeign.yml`,
`retrofit.yml`, `netflix-dgs.yml`, `spring-graphql.yml`, `microprofile-graphql.yml` — the nine
catalogs whose frameworks make `ResponseEntity<Void>` / `Mono<Void>` / `Call<Void>` the
idiomatic "no body" return. The contradicted claim is replicated verbatim in 28 other catalogs,
e.g. `spring-restclient.yml:79-87`: *"`Void` reaches no wire type at all: the empty `wire` a
`void` return already carries reads as 'no payload', never as a shape nobody can expand."*

**Why it is false.** `WireTypes.java:20` maps only `Type.VOID` (the primitive `V`) to `""`.
`java/lang/Void` is `Type.OBJECT` and falls through `objectLike`'s `default -> "object"` at
line 65. Measured on the shipped jar: field `Void boxed` → `"object"`, method `Void giveBoxed()`
→ `"object"`, method `void giveNothing()` → `""`. So `java.lang.Void: wire: ""` in `known_types`
is a **repair** of the projection, not a mirror of it, and nine catalogs never apply it.
`contracts.py:276-286` is where the repair would fire.

**Triggering input.**

```java
@Controller public class VoidController {
  @GetMapping("/orders/ping") public ResponseEntity<Void>      ping() { return null; }
  @GetMapping("/orders/view") public ResponseEntity<OrderView>  view() { return null; }
}
```

**Wrong output.**

```
GET /orders/ping  response_shape = {"nullable":true,"shape_id":"java/lang/Void#",
                                    "wire_format":"","wire_type":"object"}
shapes: {'shape_id': 'java/lang/Void#', 'content_hash': 'md5:d751713…', 'open': True}
unexpanded_types: ('java/lang/Void#',)
```

An endpoint returning no body is published as returning an **object**, and `java/lang/Void#` is
filed as an unexpanded type — a gap report pointing at a type with nothing to expand. Because
the `shapes` table is global and insert-if-absent, the bad row survives for every other catalog
that later reaches the type.

**Fix.** Both repairs are warranted. (1) Add `- { type: java.lang.Void, wire: "" }` to the nine
catalogs. (2) Better, at the source: map `java/lang/Void` to `""` in `WireTypes.objectLike`
beside the box mappings — the comment at `WireTypes.java:12-19` already argues exactly this for
the primitive. Then the catalog entries become the mirror the 28 comments claim they are, and
the invariant becomes testable as an architecture test over `WireTypes` versus every
`known_types` block. Sweep 2 notes a related inconsistency worth the same test:
`okhttp.yml:58-67` states as an invariant that every outbound catalog's
`wrappers`/`serialization`/`known_types` must agree, and they do not — `retrofit.yml` declares
2 known types, `okhttp.yml` 12.

**Not settled.** How an `open: True` shape presents in the rendered document was not traced, so
"how bad it looks to a reader" is unquantified.

---

#### `A-C2` — OkHttp `.method(verb, body)` publishes a fabricated `GET`

**Sweep 2, C-1. Proof: E2E** — real okhttp 4.12.0 from `~/.m2`, compiled `--release 21`, shipped
extractor, full `resolve()`.

**Sites.** `catalogs/okhttp.yml:17` (the root) and `:26-31` (the claim). Corroborating false
prose at `docs/COVERAGE.md:917` and `:1441`.

**The claim, and the same file's own statement of the mechanism that breaks it.** `:26-31` says
`Request.Builder.method(String, RequestBody)` "is not covered … **a known gap, not silently
guessed**". Four lines above, `:20-26` says a chain matching neither `get` nor `post` "would
fall through as an unmatched step … and the root's own `http_method: GET` default would stand
uncorrected — **a confidently WRONG verb, not an honest gap**." The second sentence describes
what the first denies.

**Why it is false.** The root `{ owner: okhttp3.Request$Builder, method: <init>, captures: {
http_method: GET } }` seeds `GET` unconditionally. `.method(...)` is not in `steps`, so it is an
unmatched step and passes through uncaptured. Nothing clears or poisons the seeded verb.

**Triggering input.**

```java
Request request = new Request.Builder()
    .url("https://orders.internal/api/orders/1").method("DELETE", body).build();
client.newCall(request).execute();
```

**Wrong output.**

```
{'protocol': 'http', 'direction': 'outbound', 'method': 'GET',
 'path': '/api/orders/1', 'peer': 'orders.internal',
 'resolution': 'resolved', 'evidence': 'compiler', 'catalog_id': 'okhttp'}
```

The module issues `DELETE`. Sextant asserts `GET`, at the top evidence tier, on a verb no
evidence supports. The precedent makes it worse:
`tests/application/test_call_engines.py:3422` fixed exactly this bug for
`put`/`patch`/`delete`/`head` while the same commit's prose declared the remaining hole safe.

**Fix.** In order of preference: (1) teach the fluent grammar to read a verb off an argument
(`http_method: arg0`), then declare `- { method: method, captures: { http_method: arg0, body:
arg1 } }`. `fluent.py:369` already distinguishes "never declared" from "declared and
unreadable", so an unreadable verb argument naturally yields `method: NULL`. (2) Cheaper:
declare the step with an `http_method` poison so it clears the root's seed — `fluent.py:87`/
`:897` carry a poisoning concept, but it poisons captures rather than the root literal, so this
needs a small engine change. **Do not** fix by deleting the root's `http_method: GET`: a bare
`Request.Builder` really does default to GET, and removing it under-reports every plain
`.url().build()` chain. Correct `COVERAGE.md:917` and `:1441` in the same commit.

---

#### `A-C5` — `spring-cloud-stream` mints Kafka boundaries from ordinary `java.util.function` methods

**Merges sweep 1 CRITICAL-3 and sweep 4 F-10.** Sweep 1 measured the behaviour; sweep 4
independently recorded that this catalog's whole binding rule is unmeasured. **Proof:
derivation** (shipped catalog, hand-built facts, `v4.py`).

**Sites.** `engines/config_join.py:215-262` (`_candidates`), `:305-332` (`_selected_entries`),
`storage/duckdb/workspace.py:249`; `catalogs/spring-cloud-stream.yml:19`, `:26-70`;
`resolve/dependencies.py:46`, `:86`.

**Triggering input.** Three ordinary methods on a plain `com/acme/util/Helpers#` class —
`nameNormalizer` returning `Function<String,String>`, `auditSink` returning `Consumer<String>`,
`clockSupplier` returning `Supplier<Clock>` — with **no `@Bean`, no `@Configuration`, no
`spring.cloud.*` key**, and in a second run **no `resolved_config` rows at all**.

**Wrong output** (identical with and without config):

```
skipped=[]  rows=4
  kafka inbound  path=None unresolved handler=…Helpers#auditSink(…)
  kafka inbound  path=None unresolved handler=…Helpers#nameNormalizer(…)
  kafka outbound path=None unresolved caller=…Helpers#clockSupplier(…)
  kafka outbound path=None unresolved caller=…Helpers#nameNormalizer(…)
```

The rows carry no address — `path` is NULL at `resolution: unresolved` — so this is not a
wrong-address fabrication. It asserts **the existence of four Kafka boundaries the module does
not have**, names a real application method as the handler of two of them, and does so on a
module with no Spring Cloud Stream dependency. §8's cardinal sin is reporting an endpoint the
running system does not serve; a boundary whose address nobody could read is still a boundary
claimed.

**The cause is a missing conjunct, not a missing test.** `_candidates` reads **every declared
method** (`workspace.py:249` is `SELECT symbol, enclosing, signature FROM symbols WHERE
construct_kind = 'method'`) with no `@Bean`, `@Configuration` or annotation filter of any kind.
`_selected_entries` **defaults to binding everything**: `if per_environment is None: return
list(candidates)` — an absent `spring.cloud.function.definition` means "bind all", not "bind
none". `detect.coordinates` does not gate, because `unmet_dependency`
(`resolve/dependencies.py:86`) returns `None` for any style outside
`DEPENDENCY_GATED = frozenset({"derived_resource"})` and membership is a property of the
**style**, so the catalog cannot opt in. `requires: [resolved_config, …]` gates on the config
pass having *run*, not on the table holding a Cloud Stream key — which
`spring-cloud-stream.yml:19` states correctly and which sweep 2 verified (#23). So the only
remaining conjunct is "the method's return type is one of three `java.util.function`
interfaces", which ordinary Java satisfies constantly.

**Fix.** A catalog/engine change: a `@Bean`/`@Configuration` requirement, a `binder_key`-presence
requirement, or admitting `config_join` to `DEPENDENCY_GATED`. The near-miss above is the
regression pin and its assertion must be `rows == []`.

**What sweep 4 adds, and what sweep 1 settles.** F-10 records that this catalog has **no probe,
no `javap` reference, no version and no checkpoint note** — the `-in-0`/`-out-0` suffix
convention, the `;`/`|` separators and the four-entry `binder_protocols` map are all from
documentation or memory, so 100% of its output rests on an unverified prediction. F-10 also
flagged as unverified whether the `when: {implements: …}` gate reaches the framework's canonical
lambda `@Bean` (where no module class implements `Function`), noting COVERAGE:367 describes a
**return-type** predicate instead. **Sweep 1's measurement answers that**: `_candidates` reads
declared methods with no implements filter and matches on the return type, and sweep 1's
`BiFunction` near-miss derives 0 rows while `Function` derives. The operative predicate is the
return type, as COVERAGE:367 says; the catalog key is named `implements`. The rest of F-10's
probe requirement stands and is rank 3 in §6.2's backlog.

---

#### `A-C6` — `retrofit` derives an outbound HTTP endpoint from a concrete class

**Sweep 1, CRITICAL-2. Proof: derivation.**

**Site.** `catalogs/retrofit.yml` — the file declares neither `type_annotation` nor
`declared_on`.

**Triggering input.** A method `com/acme/task7/Subject#onMessage(sig).` carrying
`@retrofit2.http.GET(value="/orders")` on a symbol whose enclosing `construct_kind` is `class`.

**Wrong output.** `(http, outbound, GET, '/orders', resolved, compiler)`.

**Why it is wrong.** Retrofit only ever proxies **interfaces** — `Retrofit.create()` takes a
`Class<T>` that must be an interface and throws otherwise. A `@GET`-annotated method on a
concrete class is not a Retrofit call site; it is most plausibly a hand-written class in a
codebase that also uses Retrofit, or a test double. The published row is a plausible-looking
outbound dependency that does not exist — the worst kind, because nothing downstream can tell
a plausible fabricated address from an observed one.

**Fix.** One catalog key: `declared_on: interface`. §10's pair is the input above beside the
same annotation on a symbol whose enclosing `construct_kind` is `interface`. Note that
`A-M5` is a second, independent defect in the same file and is not merged with this one.

---

#### `A-C9` — neither documented configuration file is opened, and their keys abort every command

**Sweep 3, CRIT-2, lifted to Class A per roadmap `:238-240`. Proof: read** (sweep 3 executed no
code beyond greps and one in-process `--help`).

**Document.** `docs/components/D04-config-and-exclusion.md:26-70` specifies
`~/.sextant/config.yml` (workspace location, output format, tool paths, scanner pinning,
personal redaction) and a repository-root `sextant.yml` (`version`, `first_party.groups`/
`.artifacts`, `modules.<id>.kind`, `catalogs:`, `redaction.*`), with a precedence rule at `:33`
and a merge rule at `:70`. `D02:2657-2659` depends on it: *"A repository adds its own
[catalog] … through `sextant.yml`. Both sets are loaded together and neither is privileged."*

**Consumer: none, for either file.** `grep -rn "sextant\.yml" src/ | grep -v "\.sextant\.yml"`
→ 0. `grep -rEn "\.sextant/(config|cache)|expanduser" src/` → 0. The catalog set is hard-wired:
`api.py:554` `catalogs=YamlCatalogSource(catalogs_dir())` → `resources.py:34-47` → 
`ingress/catalogs/yaml_source.py:33` globs the package's own directory. There is no mechanism
by which a repository catalog could load. `scanners.pin` is unreachable
(`ports/scanner.py:55-69` `select_scanner` takes no pin argument); `tools.helm` → 0 hits.

**Why it is Class A and not documentation debt.** The file that *is* read is the per-module
`.sextant.yml` (`ingress/detect/sextant_config.py:38`), one character from the documented name,
with a closed key set of three (`:42`, `_KEYS = frozenset({"extract_libraries", "redact",
"enrich"})`) enforced at `:103-108`. Writing any documented key — `catalogs`, `first_party`,
`modules`, `redaction`, `version`, `workspace`, `output`, `tools`, `scanners` — raises
`SextantConfigError`, and all four commands share the reader (`api.py:642`/`:643-644`, `:782`,
`:895-896`, `:1231`), so the whole run is refused with a message saying the key is "read
nowhere" and no hint that the documented file is a different, unread one. In a single-module
repository, where module root and repository root coincide, following D04 §2 produces exactly
this abort. A user following the document is not degraded; they are **stopped**.

**Cost.** NFR-9 ("extension without modification") is unmet for catalogs, which D02 §6 presents
as the supported path for an in-house client library. D04 §2's precedence chain collapses to
"flags, then the per-module file, then built-ins".

**Fix.** Either implement the repository file — the `catalogs:` key alone would satisfy NFR-9's
stated case — or retire both files from D04 §2 and D02 §6 and say what the supported path
actually is. Note the roadmap's standing ruling (`:201-205`): **project catalogs are
deliberately not scheduled anywhere**, because they would turn D02's catalog schema into a
public API after which every schema change is breaking. So the expected disposition is retire,
plus a message change so the abort names the real cause. This finding supersedes the register's
"project catalogs" item, which is **not in the register file at all** (`B-M11`).

**Companion, and it compounds this one.** `B-Mi5`: `D02:2658` and `D05:244` spell the
per-module file without its leading dot, as `sextant.yml` — the documented repository file's
name.

---

#### `A-C8` — `ARCHITECTURE.md:341` says redaction happens during extraction

**Sweep 3, CRIT-3, lifted to Class A per roadmap `:230-237`. Proof: read**, and independently
confirmed by the session controller (§8, fourth bullet).

**Document.** `docs/ARCHITECTURE.md:341`: *"**Redaction happens during extraction**, before
anything is written. The cache key includes the redaction pattern set, because a pattern added
later cannot clean facts already written."*

**What the code does.** Redaction runs at the two **exits** only — `api.py:782` (`render`) and
`api.py:1231` (`export`), both via `_redactor_for` at `api.py:447-457`.
`ingress/detect/sextant_config.py:11-13` states it outright: masking happens where data crosses
the trust boundary, and **the workspace stays verbatim**. D04 already carries the amendment at
`docs/components/D04-config-and-exclusion.md:243` (*"What ships runs at the EXITS instead"*);
ARCHITECTURE was never updated, which is a §5.1 miss. The second sentence describes nothing
either: there is no cache (`grep -rEn "\.sextant/cache" src/` → 0).

**Cost.** A confidentiality claim (NFR-8) that is false in the first document a reader or an
agent opens. Anyone reasoning about whether `<module>/.sextant/facts/**` may be copied, shared
or committed gets the wrong answer from ARCHITECTURE and the right one only from D04's
amendment paragraph. This is the one sweep-3 finding whose consequence is outside correctness.

**Fix.** Amend `ARCHITECTURE.md:341` to match `D04:243`, and drop or restate the cache-key
sentence. One sentence each.

### 3.3 Major findings

---

#### `A-M1` — a wrong `handler` is published for an overloaded `interface_implementation` receiver

**Sweep 2, M-1. Proof: E2E.** Sites: `engines/interface_implementation.py:186-196` (the prefix
first-match) and `:172` (the claim, *"only its handler is unread, never fabricated"*).

The claim reasons about the **interface**; the lookup runs against the **implementing class**.
`MessageReceiver` declares one `receiveMessage`; nothing stops the implementing class declaring
an overload beside it — a private helper, a convenience form, or a javac bridge, which
`ClassScanner.visitMethod` deliberately does not skip. `method_symbols` is `ORDER BY symbol`
(`storage/duckdb/workspace.py:218`) and the disambiguator is a SHA-256 prefix of the descriptor,
so the "tiebreak" is a hash-order coin flip between two methods, one of which is wrong.

**Input** (compiled, shipped extractor): `RawPubSubReceiver implements MessageReceiver` with the
real `receiveMessage(Object,Object)` → `sig_4243dc07` and a private
`receiveMessage(String,String)` → `sig_0b978848`; `0b97… < 4243…`.

**Wrong output**: `{'protocol':'pubsub','direction':'inbound','path':'raw-notify','handler':'…
RawPubSubReceiver#receiveMessage(sig_0b978848).','resolution':'resolved','evidence':'compiler'}`
— the private helper published as the subscription's handler at the top evidence tier. The
`path` is right; the attribution is invented. `handler` is part of this engine's dedup key
(`:82`), so the wrong symbol can also split or merge rows that should not be.

**Fix.** Replace the prefix scan with the selector `supertype_dispatch` already uses
(`supertype_dispatch.py:228-236`): read `method_declarations`, key `{(name, parameter-type
tuple): symbol}` per type, resolve `handler_method` against the interface's declared parameter
types. Where the parameter types cannot be determined and more than one candidate matches by
name, return `None` — the unread handler `:172` already promises. Sweep 2 names
`supertype_dispatch._members` as the reference implementation of §8.1's language rule in this
tree, and sweep 6 independently clears it; the fix is to copy it.

**Not settled.** Whether this fires on any real-world Pub/Sub receiver. The mechanism was proven
with a synthetic overload; published `MessageReceiver` implementations were not surveyed. The
bridge-method amplifier does not apply to `MessageReceiver` (non-generic) but would to any
future generic interface routed through this style — which is the reason to fix the selector
rather than the catalog.

---

#### `A-M2` — a servlet that wraps `service()` and delegates loses its whole surface

**Sweep 2, M-2. Proof: E2E.** Sites: `catalogs/jakarta-servlet.yml:113-127` (`bypassed_by`),
`engines/supertype_dispatch.py:55-62` and `:154-155`; same shape in `javax-servlet.yml`; stated
as a boundary at `docs/COVERAGE.md:830`.

**The claim.** *"A bypass discards the CLASS, never merely the member (CP-9 verdict 8). A class
overriding the supertype's own dispatch entry point has replaced the lookup the table
describes: measured, it serves every operation alike."*

**Why it is false — §5.4 exactly.** CP-9 rows 14-15
(`scripts/probes/cp9_servlet_shapes.md:80`) read "`service(HttpServletRequest,
HttpServletResponse)` overridden, **no `doXxx`**". The verdict was then applied to every
`service()` override. The commonest real form — a cross-cutting wrapper calling
`super.service(req, resp)` — does not replace the lookup: `HttpServlet.service` still runs and
still dispatches to the class's own `doGet`/`doPost`. That configuration was never measured.

**Input:** `@WebServlet("/wrapped")` on a class overriding `service()` to call
`super.service(req, resp)` and also declaring `doGet` and `doPost`.

**Wrong output: zero rows.** A control class in the same scan (`@WebServlet("/plain")`, no
`service` override) correctly derives `GET /plain` and `POST /plain`, so the pipeline was
working. The container serves `GET /wrapped` and `POST /wrapped`. §8: an omission leaves no
wrong row to notice.

**Fix, in order.** (1) Re-measure: run CP-9 with a delegating `service()` override that also
declares `doGet`/`doPost`, and record the configuration in the verdict (§5.4's "generate the
evidence table from the run"). (2) Until then, narrow the bypass to what was measured — a class
overriding `service()` **and declaring no dispatch-table member** derives nothing; one that
declares dispatch members is ambiguous and should derive an `open_question` naming the class
rather than vanishing, using the `service_identity` shape `annotation_driven.gaps` already
uses. (3) `COVERAGE.md:830`'s rationale is the no-`doXxx` case's reasoning and should say which
configuration was measured. The distinguishing fact — a `super.service(...)` call, `invoke_kind:
special` on an `HttpServlet#service` target — is carriable in the fact stream, but the catalog
would need `call_site` in `requires`, which it does not have today.

---

#### `A-M3` — `spring-webclient` and `spring-restclient` know five of eight verbs

**Sweep 4, F-3. Proof: framework** (`javap -p` on `spring-webflux-6.1.6.jar` and
`spring-web-6.1.6.jar`). Both `WebClient` and `RestClient` declare eight request-starting
methods: `get head post put patch delete options method(HttpMethod)`. Both catalogs declare five
roots (`get post put delete patch`) at `spring-webclient.yml:12-18` / `spring-restclient.yml:12-18`.

**Wrong output:** `webClient.head().uri("/health").retrieve()`, `restClient.options().uri(...)`
and `restClient.method(HttpMethod.PUT).uri(...)` derive **no outbound row at all** — a chain
with no matching root is never rooted, so nothing reaches a terminal (`fluent.py:21`).
`docs/COVERAGE.md:928` lists both "✅ shipped" and §5.2 states the OkHttp
`method(String, RequestBody)` boundary with no equivalent for these two: an unstated boundary,
which §8.1 rule 3 forbids.

**Fix.** Add `head`/`options` roots; state `method(HttpMethod)` as a boundary the way OkHttp's
already is (the verb is an enum argument, not the method name).

---

#### `A-M4` — `spring-webclient`'s terminal set is version-scoped and the catalog states no version

**Sweep 4, F-8. Proof: framework** (`javap -p` on `WebClient$RequestHeadersSpec`).

| | spring-webflux 6.1.6 | spring-webflux 7.0.2 |
|---|---|---|
| `retrieve()` | present | present |
| `exchangeToMono(Function)` / `exchangeToFlux(Function)` | present | present |
| `exchange()` | present | **removed** |

The catalog declares `terminal: [retrieve, exchange]`. **Both directions are wrong at once:**
`exchangeToMono`/`exchangeToFlux` — the only exchange-style terminals from Spring 7, and the
recommended ones since 5.3 — are in the list at **neither** version, so a module using them has
its whole `WebClient` surface absent; and `exchange` is declared and does not exist at Spring 7,
a dead entry. Neither the catalog nor COVERAGE says which Spring the list was read against; the
only version anywhere near it is `fixtures/orders-service/pom.xml`'s `spring-webflux 6.1.6`.
This is §5.4 with teeth.

**Fix.** Add `exchangeToMono`/`exchangeToFlux`; record the version the list was read against, in
the catalog, the way `jakarta-servlet.yml:41` does. See `A-Mi4` for why there is nowhere
structured to put it.

---

#### `A-M5` — `retrofit` knows six of Retrofit's eight request-method annotations

**Sweep 4, F-4. Proof: framework** (`unzip -l` and `javap -p -c` on `retrofit-2.11.0.jar`). The
package declares `GET POST PUT PATCH DELETE HEAD OPTIONS HTTP`;
`retrofit2.RequestFactory$Builder` — the class that turns a method's annotations into a request
— references all eight (`OPTIONS` ×3, `HTTP` ×5 constant-pool hits). `retrofit2.http.OPTIONS`
declares `String value()`; `retrofit2.http.HTTP` declares `String method()`, `String path()`,
`boolean hasBody()`.

`retrofit.yml:22-28` declares six. `@OPTIONS("/x")` and `@HTTP(method="REPORT", path="/x")`
methods derive nothing, with no COVERAGE row (§5.2 mentions Retrofit only as "✅ shipped" at
line 924). Curiously `all_methods` at line 19 *includes* `OPTIONS`, which is dead: it is
consulted only when a matched annotation pins no verb, and no listed Retrofit annotation is
verbless.

**Fix.** Add `{ fqn: retrofit2.http.OPTIONS, method: [OPTIONS] }`. `@HTTP` needs `path_from:
[path]` and a verb read from `method`; if the engine cannot express a second `path_from` per
annotation, state it as a COVERAGE boundary rather than leaving it silent.

---

#### `A-M6` — the Kafka catalogs miss the callback and listener overloads, which are the common ones

**Sweep 4, F-5. Proof: framework** (`javap -p -s` on `kafka-clients-3.6.2.jar` and
`spring-kafka-3.1.4.jar` — the versions CP-10 pinned).

| owner | declares | catalog declares |
|---|---|---|
| `KafkaProducer` | `send(ProducerRecord)`, **`send(ProducerRecord, Callback)`** | arity 1 only |
| `KafkaConsumer` | `subscribe(Collection)`, **`subscribe(Collection, ConsumerRebalanceListener)`**, `subscribe(Pattern)`, **`subscribe(Pattern, ConsumerRebalanceListener)`**, `assign(Collection<TopicPartition>)` | the two 1-arity forms |
| `KafkaTemplate` | 6 `send` overloads incl. **`send(String, Integer, K, V)`** and **`send(String, Integer, Long, K, V)`** | 4 + `sendDefault` |

`_matching_method` (`engines/single_call.py:466-505`) filters candidates by
`row.get("arity") in (None, len(arguments))` **before** consulting descriptors, so a 2-argument
`send` never sees the arity-1 row. `producer.send(record, (m,e) -> …)` — the idiomatic async
producer call — and `consumer.subscribe(topics, rebalanceListener)` — the idiomatic
consumer-group call — derive **nothing**. `docs/COVERAGE.md:1412-1413` lists both "✅ shipped"
with no arity qualification, and the under-report row at COVERAGE:1491 is scoped to the
Rabbit/JMS templates only.

**Fix.** One row per overload with its own descriptor — the remedy COVERAGE:1491 already
prescribes, applied here. `assign(Collection<TopicPartition>)` carries its topic inside a
`TopicPartition` and is a separate, statable boundary.

---

#### `A-M7` — `jakarta-jms` models one of `Session`'s eleven consumer factories

**Sweep 4, F-6. Proof: framework** (`javap -p -s` on `jakarta.jms-api-3.1.0.jar`).
`jakarta.jms.Session` declares `createConsumer(Destination)` — the one modelled — plus
`createConsumer(Destination, String)`, `createConsumer(Destination, String, boolean)`,
`createSharedConsumer(Topic, String[, String])`,
`createDurableSubscriber(Topic, String[, String, boolean])`,
`createDurableConsumer(Topic, String[, String, boolean])`,
`createSharedDurableConsumer(Topic, String[, String])` and `createBrowser(Queue[, String])`.

A selector-carrying consumer, and every durable or shared subscription, derives nothing. Each is
a real inbound JMS endpoint on a destination our `channel_via` (`createQueue`/`createTopic`)
could resolve. The catalog's comment at line 32 shows the author saw the arity-2 and arity-3
`createConsumer` overloads and declined them; the durable/shared family is not mentioned at all.
`docs/COVERAGE.md:1481` names no boundary for the other nine.

**Fix.** A row per overload — the destination is argument 0 in every one — or state the
under-report in COVERAGE §5.9 alongside the Rabbit/JMS template row.

---

#### `A-M8` — `spring-sqs` reads one half of an `@AliasFor` pair

**Sweep 4, F-7. Proof: framework** (`javap -p -s` and `javap -v` on
`spring-cloud-aws-sqs-3.1.1.jar`). `io.awspring.cloud.sqs.annotation.SqsListener` declares
**both** `String[] value()` and `String[] queueNames()`, and `queueNames()` carries
`RuntimeVisibleAnnotations: org.springframework.core.annotation.AliasFor(value="value")`. They
are one attribute under two spellings — precisely what `jakarta-servlet.yml:44` handles with
`args: [urlPatterns, value]` and `spring-web.yml:18` with `path_from: [value, path]`.

`spring-sqs.yml:19-21` declares `path_from: [value]`, so `@SqsListener(queueNames = "orders")` —
the spelling AWS's own documentation uses — reads as absent.

**The wrong output is not settled, and the two sweeps disagree with a document.** Sweep 4 quotes
`docs/COVERAGE.md:1444-1447`, which says the attribute-not-listed case *"derives a **resolved**
row with an **empty** path today rather than an unresolved one; a known wart"*. Sweep 1 measured
the sibling case on the shipped catalog — `@SqsListener(maxConcurrentMessages="10")` with `value`
absent — and got **0 rows**, dropped by the empty-opaque-address filter at
`derive_endpoints.sql:812`, which applies because this catalog declares no `path_separator`.
Both cannot be true of the same code. Either COVERAGE:1444-1447 is stale and the listener is
silently absent, or the two cases differ in a way neither sweep isolated. **Left open**; the fix
pass must measure the `queueNames` case specifically before writing the COVERAGE row. §4's
mechanism closes the resolved-empty branch if it exists and does nothing for the silent branch.

**Fix.** `path_from: [value, queueNames]`, then re-check the empty-path behaviour: a `resolved`
row with `path: ''` violates §8.1 rule 2 whether or not COVERAGE mentions it.

---

#### `A-M9` — `spring-webflux-router`'s verb vocabulary is exactly the fixture's verb vocabulary

**Sweep 4, F-9. Proof: framework** (`javap -p` on `spring-webflux-6.1.6.jar`).
`RequestPredicates` and `CoRouterFunctionDsl` each declare `GET HEAD POST PUT PATCH DELETE
OPTIONS` (plus `method(HttpMethod)`/`methods(HttpMethod...)`). `spring-webflux-router.yml:20-75`
encodes `GET, POST, HEAD` for `RequestPredicates` and `GET, POST` for `CoRouterFunctionDsl`.

**Why this is §8.1 rule 1's shape and not a mere omission.** The catalog's own comment at lines
16-18 states the standard it was built to: *"every owner/method/arity/argument position below is
exactly what 2E's checkpoint froze against a real scan… nothing here is invented past that."*
And the fixture it was frozen against —
`fixtures/orders-service/.../routes/OrderRoutes.java` and `.../KotlinOrderRoutes.kt` — declares
exactly `GET, POST, HEAD` in Java and `GET, POST` in Kotlin. **The encoded rule is a projection
of the examples in front of the author**, which §8.1 rule 1 names in as many words.

`RouterFunctions.route(RequestPredicates.PUT("/orders/{id}"), h::update)` — an entirely ordinary
WebFlux route — derives nothing, as do PATCH, DELETE, OPTIONS and the Kotlin
PUT/PATCH/DELETE/HEAD/OPTIONS. `docs/COVERAGE.md:898-909` states two WebFlux boundaries and
names no verb gap.

**Fix.** Four rows for `RequestPredicates` and five for `CoRouterFunctionDsl` — pure catalog
data, no engine change. `method(HttpMethod)`/`methods(HttpMethod...)` stay a stated boundary.

---

#### `A-M10` — an array has exactly one dimension

**Sweep 6, finding 3. Proof: E2E** at the fact level (shipped extractor over compiled classes).
Sites: `extractor-jvm/.../TypeRefs.java:29-35` (`descriptorName`) and `:161-165`
(`elementArguments`). Both call `org.objectweb.asm.Type#getElementType`, which returns an array
type's **innermost** element type, not one dimension less.

**The JLS/JVMS rule it should have been.** JLS 10.1 / JVMS 4.3.2: `[[Ljava/lang/String;` is an
array whose component type is `[Ljava/lang/String;`. The number of `[` is part of the type's
identity.

**Measured.** `probe/Arrays2D` with `byte[] oneD; byte[][] twoD; String[] oneS; String[][] twoS;`
and `takesOne(byte[])`/`takesTwo(byte[][])`:

```
oneD  {"symbol":"byte#[]","wire_type":"array","arguments":[{"symbol":"byte#"}]}
twoD  {"symbol":"byte#[]","wire_type":"array","arguments":[{"symbol":"byte#"}]}   # byte-identical
oneS / twoS  → java/lang/String#[] with one String# argument                       # byte-identical
takesOne.parameters[0].type == takesTwo.parameters[0].type                         # byte-identical
```

The two seams also disagree with each other: `domain/symbols.py:type_descriptor("byte[][]")`
returns `byte#[][]`, a string the extractor never emits — so a catalog naming a two-dimensional
type matches nothing while a catalog naming `byte[]` matches both dimensions.

**Wrong output.** `shapes/expansion.py:386-427` (`_described`) reads the collection's last type
argument, so a payload field `String[][] rows` is documented **and hashed** as
`{wire_type: array, item: {wire_type: string}}` — a DR-5 contract comparison of a caller sending
`String[][]` against a callee expecting `String[]` reads equal. `catalogs/spring-web.yml:195`
declares `bytes_payloads: [java.lang.String, "byte[]"]`, matched at `parse_binding.py:351`
against the handler parameter's own `type.symbol` — a `byte[][]` parameter matches it.

**The right reading exists one function away.** `TypeRefs.NodeCollector.visitArrayType`
(`:223-226`) recurses one dimension at a time and produces `…#[][]` correctly; only the
descriptor path is wrong, and that is the path every non-generic array takes, because the JVM
emits no `Signature` attribute for a plain `String[][]`. `MethodFlow.argumentJson:472-480`
already refuses `declaredType.getDimensions() != 1` and names `getElementType`'s behaviour in a
comment — understood in one file and missed in the other.

**Fix.** In `descriptorName`, build the element type from `Type.getType(descriptor.substring(1))`
rather than `getElementType()`; same in `elementArguments`, so `String[][]` holds one `String[]`.

**Not settled.** Whether any module in the estate carries a two-dimensional array in a payload.
The defect is proven at the fact level; its blast radius depends on real inputs not surveyed.

---

#### `A-M11` — a scanned ancestor always declares at least one method

**Sweep 6, finding 2. Proof: unit.** Site: `effective_annotations.py:500-518` (`_prefixed_types`),
consumed at `:488`. Its own docstring states the assumption: *"a scanned ancestor always encloses
at least its own inherited `Object` methods… in practice, its own declared ones."*

**The invented rule.** An ancestor type's module-prefixed symbol is recoverable only if that type
appears as an interface, an implementer, or the `enclosing` of some `construct_kind = 'method'`
row. `method_declarations` excludes constructors, so an ancestor declaring only a constructor is
unreachable and its annotations are never inherited.

**The JLS rule it should have been.** JLS 8.1.6: a class body may declare no methods at all (the
default constructor is JLS 8.8.9, and it is a constructor, not a method). "Has a symbol" and
"declares a method" are unrelated facts.

**Proven.** With `GenericPrefixBase<T>` declaring only `@RequestMapping("/api/items")` and no
method, `inherited_rows` returns nothing for `ItemController` even though its `supertype` fact is
present. Adding one line — `public void helper() {}` — makes the prefix row appear. **An abstract
base class that exists only to carry a type-level `@RequestMapping` is the exact shape that
fails**, and it is a common one.

**Fix.** Resolve the ancestor through `declared_symbols` (one column, every construct kind), or
drop the lookback entirely once `A-C4`'s `superclasses` edge lands, since that fact carries the
full symbol on both sides.

---

#### `A-M12` — the same generic-only `extends` rule in the parse-binding ancestry walk

**Sweep 6, finding 4. Proof: read** (the rule is `A-C4`'s, proven there; this site's consequence
is traced, not run). Site: `shapes/parse_binding.py:573-586` (`_facts`, which builds `ancestry`
from `supertypes` + `implementations` and never reads `superclasses`), consumed by `_reaches` at
`:262-285`.

**The stale rationale that hides it.** `_reaches`'s own docstring (`:266-272`) asserts *"a plain
`extends` is NOT in the fact stream at all (`supertype` is emitted only for a GENERIC
superclass)"*. Capability 9.13 falsified that sentence:
`ClassScanner.erasedSuperclassJson` (`ClassScanner.java:126-132`) writes `superclass` for every
non-`Object` superclass, proven in `A-C4`'s fact table. `catalogs/spring-web.yml:200-206` repeats
the same claim in its own comment.

**Wrong output.** `parse_calls`' protobuf entry matches by `owner_hierarchy`
(`MessageOrBuilder`, `GeneratedMessage`, `GeneratedMessageV3`, `GeneratedMessageLite`). Any
hierarchy path running through a non-generic `extends` is invisible, so a payload type whose only
route to a marker is `extends GeneratedMessage` binds nothing. Under-report, not fabrication.

**Fix.** Add `superclasses` to `ancestry`, and delete both stale sentences in the same commit.
Note the interaction with `A-Mi2`: sweep 2 doubts `spring-web.yml:209-210`'s premise that the
lite runtime "reaches none of these" on the grounds that `GeneratedMessageLite` is generic; under
this finding the non-generic paths are invisible regardless. Both halves are unverified and
should be measured together.

---

#### `A-M13` — an interface's methods are the ones it declares

**Sweep 6, finding 5. Proof: read** for our side; **the framework half is unverified.** Site:
`engines/derived_resource.py:656-682` (`_methods`, keyed on `enclosing`), consumed by `_queries`
(`:474-528`) via `_repositories` (`:369`).

**The JLS rule it should have been.** JLS 9.2 / 9.4.1: an interface inherits the methods of its
superinterfaces, and `Class#getMethods()` on an interface returns them.

**Input** — an ordinary shape:

```java
public interface BaseRepo<T, ID> extends JpaRepository<T, ID> { List<T> findByTenant(String t); }
public interface OrderRepo extends BaseRepo<Order, Long> {}
```

`OrderRepo` declares no method of its own, so `_methods["…OrderRepo#"]` is empty and `_queries`
returns `{}`.

**Wrong output.** `/orders` is derived with no `/orders/search/findByTenant` beside it — a route
the framework serves, silently absent, with no COVERAGE row. `BaseRepo` itself correctly derives
nothing (`_entity_of` refuses a type variable), so the row is lost outright rather than attached
to the wrong collection.

**Unverified half.** That Spring Data REST exposes an inherited query method was not measured; no
live app was run. `DefaultRepositoryInformation.getQueryMethods()` reads
`repositoryInterface.getMethods()`, which includes inherited interface methods, but §8.1's
"measure before you build on it" is unmet. The **language** half is certain.

**Fix.** Walk the declared superinterfaces the way `_reach` already does for contracts, stopping
at a `contracts` entry (whose methods are CRUD, not query methods).

---

#### `A-M14` — a method is identified by its name (repository CRUD exclusion)

**Sweep 6, finding 6. Proof: read**; framework half unverified. Site:
`engines/derived_resource.py:517-518` — `if name in crud_methods: continue`, where `name` is
`method_name(bare_descriptor(symbol))`, the plain identifier with the parameter list stripped, and
`crud_methods` is 25 bare names in `catalogs/spring-data-rest.yml:105-135`.

**The JLS rule it should have been.** JLS 8.4.2 / 8.4.9: a method's signature is its name and its
parameter types in order; overloading exists precisely so two methods may share a name and be
different methods. Spring Data's own `RepositoryInformation.isQueryMethod` resolves the target
method by signature (`getTargetClassMethod`), not by name.

**Input.** `interface OrderRepo extends JpaRepository<Order, Long> { List<Order> findAll(String
tenantId); }` — a derived query method whose name collides with `findAll`.

**Wrong output.** The row is dropped; Spring Data REST serves `/orders/search/findAll`. The
catalog's comment cites CP-2's observed 404, **but that probe was of an override of
`findAll(Pageable)` — the same signature** — and the rule was generalised from it to the name
alone. Same-name-different-signature is the case the probe did not cover: §5.4 again.

**Fix.** Compare the declared parameter types too — `method_visibility` would need `signature`
joined in, or `method_declarations` used instead — against a `crud_methods` list carrying
parameter types. If that is too expensive, the honest interim is a COVERAGE row, since today the
drop is silent.

---

#### `A-M15` — a type's public methods are the ones it declares

**Sweep 6, finding 7. Proof: read**; the JAX-WS half taken from the specification's wording, not
measured. Site: `storage/duckdb/derive_endpoints.sql:357-387` (`member_declarations`),
specifically `JOIN gate_types g ON g.type_symbol = s.enclosing` at `:380`, reached by
`catalogs/jakarta-jws.yml:109` (`members: public_methods`).

**The JLS rule it should have been.** JLS 8.2: the members of a class include those inherited from
its direct superclass. "The public methods of `C`" is not "the public methods declared in `C`",
and JAX-WS's implicit-SEI rule is stated over the former.

**Input.** `@WebService public class BillingWebService extends AbstractBilling` where `refund()`
is public on the base. **Wrong output:** the SOAP operation `refund` is absent from the derived
surface, with no COVERAGE row.

**What makes this one sting.** The catalog's own DR-6 comment argues at length that an unannotated
public method **is** an operation — *"a catalog that derived only the annotated methods would
report a service missing one of its own operations"* — and the SQL then makes exactly that
mistake one axis over.

**Fix.** Expand `gate_types` to the transitive superclass closure for the member join, using
capability 9.13's `superclass`, excluding `java/lang/Object`. This is the third consumer of
`A-C4`'s missing edge.

---

#### `A-M16` — `.sextantignore` loads at the module root, not the repository root

**Sweep 3, MAJ-12, lifted to Class A per roadmap `:241-242`. Proof: read.**

**Document.** `docs/components/D04-config-and-exclusion.md:167-171` is emphatic, and is itself an
amendment: *"One file, at the **repository root**, and every pattern in it is matched against a
path made relative to THAT root."*

**Consumer.** `application/stages/analyze.py:284` — `ignore = IgnoreRules.load(module.root)`, and
the comment there asserts `module.root` *is* the repository root. For a multi-module reactor that
is false: `api.py:593-596` analyzes each submodule with its own root, so a `.sextantignore` at the
reactor root is never read for any submodule, and patterns written relative to the reactor root
would not match if it were. The enrichment jail binds the same way (`api.py:829`).

**Bound.** Built-in patterns still apply at every depth (`domain/ignorefile.py:64`, `:130`), so
this is a coverage gap in the repository-authored layer only, **not a credential leak**. For a
single-module repository the two roots coincide and the document holds — **that case is unverified
by execution**, inferred from the call sites.

---

## 4. The cause, and what §13.8 says to do about it

### 4.1 The cause

Several Class A Criticals share one cause, and it is one sentence: **when a match misses, the
pipeline emits a confident value instead of nothing.**

- `A-C2` — okhttp's unmatched `.method(verb, body)` step leaves the root's `http_method: GET`
  default standing, and the row ships at `resolved`/`compiler` with the wrong verb.
- `A-C3` — the `Void` mapping falls back to `object` in nine catalogs, and the row ships with a
  wire type nobody can expand.
- `A-C4` — a missing annotation-inheritance edge means no prefix row exists, and
  `LEFT JOIN prefixes` composes the absence as `''`, so the row is published **without** its
  prefix rather than withheld.
- `A-C1` — the prefix seam leaves an absent `@ServerEndpoint`/`@HttpExchange` prefix as `''`, and
  the one filter that would drop the empty address is disabled by the catalog declaring a
  `path_separator`.

Sextant's design rule is **"unresolved is an answer, invention is not"** (§8, third-from-last
bullet). These paths have a default instead. Every one of them is the same trade: a value that is
cheap to produce and looks like the others, in place of the honest absence the schema already
knows how to carry.

### 4.2 §13.8 step 2 — test the cause against the principles that exist

It violates one that is already written. GUIDELINES §8: *"A derived record must be justified by
evidence specific to what it claims: **absent evidence, produce nothing**; ambiguous evidence,
produce nothing. Where a value cannot be read, record it as unresolved with its expression
verbatim."* That rule was written before these four shipped, and all four broke it.

### 4.3 §13.8 step 3 — therefore the fix is a mechanism, not N corrections

§13.8: *"If it violates an existing principle, stop and raise it. Do not fix the instance and
continue. A rule we already wrote, already agreed, and still broke twice is not an implementer's
slip — it is a rule with no reach, and the fix is a mechanism, not another correction."* This is
step 3, not step 4: there is no missing principle to write. §8.3 then requires the mechanism to
ship with the retroactive audit list of every site it governs — **§3.1's table is that list.**

**The proposed mechanism.** *No derivation may publish a defaulted value at
`resolved`/`compiler`. A value that comes from a catalog default rather than from evidence is
`unresolved`, or the row does not ship.*

The enforceable form, following §8.2's own invariant as the model: every capture, seam and
composition that can produce a value in the absence of a matching fact must mark that value as
defaulted, and a row carrying a defaulted value in an identity column (`method`, `path`, `peer`)
may not be stamped `resolved`. Where the whole address is defaulted, the row does not ship. Where
the mechanism cannot be expressed as a per-value flag, the ratchet form is an architecture test
over every catalog default and every SQL `coalesce` into an identity column, seeded with the sites
below as a shrinking allowlist.

### 4.4 What it closes, and what it does not

**Closed.**

| finding | how |
|---|---|
| `A-C2` | The unmatched step's verb becomes `NULL`/unresolved instead of the root's `GET`, which is precisely the "honest gap" `okhttp.yml:26-31` already claims. |
| `A-C4` | The absent prefix is a defaulted `''` in an identity column, so the row is withheld or unresolved rather than published at `/{id}`. The catalog fix still has to land for the *correct* row to appear. |
| `A-C1` | Same shape: the empty prefix is a defaulted address, so all three catalogs' rows stop shipping at `resolved`/`compiler`. The type gates still have to land. |
| `A-M8`, resolved-empty branch only | If `coalesce(…, [''])` produces a resolved empty SQS path, the mechanism stops it. If sweep 1's measurement is the true behaviour, there is nothing here to close — see the open disagreement in §3.3. |

**Boundary case.** `A-C3` is *not* closed as the mechanism is worded. The `object` value comes
from the **extractor's wire projection** (`WireTypes.objectLike`'s `default -> "object"`), not from
a catalog default, and `contracts.py` treats it as a read fact rather than a fallback. Extending
the mechanism to cover the projection's own `default ->` arms would close it and is the right
extension, because the failure is identical in kind. Recorded as a decision the fix pass must
take deliberately, not as something the sentence above already covers.

**Not closed — and this is most of the list.**

- **The whole silent-drop family**: `A-C6` (missing `declared_on` conjunct), `A-C7` (a gate
  narrower than the framework's predicate), `A-M2`, `A-M3`, `A-M4`, `A-M5`, `A-M6`, `A-M7`,
  `A-M9`, `A-M11`, `A-M12`, `A-M13`, `A-M14`, `A-M15`. None publishes a defaulted value; each
  fails to publish at all. §8's *other* clause — "exclude only on proof, never on inference" —
  governs these, and no mechanism is proposed for it here.
- `A-C5` — the fabricated Cloud Stream rows are already `unresolved` with `path: NULL`. The
  mechanism cannot reach a defect whose wrongness is the row's **existence**, not its value.
- `A-M1` — the wrong handler is chosen from ambiguous evidence, not defaulted. §8's "ambiguous
  evidence, produce nothing" covers it; the mechanism as worded does not.
- `A-M10` — the array fact is *wrong*, not defaulted.
- `A-Mi17` — a `protected` type recorded `public` is a wrong positive from an unread attribute.
- `A-C8`, `A-C9`, `A-M16` — documentation and configuration plumbing; no derivation involved.

**An observation, offered as a candidate second diagnosis rather than as a finding.** Fourteen
Class A Majors and two Criticals are silent drops, and a striking number carry the same tell in
their own comments: the encoded rule is a projection of the examples that were in front of the
author (`A-M9`'s catalog says so explicitly; `A-M2`'s and `A-M14`'s rules were each generalised
from one probe configuration; `A-M3`, `A-M5`, `A-M6`, `A-M7` and `A-M9` each encode the subset of
an overload or annotation set that the fixture happened to use). Whether that is one cause under
§13.8 or several is a question for the fix pass to settle at its second occurrence; this document
records the count and does not rule.

---

## 5. Class B — the documentation debt, sized

Settled at the **documentation-debt checkpoint immediately after 2O, before 2P**. Per GUIDELINES
§2, retire-and-mark is the expected outcome for most of it, *deliberately, recorded, and done* —
every retirement landing in `docs/documented-not-implemented.md`, and every entry answering one
question: **built / designed / retired?**

### 5.1 The size, measured rather than estimated

From the roadmap's documentation-debt section (`:216-226`), reproduced here so this file stands
alone:

| documented | exists |
|---|---|
| D01's 12+ base tables, `edges`, `dispatch`, `trace_summary`, `findings`, full-text index | **6 tables** — `endpoints`, `open_questions`, `raw_facts`, `resolved_config`, `shape_fields`, `shapes` |
| D01 §5's ten named queries (`trace_of`, `impact_of`, …) | zero occurrences in `src/` |
| M00's 25 CLI verbs across five nouns | 4 |
| D00 §5's 15 fact kinds | 8 have a producer |
| the overlay tier — D03 + M01, FR-15/FR-16 | unimplemented; "overlay" in `src/` names something else |
| D02 §2's thirteen styles | twelve — `filesystem` has a grammar, no engine, and would abort a run |

The 6-table row is independently confirmed by the session controller (§8, second bullet).

### 5.2 The per-document inventory

Every row is sweep 3's, with its own id preserved. `Q` is the question the checkpoint must
answer for that row.

#### Critical

| id | sweep 3 | mechanism | document | consumer | Q |
|---|---|---|---|---|---|
| `B-C1` | CRIT-1 | D01 §5's ten named queries — `callers_of`, `callees_of`, `implementations_of`, `uses_of`, `impact_of`, `paths_between`, `endpoint_for_address`, `trace_of`, `who_uses_shape`, `who_reads_config` | `D01:534-546`; repeated `M09:17-21`; built on by `M07:86`, `M04:184`, `D06:206,212`, `components/README.md:97` | **none** — zero grep hits in `src/`/`tests/`. The real registry is `workspace.py:10` `_NAMED_QUERIES`, 29 resolver-internal reads with different names | built / **designed** / retired — FR-9 and FR-10 have no surface at all; five documents cite `trace_of` |
| `B-C2` | CRIT-4 | the entire overlay tier — D03's four kinds, M01's `validate`/`claims`/`resolve`, FR-15/FR-16 | `D03` whole; `M01:14-18`, `:69-76` | **none**; and `grep -rni overlay src/` returns 131 hits that are all the *enrichment* overlay — a different envelope, different kinds, JSON not YAML, and only rank 10 exists | built / **designed** / retired — **and rename one of the two "overlay" concepts either way**; the collision is the part that costs an implementer a day |
| `B-C3` | CRIT-5 | D02 §2b's `classifications` block; D00 §4's `terminal_kind`, `target_kind`, `root_kind` | `D02:1836-1862`, `:1856-1857`; `D00:181`, `:184-188` | **none at any layer**; no closed set in `domain/closed_sets.py`; no catalog declares the block | retired, as a **cluster** — register entry #7 covers `root_kind` alone and under-states it; FR-14 is described as reachable from a mechanism with no grammar consumer, no closed set and no producer |
| `B-C4` | CRIT-6 | M00's 25 verbs across five nouns (`module`, `system`, `symbol`, `endpoint`, `overlay`), plus `--format`, `--scope`, `--workspace` | `M00:41-49`, `:129-132` | `cli/app.py` defines four: `module analyze` (`:57`), `render` (`:96`), `enrich` (`:111`), `export` (`:190`) | retired — **and redirect `D02:2662-2663` and `D04 §3`**, which route a reader to `module status` for the honesty reporting; the information is real and reachable (`metadata.json`, `document.py:1025-1031`), only the named route is not |
| `B-C5` | CRIT-7 | D01 §2's `edges` table and nine edge kinds, five Structure tables, `dispatch`/`dispatch_site`, `trace_summary`, `findings`, the full-text index, and seven of twelve base tables | `D01:43-49`, `:52-73`, `:85-92`, `:432-434`, `:476`, `:524-530` | the whole DDL is `schema.sql`: 6 tables, 6 views. `\bedges\b` in `src/` matches only local Python lists for one Mermaid diagram | **designed** / retired — D01 is ~60% proposal presented as schema, and it is the document 2P's Meridian vocabulary will be derived from. The renderer is honest where D01 is not (`document.py:62`, `metadata.py:23,25`) |
| `B-C6` | CRIT-8 | D05 §4's `<workspace>/state.json` — `stamp`, `environments`, `last_run.stages`, `allow_uncovered_used`, `allow_resolve_used`, `cache.*`, and the "guard is complete" claim | `D05:200-234`; obligations restated at `D04 §4a`, `M02:95`, `M02:183` | **none** — `grep -rn "state\.json" src/` → 0. No invalidation guard: `load_facts` unconditionally deletes and re-inserts | built / retired — **a bundle produced with network resolution permitted is today indistinguishable from one produced without it**, which is the property D04 §4a exists to guarantee |
| `B-C7` | CRIT-9 | D00 §5's fifteen fact kinds — `relationship`, `occurrence`, `constant`, `string_literal`, `dependency`, `deployment`, `declared_contract` have no producer anywhere | `D00 §5` | the `Fact` union has **eight** members; the Java extractor emits **six** kinds; the Python readers add two | **designed** / retired, per kind — each is also a D01 §2 table that does not exist (`B-C5`), so the two schema documents fail together and neither reveals the other. **2P derives Meridian's vocabulary from D00 and D01** |

#### Major

| id | sweep 3 | mechanism | the gap | Q |
|---|---|---|---|---|
| `B-M1` | MAJ-1 | `open_questions.question` closed set | D01:491-493 and `schema.sql:146-147` say **two**; `open_questions.py:26-38` enforces **five**; `channel_destination` has a render arm and **no writer** | fix the documents to the shipped five; then `channel_destination` is built / designed / **retired**. See `A-Mi12`: the same cluster has a stale comment in `src/`, and the two should be one commit |
| `B-M2` | MAJ-2 | D00 §4's `unresolved_reason` closed set (eight members) | the column exists, is written and is read — and carries D01's *config-resolution* vocabulary instead. **Zero of D00's eight members is produced anywhere.** The costliest §5.3 shape: the grep succeeds honestly and the mechanism answers a different question | retired, pointing D00 §4 at D01's set; and add "not produced this phase" beside `D01:401`'s `environment`, which the code marks unreachable honestly and the document does not |
| `B-M3` | MAJ-3 | three of six `evidence` tiers, one of four `resolution` tiers, two of six `format` members | `syntax`, `name_match`, `human` have no producer; `llm` only on enrichment claims; `Resolution.PARTIAL` → 0 hits; `narrowed` only ever `format_resolution`; `format: string`/`bytes` never produced | state per-member producer status in D00 §4, the way `OriginTier`'s own comment already does |
| `B-M4` | MAJ-4 | D00 §4's `protocol` closed set | lists ten; `closed_sets.py:78-86` adds `amqp` and `pulsar`, and three shipped catalogs declare them. **The inverse direction** — a reviewer citing D00 would call two shipped catalogs invalid | built: add the two members to `D00:190`, D01 and `ARCHITECTURE.md:169` (§5.1) |
| `B-M5` | MAJ-5 | `metadata.json` versus D05 §3 | no `resolution` key, no `provenance.generated_at`; nine top-level keys ship that D05 does not mention | **the shipped file is the better artifact and the document should follow it** |
| `B-M6` | MAJ-6 | `modules.json` versus D05 §3a | different shape, different writer (`_analyze_reactor`, not the detector), different trigger — **written only for a multi-module root**, so the document's stated purpose fails for every single-module repository. `--refresh-stale` does not exist | retired / rewritten to the shipped shape |
| `B-M7` | MAJ-7 | D06 §3's per-document `redaction_set_hash` column; §5's bundle contract | the `documents` view projects seven columns and that is not one; three of seven §5 rows are unmet; the §3 example manifest lists `edges`/`dispatch`/`trace_summary` in `contents.tables` and cannot be produced. D06 §4's eight-row compatibility table has **no reader** | correct §3's column claim; mark §5's three rows against `B-C5`; decide on §4 |
| `B-M8` | MAJ-8 | `--allow-resolve`'s "one flag, every network escape" | row 1 is wired; row 2 (remote OpenAPI `$ref`) is **dead** — there is no OpenAPI reader at all, so M03's whole `$ref` policy is unimplemented; the recording (`B-C6`) and the cache do not exist | retire the second row and the recording promise, or build them |
| `B-M9` | MAJ-9 | D02 §2's `filesystem` style | a complete grammar with `matches.manifest`, `matches.walk.root`, `endpoint_file`, `verb_from` and a segment pattern table; `_ENGINES` holds eleven and this is not one; a catalog written to it **aborts the resolve** | retired, using the model already in the same document: `protocol_hint`'s explicit *"Execution amendment (Phase 2H): it is not an engine"* at `D02:1667-1669` |
| `B-M10` | MAJ-10 | capability 9.15's `elements`, produced and read by nothing | **not a finding — see §7.1.** It is 2O Task 13, scheduled and not yet run. Retained here only so the checkpoint does not rediscover it | n/a — track as Task 13 |
| `B-M11` | MAJ-11 | the register itself | `docs/documented-not-implemented.md` holds **ten** rows, numbered 1,2,3,4,5,6,7,9,12,8. `docs/RUNBOOK.md:397-401` counts **six** instances of the class, and two of them — `trace_of` and project catalogs — **have no row at all**. Numbers **10 and 11 are absent with no explanation**, and `git log` shows no diff ever adding them. The file's prose says "eight instances"; the roadmap says "eleven documented mechanisms" | built — add the two missing rows (`B-C1`, `A-C9`), explain or reuse 10/11, reconcile the three counts. §13.8's whole mechanism is "without a record, the third occurrence looks like the first" |
| `B-M12` | MAJ-13 | D04's built-in redaction **value** patterns and its key-matching rule | `redaction.py:55-59` — *"There are no built-in VALUE patterns"*; the only value-side built-in is URL userinfo stripping. Key patterns match the **whole normalized key path**, not the final segment — and D04's own over-masking example only works under the code's rule, so two paragraphs of D04 contradict each other. Two built-in keys D04 never lists | retired / corrected. NFR-8: a reader who believes JWTs and private-key blocks are masked by default will not write the patterns that would mask them |
| `B-M13` | MAJ-14 | D00 §2's `document` metadata — nine produced fields, none projected — and its two present-tense claims | "every field is part of the cache key": there is no cache. "Every downstream question of the form 'is this symbol first-party?' reads `origin_tier`": nothing reads `origin_tier`; the readers go through `documents.origin` | correct both sentences; project the version/hash fields or say they travel only inside `facts/*.parquet` |
| `B-M14` | MAJ-15 | `construct_kind` — six of fourteen members produced | a Java `record` is emitted as `class` (no `ACC_RECORD` test); and `function` is **read** by `derive_endpoints.sql:716` and `workspace.py:219,251` while no producer writes it — a widened filter that looks like multi-language readiness and is a permanent no-op on JVM input | state per-member producer status; decide on `record` (see `B-Mi9`) |
| `B-M15` | MAJ-16 | `invoke_kind`, and `throw` | `MethodFlow` emits five kinds and has **no `ATHROW` handling**, so `throw` is never recorded; and the whole field is read by nothing. Two documents assert the `throws` terminal from opposite ends and neither end is built | retired with `B-C3`'s `terminal_kind` cluster |
| `B-M16` | MAJ-17 | `TypeRef.nullable_resolution`, typed as the four-valued `resolution` set | the extractor hardcodes `"resolved"` (`TypeRefs.java:178`) and its only reader passes it through or overwrites it; §5b's DR-5 rule has nothing to fire on. Related: D00 §3's two invariants about `candidates` have **no representation in the fact schema** | correct D00 §5a/§5b to one value; decide on the DR-5 rule |
| `B-M17` | MAJ-18 | sixteen fact fields produced and read by nothing | incl. `SymbolFact.line_start`/`line_end` (**hardcoded `"0"`**), `AnnotationFact.retention`, `AnnotationUse.unresolved`, `CallArgument.elements`, `CallSiteFact.invoke_kind`, `Parameter.name`, `ConfigEntryFact.key_raw`, `DeclaredFieldFact.default`/`.enum_symbols`/`.name`, four `ModuleFact` fields, `precedence_of()`. D00 §6's `ext.jvm`/`ext.kotlin` blocks are never produced at all | per field: built / designed / retired. **Register entry #3 records `ModuleFact` as CLOSED and it is closed for one field of five** |
| `B-M18` | MAJ-19 | three extractor keys with no pydantic field | `parameter.type_annotations`, `signature.return_type_annotations`, `ext` are written by the extractor and dropped by `extra="ignore"` on rewrite, for every document carrying an `embedded_descriptor`. **Cost today: none observable**, because nothing reads them — it becomes a silent data-loss bug the moment something does, presenting as "the extractor didn't emit it", which is false | built (add the fields) or `extra="forbid"`/`"allow"` deliberately, said in D00 §5a |

#### Minor

| id | sweep 3 | mechanism | Q |
|---|---|---|---|
| `B-Mi1` | MIN-1 | `displayName` — declared by all 52 catalogs, read by nothing. Verified exhaustively: it is the **only** D02 grammar key with no consumer | retired from D02's canonical example, or read |
| `B-Mi2` | MIN-2 | D02 §1's catalog-level `format` default, which `D02:1914-1917` denies in the same document | fix the §1 table row |
| `B-Mi3` | MIN-3 | D02 §6 states module-wide catalog activation as fact without §1's caveat, and §6 is the section a catalog author reads | correct §6 |
| `B-Mi4` | MIN-4 | "D02 §12" is cited three times and D02 has no §12 (the active-set text is §6) — including by `documented-not-implemented.md:25` and `ports/catalogs.py:38` | correct all three citations |
| `B-Mi5` | MIN-5 | `D02:2658` and `D05:244` spell the per-module file `sextant.yml` without the leading dot. **Compounds `A-C9`**, where the two spellings are two different files and one of them aborts | correct both |
| `B-Mi6` | MIN-6 | `PROJECT.md:40-60` marks every D0x and M0x "planned", including nine that are shipped. Stale in the safe direction — but it means the one table a reader could use to tell shipped from proposed is uniformly wrong, which is why `B-C1` and `B-C5` had to be found by grep | rebuild the status tables |
| `B-Mi7` | MIN-9 | **GUIDELINES §5.3's own recommended mechanism does not exist**: no test in the repository reads any component document. Per §8.3 the principle shipped with an incomplete register and no test | build it — the cheapest fix on the page, and the one that makes this sweep re-runnable in seconds |
| `B-Mi8` | MIN-10 | D00 §5's `field_write` table row contradicts D00's own JSON sketch, and the code follows the sketch | fix the row, not the code |
| `B-Mi9` | sweep 6 #14 | `ConstructKind.RECORD` is declared and unreachable: a Java record is emitted as `construct_kind: "class"`. Not *false* — JVMS says a record is a class, and structural expansion is the right answer for one | register entry; decide with `B-M14` |

### 5.3 The register's own state

`docs/documented-not-implemented.md` is the artifact every Class B retirement lands in, and sweep
3 verified all ten of its rows are **still accurately described, with none fixed since it was
written**. Two entries are narrower or wider than they read: **#3 (`ModuleFact`, marked CLOSED)**
is closed for `dependency_coordinates` only — the other four fields of the same fact are in
`B-M17`; **#7 (`root_kind`)** is right that it is a live risk to 2P and should widen to `B-C3`'s
whole cluster. Entry **#1**'s `detect.coordinates` carries a form-two note the entry does not
make: the loader *validates* the coordinate shape for all 52 catalogs while only the single
`derived_resource` catalog's value is ever read (§8, first bullet).

The file's defects are `B-M11`: ten rows, numbered 1,2,3,4,5,6,7,9,12,8; no row for `trace_of`
and none for project catalogs, both of which RUNBOOK counts; and **numbers 10 and 11 skipped with
no explanation**, with no commit ever having added them. This was independently confirmed against
the file.

---

## 6. The three standing inventories

These are deliverables in their own right: later ratchets consume them, and each is the durable
copy of a scratchpad artifact.

### 6.1 The negative-claim inventory

Sweep 2 walked every negative claim ("never", "cannot", "always", "only") in the catalogs and
engines and tried to falsify each. **Legend:** `PROVEN` — cites a test or probe by name, and it
exists · `VERIFIED` — the auditor tried to falsify it and could not, method stated · `FALSE` —
falsified, with the finding named · `UNVERIFIED` — not reached this sweep.

**On the counts.** Sweep 2's header says "44 distinct claims", its closing count line says
"PROVEN 3, VERIFIED BY ME 30, FALSE 5, UNVERIFIED 6" (which sums to 44), and its prose says "only
two of fifty-three cite their evidence" — over a table of 54 numbered rows (1–53 plus 3b). **The
arithmetic does not close and this document does not reconcile it** (§7.3). The per-row verdicts
below are reproduced as the sweep recorded them and are what a ratchet should consume; the
summary counts are not.

**Nine rows carry a FALSE verdict.** Two (#3, #30) were already corrected in place before the
sweep and are not live. The remaining seven map to six live sites, **all of which already have a
Class A row**: #4 → `A-C2`, #6 → `A-C3`, #15 → `A-M2`, #31 and #32 (one site) → `A-M1`, #44 →
`A-Mi1`, #49 → `A-Mi3`. Nothing had to be carried in.

#### Catalogs

| # | Site | Claim (abridged) | Verdict |
|---|---|---|---|
| 1 | `spring-stomp.yml:99-106` | a `@SendToUser`-only handler takes the honest path-NULL unresolved reply row | **PROVEN** — cited test exists at `test_endpoints.py:3246` |
| 2 | `fluent.py:264-268` | only steps declaring an `owner` fold backward, "two fabrications proven by probe" | **PROVEN** — names the probe and both fabrications |
| 3 | `spring-ws-template.yml:96-127` | the SUPERSEDED "costs recall … never publishes a wrong row" | **FALSE, corrected in place** by the file itself |
| 3b | `spring-ws-template.yml:119-127` | the replacement: the arity-2 descriptor makes the callback form derive nothing | **VERIFIED** |
| 4 | `okhttp.yml:26-31` | `.method(String, RequestBody)` "not covered … a known gap, not silently guessed" | **FALSE → `A-C2`** |
| 5 | `okhttp.yml:20-26` | an unmatched verb step leaves the root's GET "uncorrected — a confidently WRONG verb" | **VERIFIED — true, and it is the bug** |
| 6 | 28 catalogs, e.g. `spring-restclient.yml:79-87` | `known_types` mirrors the projection; "`Void` reaches no wire type at all" | **FALSE → `A-C3`** |
| 7 | `spring-jms-template.yml:37-40` | a `Destination` arg 0 "can never fabricate anything" | **VERIFIED** |
| 8 | `spring-websocket.yml:42-48` | `channel_arg: 1` "can never resolve" a path — an under-report, never a wrong address | **VERIFIED** |
| 9 | `spring-resttemplate.yml:26-30` | a `RequestEntity` parameter cannot accept a `String` constant | **VERIFIED** |
| 10 | `spring-resttemplate.yml:32-39` | one descriptor on one arity-less row "would have claimed every argument count … silently" | **VERIFIED** |
| 11 | `kafka-consumer.yml:44-58` | `List.of` elements are positional literals, "never an array to unpack" | **VERIFIED** |
| 12 | `jakarta-jws.yml:76-79` | no `@WebMethod` carries a `targetNamespace`, so the method-level read is "always NULL" | **VERIFIED** |
| 13 | `jakarta-jws.yml:136-138` | `@WebMethod(exclude)` matches a written-out value only; "absence never withdraws anything" | **VERIFIED** |
| 14 | `jakarta-servlet.yml:44-48` | `value`/`urlPatterns` are an alias set; "exactly one key present, or no row" | **VERIFIED** |
| 15 | `jakarta-servlet.yml:113-117` | overriding `service()` replaces the dispatch, "a wrong answer, not a partial one" | **FALSE → `A-M2`** |
| 16 | `jakarta-servlet.yml:129-140` | implicit HEAD/OPTIONS/TRACE derive nothing | **VERIFIED** — the exclusion is on absence of a handler symbol, which is proof |
| 17 | `jakarta-servlet.yml:142-154` | "THE ONE OVER-REPORT THIS FILE CANNOT SEE" (`metadata-complete="true"`) | **VERIFIED as a real over-report; the word "ONE" is FALSE** — `A-M2` is a second unseen error in the same file, in the other direction |
| 18 | `google-pubsub-client.yml:19-24` | without this row a config-built `Publisher` field would "never" appear | **VERIFIED** |
| 19 | `google-pubsub-client.yml:44-47` + 4 siblings | "a unique overload's descriptor can only ever equal what a matching call carries" | **VERIFIED** |
| 20 | `grpc-spring.yml:13-14` | an annotation row minting an endpoint "would be inventing an address" | **VERIFIED** |
| 21 | `grpc-spring.yml:44-46` | gating on an unread capability "would skip the corroboration in exactly the scans that most need it" | **VERIFIED** |
| 22 | `spring-web.yml:209-210` | "the lite runtime reaches none of these and binds nothing" | **premise UNVERIFIED / conclusion VERIFIED → `A-Mi2`** |
| 23 | `spring-cloud-stream.yml:19` | the capability gates on the pass having RUN, never on the table having rows | **VERIFIED** |
| 24 | `spring-data-rest.yml:108` / `derived_resource.py:341` | a base repository is "never a bean of its own" | **VERIFIED** |
| 25 | `spring-kafka-media.yml:24-26` | a stamp lands only where every environment agrees, "never over a non-NULL column" | **UNVERIFIED** — `stamp_media.sql` not read. See §7.4 |
| 26 | `spring-kafka-media.yml:31-33` | an unquoted `on:` key "would never reach the engine under the name D02 gives it" | **VERIFIED** |
| 27 | `spring-graphql.yml:14-16` | the two catalogs cannot claim each other's methods | **UNVERIFIED** |
| 28 | `spring-webflux-router.yml:25` | "`nest` never reaches it" | **UNVERIFIED** |
| 29 | `jakarta-websocket.yml:30-36` | "`value` is never present, so every `@OnMessage` …" | **UNVERIFIED** |
| 30 | `spring-kafka-template.yml:22-25` | the superseded "would simply never be reached (dead catalog data)" | **FALSE, corrected in place** |

#### Engines

| # | Site | Claim (abridged) | Verdict |
|---|---|---|---|
| 31 | `interface_implementation.py:186-193` | "the interface declares exactly one, which makes that ordering a tiebreak rather than a choice" | **FALSE → `A-M1`** |
| 32 | `interface_implementation.py:172` | "only its handler is unread, never fabricated" | **FALSE → `A-M1`**, same site |
| 33 | `interface_implementation.py:163-167` | the one-hop interface check holds "by construction" | **VERIFIED** |
| 34 | `combinator.py:122-124` | `handler` is resolved or NULL, "never fabricated" | **VERIFIED** — exact-key read, not the prefix scan that breaks #31 |
| 35 | `combinator.py:762` | "the route still derives; only its handler is unread, and never invented" | **VERIFIED** |
| 36 | `annotation_driven.py:151-153` | the reply row's `direction` is a literal, "so the seam can never reach it" | **VERIFIED** |
| 37 | `annotation_driven.py:202-210` | "corroboration cannot mint identity, and that is the whole design" | **VERIFIED** |
| 38 | `annotation_driven.py:832-835` | `@SendTo`'s `value` "always" arrives as a `String[]`; the scalar form is still read | **VERIFIED** — the defensive branch makes the claim non-load-bearing |
| 39 | `supertype_dispatch.py:232-236` | two members "can never share a selector" | **VERIFIED — and this is the correct implementation of the rule #31 gets wrong** |
| 40 | `supertype_dispatch.py:37-42` | an override may only widen visibility, never narrow it | **VERIFIED** — JLS §8.4.8.3 |
| 41 | `supertype_dispatch.py:107-110` | `resolution` is "always" `resolved` for an annotation address | **VERIFIED** |
| 42 | `supertype_dispatch.py:202-207` | every element the compiler writes is a string | **VERIFIED, caveat live** |
| 43 | `supertype_derived.py:405-412` | the corrected claim: which of two symbols survived "can never reach a row" | **VERIFIED** |
| 44 | `arguments.py:688-691` | "the scanner never unpacks an array argument into its elements" | **FALSE, no live consequence → `A-Mi1`** |
| 45 | `arguments.py:148-172` | anything not a string literal is path NULL, `unresolved` | **VERIFIED** — the guard that makes #7, #8, #9 and #48 hold |
| 46 | `fluent.py:364-368` | every fluent `http_method` is the catalog's own literal, so it "can never itself fail to resolve" | **VERIFIED for shipped catalogs — and it is the root cause of `A-C2`**; no loader check enforces it |
| 47 | `fluent.py:497-508` | a captured-and-unreadable `base` "poisons the whole address" | **VERIFIED** |
| 48 | `single_call.py:292-296` | the frozen catalogs' `channel_arg` positions are "never" string literals | **VERIFIED** |
| 49 | `derived_resource.py:398-404` | "ordinary names always pass" | **FALSE in a corner, latent → `A-Mi3`** |
| 50 | `derived_resource.py:415-420` | a base repository passing type variables through "IS such a case" | **VERIFIED** |
| 51 | `schema_operations.py:416-418` | a gRPC message descriptor is "always object, never nullable" | **UNVERIFIED** — proto3 presence semantics not checked |
| 52 | `injected_client.py:145-147` | "capture failure, never a fabricated stub type" | **UNVERIFIED** |
| 53 | `analyze.py:220-223` | a library class "can never" compete with a module class for one fact-file target | **VERIFIED** |

**The finding inside the inventory.** Only **two** of the fifty-plus claims cite their evidence in
the text (#1 and #2). The rest are reasoned, not measured — and five of the reasoned ones were
wrong. §9's rule ("a comment justifying an omission states the condition that would make it
wrong") is being followed in form and not in evidence.

### 6.2 The catalog measurement table and the probe backlog

**Legend.** `G` gold — CP-9/CP-5 standard: re-runnable harness, generated table, identities read
from the run's own output, framework *behaviour* under test · `D` descriptor-only (CP-10) · `P`
partial — a pre-§5.4 probe, a committed fixture, or an inline `javap` read · `N` none — the rule
is asserted from a checkpoint note, documentation or memory.

| # | Catalog | Measured (artifact) | Version scope | Verdict |
|---|---|---|---|---|
| 1 | `aws-sqs-sdk` | P — fixture + "verified live"; CP-2/CP-3 in comments | ✗ | unmeasured rule, unversioned |
| 2 | `google-pubsub-client` | D — CP-10 row 1 | ✓ 1.129.3 | descriptor measured; rule not |
| 3 | `google-pubsub-publisher` | P — "CHECKPOINT FACT (live javap)" | ✗ | unversioned |
| 4 | `google-pubsub-subscriber` | N | ✗ | **unmeasured** |
| 5 | `graphql-schema` | N | ✗ | spec reader; unmeasured |
| 6 | `grpc-java` | P — `cp3_cp8_grpc_facts.md` + committed fixture | ✗ | partial |
| 7 | `grpc-net-devh` | P — CP-8 named | ✗ | partial |
| 8 | `grpc-schema` | N | ✗ | unmeasured |
| 9 | `grpc-spring` | P — CP-8 named | ✗ | partial |
| 10 | `jakarta-jms` | D — CP-10 rows 2–3 | ✓ 3.1.0 | **`A-M7`** |
| 11 | `jakarta-jws-client` | N (sibling file carries the notes) | ✗ | unmeasured |
| 12 | `jakarta-jws` | P — "both reference implementations", unnamed | ✗ | **`A-Mi7`** |
| 13 | **`jakarta-servlet`** | **G — CP-9, `scripts/probes/cp9_servlet/`** | ✓ Tomcat 10.1.50 / 11.0.24 | **standard met** (and see `A-M2`: the verdict outran its configuration) |
| 14 | `jakarta-websocket` | N — a fact-stream note from a fixture | ✗ | **`A-C1`** |
| 15 | **`javax-servlet`** | **G — CP-9 third column** | ✓ Tomcat 9.0.121 | **standard met** |
| 16 | `kafka-clients` | D — CP-10 row 4 | ✓ 3.6.2 | **`A-M6`** |
| 17 | `kafka-consumer` | D — CP-10 row 5 | ✓ 3.6.2 | **`A-M6`** |
| 18 | `microprofile-graphql` | P — API-jar attribute read | ✗ | **`A-Mi9`** |
| 19 | `netflix-dgs` | P — annotation attribute read | ✗ | unversioned |
| 20 | `okhttp` | N | ✗ | unmeasured; **`A-C2`** |
| 21 | `retrofit` | N | ✗ | **`A-C6`, `A-M5`** |
| 22 | **`spring-actuator`** | **G — CP-5, `scripts/probes/cp5_actuator/`** | ✓ Boot 3.5.10 / 4.1.1 | **standard met** |
| 23 | `spring-cloud-openfeign` | N | ✗ | **unmeasured** |
| 24 | `spring-cloud-stream` | N | ✗ | **`A-C5`** — whole binding rule from documentation |
| 25 | `spring-data-rest` | P — CP-2 (live app; pre-§5.4, no harness) | ✓ Boot 4.0.1 / SDR 5.0.1 | measured, prose-only provenance |
| 26 | `spring-graphql` | P — annotation attrs only | ✗ | **`A-C7`** |
| 27 | `spring-http-interface` | N | ✗ | **`A-C1`** |
| 28 | `spring-jms-template` | D — CP-10 | ✓ 6.1.6 | under-report stated (COVERAGE:1491) |
| 29 | `spring-jms` | N — "CHECKPOINT FACT" note only | ✗ | unmeasured |
| 30 | `spring-kafka-media` | N — whole serializer→media table from documentation | ✗ | **unmeasured, high output weight** |
| 31 | `spring-kafka-message` | P — "live javap" | ✗ | unversioned |
| 32 | `spring-kafka-replying` | D — CP-10 | ✓ 3.1.4 | descriptor measured |
| 33 | `spring-kafka-template` | D — CP-10 | ✓ 3.1.4 | **`A-M6`** |
| 34 | `spring-kafka` | N | ✗ | `topicPartitions` under-report stated |
| 35 | `spring-mvc` | N — **nothing at all** | ✗ | **`A-C7`**; highest-output unmeasured catalog |
| 36 | `spring-pubsub` | D — CP-10 | ✓ 5.1.2 | descriptor measured |
| 37 | `spring-pulsar` | P — inline `javap` | ✓ 1.2.11 | versioned, no harness |
| 38 | `spring-rabbit-template` | D — CP-10 | ✓ 3.1.4 | under-report stated |
| 39 | `spring-rabbit` | P — inline `javap` | ✓ 3.1.4 | versioned, no harness |
| 40 | `spring-restclient` | N | ✗ | **`A-M3`** |
| 41 | `spring-resttemplate` | D — CP-10 (10 rows) | ✓ 6.1.6 | descriptor measured |
| 42 | `spring-sqs-legacy` | P — inline `javap` | ✓ 2.2.6.RELEASE / 2.4.4 | versioned, no harness |
| 43 | `spring-sqs-template` | D — CP-10 | ✓ 3.1.1 | interface-owner gap stated |
| 44 | `spring-sqs` | N | ✗ | **`A-M8`** |
| 45 | `spring-stomp` | N — 2H checkpoint note | ✗ | **`A-C1`** |
| 46 | `spring-web` | P — CP-1 (path seam), CP-6 (jackson coordinate) | ✗ | **`A-C7`** — the handler gate itself never measured |
| 47 | `spring-webclient` | N | ✗ | **`A-M3`, `A-M4`** |
| 48 | `spring-webflux-router` | P — 2E checkpoint against the fixture's own scan | ✗ | **`A-M9`** |
| 49 | `spring-websocket` | D — CP-10, and the probe **says the version is assumed** | ✓ 6.1.6 (declared an assumption) | **model of honest scoping** |
| 50 | `spring-ws-template` | D — CP-10 | ✓ 4.1.4 | descriptor measured |
| 51 | `spring-ws` | P — 2I checkpoint note | ✗ | unmeasured type gate |
| 52 | `wsdl-schema` | N | ✗ | spec reader; unmeasured |

**Grade distribution: 3 G, 13 D, 17 P, 19 N. Version scope stated: 20; silent: 32.** Sweep 4's own
headline ("21 rest on a named committed evidence artifact; 31 unmeasured") is not derivable from
this distribution — see §7.5.

**Why CP-10's green table is not measurement.** `scripts/probes/cp10_catalog_descriptors/` asks
one question — *"does every descriptor a shipped catalog declares name a method the framework's
own bytecode actually declares?"* — and never the converse: *does the framework declare a method
that serves this purpose and the catalog does not name?* `A-M5`, `A-M6`, `A-M7` and `A-M8` all
live on the converse side. A reader of CP-10's `0 NOT DECLARED` row will reasonably believe those
thirteen catalogs are settled; they are settled in one direction only, and the file does not say
so (`A-Mi5`).

#### The ranked probe backlog

Ranked by how much shipped output depends on the catalog, then by fabrication risk.

| rank | catalog(s) | why | what the probe must answer |
|---|---|---|---|
| 1 | `spring-web` + `spring-mvc` | the two highest-volume catalogs; `spring-mvc.yml` cites no evidence of any kind (`A-C7`) | pin `isHandler`'s body per Spring minor; measure the custom-stereotype, superclass and interface cases |
| 2 | `microprofile-graphql` | the only unmeasured rule found that would publish a **wrong** name (`A-Mi9`) | deploy `@Query getOrders()` under SmallRye and read the served operation name |
| 3 | `spring-cloud-stream` | 100% of its output from documentation (`A-C5`) | a live module: lambda bean, class bean, composed definition, named binder |
| 4 | `jakarta-websocket` | `A-C1`, plus no framework measurement at all | deploy `@ServerEndpoint`, `@ClientEndpoint` and a programmatic `Endpoint`; measure what is served |
| 5 | `spring-webflux-router` | `A-M9`; the largest single silent drop | `javap` the predicate classes per Spring minor; route one of each verb and curl it |
| 6 | `spring-webclient` + `spring-restclient` | `A-M3`, `A-M4`; version-sensitive terminal set, no version recorded | enumerate roots and terminals per Spring minor from the jar |
| 7 | `spring-kafka` / `spring-jms` / `spring-sqs` / `spring-stomp` | four listener catalogs whose attribute rules are checkpoint notes with no version | which attributes name a destination, per listed version; `@SqsListener.queueNames` (`A-M8`) |
| 8 | `spring-kafka-media` | the whole serializer→media table (16 rows, four Confluent classes) from documentation | confirm each class exists and emits the claimed wire form at a stated version |
| 9 | `spring-http-interface` / `spring-cloud-openfeign` | two outbound HTTP catalogs, no evidence artifact | is the `@FeignClient`/`@HttpExchange` gate literal or a predicate? |
| 10 | `retrofit` / `okhttp` | `A-M5`, `A-C2`; no evidence artifact for either | enumerate the annotation set / builder verb set per version |
| 11 | `spring-ws` / `jakarta-jws` / `jakarta-jws-client` | three SOAP catalogs on checkpoint notes (`A-Mi7`) | is Spring-WS's `@Endpoint` gate hierarchy-aware? JAX-WS's exposed-member rule per RI (`A-M15`) |
| 12 | `netflix-dgs` / `spring-graphql` | attribute reads only | DGS's own handler-bean predicate |
| 13 | `google-pubsub-*` ×3, `aws-sqs-sdk`, `grpc-schema`, `graphql-schema`, `wsdl-schema` | lower volume, or spec readers | overload/entry-point completeness; `SqsAsyncClient` as a second terminal owner |

**Six catalogs need no probe work**: `jakarta-servlet`, `javax-servlet`, `spring-actuator`,
`spring-data-rest` (its CP-2 needs rebuilding to §5.4's generated form; it is on
`test_probe_provenance.py`'s shrinking list), `spring-websocket` (its assumption is declared),
`spring-sqs-legacy`.

**And the structural blocker.** `A-Mi4`: D02 has no field in which to state a measured version, so
all 20 version statements are YAML comments — unreadable by the loader, unenforced by any test,
absent by default. Contrast `tests/architecture/test_probe_provenance.py`, which enforces exactly
this discipline for probes with a shrinking allowlist. §8.1's "state the versions measured" has
the same standing and no such enforcement; **32 of 52 catalogs are the seed list**.

### 6.3 The near-miss backlog

**Method.** Every "does this test discriminate?" claim below is a **mutation result**, not a
reading. A mirror of the repository was built outside it with `src` as a real copy and everything
else symlinked, so the engine Python, the SQL and the catalog YAML are mutable while `tests/` and
`fixtures/` are the repository's own files. Baseline: `pytest tests/application -m declines` →
**51 passed, 1012 deselected**. Each mutation removes one guard, re-runs `-m declines`, and is
reverted. A mutation that changes no marked test's outcome is the finding. Caveat recorded by the
sweep: a "51 passed" result proves *no marked test reacts*, and two mutations turned out to be
un-observable rather than uncovered (a half-mutated composite key matches nothing; a pure
optimisation) — both were re-run in an observable form before being reported.

**Counts.** 52 catalogs ship; **19 are covered** by a `@pytest.mark.declines` marker and **33 are
uncovered**, matching `_NO_DECLINING_TEST_YET` exactly. 51 marked test instances spread over 19
catalogs.

**Engine-style coverage is far worse than the catalog count suggests.**

| style | catalogs | marked-covered | uncovered |
|---|---|---|---|
| `single_call` | 13 | **13** | — |
| `supertype_dispatch` | 2 | **2** | — |
| `annotation_driven` | 21 | 4 | 17 |
| `fluent` | 6 | **0** | 6 |
| `schema_operations` | 3 | **0** | 3 |
| `config_join` | 2 | **0** | 2 |
| `combinator` | 1 | **0** | 1 |
| `derived_resource` | 1 | **0** | 1 |
| `injected_client` | 1 | **0** | 1 |
| `interface_implementation` | 1 | **0** | 1 |
| `supertype_derived` | 1 | **0** | 1 |

**Eight of eleven engine styles have no marked declining test at all.** (Sweep 1's prose says "9
of 12"; its own table lists eleven styles summing to 52 catalogs, and `resolve/endpoints.py:169`
`_ENGINES` holds eleven — see §7.2.) `supertype_derived` is the engine C-1 broke, and it still has
none.

#### The 33 uncovered catalogs, ranked by fabrication risk

Ranking drivers, in order of weight: (1) does a single method annotation mint an endpoint —
one conjunct, and the conjunct is "an annotation is present"; (2) is the matched shape common in
ordinary Java — a plain `extends`, a fluent builder, a `Function` bean, a method named `send`;
(3) would the published address be plausible-but-wrong rather than obviously empty — a plausible
address is worse, because nothing downstream can tell it from an observation and both are stamped
`resolved`/`compiler`; (4) the number of remaining conjuncts.

**Tier 1 — findings, not backlog rows.** `spring-http-interface`, `spring-stomp`,
`jakarta-websocket`, `retrofit` and `spring-cloud-stream`. All five are Class A
(`A-C1`, `A-C6`, `A-C5`); their near-misses are the regression pins, and each must assert
`rows == []`.

**Tier 2 — one conjunct, or a conjunct that ordinary Java satisfies constantly.**

| # | catalog | style | conjunct negated | why it ranks here |
|---|---|---|---|---|
| 5 | `spring-data-rest` | derived_resource | conjunct 0, `detect.coordinates` | every other conjunct holds perfectly; without the gate this publishes **seven** URLs nobody wrote at `resolved`/`declared`. `interface X extends JpaRepository<E,ID>` is in essentially every Spring Data module, and **this is the only dependency-gated catalog in the tree** — the gate has no second line of defence. Assert `endpoints == []` **and** that the catalog appears in `skipped` |
| 6 | `grpc-java` | supertype_derived | the C-1 marker gate (`supertype_derived.py:319`) | **this IS C-1.** A discriminating test already exists (`test_supertype_derived.py:342`), unmarked, running a hand-built catalog |
| 6b | `grpc-java`, second row | supertype_derived | none — the gate PASSES | **the residual C-1 path, untested and unfixed.** The marker gate keys on "some class under the same outer type called one of two `io.grpc` methods", not on protoc provenance, so hand-written gRPC plumbing mints a resolved inbound row at a plausible-but-wrong service identity |
| 7 | `google-pubsub-subscriber` | interface_implementation | the engine's **only** row-deciding conjunct (`:87`) | `interface`, `handler_method` and `channel_via` all degrade to NULL columns rather than declining. `newBuilder` is among the most common static method names on the JVM. The fabrication is direction-inverted: a topic the service PUBLISHES to, published as a subscription it CONSUMES |
| 8 | `grpc-schema` | schema_operations | the `role is not None` gate | a protobuf message FQN is lexically indistinguishable from a service identity, and `method` is NULL either way, so nothing in the row's shape flags it. Every `.proto` carries 10–50 messages per service |
| 9 | `grpc-net-devh` | injected_client | the `field_annotation` equality (`:140`) | only 2 conjuncts, and the annotation one is negated by no test today. A readable `SERVICE_NAME` sits in the facts, so an over-broad match publishes the *correct-looking* outbound row for a stub net.devh never injected |
| 10 | `wsdl-schema` | schema_operations | the `role is not None` gate | 2I Task 3 marks input elements only; the response wrapper sits one line away in the same WSDL. Every genuine operation would gain a phantom twin |
| 10b | `graphql-schema` | schema_operations | the `role is not None` gate | without it every payload type mints one row per field. Ranked last of the three because SDL binds roots explicitly, so `role` is the least inferred |

**Tier 3 — `annotation_driven` catalogs that DECLINE correctly today.** Every row measured against
the shipped catalog: the near-miss derives 0 rows and the paired positive derives 1. They rank by
what would happen if the conjunct they rely on were loosened. `spring-web` (⚠️ `@GetMapping` is the
single most common annotation in any Spring codebase and three catalogs match the family; the type
gate is the only separator and mutation A5b shows nothing pins its package comparison),
`spring-mvc`, `spring-cloud-openfeign`, `netflix-dgs` and `spring-graphql` (both on the
`requires_qualifier` gate that mutation A7 shows nothing pins; a bare `@DgsData(field="author")`
would publish a field resolver as a root operation), `jakarta-jws-client` (the SEI fence, unpinned
per A8b; **unverified** — the fence needs an `implementations` fact the probe harness does not
build), `jakarta-jws`, `spring-ws` (plus an **unverified** side observation: `@PayloadRoot(localPart="Req")`
with no namespace publishes a bare `Req` as a resolved SOAP address and the catalog declares no
`namespace_default`), `microprofile-graphql`, `spring-kafka`, `spring-jms`, `spring-sqs`, and
`grpc-spring` (**the lowest fabrication risk of all 33** — a corroboration-only catalog that can
never mint an endpoint; its only failure mode is a duplicate open question).

**`fluent`, `combinator`, `config_join`.** `spring-kafka-message` (highest of the fluent set: the
chain root is Spring Messaging's `MessageBuilder`, shared with Spring Integration, StreamBridge,
RSocket and WebSocket, and only the join owner keeps a Spring Integration channel send from being
published as a resolved **Kafka topic**), `spring-webclient` (**no test in the suite negates the
root-owner conjunct** — the nearest omits the root call entirely), `okhttp` (a request built and
logged, never sent), `aws-sqs-sdk` (the `SqsAsyncClient` terminal owner — a false negative behind
the same conjunct), `spring-restclient` (**unverified**), `google-pubsub-publisher` (**unverified**;
a false-negative risk rather than a fabrication one), `spring-webflux-router` (`test_combinator_engine.py`
contains **not one** `assert rows == []`), `spring-cloud-stream` ×2 more rows (one of which cannot
assert `rows == []`, because the engine derives a **ghost row** for the unnamed selection entry),
and `spring-kafka-media` (**unverified**; its assertion must be "the media columns are unchanged").

**A gap in the descriptor mechanism, not a catalog row.** `fluent` checks **no descriptor
anywhere** — the word does not occur in `fluent.py` — so a root, step or terminal claims every
overload of its name on the matched owner, and `argN` is read positionally against a signature
nobody verified. `tests/architecture/test_catalog_descriptor_coverage.py` cannot see these six
catalogs at all: it scans `methods:` rows and no `fluent` catalog has one. Same for `combinator`
and `config_join`. This is `A-Mi19` from the other end.

#### The coverage findings — guards with no test, and markers that do not discriminate

These are sweep 1's MAJOR/MODERATE/MINOR findings. They are not Class A: they produce no wrong row.

| id | finding | mutation evidence |
|---|---|---|
| S1-MAJ-1 | **Four fabrication-prevention guards in `derive_endpoints.sql` are pinned by NO test.** The qualifier gate (`:763`, read by four uncovered catalogs); the SEI fence (`:750-754`, whose own comment says without it "the module is published as CALLING an operation it only serves"); `declared_on` (`:726`, the key `A-C6` needs); and the `type_annotation` fqn compare (`:207`) | mutations A7, A8b, A3, A5b each leave **51 passed** |
| S1-MAJ-2 | `supertype_dispatch`'s 11 markers omit the C-1 conjunct; **the only test that pins it carries no marker** — `test_supertype_dispatch.py:535`, whose docstring names C-1 by name | D1 (supertype equality removed): 51 marked pass; exactly one failure in the whole file, at `:535`. **Adding the marker is the highest-value single edit in the report** |
| S1-MAJ-3 | `grpc-java` sits on the backlog although two discriminating tests already exist, unmarked (`:342`, `:262`) | S2 and S3 each fail exactly one test — those two. S1 (the published-stubs-jar boundary, `:312`) is pinned by nothing: **12 passed** |
| S1-MAJ-4 | `test_a_stub_from_a_published_jar_derives_nothing_not_even_unresolved` (`:279`) does not test what it says: it negates two conjuncts at once and attributes the result to the first | S1 removes the conjunct the docstring names; the test **still passes** |
| S1-MAJ-5 | `test_a_protocol_agnostic_supertype_derives_nothing` (`:447`, marked) is pinned by the `bypassed_by` rule, not by the supertype conjunct its docstring claims. Redundant with `:430` | D1, D1+D2 and D1+D4b all leave it green |
| S1-MAJ-6 | **The `owner` conjunct of 12 of the 13 `single_call` catalogs is unfalsified**, and no fixture supplies the shape either | E2 (owner check deleted): **1 of 51 fails** — the one owner near-miss anyone wrote |
| S1-MOD-1 | The five marked near-misses in `test_endpoints.py` are vacuity-safe only via other tests: `_rows_from` (`:3933`) **discards the `skipped` list** its two sibling helpers assert on | V1b (four catalogs made unrunnable): `-m declines` **51 passed**; the positives fail 8. Adding `assert skipped == []` costs one line |
| S1-MOD-2 | The two `supertype_dispatch` spelling tests negate **three** conjuncts at once, so none is individually pinned | D1, D6, D1+D6 all pass; D1+D6+D5c fails both. **D6 alone changes no outcome, so the address-annotation package comparison is pinned by nothing** |
| S1-MOD-3 | `test_a_declared_address_with_no_dispatch_override_derives_nothing` (`:525`) **cannot fail**: with no method facts the row-minting loop iterates zero times. One extra fact (a plain `helper()`) makes it real | D4b leaves it green |
| S1-MIN-1 | The backlog's own docstring (`test_catalog_near_miss_coverage.py:16-18`, `:68-70`) records the `@KafkaHandler` empty-name defect as **still live**. Measured: it derives 0 rows, removed by `derive_endpoints.sql:812` | A6 confirms `:812` is the operating guard. **But `spring-kafka` is saved by an accident of its address vocabulary** — a topic has no `/`, so it declares no `path_separator` — and its three structural twins that DO declare one all fabricate (`A-C1`). Writing this near-miss alone would record the wrong lesson |

**Nine existing tests need only the marker** (four backlog entries retire outright):
`test_supertype_dispatch.py:535`, `test_supertype_derived.py:342` and `:262` (both also need
re-pointing at the shipped `grpc-java.yml`), `test_injected_client.py:195`,
`test_interface_engine.py:314`, `test_schema_operations.py:325`, `:797`, `:1047`, and
`test_derived_resource.py:509` (plus seven siblings that negate distinct conjuncts and already
assert emptiness — `spring-data-rest` is the best-covered *uncovered* catalog by a distance). Six
of the nine were **not mutated** and should get the same treatment before their marker is added:
a test counted as coverage is more dangerous than one that is not.

**Three tests must NOT be marked as they stand**, because they do not assert emptiness:
`test_combinator_engine.py:1403` and `:1657` assert a route **list**;
`test_config_join.py:342` asserts `== ["events"]` and is the near-miss for the highest-ranked
fabrication risk in the whole report; and `test_call_engines.py:3145` asserts `endpoints == []` on
a workspace with **no call-site facts** — the vacuous pass the coverage file exists to prevent.
**It proves loading, not declining, and must never be counted.**

#### What the mutation battery found to be GOOD

Reported because a sweep listing only gaps misprices the suite. E1 (the `single_call` descriptor
discrimination) kills **34 of 51** marked tests; A6, A5, A4, A2, D4b, D5c each kill 1; D2 and D3
each kill 3. **The descriptor work is the model the rest of the suite should be held to**: 34 tests
react to one guard, every one has a paired positive, and the positives are parametrised off the
same table so a new row cannot gain a near-miss without one. A catalog-side mutation confirms the
same for the YAML.

#### The luck audit — what the fixtures are silent about

**A correction to the premise first.** C-1 "survived because the fixture lacked an ordinary
`extends` pair" understates it twice over. (a) The only real `extends …ImplBase` in the tree,
`fixtures/grpc-probe/.../OrderServiceImpl.java`, **is never compiled** — it is referenced only in
docstrings, and the `supertype_derived` suite builds every fact by hand with invented identities.
That engine has **no fixture-level coverage at all**. (b) **There is no golden fixture output.**
The one checked-in golden is built from a hand-written module in
`tests/egress/test_render_assembly.py:306-400` and derives from no fixture; `orders-service`'s
rendered document is substring-asserted and byte-compared **against a second run of itself**,
which is determinism, not content. **No fixture's derived output is snapshotted anywhere**, so a
newly fabricated row fails nothing unless a substring assertion happens to collide with it.

**Shapes absent from every fixture** — each a shape a real JVM service routinely contains, so an
over-broad rule keyed on it fires wrongly against production code and cleanly against the whole
fixture set: a call to `send`/`publish`/`convertAndSend`/`execute`/`newCall`/`get`/`post`/
`exchange`/`receive`/`subscribe` on an **application-owned** receiver; a plain-Java or app-owned
fluent chain (no `StringBuilder`, no `java.util.stream` chain, anywhere); a class implementing
`Function`/`Supplier`/`Consumer` outside Spring Cloud Stream (**the exact shape of `A-C5`**); a
servlet, filter or interceptor of any kind; **a plain abstract base class and a subclass of one**
(`abstract class` appears nowhere in any fixture — the C-1 conjunct itself, and `A-C4`'s); a
`*Grpc`/`*ImplBase` class that is not gRPC; **a plain interface with methods and no client
annotation** (which is how `A-C6` shipped); `@RabbitHandler` anywhere; `@KafkaHandler` outside a
class-level `@KafkaListener`; `@PulsarListener` at any level; the two legacy `SqsListener`
packages; a type-level use of any method-target listener annotation; a home-grown annotation
sharing a framework annotation's simple name; and `@Service`, `@Repository`,
`@SpringBootApplication`, `@ControllerAdvice`.

**What the fixtures cover well**, so the audit is not one-sided: same-name-same-arity overloads on
framework types, deliberately and thoroughly (the fixture-level counterpart of the descriptor
work, and the strongest part of the set); schema files whose types must **not** become endpoints
(the best-covered family — an imported `.proto` with no `service`, a GraphQL type with no root
operation, an unimplemented WSDL operation, Avro records); two package spellings of one
annotation; and a `@Component` with no endpoint-bearing annotation.

---

## 7. Corrections to the auditors

The six sweeps were not infallible. Everything they marked unverified is marked unverified here
too, throughout §3, §5 and §6.

### 7.1 Sweep 3's MAJ-10 is not a finding

Sweep 3 flags capability 9.15's `elements` as read by nothing *"despite the roadmap stating 2O
wires it"*. The roadmap sentence it cites (`:170-179`) states the wiring as **scheduled work** —
it is 2O **Task 13**, and Task 13 has not run; 2O is paused at Task 8 for this sweep. The
mechanism gap is real and correctly described; the implication that a document overstates
shipped state is not. **Not a finding.** It is retained as `B-M10` only so the checkpoint does not
rediscover it, and the two catalogs plus COVERAGE are honest about the gap in place
(`spring-webflux-router.yml:147-155`, `kafka-consumer.yml:53-56`, `COVERAGE.md:1412`) — sweep 3
records this as the good case, and it is. Sweep 2 (#8, `A-Mi1`) and sweep 5 (verified item 20)
independently reach the same reading of the same fact; all three agree.

### 7.2 Sweep 1's engine-style count is wrong

Sweep 1's prose says *"Of 12 engine styles, only 3 have any marked declining test"*. Its own table
in the same section lists **eleven** styles, whose catalog counts sum to 52; and
`resolve/endpoints.py:169` `_ENGINES` holds **eleven** entries (sweep 3, CRIT-adjacent MAJ-9,
independently). D02 documents thirteen styles, of which `protocol_hint` is explicitly not an
engine and `filesystem` has no engine — eleven. **The correct statement is 8 of 11 engine styles
have no marked declining test**, and §6.3 uses that. The substance — which styles are uncovered —
is unaffected.

### 7.3 Sweep 2's negative-claim arithmetic does not close

The header says "44 distinct claims", the closing count line says PROVEN 3 / VERIFIED 30 / FALSE 5
/ UNVERIFIED 6 (44), and the prose says "only two of fifty-three cite their evidence" — over a
table of **54 numbered rows** (1–53 plus 3b). The per-row verdicts show **9** FALSE rows, not 5,
of which two were already corrected in place. The parenthetical explaining the "5" lists four
sites and then names five outcomes, two of which come from rows not in its own list. **Not
reconciled.** §6.1 reproduces the per-row verdicts, which are self-consistent, and flags the
summary counts as unusable. Nothing depends on the total: all six live FALSE sites already have a
Class A row.

### 7.4 `stamp_media.sql` — two sweeps touch it and neither settles it

Sweep 1 (backlog row 33) asserts that `stamp_media.sql` matches on `(protocol, direction)` **only**
— no `catalog_id`, no module scoping — so one module's `spring.kafka.producer.value-serializer`
would stamp every `kafka/outbound` row in the workspace, including rows other catalogs derived. It
marks the row **unverified** and says the inference is from reading. Sweep 2 (#25) records
`spring-kafka-media.yml:24-26`'s own claim — "a stamp lands only where every resolved environment
agrees, and never over a non-NULL column" — as **UNVERIFIED**, because it did not read the SQL.
So one sweep alleges a cross-module over-stamp and the other declines to confirm the catalog's
narrower claim. **Open.** It is not entered as a Class A finding because neither report measured
it; it is the natural first item for the fix pass to settle, and rank 8 in §6.2's probe backlog
already requires opening the same file.

### 7.5 Sweep 4's headline counts are not derivable from its own table

The headline says 21 catalogs "rest on a named committed evidence artifact" and 31 are
"unmeasured". The table's own legend yields 3 G + 13 D + 17 P + 19 N. 3 + 13 = 16, not 21, and
19 ≠ 31; the difference is presumably a split of the 17 `P` rows between "named committed
artifact" and "an inline `javap` read", which the table does not encode. **Not reconciled.**
§6.2 reproduces the per-catalog grades, which are self-consistent, and states the distribution
rather than the headline. The version-scope counts do close: 20 stated, 32 silent.

### 7.6 Sweep 4's F-2 severity carries the auditor's own hedge

Recorded at `A-C7`: sweep 4 graded it Critical and wrote *"If the grading is strictly 'fabricates
a row', it is Major."* The grade in §3 is the auditor's. **This document re-scored no finding.**

### 7.7 COVERAGE:1444-1447 disagrees with a measurement — RESOLVED 2026-09-05

**Settled by the session controller before the round-1 fix pass. Sweep 1's
measurement is correct; `COVERAGE.md:1444-1447` is FALSE, and sweep 4's `A-M8`
mis-states the failure mode.**

The discriminator is `path_separator`, and the guard is
`derive_endpoints.sql:812`:

```sql
WHERE NOT ($path_separator IS NULL AND d.path = '')
```

An empty derived address is dropped **only when the catalog declares no
`path_separator`**. Exactly seven catalogs declare one — `jakarta-websocket`,
`spring-actuator`, `spring-cloud-openfeign`, `spring-http-interface`,
`spring-mvc`, `spring-stomp`, `spring-web` — and `spring-sqs` is not among them,
so its separator is NULL, the guard fires, and an unlisted destination attribute
derives **nothing**. Sweep 1 measured zero rows and was right.

Two consequences for the fix pass:

1. **`A-M8` is a silent under-report, not a fabrication.** Its fix is to read
   the `@AliasFor` pair so the row exists at all — not to stop a wrong row being
   published. `COVERAGE.md:1444-1447` must be corrected in the same commit: it
   tells a reader the row is present-but-empty when the row is absent, which is
   the more misleading of the two.
2. **`A-C1`'s blast radius is seven catalogs, not three.** Every catalog
   declaring `path_separator: "/"` is unguarded against an empty address, and
   sweep 1 named three because three had a reachable bare-annotation path — not
   because the other four are safe.

**And the guard itself is a third instance of the sweep's root pattern.**
Whether an empty address is meaningful is a question about the *protocol* — a
root route `/` is real, an empty AMQP destination is not. `path_separator` is a
*formatting* property: how segments are joined. Keying a validity gate on a
formatting field is the same substitution as matching a method by argument
count, and it is why the guard protects `spring-rabbit` and not its structural
twin `spring-stomp`. The round-1 mechanism should replace it with a gate that
says what it means, not one that is a projection of an unrelated field.

### 7.7a The original disagreement, as recorded before it was settled

Sweep 4's `A-M8` quotes `docs/COVERAGE.md:1444-1447`, which says an unlisted destination attribute
*"derives a **resolved** row with an **empty** path today"*. Sweep 1 measured the sibling case on
the shipped `spring-sqs` catalog and got **0 rows**, dropped by `derive_endpoints.sql:812`. Both
cannot describe the same code. Either the COVERAGE row is stale or the two cases differ in a way
neither sweep isolated. **Open**, and it changes what `A-M8`'s fix has to write.

### 7.8 A sweep-5 miss, and a sweep-3/sweep-5 duplicate

Sweep 5's scope was `src/sextant/**` and the extractor, and it did not find the stale "not yet
shipped" comment at `egress/render/document.py:699-700`, which sweep 3 found incidentally
(recorded here as `A-Mi23`). Conversely sweep 3's MIN-7 is the same finding as sweep 5's F1
(`ports/catalogs.py:46-49`) and sweep 3 says so; they are merged into `A-Mi10` and counted once.
Sweep 5 also notes that it did **not** sweep `tests/`, where the same density of reasoning lives
and where two of its own findings' subject matter (descriptor-sweep fallout in prose) is likely
concentrated — an uncovered scope, not an error.

### 7.9 Editing artifacts and single-source claims

Sweep 1's MAJOR-5 contains a visible mid-sentence self-correction (*"— wait, no: D2 alone kills
the three `overriding service` tests but not this one"*). The finding's mutation results stand;
the prose was not re-read. Sweep 1 also reports several backlog rows as measured "independently"
by a second script, and several others (`spring-restclient`, `google-pubsub-publisher`,
`spring-kafka-media`, the `jakarta-jws-client` SEI fence) as **inferred, not probed** — carried
forward as unverified in §6.3.

### 7.10 What every sweep could not determine

Carried forward so it is not rediscovered: whether `A-C1`'s `@ClientEndpoint` row materialises end
to end (read-verified only); whether `A-C4`'s wrong path column is observed in DuckDB (the join is
unconditional and the coalesce is `''`, but the row was not observed); the framework half of
`A-M13`, `A-M14`, `A-M15` and `A-Mi17`, each needing one live run; `A-C3`'s blast radius through
the renderer; whether `A-M1` fires on any real-world Pub/Sub receiver; whether `A-M10` reaches any
real payload; `A-Mi2`'s protobuf-lite premise (no `protobuf-javalite` jar available);
`A-Mi9`'s SmallRye naming rule; Feign's and Spring-WS's gate predicates; whether `@WebEndpoint` is
meta-annotated with `@Endpoint`; the `CoRouterFunctionDsl` Kotlin overload set; whether
`Resolution.PARTIAL` can reach a fact from the shipped jar; whether `CallArgument` kind `array`
makes `has_value()` return `True` for a value nothing can read (**a candidate defect, worth one
test — not a finding**); whether D02 §4's "every catalog ships a conformance fixture" holds (28 of
52 catalog ids appear in no test directory under their own name, which is **evidence of a gap, not
proof**); `A-M16`'s single-module case; and whether F1's 19 catalogs omitting a shape-rule block
cost any live row.

---

## 8. Facts verified directly by the session controller

These four were checked by the session controller against the tree, not taken from an auditor's
report. They are quoted here as independently confirmed.

- **`DEPENDENCY_GATED = frozenset({"derived_resource"})`** at
  `src/sextant/application/resolve/dependencies.py:46`. **52 catalogs declare `detect.coordinates`;
  exactly one style is gated on them, so 51 catalogs run regardless of whether their framework is
  on the build.** The loader nonetheless validates the coordinate shape for all 52
  (`ingress/catalogs/yaml_source.py:96-107`) — a validator honouring a value nothing downstream
  consumes, for 51 of 52 files. This is the §5.3 shape the register's entry #1 names, still live,
  and it is `A-C5`'s fourth missing conjunct.

- **`schema.sql` contains 6 `CREATE TABLE` statements** — `raw_facts` (`:1`), `endpoints` (`:12`),
  `shapes` (`:71`), `shape_fields` (`:77`), `resolved_config` (`:108`), `open_questions` (`:139`).
  **D01 documents twelve base tables plus `edges`, `dispatch`, `trace_summary`, `findings` and a
  full-text index.** This confirms the roadmap's measurement row and `B-C5`.

- **`spring-webmvc 6.2.15`'s `RequestMappingHandlerMapping.isHandler` is a single
  `AnnotatedElementUtils.hasAnnotation(beanType, Controller.class)`** — there is **no
  `@RequestMapping` disjunct**. **GUIDELINES §8.1 rule 1's own worked example asserts otherwise
  and is wrong**: it states that Spring's server-side handler test *"accepts `@Controller` **or**
  a type-level `@RequestMapping`"*. That was true through Spring 5.x. The sentence teaching this
  project not to trust remembered framework rules is itself a remembered framework rule that has
  since been falsified — exactly the §8.1 failure it describes, one level up. Correcting it is
  part of `A-C7`'s fix and must not be deferred with the rest of that finding: the guideline is
  read far more often than the catalog.

- **The ingest path and `stages/analyze.py` both write `redaction_set_hash=NO_REDACTION_HASH`** —
  `ingress/read/__init__.py:24`, `:62` and `application/stages/analyze.py:70`, `:428`. The
  workspace holds verbatim values. This is `A-C8`'s proof.

---

## 9. Status and ownership

**Every finding in this document started `OPEN`** and §10 is the live status table.
Nothing was fixed when this file landed; the sweeps were
read-only and this commit adds one file.

**The fix pass is one writer at a time (§13.9).** Agents and the controller share one working tree
and one git index, and Phase 2O has already paid three times for ignoring that: an implementer's
unformatted in-flight file blocked an unrelated docs commit, a bare `git commit` swept another
agent's staged files into it, and a read-only reviewer's probe files blocked the controller the
same way. Every agent that is not the writer is read-only, and everything it needs to create goes
to the session scratchpad. Explicit pathspecs (`git commit -- <paths>`) are required and are not
sufficient — the tree is shared whether or not the commit is scoped.

**The mechanism precedes the instance patches.** §4's proposed rule — *no derivation may publish a
defaulted value at `resolved`/`compiler`* — is a §13.8 step-3 outcome: an existing principle broken
repeatedly, where the fix is a mechanism and not another correction. It must be settled with the
human partner and landed **before** `A-C1`, `A-C2` and `A-C4` are patched individually, because
patching them first is what prevents the cause from being found — §13.8 says so in as many words.
Per §8.3 the mechanism ships with its retroactive audit list; §3.1's table is that list, and §4.4
says which rows it closes and which it does not.

**Class B waits for the post-2O documentation-debt checkpoint.** No Class B row is fixed in the
sweep fix pass. The three that could not wait are already Class A (`A-C8`, `A-C9`, `A-M16`). Per
GUIDELINES §2 the debt is **addressed, not dropped**, and retire-and-mark is the expected outcome
for most of it — taken deliberately, recorded in `docs/documented-not-implemented.md`, and done.
That register is itself `B-M11` and must be repaired first, or the retirements land in a file that
is already missing two of the six instances RUNBOOK counts and skips two entry numbers.

**Order of work.**

1. Settle the §4 mechanism with the human partner; land it with its ratchet.
2. Class A Criticals, then Majors, in §3.1's order; each with the §10 near-miss and paired positive
   its finding names.
3. The three §7 open disagreements (`A-M8`/COVERAGE:1445, `stamp_media.sql`, sweep 2's counts) —
   measure, then write.
4. Class A Minors, grouped by file so the stale-rationale set lands in few commits.
5. §6.3's marker work — nine markers and four backlog retirements are the cheapest coverage in the
   whole sweep, and `test_supertype_dispatch.py:535` is the single highest-value edit.
6. 2O resumes at Task 8.
7. The documentation-debt checkpoint takes Class B, after 2O and before 2P.

**Citation.** Later commits cite these ids. They are stable: `A-C1`–`A-C9`, `A-M1`–`A-M16`,
`A-Mi1`–`A-Mi23`, `B-C1`–`B-C7`, `B-M1`–`B-M18`, `B-Mi1`–`B-Mi9`. Where a finding merges two
sweeps, both are credited in its row.

---

## 10. Fix-pass status — round 1a (mechanisms + Class A Criticals)

Round 1a's scope is §4's three mechanisms and `A-C1`–`A-C9`. The sixteen Majors
and every Minor are a later dispatch and are untouched here; they stay `OPEN`
below so this table is the whole record rather than half of one.

`FIXED (<sha>)` means the behaviour changed and a paired near-miss/positive
proves it. `OPEN — <reason>` is a deliberate decision, not a gap that was
forgotten.

### Mechanisms

| mechanism | status |
|---|---|
| M1 — no derivation publishes a defaulted value at `resolved`/`compiler` | FIXED (aff29fc) — shipped as the §8.3 audit list, `tests/architecture/test_defaulted_identity_values.py`. See §10.1 for where this document's own §4.4 prediction is disputed. |
| M2 — the dependency gate covers more than one style | FIXED (2cbaa4b) — `config_join` admitted; the per-style reasoning is recorded in `resolve/dependencies.py` |
| M3 — the empty-address guard says what it means | FIXED (ed4e18c) — replaced by an addresses-nothing gate; closes `A-C1`'s fabrication half across all seven separator-declaring catalogs |

### Class A Criticals

| id | status |
|---|---|
| `A-C1` | FIXED (85af4c7) — the empty-address half by M3, the type gates and the direction inversion here; the `@OnOpen`-only under-report and the RSocket hazard are stated in COVERAGE §5.5, not closed |
| `A-C2` | FIXED (330835b) |
| `A-C3` | OPEN |
| `A-C4` | FIXED (584676b) — and `A-M11` with it, as §3.3 predicted |
| `A-C5` | FIXED (2cbaa4b) — the fabrication is closed by M2; the residual (`@Bean` conjunct, unmeasured) is stated in COVERAGE §5.8 |
| `A-C6` | FIXED (85af4c7) |
| `A-C7` | FIXED (329483c) — the composed-stereotype divergence; the superclass and interface divergences left OPEN with a stated reason, see §10.1 |
| `A-C8` | OPEN |
| `A-C9` | OPEN |

### 10.1 Where round 1a disputes this document

Recorded here rather than by editing the analysis above, so the disagreement is
visible rather than silently resolved.

- **§4.4 claims M1 closes `A-C4`. It does not, and implementing it as written
  would be a large under-report.** The reasoning there is that an absent prefix
  is "a defaulted `''` in an identity column", so the row should be withheld.
  But an absent type-level prefix is the ORDINARY case for the highest-volume
  catalogs in the tree: `@RestController class Foo { @GetMapping("/orders") }`
  carries no class-level `@RequestMapping`, and Spring serves `/orders`.
  Withholding every prefix-less controller row would delete most of the shipped
  HTTP surface. `A-C4`'s defect is not a default standing in for evidence — it
  is an inheritance edge the walk never reads, so the evidence exists and was
  not looked at. It needs its own fix and gets one.
- **§4.4 claims M1 closes `A-C1`. M3 does.** The empty prefix is not a value
  standing in for a missing one; the whole composed address is empty, which is
  the "where the whole address is defaulted, the row does not ship" clause —
  and that clause is a statement about the ADDRESS, which is exactly what M3
  makes enforceable. M1's per-value form has nothing to attach to.
- **`A-C7`'s fix is the composition half only, and the hierarchy half is
  deliberately not taken.** §3.2 proposes widening the composition pre-pass AND
  walking `supertypes`/`implementations` for the type gate. The first is
  measured and safe: `AnnotatedElementUtils.hasAnnotation` is meta-annotation
  aware, and a class wearing a composed stereotype is also a component-scan
  candidate, because the scan's default include filter considers
  meta-annotations. The second is not. `isHandler` answers true for a subclass
  of an `@Controller` base — the sweep measured that — but a class is a handler
  only if it is a handler-shaped BEAN, `@Component` is not `@Inherited`, and
  whether the component scan admits such a subclass at all is exactly what §3.2
  records as **Not settled**. Deriving on the strength of `isHandler` alone
  would add rows under conditions nobody checked, which is §8.1 rule 4. Both
  divergences are stated in COVERAGE §5.1 with the probe that would close them.

- **`A-C2`'s cause is an unmodelled framework method, not a defaulted value.**
  The root's `http_method: GET` is a true statement about a bare
  `Request.Builder`; what made it wrong was that the call which overrides it was
  not declared. M1's enforceable form therefore admits the seed and pins its
  CONDITION — every verb-setting method declared — rather than banning the seed.
