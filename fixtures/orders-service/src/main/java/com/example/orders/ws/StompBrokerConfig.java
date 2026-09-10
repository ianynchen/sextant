// The transport endpoint the STOMP destinations arrive on (W45, `G-42`).
// `OrderStompController`'s `@MessageMapping` destinations have derived since 2H
// and this module published no URL a client could open to reach them.
//
// Two registrations, deliberately: one single-path and one naming two paths, so
// the varargs collapse — one call argument holding an array — is exercised live
// rather than only over synthetic facts.
package com.example.orders.ws;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class StompBrokerConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
        registry.addEndpoint("/ws-alt", "/ws-legacy");
    }
}
