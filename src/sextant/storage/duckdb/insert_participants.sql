-- D01's system scope, first of the two native tables. One row per participant the
-- reactor names, present or absent — an ABSENT one is a row on purpose, because M06's
-- rule depends on being able to tell "a call into a participant nobody could read" from
-- "a call into nothing", and a missing row cannot say which.
--
-- A plain insert, not insert-if-absent: `reset_participants.sql` runs immediately before
-- it and one run writes each participant once. The guard on `insert_endpoint_metadata`
-- exists because three passes reach it; one pass reaches this.
INSERT INTO participants (
    name, kind, module_id, aliases, location, commit_id, present, absent_reason
)
SELECT r.name, r.kind, r.module_id, r.aliases, r.location, r.commit_id, r.present,
       r.absent_reason
FROM (SELECT UNNEST(
    $rows::STRUCT(
        name VARCHAR, kind VARCHAR, module_id VARCHAR, aliases VARCHAR,
        location VARCHAR, commit_id VARCHAR, present BOOLEAN, absent_reason VARCHAR
    )[]
) AS r);
