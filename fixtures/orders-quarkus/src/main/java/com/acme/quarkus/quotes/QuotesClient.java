package com.acme.quarkus.quotes;

import io.grpc.Channel;
import io.quarkus.grpc.MutinyClient;
import io.smallrye.mutiny.Uni;
import java.util.function.BiFunction;

// Quarkus's generated client for `Quotes`: what an `@GrpcClient Quotes` field is given.
// Quarkus finds it as the implementor of `MutinyClient` keyed by its first other interface
// (CP-53).
public class QuotesClient implements Quotes, MutinyClient<MutinyQuotesGrpc.MutinyQuotesStub> {
    private final MutinyQuotesGrpc.MutinyQuotesStub stub;

    public QuotesClient(
            String name,
            Channel channel,
            BiFunction<String, MutinyQuotesGrpc.MutinyQuotesStub, MutinyQuotesGrpc.MutinyQuotesStub> stubConfigurator) {
        this.stub = stubConfigurator.apply(name, MutinyQuotesGrpc.newMutinyStub(channel));
    }

    private QuotesClient(MutinyQuotesGrpc.MutinyQuotesStub stub) {
        this.stub = stub;
    }

    @Override
    public QuotesClient newInstanceWithStub(MutinyQuotesGrpc.MutinyQuotesStub stub) {
        return new QuotesClient(stub);
    }

    @Override
    public MutinyQuotesGrpc.MutinyQuotesStub getStub() {
        return stub;
    }

    @Override
    public Uni<String> getQuote(String request) {
        return stub.getQuote(request);
    }
}
