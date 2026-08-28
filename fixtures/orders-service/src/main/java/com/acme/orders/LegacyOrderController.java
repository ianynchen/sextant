package com.acme.orders;

import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RestController;

/**
 * The pre-4.3 Spring form, and the `path` alias. Both are ordinary Spring and
 * both were invisible: `@RequestMapping` served only as a prefix, and the path
 * was read from `value` alone, so `path = "…"` produced an endpoint with an
 * empty path — wrong output rather than a missing one.
 */
@RestController
@RequestMapping(path = "/v1/legacy")
public class LegacyOrderController {

    private final OrderService service = new OrderService();

    @RequestMapping(method = RequestMethod.GET, path = "/orders")
    public OrderResult listLegacy() {
        return service.find(1L);
    }

    @RequestMapping(method = {RequestMethod.PUT, RequestMethod.PATCH}, value = "/orders/{id}")
    public OrderResult amend(long id) {
        return service.find(id);
    }

    /** No method named: Spring accepts every one of them, so this is eight endpoints. */
    @RequestMapping("/orders/any")
    public OrderResult any() {
        return service.find(2L);
    }
}
