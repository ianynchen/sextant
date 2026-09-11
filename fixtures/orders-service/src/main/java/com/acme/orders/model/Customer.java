// The subclass. `setId` is declared on `BaseEntity` and NOT here, so a call site naming
// `Customer` as its owner resolves only by walking the hierarchy (JVMS 5.4.3.3) — the
// resolution `type_hierarchy`/`method_resolution` exist to perform (W22).
package com.acme.orders.model;

public class Customer extends BaseEntity {
    private String name;

    public String getName() {
        return this.name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
