package dev.sextant.extractor;

/** The generic supertype that makes javac emit a BRIDGE method on
 *  {@link MethodModifierSample}. A bridge cannot be written by hand — it only
 *  exists because an erased override has a different descriptor from the
 *  interface method it implements — so the only way to assert the scanner
 *  marks one is to compile a shape that produces one. */
interface MethodModifierBase<T> {
    T echo(T value);
}
