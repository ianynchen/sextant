package com.acme.orders.trace;

/** A SUBCLASS of {@link SoleRefiner}, which makes it an indirect implementation
 *  of {@link Refiner} — the transitive step a hierarchy walk has to take, and
 *  which it must NOT mistake for a second implementation of `refine`: this
 *  class declares no `refine` of its own, so `SoleRefiner`'s stays the one
 *  body a call through the interface can run.
 *
 *  <p>Its {@code tag} HIDES {@link SoleRefiner#tag()} rather than overriding
 *  it. Static methods are not dispatched: `SoleRefiner.tag()` runs
 *  `SoleRefiner.tag()` whatever the subclasses declare, which is what makes
 *  this the fixture for the exact-dispatch rule. */
public class StrictRefiner extends SoleRefiner {

    public static String tag() {
        return "strict";
    }
}
