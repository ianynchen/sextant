package dev.sextant.extractor;

/** The three alignments JVMS 4.7.18 produces, side by side, so a fix can be
 *  shown to move what it should and leave alone what it should not.
 *
 *  <p>The parameter-annotation attribute counts only parameters javac considers
 *  the source declared; the descriptor counts every parameter the JVM sees. The
 *  difference is the shift, and it is not a constant:
 *
 *  <ul>
 *    <li>a top-level class: nothing synthesised, shift <b>0</b></li>
 *    <li>an inner class: the outer instance, shift <b>1</b></li>
 *    <li>an enum: {@code $enum$name} and {@code $enum$ordinal}, shift <b>2</b>
 *        — see {@link EnumConstructorAnnotated}</li>
 *  </ul>
 *
 *  <p>A fix that aligned from the end unconditionally would break the first
 *  case, which is why it is here rather than assumed. */
public final class ConstructorAnnotationShapes {

    /** Shift 0 — the attribute and the descriptor agree. */
    public static final class TopLevel {
        public TopLevel(@Labelled("first") String first, int second) {}
    }

    /** A CLASS-retention parameter annotation on the same shape. The visible and
     *  invisible parameter-annotation tables are TWO attributes with independent
     *  counts, and the code holds a count per attribute for that reason — but
     *  every fixture used a RUNTIME annotation, so collapsing the two into one
     *  field passed the whole suite. This drives the invisible table. */
    public static final class Invisible {
        public Invisible(@Retained("first") String first, int second) {}
    }

    /** Shift 1 — the hidden leading parameter is the outer instance. Its type
     *  differs from the annotated parameter's, so this misalignment at least
     *  COULD be noticed downstream; the enum's cannot. */
    public final class Inner {
        public Inner(@Labelled("only") String only) {}
    }
}
