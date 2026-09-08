package com.acme.orders.scoped;

public class ScopedRequest {
    // No annotation of its own: the enclosing package's @NullMarked scope is
    // what makes this not-null, not anything declared on the field.
    public String code;

    // Reaches a package scoped with SPRING's spelling, through the payload graph
    // rather than through a second endpoint: expansion follows a field's type.
    public com.acme.orders.springscoped.SpringScopedDetail detail;
}
