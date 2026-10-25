package com.acme.quarkus.hello;

import com.acme.quarkus.pricing.PricingGrpc;
import io.quarkus.grpc.GrpcClient;

// Quarkus's `@GrpcClient` with its value OMITTED (spec 2026-10-24 §3e; CP-52 rows 2, 5):
// the client is named by the field, `pricing`. `@GrpcClient("")` is not this case — it
// fails the Quarkus build (CP-52 row 6). No `@Inject`, as the quickstarts'
// `HelloWorldEndpoint` writes it.
public class PricingClient {
    @GrpcClient
    PricingGrpc.PricingBlockingStub pricing;

    public String quote(String sku) {
        return pricing.quote(sku);
    }
}
