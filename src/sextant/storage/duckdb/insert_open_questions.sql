-- One question a pass could not answer and refused to guess at (2G design
-- §6). The insert-only half of the reset/replace pair the ledger is
-- rebuilt through; `resolve/open_questions.py` is the only caller, and it
-- has already checked `question` against the closed set (seven values since
-- F2 §3.4; this comment said TWO, which it has not been since Phase 2G) and
-- ordered the rows.
--
-- Appends rather than replaces, the derive_shapes.sql precedent: several
-- passes contribute rows within one resolve, so emptying the table happens
-- once per resolve in reset_open_questions.sql, outside this file.
--
-- Parameters:
--   $rows -- {protocol, method, path, question, candidates, evidence} rows.
--            `candidates` arrives as JSON TEXT, already serialized and
--            key-sorted by the pass, and is cast to JSON here so the column
--            holds a document rather than a string.
INSERT INTO open_questions (protocol, method, path, question, candidates, evidence)
SELECT r.protocol, r.method, r.path, r.question, r.candidates::JSON, r.evidence
FROM (SELECT UNNEST(
    $rows::STRUCT(
        protocol VARCHAR, method VARCHAR, path VARCHAR, question VARCHAR,
        candidates VARCHAR, evidence VARCHAR
    )[]
) AS r);
