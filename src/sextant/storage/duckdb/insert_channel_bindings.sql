-- Spec 2026-09-21 §3b. One row per channel edge an engine read: `role` says which end
-- (`fed_by`, `read_by`, `sends_to`), `symbol` the method at that end, `direction` the
-- direction the edge means for the row it may become, and `protocol`/`destination`
-- what the feeding end knows about the wire behind the channel (NULL on a reader —
-- a reader knows the channel's name and nothing about the wire). `resolution` is
-- ROLE-DEPENDENT: on `read_by` it is the channel NAME's — a name spelled as a
-- placeholder that configuration never answered stays as written, `unresolved`, and
-- joins nothing; on `fed_by` it is the WIRE's — the edge stands in for the row the
-- chain would have written, so an unread destination is an `unresolved` edge that
-- mints an `unresolved` row (D01 §3). Appended per engine run; the reset is the
-- pipeline's.
INSERT INTO channel_bindings (
    channel, role, symbol, protocol, direction, destination, catalog_id, resolution
)
SELECT r.channel, r.role, r.symbol, r.protocol, r.direction, r.destination,
       r.catalog_id, r.resolution
FROM (SELECT UNNEST(
    $rows::STRUCT(
        channel VARCHAR, role VARCHAR, symbol VARCHAR, protocol VARCHAR, direction VARCHAR,
        destination VARCHAR, catalog_id VARCHAR, resolution VARCHAR
    )[]
) AS r);
