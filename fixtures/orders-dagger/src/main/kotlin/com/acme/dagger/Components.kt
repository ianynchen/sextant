package com.acme.dagger

import com.example.network.SharedNetworkModule
import dagger.Component
import dagger.Module
import dagger.Provides
import javax.inject.Named
import javax.inject.Singleton
import retrofit2.Retrofit

/** The `@Named("shared")` Retrofit comes from a module in another build module (a jar). */
@Module
object SharedApiModule {
    @Provides
    fun sharedApi(@Named("shared") retrofit: Retrofit): SharedApi =
        retrofit.create(SharedApi::class.java)
}

@Singleton
@Component(modules = [NetworkModule::class, BillingModule::class, ConfigModule::class, JavaModule::class])
interface AppComponent {
    fun orders(): OrdersApi

    fun pay(): PayApi

    fun billing(): BillingApi

    fun config(): ConfigApi

    fun status(): StatusClient

    fun j(): JApi
}

@Component(modules = [SharedNetworkModule::class, SharedApiModule::class])
interface SharedComponent {
    fun shared(): SharedApi
}
