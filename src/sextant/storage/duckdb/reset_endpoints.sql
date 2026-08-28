-- Clears the endpoint table for one resolve. `derive_endpoints.sql` appends,
-- because D02 §5 has two catalogs both matching and both producing endpoints;
-- the whole-table rebuild therefore happens once per resolve, here, rather
-- than once per catalog. The table itself is never dropped: schema.sql
-- pre-declares it so the "endpoints" query still succeeds when capability
-- gating skips every catalog and no derivation runs at all.
DELETE FROM endpoints;
