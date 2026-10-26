package com.acme.quarkus.quotes;

import io.quarkus.grpc.GrpcService;
import io.smallrye.mutiny.Uni;

// The Mutiny server form (spec 2026-10-25 §3b): `@GrpcService` on a class implementing the
// generated interface, as both quickstarts' `HelloWorldService` writes it. Its RPC's
// identity is the one `QuotesBean`'s base delegates to.
@GrpcService
public class QuotesService implements Quotes {
    @Override
    public Uni<String> getQuote(String request) {
        return Uni.createFrom().item("quote for " + request);
    }
}
