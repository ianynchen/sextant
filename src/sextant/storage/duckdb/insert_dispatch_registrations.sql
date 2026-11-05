-- `resolve/dispatch_registrations.py`'s rows (spec 2026-11-05 §3). Every decision — which
-- calls make one group, each registration's place in it, what each argument means, the match
-- rule — is made in the pass; this file is handed the finished rows and only inserts them.
-- The insert_hops.sql precedent for a Python-built derivation.
--
-- Parameters:
--   $rows -- {group, position, key_type, key_value, key_object, predicated, handler,
--             delivers, match} rows, one per registration; `group` and `handler`
--             module-prefixed, `handler` NULL where the handler argument names no method.
INSERT INTO dispatch_registrations (
    "group", position, key_type, key_value, key_object, predicated, handler, delivers, match
)
SELECT r."group", r.position, r.key_type, r.key_value, r.key_object, r.predicated, r.handler,
       r.delivers, r.match
FROM (SELECT UNNEST(
    $rows::STRUCT(
        "group" VARCHAR, position INTEGER, key_type VARCHAR, key_value VARCHAR,
        key_object VARCHAR, predicated BOOLEAN, handler VARCHAR, delivers BOOLEAN,
        match VARCHAR
    )[]
) AS r);
