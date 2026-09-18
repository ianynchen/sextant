package com.acme.jaxrs;

import jakarta.ws.rs.sse.SseEventSink;
import java.util.List;

public class OrdersResource implements OrdersApi {
    @Override public List<String> list() { return List.of(); }
    @Override public String byId(String id) { return id; }
    @Override public void events(SseEventSink sink) {}
}
