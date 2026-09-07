"""The three stamps every fact file, workspace and bundle carries, and the ONE
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
# Each increases by ONE for a change to the thing it stamps, and they move
# independently: a fact-shape change forces re-extraction (D01 §7's table calls
# it the expensive one), while a derived-table change costs only a re-derive.
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
FACT_SCHEMA_VERSION = 4
GRAPH_SCHEMA_VERSION = 2
