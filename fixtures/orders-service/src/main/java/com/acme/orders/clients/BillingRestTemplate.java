// The RestTemplate half of the single_call surface: one method per verb
// shape the catalog's `methods` rows must each match on its own — the
// client is held in a field, never conjured per call, so every chain here
// roots on a field read like real Spring code does.
package com.acme.orders.clients;

import com.acme.orders.contracts.OrderRequest;
import com.acme.orders.contracts.OrderView;
import java.util.List;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.RestTemplate;

public class BillingRestTemplate {
    private final RestTemplate restTemplate;

    public BillingRestTemplate(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    // getForObject with a class-literal response: the URI template's `{id}`
    // placeholder is the wire path verbatim — the varargs id never changes
    // it, which is exactly the point of capturing the string literal, not
    // the resolved call.
    public OrderView getBalance(String id) {
        return restTemplate.getForObject("/billing/balances/{id}", OrderView.class, id);
    }

    // postForObject: the body is the second positional argument, the
    // response is again a class literal — the simplest shape the catalog
    // has to match.
    public OrderView submitSettlement(OrderRequest settlement) {
        return restTemplate.postForObject("/billing/settlements", settlement, OrderView.class);
    }

    // put returns void: no response argument for the catalog row to read,
    // only url and body — the row still derives on that alone.
    public void updateSettlement(String id, OrderRequest settlement) {
        restTemplate.put("/billing/settlements/{id}", settlement, id);
    }

    // exchange: the verb is an enum constant (GETSTATIC on HttpMethod, never
    // a string), the body arrives through an HttpEntity built inline so the
    // one-hop payload follow (§2) has a linked constructor call site to
    // land on, and the response is a PTR whose anonymous class is itself
    // part of the scanned surface — List<OrderView> resolves through its
    // generic supertype, never a class literal.
    public List<OrderView> batchSettlements(OrderRequest settlement) {
        ResponseEntity<List<OrderView>> response = restTemplate.exchange(
                "/billing/batch",
                HttpMethod.POST,
                new HttpEntity<>(new OrderRequest()),
                new ParameterizedTypeReference<List<OrderView>>() {});
        return response.getBody();
    }
}
