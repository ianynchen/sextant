package com.acme.app;

import dagger.Module;
import dagger.Provides;
import javax.inject.Named;
import retrofit2.Retrofit;

/** The clients. `@Named("core")` has one recipe, in the sibling; `@Named("edge")` has one in the
 * sibling and one here, and each component includes one of them. */
@Module
public final class ApiModule {
    private ApiModule() {}

    @Provides
    static CoreApi coreApi(@Named("core") Retrofit retrofit) {
        return retrofit.create(CoreApi.class);
    }

    @Provides
    static EdgeApi edgeApi(@Named("edge") Retrofit retrofit) {
        return retrofit.create(EdgeApi.class);
    }
}
