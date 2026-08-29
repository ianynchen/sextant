package com.acme.orders.contracts;

import org.springframework.http.HttpHeaders;

public class OrderView {
    public String id;
    // Third-party, an object, and in no `known_types` entry — so expansion
    // stops here, the shape is marked open, and the type is reported.
    public HttpHeaders headers;
}
