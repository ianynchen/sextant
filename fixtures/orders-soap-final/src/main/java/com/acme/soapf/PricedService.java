package com.acme.soapf;

import jakarta.jws.WebService;

/** An ANNOTATED base. `price` is declared by a `@WebService` class, so a `@WebService`
 *  subclass inheriting it serves it too (w63, both runtimes). */
@WebService(targetNamespace = "http://soapf.acme.com/")
public class PricedService {
    public String price(String sku) { return "0"; }
}
