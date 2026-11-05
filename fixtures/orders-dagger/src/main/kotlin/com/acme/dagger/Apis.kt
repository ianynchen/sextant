package com.acme.dagger

import javax.inject.Qualifier
import retrofit2.Call
import retrofit2.http.GET

interface OrdersApi { @GET("orders") fun orders(): Call<String> }

interface PayApi { @GET("pay") fun pay(): Call<String> }

interface BillingApi { @GET("bills") fun bills(): Call<String> }

interface ConfigApi { @GET("config") fun config(): Call<String> }

interface StatusApi { @GET("status") fun status(): Call<String> }

interface RegionalApi { @GET("region") fun region(): Call<String> }

interface SharedApi { @GET("shared") fun shared(): Call<String> }

/** A custom qualifier: the billing server's objects. */
@Qualifier
@Retention(AnnotationRetention.RUNTIME)
annotation class Billing
