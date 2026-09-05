-- The call-site engines (D02 §2's single_call and §4's fluent) — one call
-- carries the whole declaration, or several chained calls do, so — unlike
-- derive_endpoints.sql's SQL-side joins over annotation facts —
-- every decision (which call sites the catalog's own `matches` block claims,
-- the verb, the url/peer split, the one-hop payload follow through a
-- `call_wrappers` constructor or a `type_carriers` supertype) is made in the
-- pass itself, in Python, where the argument-resolution grammar lives. This
-- file is handed the finished rows and only inserts them.
--
-- Same insert-if-absent discipline as derive_endpoints.sql, on the same wire
-- identity (protocol, direction, method, path): D02 §5's duplicates merge
-- rather than double-insert, whether the duplicate comes from another
-- catalog or from a later resolve. Two identical calls within one method are
-- deduplicated by the pass itself before rows ever reach this file — DuckDB
-- evaluates this statement's NOT EXISTS against the table as it stood before
-- the statement began, so two same-identity rows in one `$rows` batch would
-- both insert if the pass had not already collapsed them.
--
-- `path` may be SQL NULL (an unresolved url argument, D02 §2's `single_call`
-- rule): two unresolved calls never dedup against each other here, because
-- SQL's `NULL = NULL` is unknown rather than true — each is still a distinct,
-- real "this method calls something" fact from its own call site.
--
-- Parameters:
--   $rows -- {protocol, direction, method, path, handler, caller, peer,
--             handler_signature, resolution, evidence, catalog_id,
--             request_shape, response_shape, consumes, produces} rows, one
--             per matching call site, already deduplicated on wire identity
--             by the pass. `catalog_id` (2E-prep design §1a) is the id of
--             the catalog that built the row — provenance only, never part
--             of wire identity. `consumes`/`produces` (2E design §4) are
--             carried data, never identity — every engine but Task 5's
--             Spring pass passes NULL for both.
INSERT INTO endpoints (
    protocol, direction, method, path, handler, caller, peer,
    handler_signature, resolution, evidence, catalog_id, request_shape, response_shape,
    consumes, produces
)
SELECT r.protocol, r.direction, r.method, r.path, r.handler, r.caller, r.peer,
       r.handler_signature, r.resolution, r.evidence, r.catalog_id, r.request_shape,
       r.response_shape, r.consumes, r.produces
FROM (SELECT UNNEST(
    $rows::STRUCT(
        protocol VARCHAR, direction VARCHAR, method VARCHAR, path VARCHAR,
        handler VARCHAR, caller VARCHAR, peer VARCHAR, handler_signature VARCHAR,
        resolution VARCHAR, evidence VARCHAR, catalog_id VARCHAR,
        request_shape VARCHAR, response_shape VARCHAR, consumes VARCHAR, produces VARCHAR
    )[]
) AS r)
-- THE ADDRESSES-NOTHING GATE, mechanism 3's twin on the call-site side.
--
-- `derive_endpoints.sql` has carried one since `A-C1`: a row whose address is
-- empty and whose `peer` is NULL names no endpoint, and publishing one at
-- `resolved`/`compiler` presents a boundary the running system does not serve
-- as an observation. This file had none, and the asymmetry was live —
-- `combinator` sets `resolution: resolved` whenever nothing poisoned the read,
-- and `_path_of` returns NULL when a folded route accumulated no path part, so
-- `RouterFunctions.route(RequestPredicates.accept("application/json"), h)`
-- inserted exactly that row. NULL paths also skip the dedup key below (SQL's
-- `NULL = NULL` is unknown), so N such routes inserted N of them.
--
-- SCOPED TO `resolved`, and the scope is the whole difference between this
-- gate and a silent under-report. An `unresolved` row with no path is a real,
-- distinct fact — "this method calls something whose destination nobody could
-- read" — and the paragraph above says so of the dedup for the same reason. A
-- `resolved` row with no path is the opposite: it claims the address was read
-- and that there is none. `derive_endpoints.sql`'s twin needs no such scope
-- only because its `path` is a composed string that is never NULL, and its
-- one `unresolved` shape (an expression) always carries the expression text.
--
-- A `peer` alone is still an address: a client chain that resolved a host and
-- no path is a call to that service's base address, which is real.
--
-- AND `path IS NULL` RATHER THAN `coalesce(path, '') = ''`, which is the
-- narrower reading on purpose. On this side a `path` is either an address an
-- engine READ or NULL, and the two say different things: NULL is "nothing here
-- names an address", while the empty STRING is an address that was read and is
-- empty. Whether an empty address is real is a protocol question
-- `domain/paths.py` owns — `canonical_http_path` already spells an empty
-- inbound-HTTP address `/`, so `combinator` cannot produce one — and at least
-- one shipped catalog can: `supertype_dispatch` publishes its patterns
-- verbatim (CP-9), so `@WebServlet(urlPatterns = "")`, which the Servlet
-- specification defines as the exact-match context-root pattern, arrives here
-- as `''`. What we should publish for that has been measured by no probe, and
-- dropping it here would be answering an unmeasured question by side effect.
-- `derive_endpoints.sql`'s twin does test the empty string, and correctly: its
-- `path` is a COMPOSED string that is never NULL, and its canonical gate has
-- already spelled a real root route `/` by the time the test runs.
--
-- This stops being right the day an engine can derive a row whose identity is
-- carried by neither `path` nor `peer` — a protocol addressed by something
-- else entirely — at which point the answer belongs beside `serves_urls` in
-- `domain/paths.py`, where the protocol question already lives.
WHERE NOT (r.resolution = 'resolved' AND r.path IS NULL AND r.peer IS NULL)
  AND NOT EXISTS (
    SELECT 1 FROM endpoints existing
    WHERE existing.protocol  = r.protocol
      AND existing.direction = r.direction
      AND existing.method IS NOT DISTINCT FROM r.method
      AND existing.path      = r.path
);
