package com.example.orders.graphql;
import com.acme.orders.contracts.OrderView;
import com.netflix.graphql.dgs.DgsComponent;
import com.netflix.graphql.dgs.DgsQuery;

@DgsComponent
public class DgsOrderFetcher {
    @DgsQuery(field = "dgsOrders")
    public java.util.List<OrderView> dgsOrders() { return java.util.List.of(); }
}
