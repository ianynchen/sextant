-- Replaced WHOLE per resolve, the `call_edges` discipline: this table states what one
-- pass resolved, and a row surviving from a previous pass would state it about facts
-- that are no longer there.
DELETE FROM type_hierarchy;
