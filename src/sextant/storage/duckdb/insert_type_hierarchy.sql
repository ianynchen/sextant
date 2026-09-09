-- F3 §4.2. One row per (child, direct ancestor), in JVMS 5.4.3.3's search order —
-- `position` 0 is the superclass, then each declared interface as the class file lists
-- them. `scanned` is what separates "external boundary" from "unresolved".
INSERT INTO type_hierarchy (child, ancestor, kind, position, scanned)
SELECT r.child, r.ancestor, r.kind, r.position, r.scanned
FROM (SELECT UNNEST(
    $rows::STRUCT(
        child VARCHAR, ancestor VARCHAR, kind VARCHAR, position INTEGER, scanned BOOLEAN
    )[]
) AS r);
