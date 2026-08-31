-- Clears resolved_config for one resolve. Mirrors reset_endpoints.sql /
-- reset_shapes.sql: the table itself is never dropped (schema.sql
-- pre-declares it), and this runs exactly once per resolve, unconditionally
-- before resolve_config's per-model inserts (`resolve/config.py`) — so a
-- resolve with no declared config_model, or no config facts at all, still
-- leaves an empty table rather than a stale previous run's rows (2F design
-- §2).
DELETE FROM resolved_config;
