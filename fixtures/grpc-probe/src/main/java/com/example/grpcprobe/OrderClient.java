package com.example.grpcprobe;

import com.example.grpcprobe.proto.GetOrderReply;
import com.example.grpcprobe.proto.GetOrderRequest;
import com.example.grpcprobe.proto.OrderServiceGrpc;
import io.grpc.Channel;
import io.grpc.StatusException;

/** One call through the classic blocking stub and one through the
 *  {@code OrderServiceBlockingV2Stub} grpc-java 1.81.0 generates
 *  ({@code scripts/probes/cp3_cp8_grpc_facts.md}, "Re-measured at 1.81.0"). The V2 stub
 *  extends {@code AbstractBlockingStub} and sends through
 *  {@code ClientCalls.blockingV2UnaryCall}, so {@code grpc-java.yml}'s
 *  {@code client_stub_supertype}/{@code client_call_owner} already reach it: MEASURED
 *  2026-10-30, both calls arrive at {@code OrderServiceImpl#getOrder} as a hop. */
public class OrderClient {
    private final Channel channel;

    public OrderClient(Channel channel) {
        this.channel = channel;
    }

    public GetOrderReply viaBlockingStub(String id) {
        return OrderServiceGrpc.newBlockingStub(channel)
            .getOrder(GetOrderRequest.newBuilder().setOrderId(id).build());
    }

    public GetOrderReply viaBlockingV2Stub(String id) throws StatusException {
        return OrderServiceGrpc.newBlockingV2Stub(channel)
            .getOrder(GetOrderRequest.newBuilder().setOrderId(id).build());
    }
}
