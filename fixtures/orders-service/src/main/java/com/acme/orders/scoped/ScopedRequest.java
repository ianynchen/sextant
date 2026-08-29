package com.acme.orders.scoped;

public class ScopedRequest {
    // No annotation of its own: the enclosing package's @NullMarked scope is
    // what makes this not-null, not anything declared on the field.
    public String code;
}
