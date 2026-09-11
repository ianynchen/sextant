package dev.sextant.extractor;

/** W4 fixture. Three field shapes the `ConstantValue` attribute tells apart,
 *  plus the two nesting shapes `InnerClasses`/`EnclosingMethod` do. */
public final class ConstantHolder {

    /** A compile-time constant: the class file carries its value. */
    public static final String TOPIC = "orders";

    /** Numeric, so the fact must keep a JSON number rather than text. */
    public static final int CONCURRENCY = 3;

    /** Initialised in `<clinit>` — NO `ConstantValue` attribute, so no fact. */
    public static final String COMPUTED = "orders".toUpperCase();

    /** Non-finite doubles and floats. RFC 8259 has no NaN or Infinity literal,
     *  so writing these unquoted produces a fact file a conforming reader
     *  refuses — and the strict-JSON guard could not see it, because no fixture
     *  carried a float or double at all. */
    public static final double NOT_A_NUMBER = Double.NaN;

    public static final double POSITIVE_INFINITY = Double.POSITIVE_INFINITY;

    public static final float NEGATIVE_INFINITY = Float.NEGATIVE_INFINITY;

    /** A member class: `InnerClasses` names its outer TYPE. */
    public static final class Nested {}

    /** An anonymous class: `EnclosingMethod` names this METHOD, which splitting
     *  the binary name on `$` could never recover. */
    public static Runnable make() {
        return new Runnable() {
            @Override public void run() {}
        };
    }
}
