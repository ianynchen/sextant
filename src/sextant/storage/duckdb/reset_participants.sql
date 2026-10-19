-- Replaced WHOLE per `system analyze`, the `endpoint_metadata` discipline: this table
-- states which participants ONE run could read, and a row surviving from a previous run
-- would claim a participant that may no longer be in the reactor at all.
DELETE FROM participants;
