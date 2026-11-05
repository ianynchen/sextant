package com.acme.shop

import io.ktor.client.HttpClient
import io.ktor.client.request.get

expect fun pricingUrl(): String

class PricingClient(private val client: HttpClient) {
    suspend fun quote(id: String) = client.get(pricingUrl() + "/" + id)
}
