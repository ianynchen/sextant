package com.acme.quarkus.pricing;

import io.grpc.BindableService;
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ServerServiceDefinition;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.stub.AbstractStub;
import io.grpc.stub.ServerCalls;
import io.grpc.stub.StreamObserver;
import io.quarkus.grpc.MutinyGrpc;
import io.quarkus.grpc.MutinyStub;
import io.smallrye.mutiny.Uni;

// Quarkus's Mutiny classes for `acme.pricing.Pricing`, delegating to `PricingGrpc` in
// `quotes/MutinyQuotesGrpc`'s shape.
public final class MutinyPricingGrpc implements MutinyGrpc {
    private MutinyPricingGrpc() {}

    public static MutinyPricingStub newMutinyStub(Channel channel) {
        return new MutinyPricingStub(channel);
    }

    public static class MutinyPricingStub extends AbstractStub<MutinyPricingStub> implements MutinyStub {
        private PricingGrpc.PricingStub delegateStub;

        private MutinyPricingStub(Channel channel) {
            super(channel);
            delegateStub = PricingGrpc.newStub(channel);
        }

        private MutinyPricingStub(Channel channel, CallOptions callOptions) {
            super(channel, callOptions);
            delegateStub = PricingGrpc.newStub(channel).build(channel, callOptions);
        }

        @Override
        protected MutinyPricingStub build(Channel channel, CallOptions callOptions) {
            return new MutinyPricingStub(channel, callOptions);
        }

        public Uni<String> quote(String request) {
            return io.quarkus.grpc.stubs.ClientCalls.oneToOne(request, delegateStub::quote);
        }
    }

    public abstract static class PricingImplBase implements BindableService {
        private String compression;

        public PricingImplBase withCompression(String compression) {
            this.compression = compression;
            return this;
        }

        public Uni<String> quote(String request) {
            throw new StatusRuntimeException(Status.UNIMPLEMENTED);
        }

        @Override
        public ServerServiceDefinition bindService() {
            return ServerServiceDefinition.builder(PricingGrpc.getServiceDescriptor())
                    .addMethod(
                            PricingGrpc.getQuoteMethod(),
                            ServerCalls.asyncUnaryCall(
                                    new MethodHandlers<String, String>(this, METHODID_QUOTE, compression)))
                    .build();
        }
    }

    private static final int METHODID_QUOTE = 0;

    private static final class MethodHandlers<Req, Resp> implements ServerCalls.UnaryMethod<Req, Resp> {
        private final PricingImplBase serviceImpl;
        private final int methodId;
        private final String compression;

        MethodHandlers(PricingImplBase serviceImpl, int methodId, String compression) {
            this.serviceImpl = serviceImpl;
            this.methodId = methodId;
            this.compression = compression;
        }

        @Override
        @SuppressWarnings("unchecked")
        public void invoke(Req request, StreamObserver<Resp> responseObserver) {
            switch (methodId) {
                case METHODID_QUOTE:
                    io.quarkus.grpc.stubs.ServerCalls.oneToOne(
                            (String) request,
                            (StreamObserver<String>) responseObserver,
                            compression,
                            serviceImpl::quote);
                    break;
                default:
                    throw new AssertionError();
            }
        }
    }
}
