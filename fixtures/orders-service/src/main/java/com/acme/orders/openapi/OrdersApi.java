// The OpenAPI-generator pattern: mappings live on the interface, and the
// `@RestController` gate lives on the implementation (OrdersApiController).
package com.acme.orders.openapi;

import com.acme.orders.OrderResult;
import com.acme.orders.composed.ApiGet;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;

@RequestMapping("/api")
public interface OrdersApi {

    @GetMapping("/orders")
    List<OrderResult> list();

    // The composed-AND-inherited case: `@ApiGet` must resolve through both
    // §2's composition and §3's inheritance at once.
    @ApiGet
    OrderResult composed();

    @GetMapping("/orders/{id}")
    OrderResult find(long id);
}
