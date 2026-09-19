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
catalog's `measured:` block needs (row 3). Row 4, added after the final
review of Groups B and C: which Quarkus CLIENT artifact names exist on Maven
Central across the 3.9.0 rename, so `microprofile-rest-client.yml`'s
`detect.coordinates` can list the pre-3.9 reactive names and the
RESTEasy-classic names without naming a coordinate nobody ever published.

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
microprofile-rest-client-api`, resolved at the Maven coordinates **4.0 and
3.0.1** (row 1, spanning the MP 6→7 platform boundary) — the archive itself
reports these via OSGi's `Bundle-Version` as **4.0.0** and **3.0.1**
respectively (the 4.0 coordinate pads to a three-segment `4.0.0` in the jar's
own manifest, a normal OSGi convention rather than a mismatch, and the harness
treats `4.0.0` as that jar's identity because that is what the archive itself
wrote); `derive_endpoints.sql` as it exists on this branch (row 2, not
version-scoped — it is this repository's own SQL, identified by the git
commit the harness resolves HEAD to); `io.quarkus:quarkus-rest-client`
**3.39.4** (row 3, the same generation as CP-19's sources); Maven Central's
own `maven-metadata.xml` for six `io.quarkus` client artifacts (row 4, not
version-scoped — it is the repository's index of every version, read the way
CP-19 row 5 reads the server-side relocation, and its cells name the versions
they list). Every verdict below is bounded by those four.

## Environment

`MP40=~/.m2/repository/org/eclipse/microprofile/rest/client/microprofile-rest-client-api/4.0/microprofile-rest-client-api-4.0.jar`
(already resolved in `~/.m2`); `MP301=~/.m2/repository/org/eclipse/microprofile/rest/client/microprofile-rest-client-api/3.0.1/…`
(the committed harness resolves this itself via `mvn dependency:get` rather
than depending on the design-review scratchpad's copy);
`~/.m2/repository/io/quarkus/quarkus-rest-client/3.39.4/…` (same — resolved by
the harness). This jar's classes do NOT include a `RestClientBase`/
`RestClientBuilder` class under those exact names at 3.39.4 — the resolution
logic actually lives in
`io.quarkus.rest.client.reactive.runtime.RestClientCDIDelegateBuilder`, found
by reading the jar's own class listing, see row 3.

**How to run.** `bash scripts/probes/cp22_microprofile_rest_client/run.sh`. It
resolves all three jars through Maven (network on the first run only, cached
in `~/.m2` afterwards), asks `javap` rows 1 and 3's questions, reads this
repository's own `derive_endpoints.sql` for row 2, and fetches six
`maven-metadata.xml` files from Maven Central for row 4 (network on every
run for that row). Needs a JDK, Maven and `git`. Not a test: nothing in the
suite runs it, and NFR-1's no-network rule governs the suite rather than
evidence gathering.

## Observations

Verbatim from `run.sh`'s generated table (`probe.py` prints it; nothing here
is typed by hand). **Every column header of the first table is a version the
JAR itself REPORTED, and not the version the Maven coordinate asked for** — out of
each manifest's `Bundle-Version` (rows 1a/1b) or `Implementation-Version` (row
3). `probe.py` reads the value out of the archive it opened and ABORTS the
whole run when it disagrees with what the jar was expected to report, rather
than filling a mislabelled column; that is CP-5's failure, which printed a
version it believed beside output from a version it had not run. (The
`microprofile-rest-client-api` 4.0 COORDINATE and its `4.0.0` self-reported
`Bundle-Version` are two different spellings of the same OSGi convention, not
a disagreement — see the harness comment.) Row 2 is not a jar read at all —
its identity is the git commit `run.sh` resolves HEAD to. Rows 4a–4f are not
jar reads either — each is one `maven-metadata.xml` fetched from
`repo1.maven.org` over the network, and the cell records what that index
listed at the time of the run.

```
| what the run read | 3.0.1 | 3.39.4 | 4.0.0 |
|---|---|---|---|
| artifacts reporting this version | org.eclipse.microprofile.rest.client:microprofile-rest-client-api | io.quarkus:quarkus-rest-client | org.eclipse.microprofile.rest.client:microprofile-rest-client-api |
| identity read from the archive itself | yes | yes | yes |

| # | question | artifact | version | observed |
|---|---|---|---|---|
| 1a | @RegisterRestClient: @Target, @Retention, baseUri()/configKey() defaults | `org.eclipse.microprofile.rest.client:microprofile-rest-client-api` | 4.0.0 | `@Target([Ljava/lang/annotation/ElementType;.TYPE]) ; @Retention(Ljava/lang/annotation/RetentionPolicy;.RUNTIME) ; baseUri(): String default "" ; configKey(): String default ""` |
| 1b | @RegisterRestClient: @Target, @Retention, baseUri()/configKey() defaults | `org.eclipse.microprofile.rest.client:microprofile-rest-client-api` | 3.0.1 | `@Target([Ljava/lang/annotation/ElementType;.TYPE]) ; @Retention(Ljava/lang/annotation/RetentionPolicy;.RUNTIME) ; baseUri(): String default "" ; configKey(): String default ""` |
| 2 | derive_endpoints.sql's prefixes CTE: peer off the prefix-gate row only? | `src/sextant/storage/duckdb/derive_endpoints.sql` | repo@df8b15d | `joins: JOIN prefix_gates ON pg.fqn = a.annotation ; JOIN catalog_params ON cp.catalog_id = pg.catalog_id ; reads cp.prefix_from: True ; reads cp.peer_from: True ; distinct annotation joins: 1` |
| 3 | Quarkus's configureBaseUrl: config vs. annotation baseUri precedence | `io.quarkus:quarkus-rest-client` | 3.39.4 | `invokeinterface InterfaceMethod io/quarkus/restclient/config/RestClientsConfig$RestClientConfig.uriReload:()Ljava/util/Optional; ; invokeinterface InterfaceMethod io/quarkus/restclient/config/RestClientsConfig$RestClientConfig.urlReload:()Ljava/util/Optional; ; invokestatic Method oneOf:([Ljava/util/Optional;)Ljava/util/Optional; ; getfield Field baseUriFromAnnotation:Ljava/lang/String; ; getfield Field baseUriFromAnnotation:Ljava/lang/String; ; getfield Field configKey:Ljava/lang/String; ; getfield Field configKey:Ljava/lang/String; ; getfield Field jaxrsInterface:Ljava/lang/Class; ; new class java/lang/IllegalArgumentException ; ldc_w String Unable to determine the proper baseUrl/baseUri. Consider registering using @RegisterRestClient(baseUri=\"someuri\"), @RegisterRestClient(configKey=\"orkey\"), or by adding \'%s\' or \'%s\' to your Quarkus configuration ; ldc_w String quarkus.rest-client.%s.url ; ldc_w String quarkus.rest-client.%s.uri ; invokespecial Method java/lang/IllegalArgumentException."<init>":(Ljava/lang/String;)V ; getfield Field baseUriFromAnnotation:Ljava/lang/String; ; invokevirtual Method java/util/Optional.orElse:(Ljava/lang/Object;)Ljava/lang/Object; ; invokeinterface InterfaceMethod io/quarkus/rest/client/reactive/QuarkusRestClientBuilder.baseUri:(Ljava/net/URI;)Lio/quarkus/rest/client/reactive/QuarkusRestClientBuilder; ; new class java/lang/IllegalArgumentException ; invokespecial Method java/lang/IllegalArgumentException."<init>":(Ljava/lang/String;Ljava/lang/Throwable;)V` |
| 4a | client artifact exists on Maven Central (metadata, not a jar) | `io.quarkus:quarkus-rest-client` | n/a | `maven-metadata.xml: 492 versions ; earliest GA 3.x: 3.3.0 ; last listed: 3.40.0.CR1` |
| 4b | client artifact exists on Maven Central (metadata, not a jar) | `io.quarkus:quarkus-rest-client-jackson` | n/a | `maven-metadata.xml: 458 versions ; earliest GA 3.x: 3.3.0 ; last listed: 3.40.0.CR1` |
| 4c | client artifact exists on Maven Central (metadata, not a jar) | `io.quarkus:quarkus-rest-client-reactive` | n/a | `maven-metadata.xml: 238 versions ; earliest GA 3.x: 3.3.0 ; last listed: 3.15.7` |
| 4d | client artifact exists on Maven Central (metadata, not a jar) | `io.quarkus:quarkus-rest-client-reactive-jackson` | n/a | `maven-metadata.xml: 236 versions ; earliest GA 3.x: 3.3.0 ; last listed: 3.15.7` |
| 4e | client artifact exists on Maven Central (metadata, not a jar) | `io.quarkus:quarkus-resteasy-client` | n/a | `maven-metadata.xml: 229 versions ; earliest GA 3.x: 3.7.0 ; last listed: 3.40.0.CR1` |
| 4f | client artifact exists on Maven Central (metadata, not a jar) | `io.quarkus:quarkus-resteasy-client-jackson` | n/a | `maven-metadata.xml: 229 versions ; earliest GA 3.x: 3.7.0 ; last listed: 3.40.0.CR1` |
```

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

### 4 — which Quarkus client artifact names exist on Maven Central

**Command.**
```
for a in quarkus-rest-client quarkus-rest-client-jackson quarkus-rest-client-reactive \
         quarkus-rest-client-reactive-jackson quarkus-resteasy-client quarkus-resteasy-client-jackson; do
  curl -sI https://repo1.maven.org/maven2/io/quarkus/$a/maven-metadata.xml | head -1
done
```
(`probe.py::q4_client_artifacts` fetches the same six files and counts their
`<version>` elements; rows 4a–4f above are its output.)

**Output.** Six `HTTP/2 200` lines — every one of the six names resolves to a
metadata file. Per the generated rows: `quarkus-rest-client` and
`quarkus-rest-client-jackson` list versions from before 3.9.0 (earliest GA
3.x listed 3.3.0) through `3.40.0.CR1`; `quarkus-rest-client-reactive` and
`quarkus-rest-client-reactive-jackson` stop at `3.15.7`, the last release
under the pre-rename name, exactly as CP-19 row 5b records for the
server-side `quarkus-resteasy-reactive`; `quarkus-resteasy-client` and
`quarkus-resteasy-client-jackson` list versions from 3.7.0 through
`3.40.0.CR1`.

**Claim.** All six coordinates are published artifacts. The reactive client
was renamed at 3.9.0 the same way the server was — `quarkus-rest-client-reactive`
→ `quarkus-rest-client` — and the last old-name release is 3.15.7 on both
sides; `quarkus-resteasy-client` is the RESTEasy-classic client's name from
the same rename onward. A module on either side of 3.9.0, on either
implementation, declares one of these six and nothing else names MicroProfile
REST Client in its POM, so `microprofile-rest-client.yml`'s
`detect.coordinates` lists all six (`measured 2026-09-18`, this row). What
this row does NOT measure: whether the classic client's annotation set is the
same `@RegisterRestClient` (it is the same MicroProfile API artifact, row 1,
but the classic client jar itself was not opened here).

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

4. Row 4: all six Quarkus client coordinates exist on Maven Central; the
   reactive names end at 3.15.7 (the 3.9.0 rename, mirroring CP-19 row 5) and
   the `quarkus-rest-client*`/`quarkus-resteasy-client*` names continue.

`measured: 2026-09-18` for rows 1, 2 and 4. Row 3 is measured but scoped as
stated above — its boundary is explicit rather than assumed.
