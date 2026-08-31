package dev.sextant.extractor;

/** Committed fixture for D00 §5's {@code field_write}: each constructor here
 *  exercises exactly one shape the {@code <init>} scan must tell apart from
 *  the others — compiled by Gradle's own test compilation, like every other
 *  fixture beside it, so the assertions are about the bytecode javac
 *  actually emits. */
public final class ConstructorSample {
    String url;
    long id;
    String label;

    /** {@code ALOAD 0; ALOAD 1; PUTFIELD} exactly — the one shape that
     *  produces a fact. */
    public ConstructorSample(String url) {
        this.url = url;
    }

    /** A computed assignment: the value PUTFIELD stores is the
     *  {@code invokedynamic} concatenation's result, not the parameter
     *  itself, so no fact — the resolution that would have followed it
     *  degrades honestly rather than guessing a source. */
    public ConstructorSample(String url, String suffix) {
        this.url = url + suffix;
    }

    /** {@code long} occupies two locals, so {@code label}'s own slot is 3,
     *  not 1 — the mapping this pins. {@code from_parameter} must still read
     *  1, the parameter's index, never the slot number. */
    public ConstructorSample(long id, String label) {
        this.label = label;
    }
}
