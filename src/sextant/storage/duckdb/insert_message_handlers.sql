-- `resolve/message_handlers.py`'s rows (spec 2026-11-04 §3b). Every decision — which calls
-- build one behavior, each case's place in it, what each argument means — is made in the
-- pass; this file is handed the finished rows and only inserts them. The insert_rpc_hops.sql
-- precedent for a Python-built derivation.
--
-- Parameters:
--   $rows -- {behavior, position, message_type, message_value, predicated, handler,
--             delivers, evidence} rows, one per case; `behavior` and `handler`
--             module-prefixed, `handler` NULL where the handler argument names no method.
INSERT INTO message_handlers (
    behavior, position, message_type, message_value, predicated, handler, delivers, evidence
)
SELECT r.behavior, r.position, r.message_type, r.message_value, r.predicated, r.handler,
       r.delivers, r.evidence
FROM (SELECT UNNEST(
    $rows::STRUCT(
        behavior VARCHAR, position INTEGER, message_type VARCHAR, message_value VARCHAR,
        predicated BOOLEAN, handler VARCHAR, delivers BOOLEAN, evidence VARCHAR
    )[]
) AS r);
