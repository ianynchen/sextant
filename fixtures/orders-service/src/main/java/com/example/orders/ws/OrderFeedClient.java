// The OUTBOUND WebSocket direction (W46, `G-32`). This module served WebSocket
// endpoints and opened none, so §5.5 had three inbound Java rows and zero
// outbound with nothing saying the direction derives nothing.
//
// Three shapes, deliberately: the jakarta container's `connectToServer` with its
// URL one hop away behind `URI.create`, the same with a `new URI(...)`, and
// Spring's `WebSocketStompClient` whose URL is a plain string at argument 0.
package com.example.orders.ws;

import java.net.URI;
import jakarta.websocket.ContainerProvider;
import jakarta.websocket.WebSocketContainer;
import org.springframework.messaging.simp.stomp.StompSessionHandler;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.messaging.WebSocketStompClient;

@Component
public class OrderFeedClient {

    private final WebSocketStompClient stompClient;

    public OrderFeedClient(WebSocketStompClient stompClient) { this.stompClient = stompClient; }

    /** The URL is a literal one hop away, behind the static factory. */
    public void openFeed(Object endpoint) throws Exception {
        WebSocketContainer container = ContainerProvider.getWebSocketContainer();
        container.connectToServer(endpoint, URI.create("ws://feeds.example.com/orders"));
    }

    /** The same literal, one hop away behind a constructor instead. */
    public void openAudit(Object endpoint) throws Exception {
        WebSocketContainer container = ContainerProvider.getWebSocketContainer();
        container.connectToServer(endpoint, new URI("ws://feeds.example.com/audit"));
    }

    /** Spring's STOMP client takes its url as a plain string at argument 0. */
    public void openStomp(StompSessionHandler handler) {
        stompClient.connectAsync("ws://feeds.example.com/stomp", handler);
    }
}
