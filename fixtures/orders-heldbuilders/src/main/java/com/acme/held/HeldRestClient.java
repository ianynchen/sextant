package com.acme.held;

import org.springframework.web.client.RestClient;

/** `spring-restclient.yml` in the variable style. One row, `POST /y`, with its request and
 *  response shapes. */
public class HeldRestClient {
    private final RestClient client;

    public HeldRestClient(RestClient client) {
        this.client = client;
    }

    public Order create(Order order) {
        RestClient.RequestBodyUriSpec request = client.post();
        request.uri("/y");
        request.body(order);
        RestClient.ResponseSpec response = request.retrieve();
        return response.body(Order.class);
    }
}
