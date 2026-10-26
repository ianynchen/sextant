package com.acme.quarkus.hello;

import io.quarkus.grpc.GrpcClient;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;

// grpc-java's self-call (spec 2026-10-25 §3f): a blocking stub of `acme.hello.Hello`,
// which `HelloService` serves here. No outbound row; a hop to `HelloService#sayHello`.
@Path("/hello")
public class HelloResource {
    @GrpcClient("hello")
    HelloGrpc.HelloBlockingStub hello;

    @GET
    @Path("/{name}")
    public String hello(String name) {
        return hello.sayHello(name);
    }
}
