-- F3 §4.2. One row per (class, name, descriptor) an EFFECTIVE CALL SITE names — not per
-- method declared, which would be the hierarchy's cross product for no reader's benefit,
-- and not per triple the bytecode wrote: a `$default` bridge is re-targeted to the
-- sibling it stands for before the writer asks (spec 2026-09-22 §1a).
-- `reason` and `detail` are NULL for a found body; otherwise one general reason and a
-- sentence for a person (spec 2026-11-05 §3b).
INSERT INTO method_resolution (class, name, descriptor, declaring_class, reason, detail)
SELECT r.class, r.name, r.descriptor, r.declaring_class, r.reason, r.detail
FROM (SELECT UNNEST(
    $rows::STRUCT(
        class VARCHAR, name VARCHAR, descriptor VARCHAR,
        declaring_class VARCHAR, reason VARCHAR, detail VARCHAR
    )[]
) AS r);
