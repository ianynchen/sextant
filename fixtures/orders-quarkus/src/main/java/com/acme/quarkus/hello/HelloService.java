package com.acme.quarkus.hello;

import io.grpc.stub.StreamObserver;
import io.quarkus.grpc.GrpcService;

// Quarkus's `@GrpcService` (spec 2026-10-24 §3d): REQUIRED on every Quarkus gRPC service
// bean (CP-52 row 7). The row comes from the generated supertype's own identity calls
// (`grpc-java.yml`); the annotation corroborates it (`grpc-spring.yml`).
@GrpcService
public class HelloService extends HelloGrpc.HelloImplBase {
    @Override
    public void sayHello(String request, StreamObserver<String> responseObserver) {
        responseObserver.onNext("hello " + request);
        responseObserver.onCompleted();
    }
}
