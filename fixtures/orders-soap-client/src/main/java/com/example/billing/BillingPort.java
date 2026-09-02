package com.example.billing;

import jakarta.jws.WebMethod;
import jakarta.jws.WebService;

/**
 * The shape `wsimport` generates for a service endpoint interface: a
 * {@code @WebService} INTERFACE whose operations carry {@code @WebMethod}.
 * Nothing in `orders-service` implements it — a stub is called through, never
 * served, and an interface the module implements is subtracted by the SEI
 * fence.
 */
@WebService(targetNamespace = "http://billing.example.com/ws")
public interface BillingPort {

    // The operation name differs from the method name on purpose: the derived
    // address must come from `operationName`, not from the fallback that
    // answers when no attribute names one.
    @WebMethod(operationName = "stubCharge")
    String charge(String orderId);
}
