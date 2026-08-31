package com.acme.orders;

import com.acme.orders.contracts.OrderRequest;
import com.acme.orders.contracts.OrderView;
import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/v1/orders")
public class OrderController {

    private final OrderService service = new OrderService();

    @PostMapping
    public OrderResult create(@RequestBody OrderCommand command) {
        return service.place(command);
    }

    @GetMapping(value = "/{id}", produces = "application/json")
    public OrderResult get(@PathVariable long id) {
        return service.find(id);
    }

    // A genuine overload: two methods named `get`, both mapped. Their symbols
    // must differ (D00 §1), or the resolver's join on method_symbol multiplies
    // and two routes are reported as four.
    @GetMapping("/{id}/{view}")
    public OrderResult get(@PathVariable long id, @PathVariable String view) {
        return service.find(id);
    }

    @GetMapping
    public List<OrderResult> list() {
        return service.list();
    }

    // The one endpoint that exercises the whole chain: a request payload
    // covering every nullability and naming case, and a response wrapped in a
    // declared envelope, so rooting has something real to unwrap.
    @PostMapping(value = "/detailed", consumes = "application/json", produces = "application/json")
    public ResponseEntity<OrderView> createDetailed(@RequestBody OrderRequest request) {
        return ResponseEntity.ok(new OrderView());
    }
}
