# W11 — the javax/jakarta sweep (F2 §3.3)

**Question.** Jakarta EE renamed every one of its packages from `javax.*` to
`jakarta.*`, and a Spring Boot 2 codebase is still on the old spelling. A catalog
names types by their fully qualified name and compares them exactly, so a catalog
that names only one spelling simply does not match the other. So: **for every
Jakarta EE type any shipped catalog names, does a catalog name the `javax`
spelling as well; does that counterpart exist; and when a codebase writes the
unhandled spelling, what happens?**

The third part is the one worth a probe. F2 §3.3 asks for two failure modes to be
classified *separately*, because they are not equally bad:

- *renamed, nothing published* — silence, which at least reads as absence;
- *renamed, partial data published* — a row that exists with a hole in it, so a
  reader concludes we looked and could not resolve it when we never looked in that
  spelling at all.

Both are measured below by **running the real derivation**, not by reading the
catalog and reasoning about it. A third mode turned up that §3.3 does not name,
and it is worse than either.

**Version scope (§5.4).** Read against **javax.jms-api 2.0.1, jaxb-api 2.3.1,
jakarta.jms-api 3.1.0 and jakarta.xml.bind-api 4.0.1**. Each `javax` version is
the LAST release under that coordinate, which is the only version a Boot 2
codebase can be on — neither line ships again. Widening the scope means adding a
coordinate to `run.sh` and re-running, never assuming.

## Expectation table

| # | If | then |
|---|---|---|
| 1 | a catalog names a `jakarta.*` type | it names the `javax.*` spelling too, or the gap is deliberate and recorded |
| 2 | a `javax` counterpart type exists | it declares the same method NAMES, and necessarily different descriptors, since the parameter types moved packages with it |
| 3 | a codebase writes an unhandled `javax` spelling on a POSITIVE match rule | nothing is published |
| 4 | a codebase writes an unhandled `javax` spelling on an identity rule that reads an annotation | the row is published without that identity |
| 5 | a codebase writes an unhandled `javax` spelling on a NEGATIVE list (`excludes`) | — *no expectation was written; §3.3 does not consider this case* |

## Observations

Verbatim from `scripts/probes/w11_javax_jakarta/run.sh`, which runs `sweep.py`. **Every version below is the one the JAR itself reported** — read out of its own `META-INF/maven/*/pom.properties` — and **not the version the coordinate list asked for**. `sweep.py` compares the two and ABORTS the whole run when they disagree, rather than printing a version it did not read: that is CP-5's failure, which labelled eight cells with a version the process never saw. `jaxb-api-2.3.1.jar` is why the manifest is not the source — it prints `Implementation-Version: 2.3.0` while its own `pom.properties` says `2.3.1`, so the two disagree inside one file.

| what the run read | 2.0.1 | 2.3.1 | 3.1.0 | 4.0.1 |
|---|---|---|---|---|
| artifact reporting this version | javax.jms-api | jaxb-api | jakarta.jms-api | jakarta.xml.bind-api |
| types resolved out of it | 1 | 1 | 1 | 1 |
| methods compared against the other spelling | 4 | 2 | 4 | 2 |
| of those, descriptors that DIFFER | 4 | 0 | 4 | 0 |

### 1. Every Jakarta EE type a shipped catalog names

Read from parsed catalog VALUES, never from file text — a type named in a comment is not a type a catalog matches. DOTTED names only: a type named solely inside a `descriptor:` (`Ljakarta/jms/Queue;`) is invisible here, and today nothing is slash-named without also being dotted somewhere, so this under-reports nothing yet. A Maven coordinate is not a type; its column is `detected only`.

| type | named in a RULE by | detected only, by | state |
|---|---|---|---|
| `annotation.Nullable` | `shape-models/json.yml` (jakarta), `shape-models/json.yml` (javax) | — | both |
| `jms` | — | `jakarta-jms.yml`, `javax-jms.yml` | detected, never matched |
| `jms.Message` | `spring-jms.yml` (jakarta), `spring-jms.yml` (javax) | — | both |
| `jms.Session` | `jakarta-jms.yml` (jakarta), `spring-jms.yml` (jakarta), `javax-jms.yml` (javax), `spring-jms.yml` (javax) | — | both |
| `json.bind.annotation.JsonbProperty` | `microprofile-graphql.yml` (jakarta), `microprofile-graphql.yml` (javax) | — | both |
| `jws` | — | `jakarta-jws-client.yml`, `jakarta-jws.yml` | detected, never matched |
| `jws.WebMethod` | `jakarta-jws-client.yml` (jakarta), `jakarta-jws.yml` (jakarta), `jakarta-jws-client.yml` (javax), `jakarta-jws.yml` (javax) | — | both |
| `jws.WebService` | `jakarta-jws-client.yml` (jakarta), `jakarta-jws.yml` (jakarta), `jakarta-jws-client.yml` (javax), `jakarta-jws.yml` (javax) | — | both |
| `servlet` | — | `jakarta-servlet.yml`, `javax-servlet.yml` | detected, never matched |
| `servlet.ServletRequest` | `jakarta-servlet.yml` (jakarta), `javax-servlet.yml` (javax) | — | both |
| `servlet.ServletResponse` | `jakarta-servlet.yml` (jakarta), `javax-servlet.yml` (javax) | — | both |
| `servlet.annotation.WebServlet` | `jakarta-servlet.yml` (jakarta), `javax-servlet.yml` (javax) | — | both |
| `servlet.http.HttpServlet` | `jakarta-servlet.yml` (jakarta), `javax-servlet.yml` (javax) | — | both |
| `servlet.http.HttpServletRequest` | `jakarta-servlet.yml` (jakarta), `javax-servlet.yml` (javax) | — | both |
| `servlet.http.HttpServletResponse` | `jakarta-servlet.yml` (jakarta), `javax-servlet.yml` (javax) | — | both |
| `websocket` | — | `jakarta-websocket.yml` | detected, never matched |
| `websocket.OnMessage` | `jakarta-websocket.yml` (jakarta), `jakarta-websocket.yml` (javax) | — | both |
| `websocket.server.ServerEndpoint` | `jakarta-websocket.yml` (jakarta), `jakarta-websocket.yml` (javax) | — | both |
| `xml.bind.annotation.XmlRootElement` | `spring-ws-template.yml` (jakarta), `spring-ws-template.yml` (javax) | — | both |

### 2. Does the unhandled counterpart exist, and declare the same methods?

| javax artifact | version IT reports | type | method | jakarta descriptor | javax descriptor |
|---|---|---|---|---|---|
| `javax.jms:javax.jms-api` | **2.0.1** | `jms/Session` | `createProducer` | `(Ljakarta/jms/Destination;)Ljakarta/jms/MessageProducer;` | `(Ljavax/jms/Destination;)Ljavax/jms/MessageProducer;` |
| `javax.jms:javax.jms-api` | **2.0.1** | `jms/Session` | `createConsumer` | `(Ljakarta/jms/Destination;)Ljakarta/jms/MessageConsumer;` | `(Ljavax/jms/Destination;)Ljavax/jms/MessageConsumer;` |
| `javax.jms:javax.jms-api` | **2.0.1** | `jms/Session` | `createQueue` | `(Ljava/lang/String;)Ljakarta/jms/Queue;` | `(Ljava/lang/String;)Ljavax/jms/Queue;` |
| `javax.jms:javax.jms-api` | **2.0.1** | `jms/Session` | `createTopic` | `(Ljava/lang/String;)Ljakarta/jms/Topic;` | `(Ljava/lang/String;)Ljavax/jms/Topic;` |
| `javax.xml.bind:jaxb-api` | **2.3.1** | `xml/bind/annotation/XmlRootElement` | `name` | `()Ljava/lang/String;` | `()Ljava/lang/String;` |
| `javax.xml.bind:jaxb-api` | **2.3.1** | `xml/bind/annotation/XmlRootElement` | `namespace` | `()Ljava/lang/String;` | `()Ljava/lang/String;` |

### 3. What each unhandled spelling actually derives

| catalogs run | spelling written | rows | derived by | path | peer | resolution |
|---|---|---|---|---|---|---|
| `jakarta-jms + javax-jms` | `jakarta` | 1 | jakarta-jms | `raw-audit` | None | resolved |
| `jakarta-jms + javax-jms` | `javax` | 1 | javax-jms | `raw-audit` | None | resolved |
| `spring-ws-template` | `jakarta` | 1 | spring-ws-template | `{http://acme.example/orders}placeOrderRequest` | http://billing.internal/ws | resolved |
| `spring-ws-template` | `javax` | 1 | spring-ws-template | `{http://acme.example/orders}placeOrderRequest` | http://billing.internal/ws | resolved |

### 4. An `excludes` list that names one spelling

| catalog | rule | spelling written | what becomes the payload |
|---|---|---|---|
| `spring-jms` | `request_body.excludes` | `jakarta` | `nothing (excluded)` |
| `spring-jms` | `request_body.excludes` | `javax` | `nothing (excluded)` |

<!-- gaps found: [] -->

## Verdict

**1. THREE type families were named in `jakarta` only** — `jms` (in `jakarta-jms.yml`
and `spring-jms.yml`), `xml.bind.annotation.XmlRootElement` (in
`spring-ws-template.yml`) and `websocket` (in `jakarta-websocket.yml`). All three are
closed now, which is why section 1 shows no `JAKARTA ONLY` row today.

**The third was found only after the sweep was corrected, and how it hid is the more
useful half of this probe.** The first version scanned raw catalog TEXT, so a type
named in a COMMENT counted as named — and `jakarta-websocket.yml` names both `javax`
spellings inside a comment that says, in as many words, that they derive no endpoint.
The sweep reported websocket as carrying both spellings, this verdict said so, and
`docs/COVERAGE.md` said the opposite three lines from the row that contradicted it.
**A sweep that reads prose reports a gap as closed because somebody wrote about it.**
It parses the YAML and reads rule-bearing values now.

Two further distinctions the corrected sweep makes, each of which was a wrong row
before:

- **A Maven coordinate is not a type.** `detect.coordinates` holds
  `javax.websocket:javax.websocket-api`, whose group half looks exactly like a
  package — which put four families in the table (`jms`, `jws`, `servlet`,
  `websocket`) that name no type at all. They sit under `detected only` now, which
  is the honest state: the module is recognised as WebSocket-shaped while nothing
  inside it is matched.
- **Detection is not handling.** Those two used to be one column, so "we detect this
  library" read as "we handle this spelling" — which is precisely the confusion that
  let the websocket gap stand.

**2. Both counterparts exist and declare the same method names.** `javax.jms.Session`
declares `createProducer`, `createConsumer`, `createQueue` and `createTopic` exactly
as `jakarta.jms.Session` does. **The descriptors differ**, because the parameter and
return types moved packages with the API:
`(Ljavax/jms/Destination;)Ljavax/jms/MessageProducer;` against
`(Ljakarta/jms/Destination;)Ljakarta/jms/MessageProducer;`. A twin catalog therefore
cannot copy the descriptors across — every row needs its own, measured against the
`javax` jar, and the CP-10 harness has to gain the coordinate to check them.

**The two gaps cost different amounts, and the summary table is what says so.** All
**four** JMS descriptors differ between spellings, because `Session`'s parameters and
returns are themselves JMS types that moved. **Neither** JAXB one does: `name` and
`namespace` are both `()Ljava/lang/String;` in either spelling, since an annotation
attribute returns a `java.lang.*` type that never moved. So `spring-ws-template.yml`
needs only a second annotation NAME at three identity rules, while `javax-jms.yml` is
a genuinely separate measurement. A sweep that had only asked "does the counterpart
exist" would have priced the two the same.

**3. The two failure modes F2 §3.3 names are both real, and they are different.**

Sections 3 and 4 above show every spelling resolving, because W12 closed all three
gaps. What each gap DID is recorded here, and each is one revert away from being
shown again — which is the check that this probe still measures something:

| revert | the row that changes |
|---|---|
| remove `javax-jms.yml` | §1 `jms.Session` → `JAKARTA ONLY`; §3's `javax` row → **0 rows** |
| drop the `javax` spelling from `spring-ws-template.yml`'s arity-2 rule | §3's SOAP `javax` row → `path` NULL, `unresolved` |
| drop the two `javax` entries from `spring-jms.yml`'s `excludes` | §4's `javax` row → `javax/jms/Message#` |

*Renamed, nothing published* is the JMS shape: the whole route invisible, which at
least reads as absence. *Renamed, partial data published* is the SOAP shape: the
endpoint present, addressed to the right peer, with no operation on it — which reads
as "we tried and the operation was unreadable", not as "we never looked in this
spelling". The second is worse, and running the derivation is what separates them;
reading the catalogs would not have.

**4. A third mode, which §3.3 does not name and which is worse than both.**
`spring-jms.yml`'s `request_body` declares
`{ fallback: sole_unannotated, excludes: [...] }`. `excludes` is a NEGATIVE list: it
names the opaque envelope types so the fallback will not mistake one for the payload.
Naming only the `jakarta` spelling meant the `javax` one was **not** excluded — so on
Boot 2 the fallback picked it, and the raw envelope was described AS the message
contract. Section 4's third row is where that shows; today both spellings read
`nothing (excluded)`, and the revert above puts `javax/jms/Message#` back.

Not silence, and not a hole — a **wrong contract, published**. Every rule that names
a type in order to REFUSE it inverts the failure: the missing spelling stops the
refusal rather than stopping the match. A sweep that reads only `matches` will keep
missing that class, which is why the expectation table above has no row 5 — the
design did not consider this direction, and neither did the first version of this
probe.

## What this probe deliberately did not measure

- **Whether a `javax` twin catalog would derive correctly**, only that the current
  catalogs do not derive at all (or derive partially). Building the twin is W12; this
  probe's job is to say how many are needed and what each costs.
- **Any type not named by a shipped catalog.** A Jakarta EE API nobody has written a
  catalog for is not a spelling gap, it is a missing catalog, and it would be found by
  a different question.
- **Runtime behaviour of the transitive `jakarta.*` types** a named type refers to
  (`Destination`, `Queue`, `MessageProducer`). They appear only inside descriptors,
  which finding 2 already shows must be re-measured per spelling.
- **The `spring-ws.yml` serving side.** `@PayloadRoot` is a Spring annotation and never
  moved packages; only the JAXB annotation on the payload TYPE did, and that is
  `spring-ws-template.yml`'s read, measured above.

## How the verdict is consumed

**W12 acted on all three findings, and the tables above are the post-fix run** — which is
why sections 3 and 4 now show every spelling resolving. That is deliberate: a probe whose
generated table shows the broken state stops being re-runnable the moment the break is
fixed, and a verdict quoting numbers no current run produces is the CP-5 shape this
harness exists to avoid. What the tables prove today is that the fix HOLDS; what they
proved before it is recorded in `CHANGELOG.md` beside the change that made them agree.

- `javax-jms.yml` sits beside `jakarta-jms.yml` with its own descriptors, every one
  checked against the 2.0.1 jar by `scripts/probes/cp10_catalog_descriptors.md` (which
  gained the coordinate) rather than copied. Finding 2 is why a copy would have been
  wrong: all four compared JMS descriptors differ.
- `spring-ws-template.yml`'s three identity rules name both JAXB spellings. That key —
  `path_from_argument_type.annotation` — was NOT one of F2 §3.1's twenty-one; the design
  missed it, the same way it missed `matches.steps[].owner`, and widening it is what let
  this be two names rather than a second catalog.
- `spring-jms.yml`'s `excludes` names both envelope spellings. Finding 4 is a distinct
  KIND of fix from the other two, and a sweep that only read `matches` would have missed
  it entirely.

`docs/COVERAGE.md` asserted *"Both must be matched"* in the indicative — a requirement
written as a description, which is why nobody checked it. It now carries the three-way
table above instead.
