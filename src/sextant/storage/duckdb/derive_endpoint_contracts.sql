-- Points each endpoint at the shapes its handler declares (D01 §3 Contracts).
--
-- Nothing is decided here. Which parameter carries the request payload, and
-- what a return type unwraps to, are both catalog knowledge applied in the
-- pass; this file is handed the finished answer, keyed on the handler symbol.
--
-- Keyed on `handler` rather than on the wire identity because the signature is
-- what the shapes come from: one handler mapped to eight methods (an
-- annotation that names none) is eight rows sharing one signature, and all
-- eight carry the same contract. A row whose handler this run has no answer
-- for keeps its NULL — that is the answer for a response with no field list,
-- and an invented shape row would be noise presented as fact.
--
-- Parameters:
--   $contracts -- {handler, request_shape, response_shape} rows, one per handler
--                 with at least one rooted payload
UPDATE endpoints
SET request_shape  = c.request_shape,
    response_shape = c.response_shape
FROM (SELECT UNNEST(
    $contracts::STRUCT(handler VARCHAR, request_shape VARCHAR, response_shape VARCHAR)[]
) AS c)
WHERE endpoints.handler = c.handler;
