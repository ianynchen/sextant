package com.example.grpcprobe;

import com.example.grpcprobe.proto.GetOrderReply;
import com.example.grpcprobe.proto.GetOrderRequest;
import com.example.grpcprobe.proto.OrderServiceGrpc;
import io.grpc.stub.StreamObserver;

/** CP-8(c)'s fixture: a locally implemented gRPC service, the shape
 *  {@code supertype_derived} (2O design §1b) reads — a class whose `extends`
 *  target is the generated {@code ImplBase}. */
public class OrderServiceImpl extends OrderServiceGrpc.OrderServiceImplBase {
    @Override
    public void getOrder(GetOrderRequest request, StreamObserver<GetOrderReply> responseObserver) {
        responseObserver.onNext(
            GetOrderReply.newBuilder().setOrderId(request.getOrderId()).setStatus("OPEN").build());
        responseObserver.onCompleted();
    }
}
