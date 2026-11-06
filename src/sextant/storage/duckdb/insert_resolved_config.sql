-- resolve/config.py's M04 pass 2 — a generic interpreter over a
-- catalog-declared config_model (D02 §2i). Every decision (source-pattern
-- matching, profile enumeration from both mechanisms, layering order,
-- recursive placeholder substitution with `:default` and a cycle guard) is
-- made in the pass itself, in Python, over the `config_entries` and
-- `documents` named queries — this file only inserts the finished rows,
-- the same call_endpoints.sql / derive_call_endpoints.sql precedent for a
-- Python-built engine's STRUCT-parameter insert.
--
-- Parameters:
--   $rows -- {key, value, source, environment, unresolved_reason,
--             unresolved_detail} rows, one per key per profile the pass resolved
--             (D01: "resolved_config is one row per key per environment"). `value`
--             is NULL exactly when `unresolved_reason` is set, one word of the
--             general reason list (`values._REASONS`); `unresolved_detail` says where,
--             for a person.
INSERT INTO resolved_config (key, value, source, environment, unresolved_reason,
                             unresolved_detail)
SELECT r.key, r.value, r.source, r.environment, r.unresolved_reason, r.unresolved_detail
FROM (SELECT UNNEST(
    $rows::STRUCT(
        key VARCHAR, value VARCHAR, source VARCHAR, environment VARCHAR,
        unresolved_reason VARCHAR, unresolved_detail VARCHAR
    )[]
) AS r);
