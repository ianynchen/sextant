package com.acme.soapf;

import jakarta.jws.WebService;

/** Extends an ANNOTATED base: `tier` (own) and `price` (declared by `@WebService`
 *  `PricedService`) are both operations. Its own namespace, so the inherited `price`
 *  row is told apart from `PricedService`'s own `price` row by its QName. */
@WebService(serviceName = "TieredQuoteService", targetNamespace = "http://tiered.soapf.acme.com/")
public class TieredQuoteService extends PricedService {
    public String tier(String sku) { return "standard"; }
}
