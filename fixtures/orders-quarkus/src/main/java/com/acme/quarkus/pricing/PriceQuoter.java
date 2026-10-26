package com.acme.quarkus.pricing;

import io.quarkus.grpc.GrpcClient;
import io.smallrye.mutiny.Uni;

// The two Mutiny client forms for a service this module does not serve (spec 2026-10-25
// §3f): each is an outbound row at `acme.pricing.Pricing`, resolved through the class the
// injected type delegates to.
public class PriceQuoter {
    @GrpcClient("pricing")
    Pricing pricing;

    @GrpcClient("pricing")
    MutinyPricingGrpc.MutinyPricingStub pricingStub;

    public Uni<String> quote(String sku) {
        return pricing.quote(sku);
    }

    public Uni<String> quoteByStub(String sku) {
        return pricingStub.quote(sku);
    }
}
