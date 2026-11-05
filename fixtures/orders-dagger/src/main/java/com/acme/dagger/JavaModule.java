package com.acme.dagger;

import dagger.Module;
import dagger.Provides;
import javax.inject.Named;
import retrofit2.Retrofit;

/** A Java module with static recipes. */
@Module
public final class JavaModule {
    private JavaModule() {}

    @Provides
    @Named("j")
    static Retrofit retrofit() {
        return new Retrofit.Builder().baseUrl("https://j.example.com/").build();
    }

    @Provides
    static JApi api(@Named("j") Retrofit retrofit) {
        return retrofit.create(JApi.class);
    }
}
