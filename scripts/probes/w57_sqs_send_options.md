# W57 — what does `SqsSendOptions` declare, and at which versions? (OI-74)

**Question.** `spring-sqs-template.yml`'s builder row reads a destination and a
payload from INSIDE `sqsTemplate.send(to -> to.queue(…).payload(…))`, by naming
the builder methods called in the lambda body. Those names are the whole rule: a
name the interface does not declare reads nothing, and a name it declares on a
different member than the catalog assumes reads the wrong argument.

The catalog also needs to know **how many of the interface's members take a
`String`**, because that is the size of the fabrication the owner and name
conjuncts prevent — a reader taking "the first string literal in the body" could
mistake any of them for the queue. Prose in three places quotes that number, so
it is measured here with its definition stated: a `String` at a TOP-LEVEL
parameter position. Three plausible definitions give 3, 4 and 5, which is exactly
why a bare "four" in a comment is not evidence.

**Version scope (§5.4).** Read against **spring-cloud-aws-sqs 3.1.1 and 4.1.1**,
the two versions this catalog's `measured:` block records. An interface's member
list is API surface and moves between major versions.

## Expectation table

| # | If | then |
|---|---|---|
| 1 | `queue` and `payload` are declared at both versions | the catalog's `lambda_steps` names real members, and the rule is version-stable across the pair |
| 2 | either is absent at a version | the row reads nothing there — silently, since a name that matches no call is indistinguishable from a body that never called it |
| 3 | several members take a `String` | the NAME and OWNER conjuncts are load-bearing rather than belt-and-braces |

## Observations

Verbatim from `scripts/probes/w57_sqs_send_options/run.sh`, which runs
`sweep.py`. **Every version in the headers below is the one the JAR itself
reported** — out of its own `pom.properties` or its manifest's
`Implementation-Version`, and
**not the version the coordinate list asked for**; `checked` compares the two
and ABORTS when they disagree, rather than printing a version it did not read.

| what the run read | 3.1.1 | 4.1.1 |
|---|---|---|
| artifact reporting this version | spring-cloud-aws-sqs | spring-cloud-aws-sqs |
| where the jar states that version | pom.properties | pom.properties |

### Every method `SqsSendOptions` declares

| method | 3.1.1 | 4.1.1 | read by the catalog |
|---|---|---|---|
| `delaySeconds(java.lang.Integer)` | yes | yes | no |
| `header(java.lang.String, java.lang.Object)` | yes | yes | no |
| `headers(java.util.Map<java.lang.String, java.lang.Object>)` | yes | yes | no |
| `messageDeduplicationId(java.lang.String)` | yes | yes | no |
| `messageGroupId(java.lang.String)` | yes | yes | no |
| `payload(T)` | yes | yes | **yes, at arg0** |
| `queue(java.lang.String)` | yes | yes | **yes, at arg0** |

**Read by the catalog and NOT declared at both versions:** none.
**Members taking a `String` at a top-level parameter position:** 4 — header(java.lang.String, java.lang.Object), messageDeduplicationId(java.lang.String), messageGroupId(java.lang.String), queue(java.lang.String).

**Verdict: CONFIRMED, identically at both versions.** Seven members, the same
seven at 3.1.1 and 4.1.1, with `queue(String)` and `payload(T)` among them — the
two the catalog reads, at argument 0 each. Nothing the catalog names is missing at
either version.

**Four members take a `String` at a top-level parameter position**, which is what
makes the reader's conjuncts load-bearing: `queue`, `header`, `messageGroupId` and
`messageDeduplicationId`. A reader matching on the method name alone, or on no
name at all, has four chances to publish something that is not a queue as this
module's queue — and W57's review measured exactly that happening with an owner
conjunct missing.

## What this probe does NOT establish

That `queue(String)` MEANS the destination — that is the SDK's documented
contract, and this probe read a declaration rather than sending a message. It also
says nothing about versions outside the pair, and nothing about `SqsSendOptions`'s
implementations: the catalog matches on the interface, and a call made on
`SqsTemplate$SqsSendOptionsImpl` directly would carry that owner instead.
