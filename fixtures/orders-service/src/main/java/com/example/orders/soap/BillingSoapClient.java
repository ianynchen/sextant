package com.example.orders.soap;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.ws.client.core.WebServiceTemplate;
import com.example.orders.soap.payload.PlaceOrderRequest;

@Component
public class BillingSoapClient {

    private final WebServiceTemplate template;
    private final String billingUri;

    public BillingSoapClient(WebServiceTemplate template, @Value("${soap.billing.uri}") String billingUri) {
        this.template = template;
        this.template.setDefaultUri(billingUri);
        this.billingUri = billingUri;
    }

    public Object place(PlaceOrderRequest request) {
        return template.marshalSendAndReceive(request);                                   // defaultUri path
    }

    public Object placeAt(PlaceOrderRequest request) {
        return template.marshalSendAndReceive("http://billing.example.com/ws/direct", request);  // URI-literal path
    }
}
