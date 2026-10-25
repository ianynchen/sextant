package com.acme.quarkus.pricing;

import io.grpc.Channel;
import io.quarkus.grpc.MutinyClient;
import io.smallrye.mutiny.Uni;
import java.util.function.BiFunction;

// Quarkus's generated client for `Pricing`, what an `@GrpcClient Pricing` field is given.
// Here, in the proto's package, and not `hello/PricingClient`, which is a user class.
public class PricingClient implements Pricing, MutinyClient<MutinyPricingGrpc.MutinyPricingStub> {
    private final MutinyPricingGrpc.MutinyPricingStub stub;

    public PricingClient(
            String name,
            Channel channel,
            BiFunction<String, MutinyPricingGrpc.MutinyPricingStub, MutinyPricingGrpc.MutinyPricingStub> stubConfigurator) {
        this.stub = stubConfigurator.apply(name, MutinyPricingGrpc.newMutinyStub(channel));
    }

    private PricingClient(MutinyPricingGrpc.MutinyPricingStub stub) {
        this.stub = stub;
    }

    @Override
    public PricingClient newInstanceWithStub(MutinyPricingGrpc.MutinyPricingStub stub) {
        return new PricingClient(stub);
    }

    @Override
    public MutinyPricingGrpc.MutinyPricingStub getStub() {
        return stub;
    }

    @Override
    public Uni<String> quote(String request) {
        return stub.quote(request);
    }
}
