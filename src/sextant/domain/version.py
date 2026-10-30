"""The stamps every fact file, workspace and bundle carries, and the ONE
place each is written down.

They were four hand-maintained copies across two languages until Step 0, and
they held two different values for one stamp with nothing asserting otherwise
(`analyze.py`'s own comment stated the invariant it was violating). The cause
was the copying, not the absence of a test, so the copies are gone: every
Python producer imports from here, and the JVM extractor — which cannot see a
Python constant at all — is HANDED the value as a required command-line option.

They are constants of the CODE, not of a workspace. `metadata.json` records
them, so it can never be their source: a build that read its own schema version
back from a file a previous run wrote would let a stale workspace define what
the current build claims, which is the disagreement `api._stale_stamps` exists
to catch.
"""

from importlib.metadata import version

# The tool's own release, and the one stamp that is genuinely package metadata:
# read from the installed distribution so `pyproject.toml` owns it outright
# rather than being shadowed by a literal here that drifts from it.
SEXTANT_VERSION = version("sextant")

# Both schema stamps are single monotonically increasing INTEGERS, not semver
# (Step 0, ruled by the user 2026-09-07). Neither is ever parsed, ordered or
# compared for compatibility anywhere — `api._stale_stamps` compares each for
# EQUALITY and that is all either has ever done — so three dotted numbers were
# carrying one bit of meaning apiece, in a type that let copies of one stamp
# hold different values without anything noticing.
#
# Both start at 2: the second generation, after the semver one. No workspace on
# disk can match an integer, so every workspace written before Step 0 is refused
# by the stamp gate and re-analysed. That is the designed behaviour, not a
# migration — nothing is rewritten in place.
#
# They move independently: a fact-shape change forces re-extraction (D01 §7's
# table calls it the expensive one), while a derived-table change costs only a
# re-derive.
#
# **FROZEN UNTIL RELEASE (ruled by the user 2026-09-07).** *"Sextant is not in a
# usable stage and nothing is released. So no version bump."* A stamp
# discriminates for CONSUMERS of a published bundle, and there are none — so
# every increment buys nothing and costs a full re-analysis of every developer
# workspace, several times per wave. The rule resumes at release; until then a
# fact-shape change lands WITHOUT an increment, deliberately.
#
# The consequence, stated rather than discovered: a workspace stamped 5 may
# hold any of several shapes, so the stamp no longer says which one produced
# it. That is the ambiguity Step 0 removed, accepted back on purpose and only
# while nothing depends on it. Re-analysing is one `sextant module analyze`,
# and the changes riding at 5 are additive or value-level — an older workspace
# still VALIDATES, it simply answers with older facts.
# An integer says WHICH generation and nothing about what changed, so each
# increment is recorded here or the number means nothing to the next reader.
#
#   fact schema
#     (pre-2) semver, and the reason this is now an integer: `1.1.0` was cut for
#             `DeclaredShapeFact` gaining the optional `operation` sub-record,
#             and only ONE of the four producers moved — the one whose shape had
#             NOT changed. A `.proto` or WSDL document on disk today therefore
#             carries `operation` while stamping the version that predates it.
#     2       the integer scheme itself. No shape change: the divergence above
#             is what it settles, by making every workspace written under either
#             old value refuse and re-analyse.
#     3       (Step 1) `scanner_version` is REMOVED from a document. It named a
#             version for facilities that ship inside the wheel and therefore
#             have none of their own, and on the one facility that does run
#             third-party code it held "9.18" — a CAPABILITY number, while the
#             pinned ASM was 9.10.1. The versions that can actually move are the
#             extractor's resolved libraries, now recorded once per workspace in
#             `metadata.json` instead of repeated on every document.
#     4       (Step 1, second half) a document gains `class_major` — the
#             class-file version at JVMS 4.1's fixed offset — and `partial` /
#             `partial_reason` get a producer at last. Both were the literal
#             strings "false" and "null" with no code path able to set either,
#             so `partial_documents` reached the rendered gaps list and a
#             bundle's `coverage.partial` as a number that could only be zero.
#
#   graph schema
#     (pre-2) 1.0.0, then 1.1.0 when the derived set gained `roots` and
#             `call_edges` and `## Traces` began rendering from them, then 1.2.0
#             when `roots` gained `protocol`/`method`/`path` and its row grain
#             moved from (handler, kind) to (handler, kind, address) — not
#             additive: a query against the older rows fails rather than
#             answering empty, which is what comparing a stamp is for.
#     2       the integer scheme. No table change.
#     3       `endpoint_conditions` (spec 2026-10-21-conditional-controllers): a derived
#             table the system tier federates, so a workspace without it cannot be read
#             by this build's `system analyze` — refused by name, never a bare
#             `Catalog Error`.
#     4       `bean_conditions` (spec 2026-10-22-conditional-beans): the conditions every
#             bean carries, a new derived table; `endpoint_conditions` stops being a table
#             and becomes a VIEW joining endpoint rows to it, gaining `caller`, `via`,
#             `bean_kind` and `bean`; the view `bean_presence` folds it into where each
#             bean exists; the view `symbol_beans`
#             is the one rule mapping code to its bean, and `candidate_presence` states
#             which candidates of a narrowed call exist per environment; `interface_beans`
#             names every interface the framework implements at run time (CP-46), whose
#             implementation `candidate_presence` lists as a candidate. A workspace
#             holding the old table is refused by name by `system analyze` and rebuilt by
#             `module analyze`.
#     5       no table change: what `endpoints.peer` may HOLD changed. Before 2026-10-23
#             `split_url` kept a URL's userinfo in the peer (`svc:s3cret@billing.internal`),
#             a shape no exit's `scheme://` rule could see, so a workspace of that vintage
#             puts a password into every document and bundle made from it. Bumped so every
#             reader refuses one rather than guessing at it (user ruling, 2026-10-23): in
#             text that shape cannot be told from a Spring-WS `mailto:ops@billing` peer.
#     6       no table change: condition verdicts a deployment can change are no longer
#             decided (spec 2026-10-23-deployment-set-conditions). A `profile` or
#             `property` condition is `unresolved` unless the environment's own name
#             decides it, the module's own reading kept as evidence, so a workspace of the
#             older vintage holds decided verdicts this build says the repository cannot
#             give — bumped so it is refused and re-analysed, never read beside new ones
#             (user ruling, 2026-10-23, §6).
#     7       `resolved_schedules`: a scheduled job's placeholder expression per
#             environment (spec 2026-10-23-configured-schedules), a new derived table
#             beside `scheduled_work`, which keeps one row per job.
#     8       `rpc_hops`: where a gRPC client stub's call to an RPC this module serves
#             lands, its handler named (spec 2026-10-25-quarkus-mutiny-grpc §3d), a new
#             derived table beside `call_edges`, which is untouched.
#     9       `scheduled_work` gains `name` (the trigger's own name) and
#             `expression_source` (where a walk to the expression stopped, set only when
#             `expression` is NULL); `handler`, `trigger` and `expression` may be NULL; and
#             `resolution` may be `partial` or `narrowed` (spec 2026-10-28-quartz §3e).
#             `resolved_schedules` carries `name`. A workspace of the older vintage has
#             neither column, so it is refused and re-analysed.
#     10      `scheduled_work` gains `untied`: the parts of a row that are NULL because the
#             paths to the trigger disagree on them, not because the code states none. And
#             an `@Scheduled` row's `name` is EMPTY, not NULL: the framework gives no name,
#             which is known, where NULL says the code's name is not (spec 2026-10-28-quartz,
#             "Empty cells", ruled 2026-10-29). A workspace of the older vintage reads every
#             such NULL as unknown, so it is refused and re-analysed.
#     11      `endpoints` gains `row_id` and `endpoint_metadata` gains `row_id`: every
#             endpoint row is numbered when it is written, and an entry attached to a row
#             is bound to that number when IT is written, then follows the row through
#             every pass that moves it — the path prefix, a protocol reclassification —
#             where it used to be matched by an address the prefix had already changed
#             (spec 2026-10-30-object-identity, ruling 7). The id names nothing outside
#             one resolve and the export leaves it out, so the bundle's columns are
#             unchanged; a workspace of the older vintage has rows with no id, which no
#             pass could find again, so it is refused and re-analysed.
#     12      `endpoints` gains `served_by`: the class that serves a row — the type its
#             prefix and gate were composed with, which for a mapping a controller
#             inherits without overriding (and an inherited exposed member) is the
#             subclass, not the base declaring the handler. `endpoint_conditions` and the
#             documents read the row's bean there, because Spring reads a bean's
#             conditions off the class it registers and `@Conditional` is not
#             `@Inherited` (spec 2026-10-30-object-identity, ruling 8). The export carries
#             the column — it names a class, which means something outside the run. A
#             workspace of the older vintage has no serving class, and would read every
#             inherited row's conditions off the base, so it is refused and re-analysed.
#
#   boundary vocabulary
#     1       the first generation (spec 2026-10-22-boundary-vocabulary-and-diff, FR-21):
#             seven kinds — `module`, `endpoint`, `dependency`, `data-contract`,
#             `boundary-property`, `schedule`, `error-handler` — each with the columns that
#             IDENTIFY an entry, the ones that are its ATTRIBUTES and the ones that are
#             EVIDENCE. It moves on its own, because adding a kind or moving a column
#             between those three sets changes what a diff or an observability map means
#             without changing a single table or fact: a consumer comparing two bundles
#             reads this stamp to know whether the same words were used on both sides.
#     2       `dependency` gains `conditions`; `conditions` is the declared
#             `{kind, expression}` set (spec 2026-10-23, rulings 2 and 3).
#     3       `schedule`'s identity gains `name`: `(handler, trigger, name)` (spec
#             2026-10-28-quartz, ruling 5). Two Quartz triggers of one kind on one job, told
#             apart only by their own names, are two entries rather than one with two
#             disagreeing expressions.
FACT_SCHEMA_VERSION = 5
GRAPH_SCHEMA_VERSION = 12
BOUNDARY_VOCABULARY_VERSION = 3
