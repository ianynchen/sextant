package com.acme.orders.data;

import com.acme.orders.OrderResult;

/** Exercises capability 9.14: `interfaces` alone erases {@code
 *  Repository<OrderResult, Long>} to a bare symbol, and Spring Data REST
 *  cannot derive a repository's entity type from that alone (2O design
 *  §2a) — `generic_interfaces` is the only place the entity and id types
 *  survive. */
public interface OrderRepository extends Repository<OrderResult, Long> {
}
