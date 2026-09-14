-- The second half of the annotation_driven engine (D02 §2): one catalog's rows,
-- out of the `endpoint_candidates` table `derive_endpoints.sql` derived for the
-- whole batch, into `endpoints` — run once per catalog, at that catalog's own
-- turn in `resolve/endpoints.py::derive_endpoints`'s order.
--
-- EARLIER CATALOG WINS, and this is where it is decided. D02 §5 lets two
-- catalogs match the same module; rows already present for the same wire
-- identity — protocol, direction, method and path — are the duplicates that
-- section says merge, so a candidate whose identity is already in the table is
-- not inserted. Which catalog's row that is depends only on the ORDER the
-- catalogs took their turns in, which is why the guard sits in a statement
-- that runs at each turn rather than in the one that derives every catalog's
-- rows at once: the other engines' catalogs run between annotation-driven
-- ones (the order is by filename within a direction), and a wire identity one
-- of them minted in between must refuse a later annotation-driven catalog's
-- row exactly as it always did. Rows minted at THIS turn do not refuse each
-- other — the guard reads the table as it stood when the statement began —
-- which is what lets two handlers of one route differing only in media (a
-- content-negotiation pair) both stand, as they always have.
--
-- AN OUTBOUND ROW IS PER CALLER AND PEER (F5 §6.1 rule 1, W27; A2 Task 8 fix
-- round 1). Wire identity is the whole comparison for an INBOUND row — a served
-- route is one route however many catalogs describe it — but a call is made
-- by a method to an address, and `derive_call_endpoints.sql` has compared
-- `caller` and `peer` too since W27 for exactly that reason. This statement
-- did not, so an annotation-driven client (`@FeignClient`'s `POST /v1/orders`)
-- was REFUSED whenever a call-side catalog earlier in the order had derived
-- the same identity from a DIFFERENT method — measured on `orders-service`:
-- `OrdersLoopClient#createOrder`'s row vanished the moment `JdkOrdersClient`
-- called the same path, no row, no gap. So for `direction = 'outbound'` the
-- match requires the same caller and peer as well (`IS NOT DISTINCT FROM`,
-- either may be NULL), and earlier-catalog-wins still holds for two catalogs
-- describing ONE method's call. Inbound is unchanged.
--
-- Parameters:
--   $catalog_id -- the catalog whose turn it is.
INSERT INTO endpoints (
    protocol, direction, method, path, handler, caller, peer,
    handler_signature, resolution, evidence, catalog_id, consumes, produces
)
SELECT d.protocol, d.direction, d.method, d.path, d.handler, d.caller, d.peer,
       d.handler_signature, d.resolution, d.evidence, d.catalog_id, d.consumes, d.produces
FROM endpoint_candidates d
WHERE d.catalog_id = $catalog_id
  AND NOT EXISTS (
    SELECT 1 FROM endpoints existing
    WHERE existing.protocol  = d.protocol
      AND existing.direction = d.direction
      AND existing.method IS NOT DISTINCT FROM d.method
      AND existing.path      = d.path
      AND (
          d.direction <> 'outbound'
          OR (
              existing.caller IS NOT DISTINCT FROM d.caller
              AND existing.peer IS NOT DISTINCT FROM d.peer
          )
      )
);
