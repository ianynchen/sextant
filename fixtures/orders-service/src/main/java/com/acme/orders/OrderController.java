package com.acme.orders;

import com.acme.orders.contracts.OrderRequest;
import com.acme.orders.scoped.ScopedRequest;
import com.acme.orders.contracts.OrderView;
import com.example.orders.proto.OrderProtos;
import java.util.List;
import org.springframework.http.MediaType;
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

    // The package-scope case, reachable at last: `ScopedRequest` lives in a
    // `@NullMarked` package and declares no annotation on its own field, so the
    // only thing that can make `code` not-null is the scope rule (D02 §2e).
    // Nothing referenced this type before, so no endpoint rooted it, so the shape
    // was never expanded and the rule was exercised only by a hand-built test.
    @PostMapping("/scoped")
    public OrderResult scoped(@RequestBody ScopedRequest request) {
        return service.place(new OrderCommand());
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

    // 2G Task 5: a generated protobuf payload reaching a handler signature —
    // OrderProtos.OrderRequest/OrderReply own a declared_shape (Task 2/4),
    // so their expansion must come from the schema, never from the
    // generated class's own bytecode fields.
    @PostMapping(value = "/proto-orders", produces = MediaType.APPLICATION_JSON_VALUE)
    public OrderProtos.OrderReply createProtoOrder(@RequestBody OrderProtos.OrderRequest request) {
        return OrderProtos.OrderReply.newBuilder().build();
    }
}
