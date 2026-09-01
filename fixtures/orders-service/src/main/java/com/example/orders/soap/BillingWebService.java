package com.example.orders.soap;

import jakarta.jws.WebMethod;
import jakarta.jws.WebService;
import com.acme.orders.contracts.OrderView;

@WebService(targetNamespace = "http://billing.example.com/ws")
public class BillingWebService {

    @WebMethod(operationName = "chargeOrder")
    public OrderView charge(String orderId) { return null; }

    public OrderView refund(String orderId) { return null; }        // bare public: JAX-WS exposes it (DR-6); name + namespace default

    @WebMethod(exclude = true)
    public void internalAudit() { }                                  // derives nothing
}
