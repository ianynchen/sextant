-- Replaced WHOLE per resolve, the `endpoint_metadata` discipline: a condition row surviving
-- from a previous pass would state it about a handler that may no longer carry it.
DELETE FROM endpoint_conditions;
