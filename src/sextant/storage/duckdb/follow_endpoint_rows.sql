-- Follow-the-object, Ruling 7: an entry attached to an `endpoints` row follows that row,
-- by the `row_id` it was bound to when it was written, through every pass that moves or
-- removes the row after it was minted.
--
-- Nothing is decided here. Which rows move, and where to, is decided by the pass that just
-- ran (`resolve/endpoints.py` after the borrowed-row drop, `resolve/path_prefix.py`,
-- `resolve/protocol_hint.py`, `resolve/self_calls.py`, `resolve/dispatch_hops.py`); this
-- file only brings the attached entries back into line with the rows as they now stand. No
-- parameters, so it is the same statement after every one of them — a pass that rewrites a
-- row's identity runs it rather than restating, column by column, what it moved.
--
-- **The identity columns are copied from the row**, not recomputed: `endpoint_metadata`
-- carries them beside `row_id` because the bundle leaves the id out and a reader outside the
-- run joins on them, so they must say what the row says. `caller` is not copied — no pass
-- rewrites a row's `handler` or `caller` in place: the key-handler pass
-- (`record_key_handlers`) removes a key row and inserts one per handler under new ids, and an
-- entry bound to the removed row goes with it below (a key row carries none: it reads no
-- url). Only entries that differ are touched, so a row nothing moved costs nothing.
--
-- **An entry whose row is gone goes with it.** A row the self-call pass removed is not an
-- outbound call, nor is a reactor sibling's row the borrowed-row drop removed, and an entry
-- stating what that call sends would describe a row no reader can find. An entry bound to NO row (`row_id` NULL: nothing matched when it was written) is left
-- as it was — it never followed a row, so no pass can have moved it.
UPDATE endpoint_metadata m
SET protocol  = e.protocol,
    direction = e.direction,
    method    = e.method,
    path      = e.path
FROM endpoints e
WHERE m.row_id = e.row_id
  AND (
      m.protocol  IS DISTINCT FROM e.protocol
      OR m.direction IS DISTINCT FROM e.direction
      OR m.method    IS DISTINCT FROM e.method
      OR m.path      IS DISTINCT FROM e.path
  );

DELETE FROM endpoint_metadata m
WHERE m.row_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM endpoints e WHERE e.row_id = m.row_id);

-- The same for `endpoint_existence` (OI-368): an entry states where its row exists, so it
-- carries the row's identity as the row now stands, and goes with a row that is gone. Its
-- `handler` and `caller` are not copied, for the reason given above.
UPDATE endpoint_existence x
SET protocol  = e.protocol,
    direction = e.direction,
    method    = e.method,
    path      = e.path
FROM endpoints e
WHERE x.row_id = e.row_id
  AND (
      x.protocol  IS DISTINCT FROM e.protocol
      OR x.direction IS DISTINCT FROM e.direction
      OR x.method    IS DISTINCT FROM e.method
      OR x.path      IS DISTINCT FROM e.path
  );

DELETE FROM endpoint_existence x
WHERE NOT EXISTS (SELECT 1 FROM endpoints e WHERE e.row_id = x.row_id);
