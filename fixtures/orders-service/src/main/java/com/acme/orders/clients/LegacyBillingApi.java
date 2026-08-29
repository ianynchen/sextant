package com.acme.orders.clients;

import com.acme.orders.contracts.OrderRequest;
import com.acme.orders.contracts.OrderView;
import retrofit2.http.Body;
import retrofit2.http.GET;
import retrofit2.http.POST;
import retrofit2.http.Path;

// No type-level marker exists in Retrofit: the interface is recognised by its
// method annotations alone, which is why the type gate became optional.
public interface LegacyBillingApi {
    @GET("legacy/invoices/{id}")
    OrderView invoice(@Path("id") String id);

    @POST("legacy/invoices")
    OrderView submit(@Body OrderRequest invoice);
}
