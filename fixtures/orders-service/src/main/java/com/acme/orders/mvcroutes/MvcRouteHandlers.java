// The servlet-side twin of `routes/RouteHandlers`. Bodies stay inert — no
// outbound client calls — so this surface derives rows through the combinator
// engine and nothing else.
package com.acme.orders.mvcroutes;

import org.springframework.stereotype.Component;
import org.springframework.web.servlet.function.ServerRequest;
import org.springframework.web.servlet.function.ServerResponse;

@Component
public class MvcRouteHandlers {

    public ServerResponse listInvoices(ServerRequest request) {
        return ServerResponse.ok().build();
    }

    public ServerResponse createInvoice(ServerRequest request) {
        return ServerResponse.ok().build();
    }

    public ServerResponse archive(ServerRequest request) {
        return ServerResponse.ok().build();
    }
}
