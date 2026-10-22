// Capability 9.19's shape (spec 2026-10-21-merged-values-design.md): a project's own
// HTTP wrapper that NORMALISES the path on one branch before handing it to the client.
// `apolloconfig/apollo`'s `RetryableRestTemplate#execute` verbatim, minus the retry: the
// value reaching `exchange` is the parameter OR the `substring` call's result, which the
// extractor used to collapse to one sourceless `unresolved` — and every caller's literal
// below reached no row. The two callers differ only by the leading slash the wrapper
// strips, so the merge has a ROOT (the parameter) and resolves to each caller's literal,
// inexactly: the rows publish at `partial`, because what `substring` did to the text was
// never read.
package com.acme.orders.clients;

import com.acme.orders.contracts.OrderView;
import org.springframework.http.HttpMethod;
import org.springframework.web.client.RestTemplate;

public class NormalisingBillingClient {
    private final RestTemplate restTemplate;
    private final String baseUrl;

    public NormalisingBillingClient(RestTemplate restTemplate, String baseUrl) {
        this.restTemplate = restTemplate;
        this.baseUrl = baseUrl;
    }

    // The funnel: one `exchange`, reached by every caller, with the path reassigned on a
    // branch above it. `baseUrl` is a constructor-injected value nothing here states, so
    // the assembled address begins with a hole the address layer prints as `<host>`.
    public OrderView send(HttpMethod method, String path) {
        if (path.startsWith("/")) {
            path = path.substring(1);
        }
        return restTemplate.exchange(baseUrl + path, method, null, OrderView.class).getBody();
    }

    // A caller whose literal carries the slash the wrapper strips...
    public OrderView ledger() {
        return send(HttpMethod.GET, "/billing/ledger");
    }

    // ...and one whose literal does not. Both reach the same `exchange`; the rows carry each
    // literal as written, at `partial`.
    public OrderView ledgerEntry(String id) {
        return send(HttpMethod.GET, "billing/ledger/{id}");
    }
}
