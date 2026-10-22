// A controller that exists in one environment only (spec 2026-10-21-conditional-controllers,
// ruled 2026-10-22): `@Profile("prod")` means Spring creates this bean only when the `prod`
// profile is active, so `GET /ops/status` is served in that deployment and 404s in `default`.
// The row STATES that, structured, per environment this module resolves (`default`, `prod`),
// and is dropped nowhere. Apollo's `HomePageController` is the production shape.
package com.acme.orders.conditional;

import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@Profile("prod")
@RestController
public class OpsController {
    @GetMapping("/ops/status")
    public String status() {
        return "ok";
    }
}
