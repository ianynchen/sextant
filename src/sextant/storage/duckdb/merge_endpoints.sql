-- D02 §3: a wire identity a module both exposes and calls is one endpoint,
-- direction `both`, keeping the server's handler and gaining the client's
-- caller (D01 §3 as amended — identity is minted without direction, so this
-- merge changes a property, never an identity). Runs once per resolve, after
-- every catalog. arg_min(caller, caller) picks deterministically when several
-- callers reach one exposed path (NFR-1) — the surviving signature is the
-- handler's, which is the richer side, the shapes pass reads it from this row.
--
-- What arg_min(<column>, caller) does with the other three carried columns,
-- stated precisely (fix round 1, M-4 — the previous wording here claimed more
-- than the SQL delivers): DuckDB's arg_min SKIPS a row whose value argument is
-- NULL, so each column is the answer of the lowest-named caller THAT HAS ONE,
-- not of the single caller `caller` above chose. Three consequences, all
-- intended:
--   * it is deterministic — one caller ordering, one answer, every run (NFR-1);
--   * it prefers a real answer to a NULL one, which is what makes carrying
--     worth doing at all: an independent min() over each column would be
--     equally non-NULL-seeking but could reorder differently per column;
--   * it MAY therefore pair the chosen caller with a different caller's peer,
--     media or format, where several callers reach one exposed path and only
--     some of them answered that column — including, for the two format
--     columns below, a `format` from one caller beside a `format_resolution`
--     from another. A row that says "some client of this path
--     declared this peer" is the honest reading, and the alternative — the
--     chosen caller's own NULL — would discard a real observation to preserve
--     a per-row consistency nothing downstream relies on.
--
-- The two media columns are carried for the reason `peer` is: the twin is
-- about to be DELETED, so anything it alone answered is lost with it unless
-- the surviving row takes it. D02 §3 calls `consumes`/`produces` "carried
-- data, never identity — dedup and merge never *compare* these two columns";
-- carrying is not comparing, and the coalesce keeps the surviving row's own
-- answer whenever it has one (the same first-writer discipline every media
-- evidence kind follows). Without this, a module-level `produces` stamped on
-- the outbound half of a path the module both exposes and calls vanished into
-- the merge, leaving a `both` row that read as "no producer declared" —
-- indistinguishable from a module that declares none.
--
-- The two FORMAT columns are carried for the same reason and by two
-- different rules (2G design §4). `format` coalesces exactly as the media
-- columns do — the surviving row's own answer, else the twin's.
-- `format_resolution` does NOT: it takes the WEAKER of the two markers that
-- are present, ordering `unresolved` < `narrowed` < `resolved`, so a half
-- that only guessed can never launder into an observation by being merged
-- with a half that knew. Where only one half carries a marker, that one is
-- the answer; where neither does, the result stays NULL.
--
-- **What this delivers TODAY, stated plainly** (the honesty bar the media
-- comment above sets): nothing. `resolve/format.py` is the LAST pass of a
-- resolve and this merge is the last statement of `derive_endpoints`, so
-- both format columns are still NULL on every row when this runs, and every
-- branch below evaluates to NULL. It is written because the columns are part
-- of the row and the merge deletes the twin: the day anything stamps a
-- format before the merge — a derivation that reads it off a declaration, a
-- reordered pipeline — a silently discarded half would be the failure mode,
-- and it would look exactly like a module that declared no format.
UPDATE endpoints e
SET direction = 'both',
    caller = twins.caller,
    peer   = coalesce(e.peer, twins.peer),
    consumes = coalesce(e.consumes, twins.consumes),
    produces = coalesce(e.produces, twins.produces),
    format = coalesce(e.format, twins.format),
    format_resolution = CASE
        WHEN e.format_resolution IS NULL THEN twins.format_resolution
        WHEN twins.format_resolution IS NULL THEN e.format_resolution
        WHEN 'unresolved' IN (e.format_resolution, twins.format_resolution)
            THEN 'unresolved'
        WHEN 'narrowed' IN (e.format_resolution, twins.format_resolution)
            THEN 'narrowed'
        ELSE e.format_resolution END
FROM (
    SELECT protocol, method, path,
           arg_min(caller, caller) AS caller,
           arg_min(peer, caller) AS peer,
           arg_min(consumes, caller) AS consumes,
           arg_min(produces, caller) AS produces,
           arg_min(format, caller) AS format,
           arg_min(format_resolution, caller) AS format_resolution
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
