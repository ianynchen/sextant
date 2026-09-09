package com.acme.orders.contracts;

// W26. A payload type whose wire contract is in its ACCESSORS, not its fields — an
// interface has no fields at all, so this shape was empty however well the type was
// reached. `hasDiscount` and `recalculate` are here to be LEFT OUT: neither is a bean
// accessor (`has` is not a declared prefix, `recalculate` takes an argument), and a
// rule that read "zero-argument method" rather than Jackson's own would publish both.
public interface OrderTotals {

    String getCurrency();

    int getLineCount();

    boolean isSettled();

    // Not a wire field: `is`-prefixed but not boolean, which is exactly the case
    // jackson-databind's `findNameForIsGetter` refuses unless `isGettersNonBoolean`
    // is turned on.
    String isoCode();

    boolean hasDiscount();

    int recalculate(int factor);
}
