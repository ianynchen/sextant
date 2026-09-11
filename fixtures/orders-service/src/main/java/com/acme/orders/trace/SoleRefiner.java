package com.acme.orders.trace;

/** The one implementation of {@link Refiner}, and the fixture's recursion.
 *
 *  <p>{@code refine} has TWO return statements, which is two `method_return`
 *  facts and therefore two possible answers for one call site — the set a
 *  return flow must carry rather than collapse. {@code shorten} calls itself:
 *  recursion is real Java, and the link it produces names the same method on
 *  both sides. */
public class SoleRefiner implements Refiner {

    @Override
    public String refine(String raw) {
        if (raw == null) {
            return "";
        }
        return raw.trim();
    }

    /** A STATIC method, hidden rather than overridden by {@link
     *  StrictRefiner}'s own — the JVM's rule that `invokestatic` names what
     *  runs, with no dispatch to consider. */
    public static String tag() {
        return "sole";
    }

    public String shorten(String raw, int depth) {
        if (depth <= 0) {
            return raw;
        }
        return shorten(raw, depth - 1);
    }
}
