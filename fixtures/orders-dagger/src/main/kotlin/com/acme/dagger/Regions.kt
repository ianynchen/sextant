package com.acme.dagger

import dagger.Component
import dagger.Module
import dagger.Provides
import javax.inject.Named
import retrofit2.Retrofit

/** One key, two recipes: each component includes one of them, so each build of the app talks to
 * one region. Which one is not in the module. */
@Module
object EuModule {
    @Provides
    @Named("regional")
    fun euRetrofit(): Retrofit = Retrofit.Builder().baseUrl("https://eu.example.com/").build()
}

@Module
object UsModule {
    @Provides
    @Named("regional")
    fun usRetrofit(): Retrofit = Retrofit.Builder().baseUrl("https://us.example.com/").build()
}

@Module
object RegionalApiModule {
    @Provides
    fun regionalApi(@Named("regional") retrofit: Retrofit): RegionalApi =
        retrofit.create(RegionalApi::class.java)
}

@Component(modules = [EuModule::class, RegionalApiModule::class])
interface EuComponent {
    fun regional(): RegionalApi
}

@Component(modules = [UsModule::class, RegionalApiModule::class])
interface UsComponent {
    fun regional(): RegionalApi
}
