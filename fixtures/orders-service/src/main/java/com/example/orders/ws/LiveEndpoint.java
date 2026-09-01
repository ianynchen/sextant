package com.example.orders.ws;
import jakarta.websocket.OnMessage;
import jakarta.websocket.server.ServerEndpoint;

@ServerEndpoint("/live")
public class LiveEndpoint {
    @OnMessage
    public void onFrame(String frame) { }
}
