package com.acme.orders;

import com.acme.orders.contracts.OrderView;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

// Spec 2026-09-19 §5c: a mapping's OWN `params`/`headers` expressions are requirements the
// routing tree enforces, one `endpoint_metadata` row each, parsed as
// `AbstractNameValueExpression` parses them (CP-25 row 13) and UNIONED across the class and
// the method as `ParamsRequestCondition.combine` unions them. `tenant` on the class reaches
// every handler: `required`. On `versioned`: `v=1` is `required` with the value, `!X-Legacy`
// is `absent` — the request must NOT carry the header. On `legacy`: `v!=1` is `optional`
// (served whenever `v` is not `1`, an absent `v` included; the excluded value has no column),
// `X-Api` is `required`, and `Accept=application/json` gets NO row — `HeadersRequestCondition`
// drops `Accept`/`Content-Type` and Spring reads them as produces/consumes instead (A4, CP-25
// row 4). `kind: param` for `params=`, because Spring reads the query string and a form body
// through one API. A class of its own so no pinned row moves; `RoutingConditionsController`
// (W28) carries the same attributes for the conflict detector and derives rows here too.
@RestController
@RequestMapping(value = "/v1/conditions", params = "tenant")
public class MappingConditionsController {

    @GetMapping(value = "/orders", params = "v=1", headers = "!X-Legacy")
    public OrderView versioned() {
        return null;
    }

    @GetMapping(value = "/legacy", params = "v!=1", headers = {"X-Api", "Accept=application/json"})
    public OrderView legacy() {
        return null;
    }
}
