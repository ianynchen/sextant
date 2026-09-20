package com.acme.orders;

import com.acme.orders.contracts.OrderView;
import java.util.Map;
import java.util.Optional;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

// Spec 2026-09-19 §5b: what Spring's binder ENFORCES on each annotated parameter, one
// handler carrying every form the rule reads (CP-25 rows 2, 3 and 5). `q` is required —
// no default, `required` at its default, a plain `String` (whose type reference is
// `nullable: true` by Java's rule and whose binder rejects a request without it all the
// same); `tag` is optional by `required = false`; `page` by a WRITTEN `defaultValue`;
// `sort` by its `Optional` type, and named by the attribute rather than the parameter;
// `all` is the whole-map binding the catalog skips — it binds everything and names
// nothing; `tenant` a required header; `session` an optional cookie.
//
// Its own handler rather than a parameter added to `OrderController`, so no pinned row
// there moves: a class whose every row is new.
@RestController
@RequestMapping("/v1/params")
public class RequestParamsController {

    @GetMapping("/search")
    public OrderView search(
            @RequestParam String q,
            @RequestParam(required = false) String tag,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(name = "sort") Optional<String> sort,
            @RequestParam Map<String, String> all,
            @RequestHeader("X-Tenant") String tenant,
            @CookieValue(value = "session", required = false) String session) {
        return null;
    }
}
