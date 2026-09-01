package com.example.orders.soap;

import javax.jws.WebMethod;
import javax.jws.WebService;
import com.acme.orders.contracts.OrderView;

// javax spelling of BillingWebService, no explicit targetNamespace — pins
// the reversed-package default derivation on the javax row too (DR-6).
@WebService
public class LegacyBillingWebService {

    @WebMethod(operationName = "legacyCharge")
    public OrderView charge(String orderId) { return null; }
}
