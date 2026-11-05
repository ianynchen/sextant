package com.acme.dagger

import javax.inject.Inject
import javax.inject.Named
import retrofit2.Retrofit

/** An `@Inject` constructor makes the client from the Retrofit the container hands it. */
class StatusClient @Inject constructor(@Named("status") retrofit: Retrofit) {
    val api: StatusApi = retrofit.create(StatusApi::class.java)
}
