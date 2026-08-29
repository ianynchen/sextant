package com.acme.orders.clients;

import com.acme.orders.contracts.OrderRequest;
import com.acme.orders.contracts.OrderView;
import java.util.List;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

// value aliases *name* on @FeignClient — the service id, never a path. The
// catalog reads peer_from [name, value] and prefix_from [path], which is the
// split Task 3 exists for.
@FeignClient(name = "billing", path = "/billing")
public interface BillingClient {
    // The body parameter is explicit here; sole-unannotated fallback is
    // exercised by createOrder below.
    @PostMapping("/invoices")
    OrderView submitInvoice(@RequestBody OrderRequest invoice);

    // A collection payload: the endpoint descriptor must say "array of
    // OrderView", which is the gap 2A parked and this phase closes.
    @GetMapping("/invoices")
    List<OrderView> invoices();

}
