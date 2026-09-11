-- F8 §9.4 (W37): what each root reaches, materialised.
--
-- The rows are built in `resolve/reachability.py` from `query/trace.py`'s own
-- walk — the same function that produces a rendered trace, so the table and
-- the document cannot disagree about what is reachable. This file is handed
-- the finished rows and only inserts them, the `insert_roots.sql` precedent:
-- deciding what counts as reached, and at what depth, is the walk's rule and
-- restating any of it as SQL would be a second answer.
--
-- NO insert-if-absent guard. The pass emits one row per (root, symbol) by
-- construction — the walk expands a method once per trace, and the pass keeps
-- a `seen` set per root besides — so a duplicate arriving here is a defect in
-- the pass, and a silent dedup would hide it.
--
-- Parameters:
--   $rows -- {root, symbol, depth, terminal} rows, one per symbol a root
--            reaches, including the root itself at depth 0.
INSERT INTO reachability (root, symbol, depth, terminal)
SELECT r.root, r.symbol, r.depth, r.terminal
FROM (
    SELECT UNNEST($rows::STRUCT(
        root VARCHAR, symbol VARCHAR, depth INTEGER, terminal BOOLEAN
    )[]) AS r
);
