-- The `error_advice` engine's rows (2O design §4b). The
-- insert_scheduled_work.sql twin: every decision — which classes are handler
-- containers, which methods are handlers, which exceptions a handler names and
-- where its status came from — is made in the pass, in Python, and this file
-- only inserts.
--
-- Appends rather than replaces, and the reset lives in the pipeline, for the
-- reason reset_error_handlers.sql states.
--
-- Parameters:
--   $rows -- {handler, advice, declared_by, scope, exception, status,
--            response_shape, resolution, evidence, catalog_id} rows, one per
--            (handler, exception) pair. `scope` arrives as JSON TEXT, already
--            serialized and key-sorted by the pass, and is cast to JSON here
--            so the column holds a document rather than a string — the
--            insert_open_questions.sql precedent for `candidates`.
INSERT INTO error_handlers (
    handler, advice, declared_by, scope, exception, status, response_shape,
    resolution, evidence, catalog_id
)
SELECT r.handler, r.advice, r.declared_by, r.scope::JSON, r.exception, r.status,
       r.response_shape, r.resolution, r.evidence, r.catalog_id
FROM (SELECT UNNEST(
    $rows::STRUCT(
        handler VARCHAR, advice VARCHAR, declared_by VARCHAR, scope VARCHAR,
        exception VARCHAR, status VARCHAR, response_shape VARCHAR,
        resolution VARCHAR, evidence VARCHAR, catalog_id VARCHAR
    )[]
) AS r);
