package com.acme.dagger

import dagger.Module
import dagger.Provides
import javax.inject.Named
import javax.inject.Singleton
import retrofit2.Retrofit

object BuildConfig {
    const val API_URL = "https://orders.example.com/"
}

/** A Kotlin `object` module: the unqualified Retrofit, and two `@Named` ones. */
@Module
object NetworkModule {
    @Provides
    @Singleton
    fun retrofit(): Retrofit = Retrofit.Builder().baseUrl(BuildConfig.API_URL).build()

    @Provides
    fun ordersApi(retrofit: Retrofit): OrdersApi = retrofit.create(OrdersApi::class.java)

    @Provides
    @Named("pay")
    fun payRetrofit(): Retrofit = Retrofit.Builder().baseUrl("https://pay.example.com/").build()

    @Provides
    fun payApi(@Named("pay") retrofit: Retrofit): PayApi = retrofit.create(PayApi::class.java)

    @Provides
    @Named("status")
    fun statusRetrofit(): Retrofit =
        Retrofit.Builder().baseUrl("https://status.example.com/").build()
}

/** A `class` module, with a custom qualifier. */
@Module
class BillingModule {
    @Provides
    @Billing
    fun billingRetrofit(): Retrofit =
        Retrofit.Builder().baseUrl("https://billing.example.com/").build()

    @Provides
    fun billingApi(@Billing retrofit: Retrofit): BillingApi = retrofit.create(BillingApi::class.java)
}

/** A qualified base `String`: the Retrofit is built from what another recipe returns. The
 * unqualified `String` beside it is not a candidate for the `@Named("baseUrl")` parameter. */
@Module
object ConfigModule {
    @Provides
    @Named("baseUrl")
    fun baseUrl(): String = "https://config.example.com/"

    @Provides
    fun userAgent(): String = "shop/1.0"

    @Provides
    @Named("config")
    fun configRetrofit(@Named("baseUrl") url: String): Retrofit =
        Retrofit.Builder().baseUrl(url).build()

    @Provides
    fun configApi(@Named("config") retrofit: Retrofit): ConfigApi =
        retrofit.create(ConfigApi::class.java)
}
