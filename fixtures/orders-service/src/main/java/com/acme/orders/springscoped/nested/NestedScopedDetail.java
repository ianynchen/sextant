package com.acme.orders.springscoped.nested;

public class NestedScopedDetail {
    // This package declares NO scope. Its parent `com.acme.orders.springscoped`
    // declares `@NonNullFields`, and a Java package annotation is not inherited
    // by subpackages (JLS 7.4.1 gives `a.b` and `a.b.c` no relationship beyond
    // the name), so this stays nullable. Matching the parent's prefix by bare
    // `startswith` claimed 462 unmarked subpackages across 1,672 cached jars.
    public String tag;
}
