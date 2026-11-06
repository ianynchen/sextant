package com.acme.dagger;

import retrofit2.Call;
import retrofit2.http.GET;

public interface JApi {
    @GET("j")
    Call<String> j();
}
