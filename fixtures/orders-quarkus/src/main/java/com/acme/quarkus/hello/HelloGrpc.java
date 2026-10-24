package com.acme.quarkus.hello;

import io.grpc.BindableService;
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.MethodDescriptor;
import io.grpc.ServerServiceDefinition;
import io.grpc.ServiceDescriptor;
import io.grpc.stub.AbstractBlockingStub;
import io.grpc.stub.ClientCalls;
import io.grpc.stub.ServerCalls;
import io.grpc.stub.StreamObserver;

// A hand-written stand-in for what protoc-gen-grpc-java generates from
// `service Hello { rpc SayHello (…) returns (…); }` in package `acme.hello`, in the shape
// `fixtures/grpc-probe`'s real generated `OrderServiceGrpc` has (1.62.2, `javap`):
// - the identity-building calls on the outer class, `ServiceDescriptor.newBuilder(SERVICE_NAME)`
//   and `MethodDescriptor.generateFullMethodName(SERVICE_NAME, "SayHello")`;
// - the handler as a DEFAULT method of the nested `AsyncService` interface, with
//   `HelloImplBase` implementing it and declaring only `bindService`;
// - the nested `HelloBlockingStub`, and the descriptor-supplier classes at the bottom.
// Strings stand in for protobuf messages so the fixture needs no protoc step; nothing here
// ever runs.
public final class HelloGrpc {
    private HelloGrpc() {}

    public static final String SERVICE_NAME = "acme.hello.Hello";

    private static volatile MethodDescriptor<String, String> sayHelloMethod;
    private static volatile ServiceDescriptor serviceDescriptor;

    public static MethodDescriptor<String, String> getSayHelloMethod() {
        MethodDescriptor<String, String> method = sayHelloMethod;
        if (method == null) {
            method = MethodDescriptor.<String, String>newBuilder()
                    .setType(MethodDescriptor.MethodType.UNARY)
                    .setFullMethodName(MethodDescriptor.generateFullMethodName(SERVICE_NAME, "SayHello"))
                    .setRequestMarshaller(Utf8.INSTANCE)
                    .setResponseMarshaller(Utf8.INSTANCE)
                    .build();
            sayHelloMethod = method;
        }
        return method;
    }

    public static ServiceDescriptor getServiceDescriptor() {
        ServiceDescriptor descriptor = serviceDescriptor;
        if (descriptor == null) {
            descriptor = ServiceDescriptor.newBuilder(SERVICE_NAME)
                    .addMethod(getSayHelloMethod())
                    .build();
            serviceDescriptor = descriptor;
        }
        return descriptor;
    }

    public static HelloBlockingStub newBlockingStub(Channel channel) {
        return new HelloBlockingStub(channel, CallOptions.DEFAULT);
    }

    // The handlers are DEFAULT methods of this nested interface, and the base class only
    // implements it: protoc-gen-grpc-java's shape since it introduced `AsyncService`
    // (`fixtures/grpc-probe`, 1.62.2, `javap`).
    public interface AsyncService {
        default void sayHello(String request, StreamObserver<String> responseObserver) {
            ServerCalls.asyncUnimplementedUnaryCall(getSayHelloMethod(), responseObserver);
        }
    }

    public abstract static class HelloImplBase implements BindableService, AsyncService {
        @Override
        public final ServerServiceDefinition bindService() {
            return HelloGrpc.bindService(this);
        }
    }

    public static ServerServiceDefinition bindService(AsyncService service) {
        return ServerServiceDefinition.builder(getServiceDescriptor())
                .addMethod(getSayHelloMethod(), ServerCalls.asyncUnaryCall(service::sayHello))
                .build();
    }

    public static final class HelloBlockingStub extends AbstractBlockingStub<HelloBlockingStub> {
        private HelloBlockingStub(Channel channel, CallOptions callOptions) {
            super(channel, callOptions);
        }

        @Override
        protected HelloBlockingStub build(Channel channel, CallOptions callOptions) {
            return new HelloBlockingStub(channel, callOptions);
        }

        public String sayHello(String request) {
            return ClientCalls.blockingUnaryCall(
                    getChannel(), getSayHelloMethod(), getCallOptions(), request);
        }
    }

    // The nesting protoc emits beside the stubs in every full-protobuf `<Service>Grpc`: a
    // descriptor-supplier base and two classes extending it. Real ones implement
    // `io.grpc.protobuf.Proto*DescriptorSupplier` and return the file's descriptors; these
    // keep the two `extends` edges, which are what an analysis of the class reads.
    private abstract static class HelloBaseDescriptorSupplier {}

    private static final class HelloFileDescriptorSupplier extends HelloBaseDescriptorSupplier {}

    private static final class HelloMethodDescriptorSupplier extends HelloBaseDescriptorSupplier {
        private final String methodName;

        HelloMethodDescriptorSupplier(String methodName) {
            this.methodName = methodName;
        }
    }
}
