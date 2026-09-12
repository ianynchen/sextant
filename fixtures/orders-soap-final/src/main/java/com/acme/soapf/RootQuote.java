package com.acme.soapf;

import jakarta.jws.WebService;

/** An ANNOTATED grandparent above the plain `AbstractQuote`. `root` is declared by a
 *  `@WebService` class, so `PlainBasedService` — reached through the plain class between
 *  them — serves it: the declaring-class check is a filter, not a stop in the walk. */
@WebService(targetNamespace = "http://root.soapf.acme.com/")
public class RootQuote {
    public String root() { return "root"; }
}
