-- Replaced WHOLE per `system analyze`, for `reset_participants.sql`'s reason: a link is a
-- statement about two endpoints as ONE run read them, and a survivor would assert a
-- dependency between rows that may have changed on either side.
DELETE FROM links;
