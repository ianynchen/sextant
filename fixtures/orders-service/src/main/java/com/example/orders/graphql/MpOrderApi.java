package com.example.orders.graphql;
import com.acme.orders.contracts.OrderView;
import org.eclipse.microprofile.graphql.GraphQLApi;
import org.eclipse.microprofile.graphql.Query;

@GraphQLApi
public class MpOrderApi {
    @Query("mpOrders")
    public java.util.List<OrderView> mpOrders() { return java.util.List.of(); }
}
