package com.acme.network;

import dagger.Module;
import dagger.Provides;
import javax.inject.Named;
import retrofit2.Retrofit;

/** The core server's Retrofit, for the app module to inject. */
@Module
public final class CoreNetworkModule {
    private CoreNetworkModule() {}

    @Provides
    @Named("core")
    static Retrofit coreRetrofit() {
        return new Retrofit.Builder().baseUrl("https://core.example.com/").build();
    }
}
