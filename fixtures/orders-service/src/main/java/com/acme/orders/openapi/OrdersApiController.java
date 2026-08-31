// Implements OrdersApi: overrides carry no mapping annotations of their own
// -- §3's inherited-mapping resolution must supply them from the interface.
// `find` returns DetailedOrderResult, a subtype of the interface's declared
// OrderResult: the covariant-return case whose name+descriptor join must
// miss honestly, and whose compiler-generated bridge method must not
// double-join.
package com.acme.orders.openapi;

import com.acme.orders.OrderResult;
import java.util.List;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrdersApiController implements OrdersApi {

    @Override
    public List<OrderResult> list() {
        return List.of();
    }

    @Override
    public OrderResult composed() {
        return new OrderResult();
    }

    @Override
    public DetailedOrderResult find(long id) {
        return new DetailedOrderResult();
    }
}
