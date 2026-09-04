package com.acme.orders.data;

/** A minimal stand-in for Spring Data's own generic repository contracts
 *  (`CrudRepository`, `JpaRepository`, ...) — see {@link OrderRepository}.
 *  The shape capability 9.14 reads is the same either way: a superinterface
 *  fixing its own type arguments. */
public interface Repository<T, ID> {
}
