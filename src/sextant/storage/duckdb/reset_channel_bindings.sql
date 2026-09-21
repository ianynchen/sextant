-- Spec 2026-09-21 §3b: the channel EDGE as data — who feeds a named in-process channel
-- (`fed_by`: an adapter or flow that captured the channel and the destination behind
-- it), who reads it (`read_by`: a handler whose annotation names it), and the slot for
-- later writers (`sends_to`). Written by more than one engine, joined once per resolve
-- by `resolve/channel_bindings.py` into endpoint rows, and read by `config_join.gaps`,
-- which asks only about a channel nothing fed.
--
-- A TEMP table rather than a table `schema.sql` declares, for `route_requirements`'
-- reason: it lives for the one resolve that reads it, is replaced by the next, and never
-- reaches the workspace file or an export bundle (`DuckDbWorkspace.schema_objects` leaves
-- it out by name). Replaced WHOLE, once per resolve, from `derive_endpoints` beside
-- `endpoints_reset` — several catalogs write it, so a reset owned by one engine would
-- erase whichever ran first.
CREATE OR REPLACE TEMP TABLE channel_bindings (
    channel TEXT, role TEXT, symbol TEXT, protocol TEXT, direction TEXT, destination TEXT,
    catalog_id TEXT, resolution TEXT
);
