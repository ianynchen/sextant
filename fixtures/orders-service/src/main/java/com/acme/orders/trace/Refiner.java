package com.acme.orders.trace;

/** 2Q `G3`'s sole-implementation dispatch fixture: an interface with exactly
 *  ONE in-module implementation, called through the interface so the call
 *  site's declared target is this abstract declaration and not the body that
 *  runs. Nothing here is annotated and nothing constructs it — it derives no
 *  endpoint, no shape and no schedule, so it exercises the return-flow join
 *  and only that. */
public interface Refiner {
    String refine(String raw);
}
