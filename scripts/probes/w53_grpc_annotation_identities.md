# W53 — do the gRPC annotation FQNs two catalogs name actually exist? (G-91)

**Question.** `grpc-net-devh.yml` matches on `net.devh.boot.grpc.client.inject.GrpcClient`
and `grpc-spring.yml` corroborates on two `@GrpcService` spellings — Spring gRPC's
and net.devh's, "differing only in package", as the file puts it. When A2 audited
them **neither `net.devh:*` nor `org.springframework.grpc:*` resolved in either
local repository**, so all three spellings were beliefs rather than readings, and
that is `G-91`.

**A wrong FQN in an `annotation_driven` or `injected_client` catalog is silent.**
The annotation never matches, the catalog derives nothing, and nothing anywhere
says a name was wrong — there is no unmet capability, no skip, no gap row. It
reads exactly like a module that happens not to use the framework. That is why
these are worth opening rather than leaving on `_NOT_MEASURED_YET`.

**Version scope (§5.4).** Read against **net.devh 3.1.0.RELEASE** (client and
server starters) and **Spring gRPC 0.10.0** (`spring-grpc-core` and its Boot
starter). Which package an annotation lives in is API surface and moves between
major versions; these are the versions read, and no others.

## Expectation table

| # | If | then |
|---|---|---|
| 1 | every named type exists at the coordinate the catalog gates on | the spellings are measured and the catalogs leave `_NOT_MEASURED_YET` |
| 2 | a type exists but in a different package | the catalog matches nothing and says nothing — the silent failure above |
| 3 | a gated coordinate carries no classes at all | it is an aggregator, and the type arrives transitively — which a Maven module declaring only that coordinate still resolves, but which F1 does not record |

## Observations

Verbatim from `scripts/probes/w53_grpc_annotation_identities/run.sh`, which runs
`sweep.py`. **Every version in the headers below is the one the JAR itself
reported** — out of its own `pom.properties` or its manifest's
`Implementation-Version`, and **not the version the coordinate list asked for**;
`checked` compares the two and ABORTS when they disagree.

| what the run read | 3.1.0.RELEASE | 0.10.0 |
|---|---|---|
| artifacts reporting this version | grpc-client-spring-boot-starter, grpc-server-spring-boot-starter | spring-grpc-core, spring-grpc-spring-boot-starter |
| where the jar states it | MANIFEST.MF | pom.properties |

### Does each named type exist where the catalog says?

| coordinate | class the catalog names | carries it | classes in the jar | used as |
|---|---|---|---|---|
| `net.devh:grpc-client-spring-boot-starter:3.1.0.RELEASE` | `net.devh.boot.grpc.client.inject.GrpcClient` (grpc-net-devh.yml) | **yes** | 60 | field_annotation, and detect.coordinates |
| `net.devh:grpc-server-spring-boot-starter:3.1.0.RELEASE` | `net.devh.boot.grpc.server.service.GrpcService` (grpc-spring.yml) | **yes** | 87 | corroborates.class_annotations |
| `org.springframework.grpc:spring-grpc-core:0.10.0` | `org.springframework.grpc.server.service.GrpcService` (grpc-spring.yml) | **yes** | 99 | corroborates.class_annotations |
| `org.springframework.grpc:spring-grpc-spring-boot-starter:0.10.0` | `org.springframework.grpc.server.service.GrpcService` (grpc-spring.yml) | no | 0 | detect.coordinates |

**Verdict: all three spellings CONFIRMED.** `net.devh.boot.grpc.client.inject.GrpcClient`,
`net.devh.boot.grpc.server.service.GrpcService` and
`org.springframework.grpc.server.service.GrpcService` each exist in the artifact
the catalog names. A2's prediction was right, and it is now a reading.

**One thing the probe found that the question did not ask.**
`org.springframework.grpc:spring-grpc-spring-boot-starter:0.10.0` — the coordinate
`grpc-spring.yml` puts in `detect.coordinates` — **carries no classes at all**. It
is a seven-file aggregator whose only job is to pull `spring-grpc-core`, which is
where `@GrpcService` actually lives. That costs nothing today, because
`grpc-spring.yml` declares no `detect.required` and its style is not in
`DEPENDENCY_GATED`, so the coordinate is provenance rather than a fence. It would
matter the day this catalog became gated: a Maven module declaring only the starter
records only the starter, since F1 reads inheritance and not mediation, and the
class that satisfies the annotation would be on a classpath no recorded coordinate
names. Recorded here rather than acted on.

## What this probe does NOT establish

That the annotations MEAN what the catalogs assume. It confirms the types exist at
those coordinates; it does not confirm that `@GrpcService` is optional on Spring
gRPC (the file's claim that any `BindableService` bean is exposed), nor that
`@GrpcClient` injects the stub the catalog reads a type off. Those are behaviour,
and this probe reads names.
