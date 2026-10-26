package com.acme.quarkus.quotes;

import com.acme.quarkus.hello.Utf8;
import io.grpc.BindableService;
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.MethodDescriptor;
import io.grpc.ServerServiceDefinition;
import io.grpc.ServiceDescriptor;
import io.grpc.stub.AbstractAsyncStub;
import io.grpc.stub.AbstractBlockingStub;
import io.grpc.stub.ClientCalls;
import io.grpc.stub.ServerCalls;
import io.grpc.stub.StreamObserver;

// The stand-in for what protoc-gen-grpc-java generates from
// `service Quotes { rpc GetQuote (…) returns (…); }` in package `acme.quotes`, in
// `hello/HelloGrpc`'s shape (that file says what the stand-ins stand in for), plus the
// asynchronous `QuotesStub` and `newStub`. Quarkus's Mutiny classes (`MutinyQuotesGrpc`)
// delegate to this class, and so does the identity they carry (spec 2026-10-25 §2a).
public final class QuotesGrpc {
    private QuotesGrpc() {}

    public static final String SERVICE_NAME = "acme.quotes.Quotes";

    private static volatile MethodDescriptor<String, String> getQuoteMethod;
    private static volatile ServiceDescriptor serviceDescriptor;

    public static MethodDescriptor<String, String> getGetQuoteMethod() {
        MethodDescriptor<String, String> method = getQuoteMethod;
        if (method == null) {
            method = MethodDescriptor.<String, String>newBuilder()
                    .setType(MethodDescriptor.MethodType.UNARY)
                    .setFullMethodName(MethodDescriptor.generateFullMethodName(SERVICE_NAME, "GetQuote"))
                    .setRequestMarshaller(Utf8.INSTANCE)
                    .setResponseMarshaller(Utf8.INSTANCE)
                    .build();
            getQuoteMethod = method;
        }
        return method;
    }

    public static ServiceDescriptor getServiceDescriptor() {
        ServiceDescriptor descriptor = serviceDescriptor;
        if (descriptor == null) {
            descriptor = ServiceDescriptor.newBuilder(SERVICE_NAME)
                    .addMethod(getGetQuoteMethod())
                    .build();
            serviceDescriptor = descriptor;
        }
        return descriptor;
    }

    public static QuotesStub newStub(Channel channel) {
        return new QuotesStub(channel, CallOptions.DEFAULT);
    }

    public static QuotesBlockingStub newBlockingStub(Channel channel) {
        return new QuotesBlockingStub(channel, CallOptions.DEFAULT);
    }

    public interface AsyncService {
        default void getQuote(String request, StreamObserver<String> responseObserver) {
            ServerCalls.asyncUnimplementedUnaryCall(getGetQuoteMethod(), responseObserver);
        }
    }

    public abstract static class QuotesImplBase implements BindableService, AsyncService {
        @Override
        public final ServerServiceDefinition bindService() {
            return QuotesGrpc.bindService(this);
        }
    }

    public static ServerServiceDefinition bindService(AsyncService service) {
        return ServerServiceDefinition.builder(getServiceDescriptor())
                .addMethod(getGetQuoteMethod(), ServerCalls.asyncUnaryCall(service::getQuote))
                .build();
    }

    // The stub `MutinyQuotesStub` delegates to: the call leaves through
    // `ClientCalls.asyncUnaryCall`, as protoc emits it.
    public static final class QuotesStub extends AbstractAsyncStub<QuotesStub> {
        private QuotesStub(Channel channel, CallOptions callOptions) {
            super(channel, callOptions);
        }

        @Override
        protected QuotesStub build(Channel channel, CallOptions callOptions) {
            return new QuotesStub(channel, callOptions);
        }

        public void getQuote(String request, StreamObserver<String> responseObserver) {
            ClientCalls.asyncUnaryCall(
                    getChannel().newCall(getGetQuoteMethod(), getCallOptions()), request, responseObserver);
        }
    }

    public static final class QuotesBlockingStub extends AbstractBlockingStub<QuotesBlockingStub> {
        private QuotesBlockingStub(Channel channel, CallOptions callOptions) {
            super(channel, callOptions);
        }

        @Override
        protected QuotesBlockingStub build(Channel channel, CallOptions callOptions) {
            return new QuotesBlockingStub(channel, callOptions);
        }

        public String getQuote(String request) {
            return ClientCalls.blockingUnaryCall(
                    getChannel(), getGetQuoteMethod(), getCallOptions(), request);
        }
    }

    // protoc's descriptor-supplier nesting (`hello/HelloGrpc` says why it is kept).
    private abstract static class QuotesBaseDescriptorSupplier {}

    private static final class QuotesFileDescriptorSupplier extends QuotesBaseDescriptorSupplier {}

    private static final class QuotesMethodDescriptorSupplier extends QuotesBaseDescriptorSupplier {
        private final String methodName;

        QuotesMethodDescriptorSupplier(String methodName) {
            this.methodName = methodName;
        }
    }
}
