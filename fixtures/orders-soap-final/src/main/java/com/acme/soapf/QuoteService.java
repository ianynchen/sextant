package com.acme.soapf;

import jakarta.jws.WebService;

@WebService(serviceName = "QuoteService", targetNamespace = "http://soapf.acme.com/")
public class QuoteService {
    public String quote(String sku) { return "0.00"; }
    /** `isWebMethodBySpec` excludes a final method (CP-13 Q4): NOT an operation. */
    public final String internalAudit() { return "n/a"; }
}
