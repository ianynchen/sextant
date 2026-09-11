package com.acme.orders.trace;

/** 2Q `G3`'s BRANCH fixture: an interface with two in-module implementations,
 *  so a call through it narrows to a set of candidates and picks none. The
 *  roadmap records that this case has never occurred on real code — measured
 *  again on `macrozheng/mall` at G3, where every one of its 166 dispatched
 *  calls has exactly one implementation — so the rule is exercised here or
 *  nowhere. */
public interface Splitter {
    String head(String raw);
}
