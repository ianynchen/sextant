-- Replaced WHOLE per resolve, the `endpoint_metadata` discipline: a condition row surviving
-- from a previous pass would state it about a bean that may no longer carry it.
DELETE FROM bean_conditions;
-- The interface beans are the same pass's, replaced with it.
DELETE FROM interface_beans;
