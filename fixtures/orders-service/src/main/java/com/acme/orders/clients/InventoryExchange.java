package com.acme.orders.clients;

import com.acme.orders.contracts.OrderRequest;
import com.acme.orders.contracts.OrderView;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.annotation.PostExchange;

// The type-level annotation is the prefix carrier here; the base URL lives in
// builder code the annotation never sees, so `peer` stays NULL and the named
// gap client_base_addresses_not_resolved covers it.
@HttpExchange("/v1/inventory")
public interface InventoryExchange {
    @GetExchange("/levels")
    OrderView levels();

    @PostExchange("/reserve")
    OrderView reserve(@RequestBody OrderRequest request);
}
