package com.acme.orders.ws;

import jakarta.websocket.Endpoint;
import jakarta.websocket.EndpointConfig;
import jakarta.websocket.Session;
import jakarta.websocket.server.ServerApplicationConfig;
import jakarta.websocket.server.ServerEndpointConfig;
import java.util.Set;

/** The OTHER way a Jakarta WebSocket endpoint is registered: programmatically, through
 *  `ServerEndpointConfig.Builder.create(Class, path)`, with no `@ServerEndpoint` anywhere.
 *
 *  <p>A container discovers these through `ServerApplicationConfig`, which is how any
 *  application that computes its paths — or serves the same endpoint at several — does it. */
public class ProgrammaticWsConfig implements ServerApplicationConfig {

    public static class TicketEndpoint extends Endpoint {
        @Override
        public void onOpen(Session session, EndpointConfig config) {}
    }

    @Override
    public Set<ServerEndpointConfig> getEndpointConfigs(Set<Class<? extends Endpoint>> endpoints) {
        return Set.of(
            ServerEndpointConfig.Builder.create(TicketEndpoint.class, "/ws/tickets").build());
    }

    @Override
    public Set<Class<?>> getAnnotatedEndpointClasses(Set<Class<?>> scanned) {
        return Set.of();
    }
}
