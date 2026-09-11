# W53 — every verb-setting method `okhttp3.Request$Builder` declares (G-22)

**Question.** `okhttp.yml` seeds `http_method: GET` at the chain root, because
that is OkHttp's own default for a fresh `Request.Builder`. That default is only
safe while the catalog's verb-setter list is COMPLETE: a setter the list misses
falls through as an unmatched step (D02 §4's "unmatched steps pass through
uncaptured"), the seeded GET stands uncorrected, and the row publishes a
confidently WRONG verb rather than an honest gap. `test_defaulted_identity_values.py`
allowlists that default on exactly this condition.

The file already claimed the list was *"measured rather than remembered — `javap -p
-s` on okhttp 3.14.9 and 4.12.0"*. **CP-11 measured 4.12.0 alone.** Its own
`measured:` block recorded `["4.12.0"]`, and `3.14.9` appeared nowhere else in the
repository — an unmeasured version presented as measured, which is `G-22`. Both
jars resolve, so the remedy is to measure the second one rather than to delete the
claim.

**Version scope (§5.4).** Read against **okhttp 3.14.9** and **okhttp 4.12.0**.
The 3.x line is Java and the 4.x line is Kotlin, which is why reading both matters
rather than trusting one: a Kotlin default argument compiles to extra overloads, so
"the same eight either way" is a claim about two compilers' output and not one.
`delete()` is `public` at 3.14.9 and `public final` at 4.12.0 for that reason, and
the pairing a step matches on — name and erased argument list — is unchanged.

## Expectation table

| # | If | then |
|---|---|---|
| 1 | both versions declare the same eight | the catalog's completeness claim holds at both, and the seeded GET default is safe |
| 2 | either declares a ninth | the seed is unsafe on that version and the allowlisted default stops being true |
| 3 | the catalog encodes a method neither declares | a dead step, harmless but unmeasured |
| 4 | a jar states no version of its own | the honest identity is `assumed`, never the coordinate printed as though confirmed |

## Observations

Verbatim from `scripts/probes/w53_okhttp_verb_setters/run.sh`, which runs
`sweep.py`. **Every version in the headers below is the one the JAR itself
reported** — out of its own `pom.properties`, its manifest, or, where the 4.x
jars carry neither, the `ConstantValue` of `okhttp3.OkHttp.VERSION`; and
**not the version the coordinate list asked for**; `checked` compares the two
and ABORTS when they disagree, rather than printing a version it did not read.

| what the run read | 3.14.9 | 4.12.0 |
|---|---|---|
| artifact reporting this version | okhttp | okhttp |
| where the jar states that version | pom.properties | okhttp3.OkHttp.VERSION |

### Every method that returns the builder, at both versions

Not only the seven verb names: filtering to those would make the last column's
`none` true by construction. A method this probe never opened cannot be reported
as missing.

| method | 3.14.9 | 4.12.0 | in the catalog |
|---|---|---|---|
| `addHeader(java.lang.String, java.lang.String)` | yes | yes | not a verb setter |
| `cacheControl(okhttp3.CacheControl)` | yes | yes | not a verb setter |
| `delete$default(okhttp3.Request$Builder, okhttp3.RequestBody, int, java.lang.Object)` | — | yes | synthetic `$default` bridge — stated boundary |
| `delete()` | yes | yes | **encoded** |
| `delete(okhttp3.RequestBody)` | yes | yes | **encoded** |
| `get()` | yes | yes | **encoded** |
| `head()` | yes | yes | **encoded** |
| `header(java.lang.String, java.lang.String)` | yes | yes | not a verb setter |
| `headers(okhttp3.Headers)` | yes | yes | not a verb setter |
| `method(java.lang.String, okhttp3.RequestBody)` | yes | yes | **encoded** |
| `patch(okhttp3.RequestBody)` | yes | yes | **encoded** |
| `post(okhttp3.RequestBody)` | yes | yes | **encoded** |
| `put(okhttp3.RequestBody)` | yes | yes | **encoded** |
| `removeHeader(java.lang.String)` | yes | yes | not a verb setter |
| `tag(java.lang.Class<? super T>, T)` | yes | yes | not a verb setter |
| `tag(java.lang.Object)` | yes | yes | not a verb setter |
| `url(java.lang.String)` | yes | yes | not a verb setter |
| `url(java.net.URL)` | yes | yes | not a verb setter |
| `url(okhttp3.HttpUrl)` | yes | yes | not a verb setter |

**Verb setters declared and not encoded:** none.
**Encoded and not declared at either version:** none.

**Verdict: CONFIRMED at both versions.** The same eight verb setters, no ninth at
either, and nothing encoded that neither declares.

**The table above reads every builder-returning method, not only the seven names the
catalog carries** — because the first version of this probe filtered on those names,
which made "declared and not encoded: none" true by construction and would have hidden
the very ninth verb the catalog's comment says it is watching for. It also hid the one
overload the two-compiler argument predicts: at 4.12.0 the Kotlin default argument on
`delete()` emits a static `delete$default(...)` bridge, absent at 3.14.9. That is a
synthetic forwarder rather than a distinct verb, and `COVERAGE.md` already files
`$default` synthetics as unsupported, so it is a stated boundary — but it is stated
now, rather than filtered out before the comparison ran. `G-22`'s defect was the RECORD,
not the list: the claim the file made was true and only one of its two versions had
ever been read. `okhttp.yml`'s `measured:` block now carries both.

**Both identities are `reported`, by different routes** — and that is worth stating
because the two 4.x jars in this repository's reach carry no maven metadata and no
`Implementation-Version` at all. 3.14.9 states its version in `pom.properties`;
4.12.0 states it only as the `ConstantValue` of `okhttp3.OkHttp.VERSION`, which is
the route CP-11 used. A reader that knew only the manifest route would have called
4.12.0 unmeasurable and written `assumed` — the `retrofit.yml` precedent — where a
real self-report exists.

## What this probe does NOT establish

It reads declarations, not behaviour: that `post(RequestBody)` sets the verb to
POST is OkHttp's documented contract and this probe did not execute a request to
confirm it. It also says nothing about the 3.12.x or 5.0.0-alpha lines, both of
which sit in the local repository unread — the scope is the two versions the
catalog claims.
