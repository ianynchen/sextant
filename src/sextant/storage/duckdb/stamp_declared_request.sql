-- The `schema_operations` style's declared-REQUEST stamp — `stamp_declared_
-- response.sql`'s sibling, and everything that file's header states about
-- what is decided where holds here unchanged: nothing is decided in SQL, the
-- pass hands over one finished descriptor per wire identity and the four
-- columns that select the rows.
--
-- **Why a second statement rather than a second column on the first**
-- (2O design §1, fix round 2's C-2). The response stamp reaches rows whose
-- `response_shape` is NULL; a row may legitimately have one column already
-- answered and the other not, and a single UPDATE writing both would have to
-- choose one guard for two independent first-writer decisions — either
-- refusing a request stamp because a response was already there, or
-- overwriting a response because a request was missing. Two statements, each
-- guarding its own column, is the same rule applied twice rather than one
-- rule that cannot express both.
--
-- **First-writer discipline lives in the WHERE clause**, exactly as
-- `stamp_declared_response.sql` and `stamp_media.sql` keep it: only a row
-- whose `request_shape` IS NULL is touched, which is `coalesce(existing,
-- declared)` written as a guard. A row another evidence kind already answered
-- keeps its own answer.
--
-- **What this actually delivers, stated rather than implied** (the same
-- honesty bar the sibling file states). Inside `derive_endpoints` every
-- annotation-derived row still carries `request_shape` NULL — the shape pass
-- runs later (`resolve/pipeline.py`) — so the rows this statement reaches
-- are the style's OWN rows and every twin another engine minted at the same
-- wire identity that has no request payload of its own. The gRPC case is
-- exactly the second: `supertype_derived` (2O design §1b) mints the identity
-- first with the handler symbol and NULL payload columns, `schema_operations`
-- runs last (`resolve/endpoints.py`'s `_RUNS_LAST`), its own insert is a
-- no-op against `derive_call_endpoints.sql`'s insert-if-absent guard, and
-- these two stamps are what carry the descriptor's half onto the row that
-- survived. Without them the merged row would be strictly THINNER than the
-- descriptor row alone, which is the defect this file closes.
--
-- A row still carrying its own `handler_signature` is re-answered later by
-- `derive_endpoint_contracts.sql`, exactly as the response sibling documents;
-- a `supertype_derived` row carries none, so the stamp stands.
--
-- Parameters:
--   $rows -- {protocol, direction, method, path, request_shape} rows, one per
--            operation identity the pass derived, already deduplicated on
--            that identity by the pass
UPDATE endpoints e
SET request_shape = r.request_shape
FROM (SELECT UNNEST(
    $rows::STRUCT(
        protocol VARCHAR, direction VARCHAR, method VARCHAR, path VARCHAR,
        request_shape VARCHAR
    )[]
) AS r)
WHERE e.protocol  = r.protocol
  AND e.direction = r.direction
  AND e.method IS NOT DISTINCT FROM r.method
  AND e.path      = r.path
  AND e.request_shape IS NULL;
