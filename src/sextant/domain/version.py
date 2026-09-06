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
GRAPH_SCHEMA_VERSION = "1.1.0"
