-- Replaced WHOLE per resolve (OI-368), the `endpoint_metadata` discipline: an entry states
-- where a row of this resolve exists, and one surviving from a previous resolve would state it
-- about a row that is no longer there.
DELETE FROM endpoint_existence;
