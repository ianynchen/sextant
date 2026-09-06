SEXTANT_VERSION = "0.1.0"
# 1.1.0 (2O Task 4): `DeclaredShapeFact` gains the optional `operation`
# sub-record (D00 §5's amendment note carries the estate cost — re-analysis
# of existing workspaces, accepted pre-gate: every fact file already on disk
# still validates, with the new field simply absent).
FACT_SCHEMA_VERSION = "1.1.0"
# 1.1.0 (2Q `G4`/`I3`, moved by the change that gave the walk a reader): the
# derived set gained `roots` and `call_edges`, and `## Traces` now renders from
# them. Purely additive, so a 1.0.0 workspace holds no wrong row — it holds
# NO row, and an empty `roots` reads as a module nothing starts work in rather
# than as a workspace derived before the table existed. That is the difference
# a stamp exists to catch, and `api._stale_stamps` now catches it (OI-24).
#
# 1.2.0 (2Q close, defect 1): `roots` gains `protocol`/`method`/`path` and its
# ROW grain moves from (handler, kind) to (handler, kind, address), so a trace
# can be named by the address a reader searches for. NOT additive in the sense
# 1.1.0 was: a 1.1.0 workspace's rows have no address columns at all, so the
# query reading them fails rather than answering empty — the stamp refuses such
# a workspace first, which is the whole point of comparing it.
GRAPH_SCHEMA_VERSION = "1.2.0"
