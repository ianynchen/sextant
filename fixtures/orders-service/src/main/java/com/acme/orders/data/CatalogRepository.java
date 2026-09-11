package com.acme.orders.data;

import java.util.List;

import org.springframework.data.repository.CrudRepository;

import com.acme.orders.contracts.OrderView;

/** Spring Data REST's whole point, and the reason 2O design §2 exists: this
 *  interface declares no path, no verb and no HTTP anything, and the framework
 *  serves eight routes for it — six CRUD plus `/search/findByStatus` and
 *  `/search/by-customer` (the renamed one). No annotation is needed for any of
 *  it; `@RepositoryRestResource` is optional and this interface deliberately
 *  carries none, because the un-annotated case is the common one. */
public interface CatalogRepository extends CrudRepository<OrderView, Long> {

    List<OrderView> findByStatus(String status);

    @org.springframework.data.rest.core.annotation.RestResource(path = "by-customer")
    List<OrderView> findByCustomerId(String customerId);
}
