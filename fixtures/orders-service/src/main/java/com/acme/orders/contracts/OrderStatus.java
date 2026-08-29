package com.acme.orders.contracts;

/**
 * A closed set of constants on the wire (D00 §5b's `enum`), not a record. The
 * constants below are the fields of this class file; a pass that read them as
 * payload fields would publish a contract nobody wrote — and the compiler's own
 * `$VALUES` array beside them is not a declaration at all.
 */
public enum OrderStatus {
    NEW,
    DONE
}
