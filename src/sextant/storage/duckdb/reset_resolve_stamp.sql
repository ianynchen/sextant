-- Empties `resolve_stamp` before a resolve runs (OI-325): a resolve that stops part-way
-- leaves tables no stamp vouches for, so the next run resolves again.
DELETE FROM resolve_stamp;
