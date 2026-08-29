// OrdersLoopClient.java — its own interface, deliberately: @FeignClient's
// `path` prefix applies to every method in the interface, and this method's
// wire identity must be exactly the POST /v1/orders the module itself
// exposes, or D02 §3's merge has nothing to match (pre-flight ruling R1).
package com.acme.orders.clients;

import com.acme.orders.contracts.OrderRequest;
import com.acme.orders.contracts.OrderView;
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.PostMapping;

@FeignClient(name = "orders-loop")
public interface OrdersLoopClient {
    // The sole unannotated parameter is the body (Feign's contract — the
    // fallback rule Task 6 implements).
    @PostMapping("/v1/orders")
    OrderView createOrder(OrderRequest order);
}
