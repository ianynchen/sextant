package com.acme.orders;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * The class-prefix seam, in the form real code writes it: the prefix carries no
 * trailing slash and the method path carries no leading one, so the separator
 * is spelled by NEITHER half. Spring joins them with exactly one `/` regardless
 * — this is served at `/v1/seam/owners/{ownerId}`.
 *
 * <p>Ordinary Spring, and it derived a wrong address: the composition was a
 * bare concatenation, which published `/v1/seamowners/{ownerId}` at
 * `resolved`/`compiler` — an address nobody serves, presented as observed.
 * Found live against spring-petclinic-microservices, whose api-gateway writes
 * exactly this (`@RequestMapping("/api/gateway")` +
 * `@GetMapping("owners/{ownerId}")`).
 */
@RestController
@RequestMapping("/v1/seam")
public class SeamController {

    private final OrderService service = new OrderService();

    @GetMapping("owners/{ownerId}")
    public OrderResult owner(@PathVariable long ownerId) {
        return service.find(ownerId);
    }
}
