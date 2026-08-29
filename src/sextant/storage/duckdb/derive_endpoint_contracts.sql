-- Points each endpoint at the wire descriptors its owner declares (D01 §3
-- Contracts, as amended).
--
-- Nothing is decided here. Which parameter carries the request payload, and
-- what a return type unwraps to, are both catalog knowledge applied in the
-- pass; this file is handed the finished answer, keyed on the owner symbol.
-- `request_shape` and `response_shape` hold the recursive
-- `{wire_type, wire_format, nullable, shape_id?, item?}` descriptor, never a
-- bare shape id — a collection payload now carries what it holds, and a
-- scalar is recorded rather than dropped. NULL means exactly *no payload*: a
-- `void` return, or no body parameter.
--
-- Keyed on `coalesce(handler, caller)` rather than on the wire identity
-- because the signature is what the shapes come from: one handler mapped to
-- eight methods (an annotation that names none) is eight rows sharing one
-- signature, and all eight carry the same contract. The coalesce is what
-- lets an outbound row — `caller` set, `handler` NULL (D01 §3, amended) —
-- receive contracts alongside an inbound one. A row whose owner this run has
-- no answer for keeps its NULL — that is the answer for a response with no
-- field list, and an invented shape row would be noise presented as fact.
--
-- Parameters:
--   $contracts -- {handler, request_shape, response_shape} rows, one per
--                 owner (handler or caller) with at least one rooted payload
UPDATE endpoints
SET request_shape  = c.request_shape,
    response_shape = c.response_shape
FROM (SELECT UNNEST(
    $contracts::STRUCT(handler VARCHAR, request_shape VARCHAR, response_shape VARCHAR)[]
) AS c)
WHERE coalesce(endpoints.handler, endpoints.caller) = c.handler;
