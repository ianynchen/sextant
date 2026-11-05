package com.example.network;

import dagger.Module;
import dagger.Provides;
import javax.inject.Named;
import retrofit2.Retrofit;

/** The shared server's Retrofit, provided from this library for any component to include. */
@Module
public final class SharedNetworkModule {
    private SharedNetworkModule() {}

    @Provides
    @Named("shared")
    static Retrofit sharedRetrofit() {
        return new Retrofit.Builder().baseUrl("https://shared.example.com/").build();
    }
}
