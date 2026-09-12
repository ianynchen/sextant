package com.acme.soapf;

import jakarta.jws.WebService;

/** Extends an UNANNOTATED base: `own` is an operation; the inherited `audit` is NOT —
 *  `AbstractQuote` carries no `@WebService`, and neither runtime serves it (w63,
 *  `jaxws-inherited-unannotated`). */
@WebService(serviceName = "PlainBasedService", targetNamespace = "http://plain.soapf.acme.com/")
public class PlainBasedService extends AbstractQuote {
    public String own() { return "own"; }
}
