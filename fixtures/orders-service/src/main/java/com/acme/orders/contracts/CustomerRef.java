package com.acme.orders.contracts;

// A simple first-party nested object, referenced singly and as a collection
// by OrderRequest — exercises structural expansion at depth (D2).
public class CustomerRef {
    public String id;
    public String name;
}
