package com.acme.quarkus.quotes;

import io.quarkus.grpc.MutinyService;
import io.smallrye.mutiny.Uni;

// Quarkus's generated Mutiny service interface (`MutinyQuotesGrpc` says what the Mutiny
// stand-ins stand in for). A service implements it; a client field is typed by it.
public interface Quotes extends MutinyService {
    Uni<String> getQuote(String request);
}
