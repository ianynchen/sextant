package com.acme.quarkus.hello;

import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.MethodDescriptor;
import io.grpc.ServiceDescriptor;
import io.grpc.stub.AbstractBlockingStub;
import io.grpc.stub.ClientCalls;

// The stand-in for the generated client side of a service this module CALLS and does not
// serve, `acme.pricing.Pricing` (`HelloGrpc` states what the stand-ins stand in for).
// The client must call a service the module does not implement: an injected stub whose
// service the module serves itself is fenced (`injected_client`), and gives no row.
public final class PricingGrpc {
    private PricingGrpc() {}

    public static final String SERVICE_NAME = "acme.pricing.Pricing";

    private static volatile MethodDescriptor<String, String> quoteMethod;
    private static volatile ServiceDescriptor serviceDescriptor;

    public static MethodDescriptor<String, String> getQuoteMethod() {
        MethodDescriptor<String, String> method = quoteMethod;
        if (method == null) {
            method = MethodDescriptor.<String, String>newBuilder()
                    .setType(MethodDescriptor.MethodType.UNARY)
                    .setFullMethodName(MethodDescriptor.generateFullMethodName(SERVICE_NAME, "Quote"))
                    .setRequestMarshaller(Utf8.INSTANCE)
                    .setResponseMarshaller(Utf8.INSTANCE)
                    .build();
            quoteMethod = method;
        }
        return method;
    }

    public static ServiceDescriptor getServiceDescriptor() {
        ServiceDescriptor descriptor = serviceDescriptor;
        if (descriptor == null) {
            descriptor = ServiceDescriptor.newBuilder(SERVICE_NAME)
                    .addMethod(getQuoteMethod())
                    .build();
            serviceDescriptor = descriptor;
        }
        return descriptor;
    }

    public static PricingBlockingStub newBlockingStub(Channel channel) {
        return new PricingBlockingStub(channel, CallOptions.DEFAULT);
    }

    public static final class PricingBlockingStub extends AbstractBlockingStub<PricingBlockingStub> {
        private PricingBlockingStub(Channel channel, CallOptions callOptions) {
            super(channel, callOptions);
        }

        @Override
        protected PricingBlockingStub build(Channel channel, CallOptions callOptions) {
            return new PricingBlockingStub(channel, callOptions);
        }

        public String quote(String request) {
            return ClientCalls.blockingUnaryCall(
                    getChannel(), getQuoteMethod(), getCallOptions(), request);
        }
    }

    // The nesting protoc emits beside the stubs in every full-protobuf `<Service>Grpc`: a
    // descriptor-supplier base and two classes extending it. Real ones implement
    // `io.grpc.protobuf.Proto*DescriptorSupplier` and return the file's descriptors; these
    // keep the two `extends` edges, which are what an analysis of the class reads.
    private abstract static class PricingBaseDescriptorSupplier {}

    private static final class PricingFileDescriptorSupplier extends PricingBaseDescriptorSupplier {}

    private static final class PricingMethodDescriptorSupplier extends PricingBaseDescriptorSupplier {
        private final String methodName;

        PricingMethodDescriptorSupplier(String methodName) {
            this.methodName = methodName;
        }
    }
}
