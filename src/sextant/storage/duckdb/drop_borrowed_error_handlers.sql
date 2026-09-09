-- F4 §5.2 (W24), the `drop_borrowed_endpoints.sql` rule applied to advice.
--
-- An `@ControllerAdvice` in a dependency IS active in this module's Spring context when
-- component scanning reaches it, so a row whose HANDLER is this module's own is real
-- and stays — the tier is read off the handler, never off the advice. What goes is a
-- row where the advice AND the handler both belong to the dependency: that is the
-- dependency's own error handling, describing responses this module never serves.
--
-- Measured on `mall-admin`: four rows, every one `mall-common`'s
-- `GlobalExceptionHandler` advising `mall-common`'s own handlers.
DELETE FROM error_handlers
WHERE handler IN (
    SELECT s.symbol
    FROM symbols s
    JOIN documents d ON d.document_id = s.document_id
    WHERE d.origin_tier <> 'module_output'
);
