-- `resolve/resolved_schedules.py`'s rows (spec 2026-10-23-configured-schedules
-- §3b). Every decision — which jobs hold a placeholder, the delimiters and
-- `:default` of the config model, relaxed or exact key matching — is made in the
-- pass, through `resolve/config.py::substitute`, the project's one placeholder
-- rule; this file is handed the finished rows and only inserts them. The
-- insert_resolved_config.sql / insert_scheduled_work.sql precedent for a
-- Python-built derivation.
--
-- Parameters:
--   $rows -- {handler, trigger, expression, environment, value, unresolved_reason}
--             rows, one per (placeholder job, environment of `resolved_config`); the
--             first three are the job's `scheduled_work` columns verbatim. `value` is
--             NULL exactly when `unresolved_reason` is set, one of D01's closed set.
INSERT INTO resolved_schedules (handler, trigger, expression, environment, value,
                                unresolved_reason)
SELECT r.handler, r.trigger, r.expression, r.environment, r.value, r.unresolved_reason
FROM (SELECT UNNEST(
    $rows::STRUCT(
        handler VARCHAR, trigger VARCHAR, expression VARCHAR, environment VARCHAR,
        value VARCHAR, unresolved_reason VARCHAR
    )[]
) AS r);
