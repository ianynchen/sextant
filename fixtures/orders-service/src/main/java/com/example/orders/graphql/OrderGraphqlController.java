package com.example.orders.graphql;

import com.acme.orders.contracts.OrderView;
import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.graphql.data.method.annotation.SubscriptionMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

import java.util.List;
import java.util.Map;

@Controller
public class OrderGraphqlController {

    @QueryMapping("orderById")            // explicit field name
    public OrderView byId(String id) { return null; }

    @QueryMapping                          // method-name fallback → field "orders"
    public List<OrderView> orders() { return List.of(); }

    @MutationMapping
    public OrderView placeOrder(String sku) { return null; }

    @SubscriptionMapping
    public Flux<OrderView> orderUpdates() { return Flux.empty(); }

    @SchemaMapping(typeName = "Order", field = "lines")
    public List<String> orderLines(OrderView order) { return List.of(); }

    @BatchMapping(typeName = "Order")      // field falls back to method name "totals"
    public Map<OrderView, Long> totals(List<OrderView> orders) { return Map.of(); }

    // No typeName here and none on the class: Spring infers the parent type
    // from the parameter, which is a fact no annotation carries. There is no
    // address to derive, so this method must derive NO ROW — never the bare
    // field name `orphan`, which would claim a root-operation-shaped identity
    // for a resolver.
    @SchemaMapping(field = "orphan")
    public String orphanField(OrderView order) { return null; }
}
