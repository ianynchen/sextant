package com.acme.quarkus.pricing;

import io.quarkus.grpc.MutinyService;
import io.smallrye.mutiny.Uni;

// Quarkus's generated Mutiny interface for `acme.pricing.Pricing`, a service this module
// calls and does not serve (`quotes/MutinyQuotesGrpc` says what the Mutiny stand-ins stand
// in for).
public interface Pricing extends MutinyService {
    Uni<String> quote(String request);
}
