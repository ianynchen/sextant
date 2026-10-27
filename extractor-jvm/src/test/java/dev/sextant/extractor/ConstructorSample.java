package dev.sextant.extractor;

/** Committed fixture for D00 §5's {@code field_write}: each constructor here
 *  exercises exactly one shape the {@code <init>} scan must tell apart from
 *  the others — compiled by Gradle's own test compilation, like every other
 *  fixture beside it, so the assertions are about the bytecode javac
 *  actually emits. */
public final class ConstructorSample {
    /** A static field written from a CALL'S RESULT in the static initialiser —
     *  {@code ldc; invokestatic List.of; putstatic}, javac's spelling of CP-33 row
     *  6 with a call where the constant was. */
    static final java.util.List<String> NAMES = java.util.List.of("orders");

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

    /** A field assigned another CALL'S RESULT — {@code ALOAD 0; INVOKESTATIC;
     *  PUTFIELD}, the factory shape ({@code this.c = Factory.make()}). */
    public ConstructorSample(boolean fromFactory) {
        this.url = make();
    }

    /** CP-33 row 7's own sequence: {@code aload_0; aload_1; iconst_0;
     *  invokeinterface; checkcast; putfield} — a call, then a cast, between the
     *  receiver load and the write. */
    public ConstructorSample(java.util.List<String> urls) {
        this.url = urls.get(0);
    }

    /** A value BUILT here — {@code aload_0; new; dup; aload_1; invokespecial <init>;
     *  putfield}. The instruction right below the write is a call, and it is the
     *  constructor, which hands nothing back: the value is the {@code NEW}'s. */
    public ConstructorSample(StringBuilder built) {
        this.url = new String(built);
    }

    static String make() {
        return "http://made/";
    }
}
