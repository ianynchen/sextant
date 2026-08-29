// A package-level scope declaration (D02 §2e): every field in this package
// defaults to not-null unless it says otherwise, inverting the ordinary
// permissive default. Compiled onto a synthetic `package-info` class, whose
// symbol the derivation strips its file-class name from to recover the
// package the scope actually claims.
@org.jspecify.annotations.NullMarked
package com.acme.orders.scoped;
