package com.example.orders.soap;

import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;
import org.springframework.ws.soap.server.endpoint.annotation.SoapAction;
import com.example.orders.soap.payload.PlaceOrderRequest;
import com.acme.orders.contracts.OrderView;

@Endpoint
public class OrderSoapEndpoint {

    @PayloadRoot(namespace = "http://orders.example.com/ws", localPart = "placeOrderRequest")
    @ResponsePayload
    public OrderView placeOrder(@RequestPayload PlaceOrderRequest request) { return null; }

    // ONE handler for TWO message types. Spring-WS reads `@PayloadRoots`, the container
    // `@PayloadRoot` declares itself `@Repeatable` with, so both messages route here.
    @PayloadRoot(namespace = "http://orders.example.com/ws", localPart = "amendOrderRequest")
    @PayloadRoot(namespace = "http://orders.example.com/ws", localPart = "reviseOrderRequest")
    @ResponsePayload
    public OrderView amendOrder(@RequestPayload PlaceOrderRequest request) { return null; }

    @SoapAction("http://orders.example.com/action/cancelOrder")
    @ResponsePayload
    public OrderView cancelOrder(@RequestPayload PlaceOrderRequest request) { return null; }
}
