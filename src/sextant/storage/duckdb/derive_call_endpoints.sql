-- The single_call engine (D02 §2): one call carries the whole declaration,
-- so — unlike derive_endpoints.sql's SQL-side joins over annotation facts —
-- every decision (which call sites match the catalog's `owner`/`methods`,
-- the verb, the url/peer split, the one-hop payload follow through a
-- `call_wrappers` constructor or a `type_carriers` supertype) is made in the
-- pass itself, in Python, where the argument-resolution grammar lives. This
-- file is handed the finished rows and only inserts them.
--
-- Same insert-if-absent discipline as derive_endpoints.sql, on the same wire
-- identity (protocol, direction, method, path): D02 §5's duplicates merge
-- rather than double-insert, whether the duplicate comes from another
-- catalog or from a later resolve. Two identical calls within one method are
-- deduplicated by the pass itself before rows ever reach this file — DuckDB
-- evaluates this statement's NOT EXISTS against the table as it stood before
-- the statement began, so two same-identity rows in one `$rows` batch would
-- both insert if the pass had not already collapsed them.
--
-- `path` may be SQL NULL (an unresolved url argument, D02 §2's `single_call`
-- rule): two unresolved calls never dedup against each other here, because
-- SQL's `NULL = NULL` is unknown rather than true — each is still a distinct,
-- real "this method calls something" fact from its own call site.
--
-- Parameters:
--   $rows -- {protocol, direction, method, path, handler, caller, peer,
--             handler_signature, resolution, evidence, request_shape,
--             response_shape} rows, one per matching call site, already
--             deduplicated on wire identity by the pass
INSERT INTO endpoints (
    protocol, direction, method, path, handler, caller, peer,
    handler_signature, resolution, evidence, request_shape, response_shape
)
SELECT r.protocol, r.direction, r.method, r.path, r.handler, r.caller, r.peer,
       r.handler_signature, r.resolution, r.evidence, r.request_shape, r.response_shape
FROM (SELECT UNNEST(
    $rows::STRUCT(
        protocol VARCHAR, direction VARCHAR, method VARCHAR, path VARCHAR,
        handler VARCHAR, caller VARCHAR, peer VARCHAR, handler_signature VARCHAR,
        resolution VARCHAR, evidence VARCHAR, request_shape VARCHAR, response_shape VARCHAR
    )[]
) AS r)
WHERE NOT EXISTS (
    SELECT 1 FROM endpoints existing
    WHERE existing.protocol  = r.protocol
      AND existing.direction = r.direction
      AND existing.method    = r.method
      AND existing.path      = r.path
);
