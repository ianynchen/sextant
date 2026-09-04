package com.example.siprobe;

/** Destination names as constants — the "variance" arm of the probe (Q5).
 *
 *  <p>{@link #ORDERS_QUEUE} is a JLS 15.29 compile-time constant, so javac is
 *  required to inline its value at every use site. {@link #LATE_QUEUE} is not
 *  (its initialiser is a method call), so a use site emits a GETSTATIC of the
 *  field instead. The two spellings look identical in source and are meant to
 *  land differently in the fact stream. */
public final class Destinations {
    public static final String ORDERS_QUEUE = "const.orders.queue";
    public static final String ORDERS_CHANNEL = "constOrdersChannel";
    public static final String LATE_QUEUE = late();

    private Destinations() {}

    private static String late() {
        return "late.orders.queue";
    }
}
