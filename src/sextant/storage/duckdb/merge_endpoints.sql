-- D02 §3: a wire identity a module both exposes and calls is one endpoint,
-- direction `both`, keeping the server's handler and gaining the client's
-- caller (D01 §3 as amended — identity is minted without direction, so this
-- merge changes a property, never an identity). Runs once per resolve, after
-- every catalog. min() picks deterministically when several callers reach one
-- exposed path (NFR-1); the surviving signature is the handler's, which is
-- the richer side — the shapes pass reads it from this row.
UPDATE endpoints e
SET direction = 'both',
    caller = twins.caller,
    peer   = coalesce(e.peer, twins.peer)
FROM (
    SELECT protocol, method, path, min(caller) AS caller, min(peer) AS peer
    FROM endpoints
    WHERE direction = 'outbound'
    GROUP BY protocol, method, path
) twins
WHERE e.direction = 'inbound'
  AND e.protocol = twins.protocol
  AND e.method   = twins.method
  AND e.path     = twins.path;

DELETE FROM endpoints o
WHERE o.direction = 'outbound'
  AND EXISTS (
    SELECT 1 FROM endpoints b
    WHERE b.direction = 'both'
      AND b.protocol = o.protocol
      AND b.method   = o.method
      AND b.path     = o.path
  );
