package com.acme.orders.scoped;

public class ScopedRequest {
    // No annotation of its own: the enclosing package's @NullMarked scope is
    // what makes this not-null, not anything declared on the field.
    public String code;

    // Reaches a package scoped with SPRING's spelling, through the payload graph
    // rather than through a second endpoint: expansion follows a field's type.
    public com.acme.orders.springscoped.SpringScopedDetail detail;

    // The two cases a scope must NOT reach, both reached the same way. One
    // package declares `@NonNullApi` and nothing about fields; the other is a
    // SUBpackage of a package that does declare a field scope. Both fields must
    // come out nullable, and both were coming out not-null.
    public com.acme.orders.apiscoped.ApiScopedDetail apiOnly;

    public com.acme.orders.springscoped.nested.NestedScopedDetail nested;
}
