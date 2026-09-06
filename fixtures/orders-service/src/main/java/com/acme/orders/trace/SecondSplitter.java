package com.acme.orders.trace;

/** The other of {@link Splitter}'s two implementations. Its return is a
 *  literal rather than a parameter, so the two candidates are told apart by
 *  what they return and not only by their symbols. */
public class SecondSplitter implements Splitter {

    @Override
    public String head(String raw) {
        return "second";
    }
}
