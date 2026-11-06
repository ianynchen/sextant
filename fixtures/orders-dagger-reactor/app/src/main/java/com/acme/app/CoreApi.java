package com.acme.app;

import retrofit2.Call;
import retrofit2.http.GET;

public interface CoreApi {
    @GET("core")
    Call<String> core();
}
