package com.acme.orders.trace;

/** The caller 2Q `G3` joins from — the fixture's stand-in for
 *  `OmsOrderController#list`, whose call sites are a chain of results the
 *  facts already carry and each of whose links crosses a method boundary.
 *  One call per dispatch form: through an interface with one implementation,
 *  through an interface with two, virtually on a class that has a subclass,
 *  and statically on a class whose subclass hides the same method.
 *
 *  <p>Static, with both collaborators arriving as parameters, so this class
 *  declares no field and no constructor beyond the implicit one: the fixture
 *  is here for the dispatch forms, and a field write is a different fact
 *  kind's subject. */
public final class TraceProbe {

    private TraceProbe() {
    }

    public static String describe(Refiner refiner, Splitter splitter, String raw) {
        String refined = refiner.refine(raw);
        String head = splitter.head(refined);
        String shortened = new SoleRefiner().shorten(head, 2);
        return SoleRefiner.tag().concat(shortened);
    }
}
