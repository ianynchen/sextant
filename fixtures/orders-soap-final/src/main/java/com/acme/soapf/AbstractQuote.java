package com.acme.soapf;

/** A plain base: no `@WebService`. Both runtimes read `@WebService` off a method's OWN
 *  declaring class (w63: RI `isWebMethodBySpec` offsets 124-147, CXF
 *  `hasWebServiceAnnotation` offsets 0-17), so `audit` is NOT an operation of any
 *  `@WebService` subclass that inherits it without overriding it. */
public class AbstractQuote {
    public String audit() { return "n/a"; }
}
