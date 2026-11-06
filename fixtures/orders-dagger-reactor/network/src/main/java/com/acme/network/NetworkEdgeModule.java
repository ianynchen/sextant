package com.acme.network;

import dagger.Module;
import dagger.Provides;
import javax.inject.Named;
import retrofit2.Retrofit;

/** One of two `@Named("edge")` recipes: the app module holds the other. */
@Module
public final class NetworkEdgeModule {
    private NetworkEdgeModule() {}

    @Provides
    @Named("edge")
    static Retrofit edgeRetrofit() {
        return new Retrofit.Builder().baseUrl("https://network-edge.example.com/").build();
    }
}
