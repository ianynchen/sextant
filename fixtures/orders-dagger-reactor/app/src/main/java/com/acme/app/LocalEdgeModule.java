package com.acme.app;

import dagger.Module;
import dagger.Provides;
import javax.inject.Named;
import retrofit2.Retrofit;

/** The app's own `@Named("edge")` recipe. */
@Module
public final class LocalEdgeModule {
    private LocalEdgeModule() {}

    @Provides
    @Named("edge")
    static Retrofit edgeRetrofit() {
        return new Retrofit.Builder().baseUrl("https://app-edge.example.com/").build();
    }
}
