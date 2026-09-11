// The superclass half of the shape F3 §4.2 is about (W21).
//
// `spring-petclinic-rest` scores 131 calls whose OWNER is a class the module scans and
// whose method is declared on an ancestor it also scans — `Owner#setId`, where `setId`
// lives on `BaseEntity`. This fixture scored ZERO of them, which is why the always-on
// suite could not see either of Wave 3's Criticals: of the 160 calls it makes onto a
// scanned owner that owner does not declare, all but these two are generated code
// extending LIBRARY supertypes — 101 protobuf and 57 Avro — where "external boundary"
// is the correct answer rather than a defect.
//
// So the shape is modelled here, in the corpus that runs without a network, rather than
// only pinned against a clone that `field_check.py` reaches opt-in.
package com.acme.orders.model;

public abstract class BaseEntity {
    private Long id;

    public Long getId() {
        return this.id;
    }

    public void setId(Long id) {
        this.id = id;
    }
}
