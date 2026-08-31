# Phase 2F — Configuration resolution

Configuration is where three stuck things unlock at once: outbound base addresses become
resolvable peers, Spring Cloud Stream and spring-cloud-aws bindings become endpoints, and
the environment expressions D06 has always reserved a manifest field for become real. The
phase ships the `ArtifactReader` port's first implementations, M04's pass 2 exactly as
that document has specified it since Phase 1, the `resolved_config` table D01 already
names, the eighth engine style (`config_join`), and — a deliberate, scoped end to the
zero-extractor-changes streak — two additive D00 amendments so imperatively-fed base
addresses join too.

User rulings binding this spec: `bootstrap.yml`/`bootstrap-{profile}.*` are in the source
set; every join is RECORDED with its full trail but LLM verification of doubtful joins
waits for 2K (D02 §2d's second authority layer — the seat is deferred, never the
evidence); Spring Cloud Stream ships tiers 1+2 only (function beans + `definition`
selection; composition pipes degrade visibly, the legacy annotation model is out —
deprecated 3.x, removed 4.x); serializer-configured media is IN (the 2E §4 evidence-kind-
(d) promise); BOTH halves of base-address resolution ship, including the extractor
amendments; readers are format-keyed with framework semantics in catalog data (the
cross-language ruling — Quarkus's `%dev.` prefixes, node-config's file-per-env, viper
layouts become future YAML against the same readers and the same pass).

## 1. Ingestion — format-keyed readers, neutral facts

`ArtifactReader` (M03's dormant second port) gains a protocol in `application/ports`
mirroring `Scanner`'s shape — `accepts(file_kind)`, `read(files) -> facts` — and two
implementations in a new `src/sextant/ingress/read/`: **properties** and **YAML**.
Selection is by file kind; readers never compete (M03). JSON/TOML/.env are future
drop-ins behind the same port, unbuilt until a consumer exists.

The detector (M02) contributes the module's **resource roots** (`src/main/resources` for
Maven). The reader layer reads every parseable config-format file under them. Ingress
stays model-blind: no layering, no profiles, no placeholder interpretation — which files
matter and in what order is the resolution side's question, answered from catalog data.
Reading everything parseable is what lets a viper or node-config layout arrive later
without re-teaching ingress anything.

**The facts.** One `document` fact per config file — its language column carries the
FORMAT (`yaml`, `properties`; formats are not language names, the confinement test stays
honest) — and one `config_entry` fact per key:

- `key_raw` — exactly as written;
- `key_path` — normalized dot-joined segments; YAML lists normalize to indexed segments
  (`foo[0]`, Spring's own canonical form and a neutral one);
- `value` — verbatim, always a string, never coerced (a value is a claim to resolve);
- the source file, the YAML document index (multi-doc activation needs it), and
  declaration-order `seq` (NFR-1).

**Where the facts land.** Readers return facts; the analyze stage writes them through
the existing domain factfile writer into the same JSONL fact tree the scanner feeds, one
document per config file — `load_facts`'s bulk read picks them up with zero changes, and
ingress keeps its write-only contract (readers never touch the Workspace port).

Unparseable files record their document `partial` (the existing degradation vocabulary).
Config-as-code — Django `settings.py`, Nest config factories — is out of any file
reader's reach by construction; its gap key lands in §5.

## 2. The config model, and resolution as M04's pass 2

**The model is catalog data** — a new top-level catalog block, `config_model`, one per
framework family. Spring's ships in 2F:

```yaml
config_model:
  sources:                      # precedence order, lowest first
    - { pattern: "bootstrap{-profile}.properties" }
    - { pattern: "bootstrap{-profile}.yml" }
    - { pattern: "application{-profile}.properties" }
    - { pattern: "application{-profile}.yml" }
  profiles:
    from_filename: "{-profile}"
    from_document_key: spring.config.activate.on-profile
    default_profile: default
  placeholders: { open: "${", close: "}", default_separator: ":" }
  key_matching: relaxed          # relaxed | exact
```

Profile spelling is a closed three-mechanism vocabulary — `from_filename`,
`from_document_key`, and `from_key_prefix` (reserved for Quarkus's `%dev.`, documented
now, unimplemented until a Quarkus catalog exists). The filename marker generalizes: a
`{profile}` (or `{-profile}`) placeholder may sit ANYWHERE in a source pattern —
`application{-profile}.yml` for Spring, `{profile}.json` for a node-config layout whose
whole filename is the profile — with the empty match naming the base file. No regex-in-YAML anywhere; the
placeholder grammar is delimiters plus a default separator, which covers every surveyed
ecosystem.

**The pass** (M04 pass 2, a generic interpreter over one declared model): enumerate the
profiles present (filenames + document keys); per profile, layer matching sources in
declared order (profile variant over base, later source over earlier), resolve
placeholders recursively with `:default` support and a cycle guard, and write
`resolved_config(key, value, source, environment)` — one row per key per environment,
`source` naming the winning file. The `default` profile always resolves; every
discovered profile resolves beside it.

**Unresolved is an answer, with a reason and an environment**: `missing_key`,
`environment` (the value comes from an env var or launch flag — universal across
ecosystems), `remote_source` (config-server/import URLs), `placeholder_cycle`.
"Unresolved for `prod`, resolved for `dev`" is expressible and meaningful.

**Inherited unchanged:** endpoints keep expressions; `resolved_config` carries values;
nothing rewrites an endpoint row per environment.

## 3. The `config_join` engine — the eighth style

Registered like the other seven; sequenced after pass 2 (it consumes `resolved_config`)
and after the call-site styles within the engine loop (its stamps enrich rows other
engines minted). `requires: [resolved_config]` — the first PIPELINE-declared capability
(every prior one is scanner-declared): the pipeline adds it once pass 2 has run, so a
config-less run skips these catalogs visibly, never silently. D02 §1's capability
paragraph gains one sentence naming the two provenance kinds, so 2J's reviewers read
this as design, not drift.

**Job 1 — binding-derived endpoints** (D02 §2d's `address_from_config`, implemented):

```yaml
matches:
  address_from_config:
    key: "spring.cloud.stream.bindings.{binding}.destination"
    binding:
      from: bean_name
      selected_by: spring.cloud.function.definition
      suffix:
        - { when: { implements: java.util.function.Consumer }, then: "-in-0", direction: inbound }
        - { when: { implements: java.util.function.Supplier }, then: "-out-0", direction: outbound }
        # A Function is both halves at once: its one entry derives TWO rows,
        # `-in-0` inbound and `-out-0` outbound, each through the same key template.
        - { when: { implements: java.util.function.Function }, then: ["-in-0", "-out-0"] }
```

A candidate bean is a method whose RETURN type implements one of the declared
interfaces (the `implemented_interfaces`/supertype facts the interface engine already
reads, checked on the returned type), and its bean name is the method's own name —
Spring's default, stated here so the plan does not re-derive it. The engine applies
selection (`definition` absent → every candidate binds,
Spring's default; a `definition` entry containing `|` derives ONE unresolved row naming
the expression verbatim — the composition degrade, never silence, never a guess), builds
each key, and looks it up in `resolved_config`. Row shape: protocol read from the
binder configuration (`...bindings.{binding}.binder` / the default binder) where
declared, else the catalog's declared protocol; destination keeps its expression form
when the config value itself carries `${...}`; `handler` is the bean's real
module-prefixed method symbol; a missing key derives the row with `path` NULL,
`resolution: unresolved`, and the coverage report names the key (D02 §2d verbatim).
Payload shapes root from the functional interface's type argument — whether the facts
carry that parameter-position generic is checkpoint item (1); if they do not, shapes
stay honestly NULL under the existing named gap.

**Job 2 — serializer media stamping** (`media_from_config`):

```yaml
media_from_config:
  rules:
    - { key: spring.kafka.producer.value-serializer,   fills: produces, on: { protocol: kafka, direction: outbound } }
    - { key: spring.kafka.consumer.value-deserializer, fills: consumes, on: { protocol: kafka, direction: inbound } }
  values:
    org.springframework.kafka.support.serializer.JsonSerializer: application/json
    org.apache.kafka.common.serialization.StringSerializer: text/plain
    org.apache.kafka.common.serialization.ByteArraySerializer: application/octet-stream
```

Stamps module-level defaults onto matching messaging rows ONLY where every resolved
environment agrees; a per-environment split leaves NULL with the degrade recorded (media
columns are single-valued). Stamps never overwrite a non-NULL column (first-writer
discipline). An unknown serializer class stamps nothing — the class name is in
`resolved_config` regardless, which is what 2G's format inference reads.

**Job 3 — peer resolution is a join, not a write**: a named query joining outbound rows'
`${...}`-bearing `peer`/`path` expressions against `resolved_config` per environment.
D06 bundles it; L links on it; endpoint rows are untouched.

## 4. Both halves of base addresses — the scoped extractor amendments

Two additive D00 amendments, both bumping the extractor version (D05 invalidation; the
version-coupling build note applies). **Both are written into D00 the way `lambda` and
`<init>` were** — a neutral cross-language contract definition first ("an argument that
reads a declared field, carrying that field's symbol"; "a constructor assigns parameter
N directly to field F"), with the JVM instructions below as ONE extractor's mapping into
it: a Python attribute read or a Go struct-field read normalizes into the same kinds.

1. **A `field` argument kind.** A GETFIELD/GETSTATIC that is not the enum-constant shape
   becomes `{kind: field, symbol: <the field's bare descriptor>}` instead of
   `unresolved`. Strictly additive: an engine that does not consult `field` treats it
   exactly as it treated `unresolved` — checkpoint item (2) VERIFIES this against every
   existing engine rather than assuming it.
2. **A `field_write` fact**, constructors only, direct traces only:
   `{kind: field_write, field: <symbol>, from_parameter: N}` for a PUTFIELD whose value
   traces straight to parameter N. A computed assignment emits nothing and the join
   degrades honestly. Setter injection is deliberately out — one COVERAGE sentence.

**The join is a ladder** beside the existing literal-first ladders in
`shapes/arguments.py`, shared by `single_call` and `fluent`, tried in order for a
`field`-kind argument in a URL/channel position:

1. the field's own `@Value("${key}")` annotation → the expression → `resolved_config`;
2. `field_write` from parameter N of `<init>` + `@Value` on that constructor parameter;
3. the enclosing class's `@ConfigurationProperties(prefix)` → `prefix` + the
   relaxed-bound field name (§2's `key_matching` strategy, reused);
4. nothing matches → today's answer, unchanged: `unresolved`.

The resolved EXPRESSION enters the row (CP-2's peer/path split applies to it as if
literal); values stay in `resolved_config`. Scope fence: the `field` kind is consulted
only where an argument ladder reads it — no shape or nullability behavior changes from
field-kind arguments, and the frozen pins prove it.

**Gap rotation:** `client_base_addresses_not_resolved` retires;
`computed_base_addresses_not_traced` arrives (concatenation, setter injection,
method-returned bases) so the boundary stays named instead of vanishing.

## 5. Fixtures, testing, docs, close-out

**Fixture.** `src/main/resources/`: `application.yml` (a topic placeholder an existing
listener already carries, Feign's `billing.url`, Stream bindings + `definition`,
serializer config), `application-prod.yml` (one override + one key resolved in `default`
but missing in `prod`), `bootstrap.yml` (lowest-precedence layering pin), one multi-doc
`on-profile` section. Code: a `Consumer<OrderEvent>` bean, a `Supplier`, one unselected
bean (the `definition` filter pin), one piped `definition` entry (composition degrade
pin); three half-2 clients — `@Value`-on-field, constructor-injected,
`@ConfigurationProperties` — each feeding a builder base URL; one computed-base case for
the honest miss.

**Testing.** Reader unit tests (both formats, multi-doc, list normalization,
unparseable → partial); resolution-pass unit tests over hand-built entries (layering
order, profile enumeration, recursive placeholders with defaults and a cycle, all four
unresolved reasons); `config_join` unit tests through invented catalogs (binding
derivation across the three interface shapes, selection, the missing-key row, media
agreement and per-env split, protocol-from-binder); ladder unit tests, all four rungs;
frozen exact sets extended once from live runs; the determinism double-run covering
`resolved_config` and the new facts by construction; loader-iterating sweeps picking up
the new catalogs automatically.

**Docs.** D00: the `field` kind, the `field_write` fact, `config_entry` (each with its
cross-language contract sentence, §4's rule); D01: `resolved_config` real, the peer join
documented; D02: `config_model`, `address_from_config` as-implemented,
`media_from_config`, the eighth style's section, the capability-provenance sentence in
§1; D06: `environments` live; M02 resource roots; M03 readers real; M04 pass 2 real.
**Renderer (M07):** the module document's coverage section lists the environments
resolved and NAMES every unresolved config key with its reason and environment — the
missing-`prod`-key case must be readable on the page, not only in the table.
Per-environment peer tables are deliberately NOT rendered at module level (one
sentence records it): resolved peers are L's system-document material; the module page
stays environment-neutral like its endpoint rows.
COVERAGE: Stream/aws rows flip with their boundaries (config-as-code, setter injection,
computed bases, per-env serializer splits, remote sources). Gap keys: retire
`client_base_addresses_not_resolved`; add `computed_base_addresses_not_traced` and
`config_as_code_not_read`. Roadmap 2F → delivered.

## 6. Checkpoint — frozen from reality after the fixture and extractor tasks

(1) whether `Consumer<Order>`'s type argument survives into the bean method's facts —
binding-row shapes hinge on it; (2) the emitted shapes of `field` and `field_write` on
the three real fixture clients, AND that every existing engine treats the unknown kind
as unresolved (the additive-degrade claim, verified not assumed); (3) `@Value` and
`@ConfigurationProperties` annotation fact shapes on fields and constructor parameters;
(4) real multi-doc and profile-variant files through the readers; (5) the exact
expected-row delta frozen for the pin tasks.

## 7. Review discipline

The final whole-branch review receives the seam list: the readers × the resolution pass
(facts neutral, model catalog-side only); the pass × `config_join` (`resolved_config` is
the whole interface); `config_join` × the existing engines (stamps never overwrite, rows
keep expressions); the field ladder × CP-2 and the existing literal-first ladders; the
extractor amendments × every existing engine's unknown-kind behavior; the new facts and
tables × the D06 bundle and the determinism tests.
