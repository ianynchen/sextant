# CP-22 — MicroProfile REST Client: `@RegisterRestClient`'s attributes, whether `peer` and `prefix` share an annotation row, and Quarkus's base-URI resolution order

**Question.** Group B/C's outbound (client) catalogs mirror the inbound JAX-RS
catalogs on the same words. Three facts anchor that: `@RegisterRestClient`'s
own attribute set and defaults (row 1); whether `derive_endpoints.sql`'s
`prefixes` CTE reads `peer` off the SAME annotation row as `prefix` — and,
given row 1's finding that `@RegisterRestClient` carries no prefix attribute
at all, whether MP REST Client's `prefix` (`@Path`) and `peer`
(`@RegisterRestClient`) land on two different annotations, meaning
`peer_from` alone is not sufficient and a `peer_annotation`-shaped key is
needed (row 2, spec §3f); and, for the Quarkus implementation specifically,
what order `baseUri` (from the annotation), `configKey` (mapped to
`/mp-rest/url`-style properties) and Quarkus's own
`quarkus.rest-client.<key>.url` config resolve in — the boundary statement a
catalog's `measured:` block needs (row 3).

**What this probe does not settle.** Nothing was deployed; no HTTP request was
dispatched, no CDI container was booted. Row 3 opens exactly the class its
base-URI resolution lives in
(`RestClientCDIDelegateBuilder.configureBaseUrl`); it does not trace how the
STANDARD MicroProfile `<fqn>/mp-rest/url` legacy property name gets mapped
into the `RestClientsConfig$RestClientConfig` object this method reads from —
that mapping lives elsewhere in Quarkus's config subsystem and is NOT
measured here. The claim below is scoped to what `configureBaseUrl` itself
does once it has that config object in hand.

**Version scope (§5.4).** `org.eclipse.microprofile.rest.client:
microprofile-rest-client-api` **4.0 and 3.0.1** (row 1, spanning the MP 6→7
platform boundary); `derive_endpoints.sql` as it exists on this branch (row
2, not version-scoped — it is this repository's own SQL); `io.quarkus:
quarkus-rest-client` **3.39.4** (row 3, the same generation as CP-19's
sources). Every verdict below is bounded by those three.

## Environment

`MP40=~/.m2/repository/org/eclipse/microprofile/rest/client/microprofile-rest-client-api/4.0/microprofile-rest-client-api-4.0.jar`
(already resolved in `~/.m2`); `MP301=<scratchpad>/mp-rest-client-api-3.0.1.jar`
(fetched from `https://repo1.maven.org/maven2/…/3.0.1/…` — not previously
staged); `<scratchpad>/quarkus-rest-client-3.39.4.jar` (fetched from
`https://repo1.maven.org/maven2/io/quarkus/quarkus-rest-client/3.39.4/…` — not
previously staged; this jar's classes do NOT include a
`RestClientBase`/`RestClientBuilder` class under those exact names at 3.39.4 —
the resolution logic actually lives in
`io.quarkus.rest.client.reactive.runtime.RestClientCDIDelegateBuilder`, found
by reading the jar's own class listing, see row 3).

## Rows

### 1 — `@RegisterRestClient`: `@Target`, `@Retention`, `baseUri()`/`configKey()` and their defaults

**Command.**
```
javap -v -cp $MP40  org.eclipse.microprofile.rest.client.inject.RegisterRestClient | grep -E 'public abstract|Retention|Target|AnnotationDefault' -A2
javap -v -cp $MP301 org.eclipse.microprofile.rest.client.inject.RegisterRestClient | grep -E 'public abstract|Retention|Target|AnnotationDefault' -A2
```

**Output (identical at both versions).**
```
public abstract java.lang.String baseUri();
    AnnotationDefault:
      default_value: s#10 (or s#7 at 3.0.1)
        ""
public abstract java.lang.String configKey();
    AnnotationDefault:
      default_value: s#10 (or s#7 at 3.0.1)
        ""
java.lang.annotation.Retention(value=RetentionPolicy.RUNTIME)
java.lang.annotation.Target(value=[ElementType.TYPE])
```

**Claim.** `@RegisterRestClient` is `@Target(TYPE)`-only, `@Retention(RUNTIME)`,
and declares exactly two `String` attributes, `baseUri()` and `configKey()`,
both defaulting to the empty string — unchanged between 3.0.1 and 4.0.
(`measured 2026-09-18`, matching the brief's pre-stated expectation exactly.)

### 2 — is `peer` read off the prefix annotation's own row only?

**Command.**
```
grep -n "^prefixes AS" src/sextant/storage/duckdb/derive_endpoints.sql
sed -n '935,972p' src/sextant/storage/duckdb/derive_endpoints.sql
```

**Output (the `prefixes` CTE, relevant lines).**
```
935  prefixes AS (
936      SELECT
937          pg.catalog_id AS catalog_id,
938          a.target AS type_symbol,
939          coalesce(list_extract(list_filter(list_transform(
940              cp.prefix_from,
941              n -> coalesce(a.args -> n ->> 0, a.args ->> n)
942          ), v -> v IS NOT NULL), 1), '') AS prefix,
943          list_extract(list_filter(list_transform(
944              cp.peer_from,
945              n -> coalesce(a.args -> n ->> 0, a.args ->> n)
946          ), v -> v IS NOT NULL), 1) AS peer,
... (lines 947–967 omitted: the `consumes_list`/`produces_list` extraction
    and its comment, irrelevant to the prefix/peer question this row asks)
968      FROM annotations_effective a
969      JOIN prefix_gates pg ON pg.fqn = a.annotation
970           AND (a.catalog_id IS NULL OR a.catalog_id = pg.catalog_id)
971      JOIN catalog_params cp ON cp.catalog_id = pg.catalog_id
972  ),
```

**Claim (settling row 2).** The `prefixes` CTE selects from a SINGLE row of
`annotations_effective a`, filtered to rows whose `a.annotation` matches
`prefix_gates.fqn` (line 969 — the prefix-gate annotation, e.g.
`@RegisterRestClient`). Both `prefix` (939–942, from `cp.prefix_from`) and
`peer` (943–946, from `cp.peer_from`) are extracted from `a.args` on that SAME
joined row — there is no second join to any other annotation, no
`peer_gates` table, nothing that could read `peer` off a DIFFERENT annotation
than the one that supplied `prefix`. **The measurement confirms: `peer` is
read exclusively off the prefix gate annotation's own row.**

That measurement, applied to MicroProfile REST Client, is where the shape
breaks rather than holds. Row 1 already showed `@RegisterRestClient` declares
exactly two attributes, `baseUri()` and `configKey()` — **no prefix attribute
of any kind.** The prefix on an MP REST Client interface is not
`@RegisterRestClient` at all; it is the plain JAX-RS `@Path` (CP-18 row 2),
a DIFFERENT annotation entirely. So for this framework, `prefix` and `peer`
do NOT live on the same annotation row: `@Path` supplies the prefix,
`@RegisterRestClient` supplies the peer (`configKey`, or `baseUri` as a
fallback identifier). Under the current SQL, `prefixes` joins on a single
`prefix_gates.fqn` — if a catalog names `@Path` as `prefix_gates` (which it
must, since that is where the actual path string lives), `cp.peer_from`
naming `[configKey, baseUri]` would be evaluated against `@Path`'s own
`a.args`, which carries neither attribute, and `peer` would derive NULL for
every MP REST Client interface. **Group B/C's Word 3f therefore DOES need a
`peer_annotation` key (or an equivalent second-annotation lookup) for this
framework** — `peer_from` alone, naming an attribute on the SAME row as
`prefix_from`, is insufficient whenever prefix and peer are declared on two
different annotations, which is exactly MP REST Client's shape. The design
spec's §3f first bullet is answered the other way from what this probe
originally concluded: the plan's Task 10b Step 2 already anticipates a
`peer_annotation`-shaped key, and this measurement is the evidence that Task
10b needs it, not evidence that it can be skipped.

### 3 — Quarkus's base-URI resolution: annotation `baseUri` vs. `configKey`-mapped config vs. `quarkus.rest-client.<key>.url`

**Command.**
```
unzip -l quarkus-rest-client-3.39.4.jar | grep -i 'RestClientBase\|RestClientBuilder'
javap -c -p -cp quarkus-rest-client-3.39.4.jar io.quarkus.rest.client.reactive.runtime.RestClientCDIDelegateBuilder
```
(the `unzip -l` listing carries no `RestClientBase` class and no
`RestClientBuilder` class under those literal names at 3.39.4; the classes
present are `QuarkusRestClientBuilder`, `QuarkusRestClientBuilderImpl`,
`RestClientBuilderImpl`, `RestClientCDIDelegateBuilder` — the last is where
`configureBaseUrl` lives.)

**Output — `RestClientCDIDelegateBuilder.configureBaseUrl` (disassembled,
paraphrased for control flow, with the exact strings quoted verbatim).**
```
private void configureBaseUrl(QuarkusRestClientBuilder builder) {
    Optional<String> reload = oneOf(restClientConfig.uriReload(), restClientConfig.urlReload());
    if ((baseUriFromAnnotation == null || baseUriFromAnnotation.isEmpty())
            && reload.isEmpty()) {
        String key = (configKey != null) ? configKey : (jaxrsInterface.getName() + /* fqn */);
        throw new IllegalArgumentException(
            "Unable to determine the proper baseUrl/baseUri. Consider registering using "
          + "@RegisterRestClient(baseUri=\"someuri\"), @RegisterRestClient(configKey=\"orkey\"), "
          + "or by adding '%s' or '%s' to your Quarkus configuration"
              .formatted(
                  "quarkus.rest-client.%s.url".formatted(key),
                  "quarkus.rest-client.%s.uri".formatted(key)));
    }
    String uri = reload.orElse(baseUriFromAnnotation);
    builder.baseUri(new URI(uri));
}
```
(bytecode: offsets 0–31 build `reload` from `oneOf(uriReload(), urlReload())`;
32–53 test `baseUriFromAnnotation` null-or-empty AND `reload.isEmpty()`; 56–77
pick `configKey` else `jaxrsInterface.getName()` as the error message's `%s`;
83–134 throw with both `quarkus.rest-client.%s.url` and
`quarkus.rest-client.%s.uri` quoted; 135–162, the path actually taken when
either source is present, is `reload.orElse(baseUriFromAnnotation)` — i.e.
`reload` WINS when present, `baseUriFromAnnotation` is used only when
`reload` is empty.)

**Claim.** In `RestClientCDIDelegateBuilder`, when BOTH a Quarkus
`quarkus.rest-client.<key>.url`/`.uri` config reload value AND the
annotation's `baseUri` are present, **the Quarkus config value wins** —
`reload.orElse(baseUriFromAnnotation)` tries the config-sourced `Optional`
first and only falls back to the annotation's `baseUri` when that `Optional`
is empty. `<key>` is `configKey` when the annotation set one, else the JAX-RS
interface's fully-qualified class name. Only when NEITHER `baseUri` nor a
Quarkus config value is present does the client fail to build, at which point
the exception names both `quarkus.rest-client.<key>.url` and
`quarkus.rest-client.<key>.uri` as the properties to add. **This probe does
NOT trace how the standard MicroProfile legacy property
`<fqn>/mp-rest/url` gets bound into `restClientConfig.uriReload()`/
`urlReload()`** — that mapping is outside `RestClientCDIDelegateBuilder` and
is not measured here; the boundary statement for `quarkus-rest.yml`'s
`measured:` block should say so rather than assume `/mp-rest/url` and
`quarkus.rest-client.<key>.url` are read in a stated priority against each
other, since only the LATTER's precedence over the annotation was actually
observed.

## Verdict

1. Row 1: `@RegisterRestClient` is confirmed `@Target(TYPE)`, two `String`
   attributes (`baseUri`, `configKey`), both defaulting to `""`, unchanged
   3.0.1 → 4.0.
2. Row 2: the SQL measurement holds — `derive_endpoints.sql`'s `prefixes` CTE
   joins `prefix_gates` once and reads both `prefix` and `peer` from that
   SAME row's `a.args`; there is no mechanism to read `peer` off a second
   annotation. Applied to MP REST Client, this is why a `peer_annotation` key
   IS needed: row 1 shows `@RegisterRestClient` has no prefix attribute, so
   the prefix comes from `@Path` instead — prefix and peer sit on two
   different annotations for this framework, and `peer_from` alone (naming
   an attribute on whichever single annotation `prefix_gates` names) cannot
   reach `@RegisterRestClient`'s `configKey`/`baseUri` when `prefix_gates`
   names `@Path`. Task 10b Step 2, which already anticipates this key, is
   confirmed necessary by this measurement rather than made optional by it.
3. Row 3: Quarkus's own base-URI resolution (`RestClientCDIDelegateBuilder.
   configureBaseUrl`) prefers `quarkus.rest-client.<key>.url`/`.uri` config
   over the annotation's `baseUri` when both are present, falling back to the
   annotation only when config is absent, and failing loudly (naming both
   config property names) when neither exists. The MicroProfile legacy
   `/mp-rest/url` property's own binding path into this same config object is
   NOT traced by this probe and must not be assumed to share Quarkus config's
   precedence without a further reading.

`measured: 2026-09-18` for rows 1 and 2. Row 3 is measured but scoped as
stated above — its boundary is explicit rather than assumed.
