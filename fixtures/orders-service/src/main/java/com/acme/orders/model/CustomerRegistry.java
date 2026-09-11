// The call site. `setId`/`getId` are invoked with `Customer` as the owner while being
// declared on `BaseEntity`; `setName` is declared on `Customer` itself and is the
// control — the two must resolve differently in `method_resolution` and identically to
// a reader of the source.
package com.acme.orders.model;

public class CustomerRegistry {
    public Customer register(String name, Long id) {
        Customer customer = new Customer();
        customer.setId(id);
        customer.setName(name);
        return customer;
    }

    public Long identify(Customer customer) {
        return customer.getId();
    }
}
