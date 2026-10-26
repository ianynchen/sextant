package com.acme.quarkus.quotes;

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

// The stand-in for what Quarkus's Mutiny generator emits beside `QuotesGrpc`, in the shape
// `quarkus-quickstarts`' `MutinyGreeterGrpc` has (spec 2026-10-25 §2a, `javap`). Nothing
// here states the identity: the base's `bindService` takes it from `QuotesGrpc`, and the
// stub's constructor builds a `QuotesGrpc.QuotesStub` and its method reaches that stub by a
// method reference, through Quarkus's own `ClientCalls`.
public final class MutinyQuotesGrpc implements MutinyGrpc {
    private MutinyQuotesGrpc() {}

    public static MutinyQuotesStub newMutinyStub(Channel channel) {
        return new MutinyQuotesStub(channel);
    }

    public static class MutinyQuotesStub extends AbstractStub<MutinyQuotesStub> implements MutinyStub {
        private QuotesGrpc.QuotesStub delegateStub;

        private MutinyQuotesStub(Channel channel) {
            super(channel);
            delegateStub = QuotesGrpc.newStub(channel);
        }

        private MutinyQuotesStub(Channel channel, CallOptions callOptions) {
            super(channel, callOptions);
            delegateStub = QuotesGrpc.newStub(channel).build(channel, callOptions);
        }

        @Override
        protected MutinyQuotesStub build(Channel channel, CallOptions callOptions) {
            return new MutinyQuotesStub(channel, callOptions);
        }

        public Uni<String> getQuote(String request) {
            return io.quarkus.grpc.stubs.ClientCalls.oneToOne(request, delegateStub::getQuote);
        }
    }

    public abstract static class QuotesImplBase implements BindableService {
        private String compression;

        public QuotesImplBase withCompression(String compression) {
            this.compression = compression;
            return this;
        }

        public Uni<String> getQuote(String request) {
            throw new StatusRuntimeException(Status.UNIMPLEMENTED);
        }

        @Override
        public ServerServiceDefinition bindService() {
            return ServerServiceDefinition.builder(QuotesGrpc.getServiceDescriptor())
                    .addMethod(
                            QuotesGrpc.getGetQuoteMethod(),
                            ServerCalls.asyncUnaryCall(
                                    new MethodHandlers<String, String>(this, METHODID_GET_QUOTE, compression)))
                    .build();
        }
    }

    private static final int METHODID_GET_QUOTE = 0;

    private static final class MethodHandlers<Req, Resp> implements ServerCalls.UnaryMethod<Req, Resp> {
        private final QuotesImplBase serviceImpl;
        private final int methodId;
        private final String compression;

        MethodHandlers(QuotesImplBase serviceImpl, int methodId, String compression) {
            this.serviceImpl = serviceImpl;
            this.methodId = methodId;
            this.compression = compression;
        }

        @Override
        @SuppressWarnings("unchecked")
        public void invoke(Req request, StreamObserver<Resp> responseObserver) {
            switch (methodId) {
                case METHODID_GET_QUOTE:
                    io.quarkus.grpc.stubs.ServerCalls.oneToOne(
                            (String) request,
                            (StreamObserver<String>) responseObserver,
                            compression,
                            serviceImpl::getQuote);
                    break;
                default:
                    throw new AssertionError();
            }
        }
    }
}
