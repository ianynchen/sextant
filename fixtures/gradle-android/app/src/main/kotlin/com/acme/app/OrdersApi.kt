package com.acme.app

import retrofit2.Call
import retrofit2.Retrofit
import retrofit2.http.GET
import retrofit2.http.Path

interface OrdersApi {
    @GET("orders/{id}")
    fun order(@Path("id") id: String): Call<String>
}

object Orders {
    val api: OrdersApi = Retrofit.Builder()
        .baseUrl(BuildConfig.API_URL)
        .build()
        .create(OrdersApi::class.java)
}
