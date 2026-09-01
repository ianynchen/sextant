package com.example.orders.graphql;
import com.acme.orders.contracts.OrderView;
import com.netflix.graphql.dgs.DgsComponent;
import com.netflix.graphql.dgs.DgsData;
import com.netflix.graphql.dgs.DgsQuery;

@DgsComponent
public class DgsOrderFetcher {
    @DgsQuery(field = "dgsOrders")
    public java.util.List<OrderView> dgsOrders() { return java.util.List.of(); }

    // The long form, and DGS's own spelling of the qualifier — `parentType`
    // where Spring says `typeName`. Same projection, no engine change.
    @DgsData(parentType = "Order", field = "dgsLines")
    public java.util.List<String> dgsLines(OrderView order) { return java.util.List.of(); }
}
