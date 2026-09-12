package com.acme.soapf;

/** A plain base: no `@WebService`. Both runtimes read `@WebService` off a method's OWN
 *  declaring class (w63: RI `isWebMethodBySpec` offsets 124-147, CXF
 *  `hasWebServiceAnnotation` offsets 0-17), so `audit` is NOT an operation of any
 *  `@WebService` subclass that inherits it without overriding it — while `RootQuote.root`
 *  above it still is, because the walk continues past this class. */
public class AbstractQuote extends RootQuote {
    public String audit() { return "n/a"; }
}
