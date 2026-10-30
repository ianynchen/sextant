package com.example.grpcprobe;

import com.example.grpcprobe.proto.GetOrderReply;
import com.example.grpcprobe.proto.GetOrderRequest;
import com.example.grpcprobe.proto.OrderServiceGrpc;
import io.grpc.Server;
import io.grpc.ServerBuilder;
import io.grpc.stub.StreamObserver;

/** The newer grpc-java service shape, re-measured at 1.81.0
 *  ({@code scripts/probes/cp3_cp8_grpc_facts.md}): a class implementing the generated
 *  {@code AsyncService} interface directly, never extending {@code OrderServiceImplBase},
 *  and registered through the generated static {@code OrderServiceGrpc.bindService}.
 *  MEASURED 2026-10-30: {@code grpc-java.yml} derives no row for it, so this class is
 *  not named as a handler. Kept as the evidence for that finding, not as a pinned
 *  expectation. */
public class OrderServiceAsyncImpl implements OrderServiceGrpc.AsyncService {
    @Override
    public void getOrder(GetOrderRequest request, StreamObserver<GetOrderReply> responseObserver) {
        responseObserver.onNext(
            GetOrderReply.newBuilder().setOrderId(request.getOrderId()).setStatus("OPEN").build());
        responseObserver.onCompleted();
    }

    public static Server serve(int port) {
        return ServerBuilder.forPort(port)
            .addService(OrderServiceGrpc.bindService(new OrderServiceAsyncImpl()))
            .build();
    }
}
