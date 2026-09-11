package dev.sextant.extractor;

/** W6's fixture, and its LINE NUMBERS ARE THE FIXTURE.
 *
 *  <p>`SourceLocationTest` pins them literally, so editing anything above or
 *  inside these methods moves them and fails that test. That is deliberate: the
 *  numbers are what is under test, and a test that only checked "non-zero" would
 *  pass with every method reporting the same wrong line.
 *
 *  <p>Keep additions at the BOTTOM of the file. */
public abstract class SourceLocationSample {

    /** Declared on line 15, body on line 16 — and 16 is what a `LineNumberTable`
     *  states, because it maps BYTECODE to lines and a signature emits none. */
    public int single(int value) {
        return value + 1;
    }

    /** Body spanning lines 22 to 25, so a range that is not a point is covered
     *  and `line_end` cannot be a copy of `line_start`. */
    public int spanning(int first, int second) {
        int total = first;
        total += second;
        total *= 2;
        return total;
    }

    /** No body at all, so no `Code` attribute and no `LineNumberTable` inside
     *  one — the class file states no line, and 0 means exactly that. */
    public abstract String stated();

    /** A `long` FIRST, so the parameter after it sits at local slot 3 and not 2:
     *  JVMS 2.6.1 gives a long two slots. Counting parameters instead of walking
     *  their sizes reads the second half of the long, which holds no variable,
     *  and `label` comes back unnamed. */
    public String widened(long id, String label) {
        return label + id;
    }
}
