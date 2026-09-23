-- F3 §4.2. One row per (class, name, descriptor) an EFFECTIVE CALL SITE names — not per
-- method declared, which would be the hierarchy's cross product for no reader's benefit,
-- and not per triple the bytecode wrote: a `$default` bridge is re-targeted to the
-- sibling it stands for before the writer asks (spec 2026-09-22 §1a).
-- `reason` is always present: the single word this table replaces meant four things.
INSERT INTO method_resolution (class, name, descriptor, declaring_class, reason)
SELECT r.class, r.name, r.descriptor, r.declaring_class, r.reason
FROM (SELECT UNNEST(
    $rows::STRUCT(
        class VARCHAR, name VARCHAR, descriptor VARCHAR,
        declaring_class VARCHAR, reason VARCHAR
    )[]
) AS r);
