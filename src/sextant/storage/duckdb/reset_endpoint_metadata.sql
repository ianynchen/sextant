-- Replaced WHOLE per resolve, the `type_hierarchy`/`call_edges` discipline: this table
-- states what one pass read off one set of call sites, and a row surviving from a
-- previous pass would state it about calls that are no longer there.
DELETE FROM endpoint_metadata;
