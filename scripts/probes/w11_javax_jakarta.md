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

| type | jakarta | javax | state |
|---|---|---|---|
| `annotation.Nullable` | `json.yml` | `json.yml` | both |
| `jms` | `jakarta-jms.yml` | — | **JAKARTA ONLY** |
| `jms.Message` | `google-pubsub-publisher.yml`, `jakarta-jms.yml`, `spring-jms.yml` | — | **JAKARTA ONLY** |
| `jms.Session` | `jakarta-jms.yml`, `spring-jms.yml` | — | **JAKARTA ONLY** |
| `json.bind.annotation.JsonbProperty` | `microprofile-graphql.yml` | `microprofile-graphql.yml` | both |
| `jws` | `jakarta-jws-client.yml`, `jakarta-jws.yml`, `spring-ws.yml` | `jakarta-jws-client.yml`, `jakarta-jws.yml` | both |
| `jws.WebMethod` | `jakarta-jws-client.yml`, `jakarta-jws.yml` | `jakarta-jws-client.yml`, `jakarta-jws.yml` | both |
| `jws.WebService` | `jakarta-jws-client.yml`, `jakarta-jws.yml` | `jakarta-jws-client.yml`, `jakarta-jws.yml` | both |
| `servlet` | `jakarta-servlet.yml` | `javax-servlet.yml` | both |
| `servlet.ServletRequest` | `jakarta-servlet.yml` | `javax-servlet.yml` | both |
| `servlet.ServletResponse` | `jakarta-servlet.yml` | `javax-servlet.yml` | both |
| `servlet.annotation.WebServlet` | `jakarta-servlet.yml` | `javax-servlet.yml` | both |
| `servlet.http.HttpServlet` | `jakarta-servlet.yml` | `javax-servlet.yml` | both |
| `servlet.http.HttpServletRequest` | `jakarta-servlet.yml` | `javax-servlet.yml` | both |
| `servlet.http.HttpServletResponse` | `jakarta-servlet.yml` | `javax-servlet.yml` | both |
| `websocket` | `jakarta-websocket.yml` | `jakarta-websocket.yml` | both |
| `websocket.OnMessage` | `jakarta-websocket.yml` | `jakarta-websocket.yml` | both |
| `websocket.server.ServerEndpoint` | `jakarta-websocket.yml` | `jakarta-websocket.yml` | both |
| `xml.bind.annotation.XmlRootElement` | `spring-ws-template.yml` | — | **JAKARTA ONLY** |

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

| catalog | spelling written | rows | protocol | path | peer | resolution |
|---|---|---|---|---|---|---|
| `jakarta-jms` | `jakarta` | 1 | jms | `raw-audit` | None | resolved |
| `jakarta-jms` | `javax` | **0** | — | — | — | — |
| `spring-ws-template` | `jakarta` | 1 | soap | `{http://acme.example/orders}placeOrderRequest` | http://billing.internal/ws | resolved |
| `spring-ws-template` | `javax` | 1 | soap | `None` | http://billing.internal/ws | unresolved |

### 4. An `excludes` list that names one spelling

| catalog | rule | spelling written | what becomes the payload |
|---|---|---|---|
| `spring-jms` | `request_body.excludes` | `jakarta` | `nothing (excluded)` |
| `spring-jms` | `request_body.excludes` | `javax` | `javax/jms/Message#` |

<!-- gaps found: [".jms", ".jms.Message", ".jms.Session", ".xml.bind.annotation.XmlRootElement"] -->

## Verdict

**1. Three type families are named in `jakarta` only.** `jms` (in `jakarta-jms.yml`,
`spring-jms.yml` and `google-pubsub-publisher.yml`), and
`xml.bind.annotation.XmlRootElement` (in `spring-ws-template.yml`). Everything else
a catalog names — servlet, jws, websocket, json.bind, annotation.Nullable — already
carries both spellings. The sweep is mechanical and re-runnable, which is the point:
the four instances F2 §3.3 counted accumulated one at a time because nobody asked
the question of every catalog at once.

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

| | jakarta spelling | javax spelling |
|---|---|---|
| `jakarta-jms`, a producer on a queue | 1 row, `path: raw-audit`, `resolved` | **0 rows** |
| `spring-ws-template`, a SOAP call | 1 row, `path: {http://acme.example/orders}placeOrderRequest`, `resolved` | 1 row, **`path: NULL`**, `unresolved`, `peer` still published |

*Renamed, nothing published* for JMS: the whole route is invisible. *Renamed, partial
data published* for SOAP: the endpoint is there, addressed to the right peer, with no
operation on it — which reads as "we tried and the operation was unreadable", not as
"we never looked in this spelling". The second is worse, and the measurement is what
separates them rather than the reasoning.

**4. A third mode, which §3.3 does not name and which is worse than both.**
`spring-jms.yml` declares
`request_body: { fallback: sole_unannotated, excludes: [jakarta.jms.Session, jakarta.jms.Message] }`.
`excludes` is a NEGATIVE list: it names the opaque envelope types so the fallback will
not mistake one for the payload. Naming only the `jakarta` spelling means the `javax`
one is **not** excluded — so on Boot 2 the fallback picks it, and the raw envelope is
described AS the message contract:

| `@JmsListener void onOrder(… Message m)` | what becomes the payload |
|---|---|
| `jakarta.jms.Message` | nothing (excluded) |
| `javax.jms.Message` | **`javax/jms/Message#`** |

Not silence, and not a hole — a **wrong contract, published**. Every rule that names a
type to REFUSE it inverts the failure: the missing spelling stops the refusal rather
than stopping the match. W12 must therefore sweep `excludes` and every other negative
list separately from the positive `matches`, and the expectation table above has no
row 5 because the design did not consider this direction.

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

W12 writes `javax-jms.yml` beside `jakarta-jms.yml` with its own measured descriptors,
adds the `javax` JAXB spelling to `spring-ws-template.yml`'s three identity rules, and
adds both `javax` envelope spellings to `spring-jms.yml`'s `excludes`. Finding 2 says
the first cannot be a copy; finding 4 says the third is a distinct kind of fix from the
other two and would have been missed by a sweep that only looked at `matches`.

`docs/COVERAGE.md`'s prose asserts *"Both must be matched"* in the indicative. Findings
1, 3 and 4 are what make that sentence false today; F8 corrects it.
