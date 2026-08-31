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
--
-- Restricted to a row that still carries its OWN `handler_signature` (Task
-- 10 fix): the owner-keyed join above is `coalesce(handler, caller)`, a
-- SYMBOL — and a listener method's symbol plays two different roles once a
-- `reply` block exists for it (D02 §2's amended annotation_driven engine,
-- Task 8): it is `handler` on its own INBOUND row, whose real contract this
-- update exists to fill in, and it is also `caller` on the OUTBOUND reply
-- row `_derive_replies` (annotation_driven.py) mints for it — a *different*
-- row, already carrying its own correct `request_shape`/`response_shape`
-- (the reply payload, computed off the RETURN type; `response_shape`
-- deliberately NULL, "a reply carries no response of its own"). Without
-- this guard, the reply row's own values were overwritten by its handler's
-- unrelated INBOUND contract (the received payload and the handler's return
-- type) the moment both rows shared one owner symbol — silently, since the
-- join has no way to tell "already answered by the row's own engine" apart
-- from "still NULL, waiting for this pass" once both are keyed on the same
-- symbol. `handler_signature` is exactly that tell: an annotation_driven
-- row (inbound or outbound) always carries the real declared signature
-- (`derive_endpoints.sql`'s `s.signature`) and wants the owner-keyed
-- contract; a `single_call`/`fluent` call-site row and a `reply` row both
-- set it NULL and already have their own request_shape/response_shape set
-- directly by the pass that derived them (D02 §2h; this file's own comment
-- above), so this update must leave them alone.
UPDATE endpoints
SET request_shape  = c.request_shape,
    response_shape = c.response_shape
FROM (SELECT UNNEST(
    $contracts::STRUCT(handler VARCHAR, request_shape VARCHAR, response_shape VARCHAR)[]
) AS c)
WHERE coalesce(endpoints.handler, endpoints.caller) = c.handler
  AND endpoints.handler_signature IS NOT NULL;
