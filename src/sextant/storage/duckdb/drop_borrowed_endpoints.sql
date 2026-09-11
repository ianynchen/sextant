-- F4 §5.2 (W24): a module reads a dependency's TYPES; it does not publish its ROWS.
--
-- A reactor sibling is scanned as a library root — its types are on this module's
-- classpath and appear in its signatures — and a library's compiled output contains its
-- own controllers, listeners and schemas. Deriving from those publishes a neighbour's
-- API as this module's, with nothing in the row saying where it came from. Measured
-- before the sibling set was narrowed to declared dependencies: `mall-admin` derived
-- **246** endpoints against its own 160.
--
-- **`extract_libraries` is deliberately NOT covered, and it took a failing test to see
-- why.** An earlier version of this keyed on the tier, which both kinds share, and it
-- deleted the SOAP operation `tests/e2e/test_vertical_slice.py` asserts an opted-in
-- library contributes. That is not a hole being closed: D04 §2a defines that file as
-- "scan this dependency's own bytecode as well as mine", so the surface is what the
-- person asked for. A sibling is scanned because it is on the classpath and nobody was
-- asked. **Consent is the difference**, and it is not readable from the tier — which is
-- why the module fact carries `sibling_coordinates` and this keys on those.
--
-- **The ordering constraint this once carried is gone with the statement it named.**
-- It read "runs BEFORE `endpoints_merge`, and that ordering is the whole correctness of
-- it": the merge folded an inbound row and an outbound row for one address into a single
-- `both` row carrying the INBOUND handler, so running after it would have keyed this
-- delete on that handler and taken the module's own outbound row with it — §8's
-- exclude-only-on-proof violated in the direction that leaves no trace. W27 deleted the
-- merge (F5 §6.1: the two rows stand and `self_exchange` asks the question), so there is
-- no longer a row whose handler came from a different row than its caller did, and the
-- hazard cannot arise. Recorded rather than deleted, because it is why this statement is
-- keyed on `coalesce(handler, caller)` at all.
--
-- `coalesce(handler, caller)` reaches every row any engine mints with either column
-- set. The one style that sets NEITHER — `schema_operations`, whose rows come from a
-- schema rather than from code — filters its own roots at source instead, because
-- there is nothing on such a row for this statement to key on.
DELETE FROM endpoints
WHERE coalesce(handler, caller) IN (
    SELECT s.symbol
    FROM symbols s
    JOIN documents d ON d.document_id = s.document_id
    WHERE d.origin IN (
        SELECT unnest(from_json(payload -> 'sibling_coordinates', '["VARCHAR"]'))
        FROM raw_facts WHERE kind = 'module'
    )
);
