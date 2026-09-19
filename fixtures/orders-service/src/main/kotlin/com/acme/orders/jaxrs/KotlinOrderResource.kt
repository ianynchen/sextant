package com.acme.orders.jaxrs

// M2's Kotlin case: kotlinc writes `@org.jetbrains.annotations.NotNull` on `order`, and
// the extractor records it (retention: class). Under `sole_unannotated` that erased the
// body.
import jakarta.ws.rs.POST
import jakarta.ws.rs.Path

@Path("/kt/orders")
class KotlinOrderResource {
    class KtOrder(val sku: String, val quantity: Int)

    @POST
    fun create(order: KtOrder): KtOrder = order
}
