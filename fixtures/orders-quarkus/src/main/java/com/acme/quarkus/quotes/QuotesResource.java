package com.acme.quarkus.quotes;

import io.quarkus.grpc.GrpcClient;
import io.smallrye.mutiny.Uni;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;

// Two calls to `acme.quotes.Quotes`, which this module serves (`QuotesService`), the way
// the quickstarts' `HelloWorldEndpoint` calls its own service: one through grpc-java's
// blocking stub, one through the Mutiny interface. Neither is an outbound row; each is a
// hop to the handler (spec 2026-10-25 rulings 1, 2).
@Path("/quotes")
public class QuotesResource {
    @GrpcClient("quotes")
    QuotesGrpc.QuotesBlockingStub blockingQuotes;

    @GrpcClient("quotes")
    Quotes quotes;

    @GET
    @Path("/blocking/{symbol}")
    public String blocking(String symbol) {
        return blockingQuotes.getQuote(symbol);
    }

    @GET
    @Path("/mutiny/{symbol}")
    public Uni<String> mutiny(String symbol) {
        return quotes.getQuote(symbol);
    }
}
