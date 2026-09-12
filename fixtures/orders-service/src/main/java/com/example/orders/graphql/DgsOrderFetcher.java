package com.example.orders.graphql;
import com.acme.orders.contracts.OrderView;
import com.netflix.graphql.dgs.DgsComponent;
import com.netflix.graphql.dgs.DgsData;
import com.netflix.graphql.dgs.DgsEntityFetcher;
import com.netflix.graphql.dgs.DgsQuery;

@DgsComponent
public class DgsOrderFetcher {
    @DgsQuery(field = "dgsOrders")
    public java.util.List<OrderView> dgsOrders() { return java.util.List.of(); }

    // The long form, and DGS's own spelling of the qualifier — `parentType`
    // where Spring says `typeName`. Same projection, no engine change.
    @DgsData(parentType = "Order", field = "dgsLines")
    public java.util.List<String> dgsLines(OrderView order) { return java.util.List.of(); }

    // ONE resolver for two fields. `@DgsData` is `@Repeatable(DgsData.List.class)` and DGS
    // registers both, which is the ordinary way to share a fetcher between two fields.
    @DgsData(parentType = "Order", field = "dgsTotal")
    @DgsData(parentType = "Order", field = "dgsSubtotal")
    public String dgsAmounts(OrderView order) { return ""; }

    // Apollo Federation's entity resolution. DGS registers it under the TYPE it resolves,
    // not under a schema field, which is a different identity from every row above.
    @DgsEntityFetcher(name = "Order")
    public OrderView resolveOrderEntity(java.util.Map<String, Object> values) { return null; }
}
