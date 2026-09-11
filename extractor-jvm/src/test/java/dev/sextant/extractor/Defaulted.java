package dev.sextant.extractor;
public @interface Defaulted {
    String value() default "orders";
    int concurrency() default 3;
    String[] topics() default {"a", "b"};
    boolean eager() default true;

    /** A PRIMITIVE array default. ASM hands the whole `int[]` over rather than
     *  calling visitArray, and stringifying it produced an identity hash that
     *  differed on every run (NFR-1). */
    int[] partitions() default {1, 2, 3};

    /** A non-finite default: `Double.NaN` is a constant variable, so this
     *  compiles, and writing it unquoted is invalid JSON. */
    double gap() default Double.NaN;
}
