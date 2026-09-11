package com.acme.orders.trace;

/** One of {@link Splitter}'s two implementations. */
public class FirstSplitter implements Splitter {

    @Override
    public String head(String raw) {
        return raw;
    }
}
