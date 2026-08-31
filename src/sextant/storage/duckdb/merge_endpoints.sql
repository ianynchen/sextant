-- D02 §3: a wire identity a module both exposes and calls is one endpoint,
-- direction `both`, keeping the server's handler and gaining the client's
-- caller (D01 §3 as amended — identity is minted without direction, so this
-- merge changes a property, never an identity). Runs once per resolve, after
-- every catalog. arg_min(caller, caller) picks deterministically when several
-- callers reach one exposed path (NFR-1) — the surviving signature is the
-- handler's, which is the richer side, the shapes pass reads it from this
-- row. arg_min(peer, caller) is keyed on that same chosen caller, so the
-- surviving peer is always that caller's own: an independent min(peer) could
-- pair one caller's signature with a different caller's peer.
-- The two media columns are carried the same way `peer` is, and for the same
-- reason: the twin is about to be DELETED, so anything it alone answered is
-- lost with it unless the surviving row takes it. D02 §3 calls
-- `consumes`/`produces` "carried data, never identity — dedup and merge never
-- *compare* these two columns"; carrying is not comparing, and the coalesce
-- keeps the surviving row's own answer whenever it has one (the same
-- first-writer discipline every media evidence kind follows). Without this, a
-- module-level `produces` stamped on the outbound half of a path the module
-- both exposes and calls vanished into the merge, leaving a `both` row that
-- read as "no producer declared" — indistinguishable from a module that
-- declares none.
UPDATE endpoints e
SET direction = 'both',
    caller = twins.caller,
    peer   = coalesce(e.peer, twins.peer),
    consumes = coalesce(e.consumes, twins.consumes),
    produces = coalesce(e.produces, twins.produces)
FROM (
    SELECT protocol, method, path,
           arg_min(caller, caller) AS caller,
           arg_min(peer, caller) AS peer,
           arg_min(consumes, caller) AS consumes,
           arg_min(produces, caller) AS produces
    FROM endpoints
    WHERE direction = 'outbound'
    GROUP BY protocol, method, path
) twins
WHERE e.direction = 'inbound'
  AND e.protocol = twins.protocol
  AND e.method IS NOT DISTINCT FROM twins.method
  AND e.path     = twins.path;

DELETE FROM endpoints o
WHERE o.direction = 'outbound'
  AND EXISTS (
    SELECT 1 FROM endpoints b
    WHERE b.direction = 'both'
      AND b.protocol = o.protocol
      AND b.method IS NOT DISTINCT FROM o.method
      AND b.path     = o.path
  );
