-- The `scheduled_work` engine's rows (2O design §4a). Every decision — which
-- annotation the catalog claims, which of its attributes name a trigger at
-- all, and what the expression literally says — is made in the pass itself, in
-- Python, where the annotation-argument grammar lives; this file is handed the
-- finished rows and only inserts them. The derive_call_endpoints.sql /
-- insert_resolved_config.sql precedent for a Python-built engine.
--
-- Appends rather than replaces, the insert_open_questions.sql precedent: more
-- than one catalog contributes rows within one resolve (2O design §4a's
-- "Quartz: later catalog, same table"), so emptying the table happens once per
-- resolve in reset_scheduled_work.sql, outside this file.
--
-- NO insert-if-absent guard, unlike derive_call_endpoints.sql, and the
-- difference is a property of what the two tables hold. An endpoint row is a
-- WIRE IDENTITY, which two catalogs can legitimately describe twice and which
-- must collapse to one. A scheduled row is a DECLARATION — this method, this
-- trigger, this expression — and two identical ones can only come from two
-- catalogs claiming the same annotation, which is a catalog defect a silent
-- dedup would hide. The pass deduplicates its OWN rows before they reach here
-- (an annotation cannot be written twice on one method), so a duplicate that
-- survives to this table is evidence and not noise.
--
-- Parameters:
--   $rows -- {handler, trigger, name, expression, expression_source, resolution,
--            evidence, catalog_id, untied}
--            rows, one per trigger attribute the declaration writes. A
--            declaration naming no trigger at all contributes none: there is
--            no expression to carry, and a row with an empty schedule would
--            claim work the framework never runs.
INSERT INTO scheduled_work (handler, trigger, name, expression, expression_source,
                            resolution, evidence, catalog_id, untied)
SELECT r.handler, r.trigger, r.name, r.expression, r.expression_source, r.resolution,
       r.evidence, r.catalog_id, r.untied
FROM (SELECT UNNEST(
    $rows::STRUCT(
        handler VARCHAR, trigger VARCHAR, name VARCHAR, expression VARCHAR,
        expression_source VARCHAR, resolution VARCHAR, evidence VARCHAR, catalog_id VARCHAR,
        untied VARCHAR[]
    )[]
) AS r);
