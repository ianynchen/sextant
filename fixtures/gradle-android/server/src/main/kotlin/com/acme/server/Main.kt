package com.acme.server

import com.acme.shop.PricingClient
import io.ktor.client.HttpClient
import io.ktor.client.engine.cio.CIO

suspend fun main() {
    val pricing = PricingClient(HttpClient(CIO))
    println(pricing.quote("A-100").status)
}
