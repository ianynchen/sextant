// Half-2 of base-address resolution (2F design §4): every base URL below
// reaches the exact position `url_of` already captures off a WebClient
// chain — `.uri()`'s own argument, InventoryWebClient's literal-string
// position — fed imperatively instead: through a field, a constructor
// parameter, and a bound properties object. Verified against a live run
// (Task 3 report): `WebClient.builder().baseUrl(...)` is never itself a
// captured step in the shipped catalog, so a field threaded only through
// `baseUrl()` would leave every row here identical to a hand-built
// WebClient's own unrelated literal path — the field has to sit at
// `.uri()`'s own position for the field ladder (Task 8) to have anything
// to resolve. The fourth case defeats every rung on purpose: a
// concatenation the ladder cannot trace back to a single key.
package com.acme.orders.config;

import com.acme.orders.contracts.OrderView;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

public class BillingClients {

    private final WebClient webClient;

    // (a) field-level @Value — the field ladder's rung 1: the field's own
    // annotation names the placeholder expression directly.
    @Value("${billing.url}")
    private String fieldUrl;

    private final String constructorUrl;
    private final BillingProperties billingProperties;

    // (b) constructor-injected final field, fed by a @Value-annotated
    // parameter — rung 2: a field_write fact traces the assignment straight
    // back to the annotated parameter.
    public BillingClients(
            WebClient webClient,
            @Value("${billing.url}") String url,
            BillingProperties billingProperties) {
        this.webClient = webClient;
        this.constructorUrl = url;
        this.billingProperties = billingProperties;
    }

    public Mono<OrderView> fieldFedInvoice() {
        return webClient.get().uri(fieldUrl).retrieve().bodyToMono(OrderView.class);
    }

    public Mono<OrderView> constructorFedInvoice() {
        return webClient.get().uri(constructorUrl).retrieve().bodyToMono(OrderView.class);
    }

    // (c) @ConfigurationProperties(prefix = "billing") — rung 3: prefix
    // plus the relaxed-bound field name (`url`) synthesizes the
    // ${billing.url} expression with no @Value annotation anywhere on this
    // path.
    public Mono<OrderView> propertiesFedInvoice() {
        return webClient.get().uri(billingProperties.getUrl()).retrieve().bodyToMono(OrderView.class);
    }

    // (d) the computed-base miss: concatenation defeats every rung — rung
    // 4's unchanged answer, `unresolved` (the
    // computed_base_addresses_not_traced gap).
    public Mono<OrderView> computedBaseInvoice() {
        return webClient.get().uri(this.fieldUrl + "/v2").retrieve().bodyToMono(OrderView.class);
    }

    // Constructor-free, field-style @ConfigurationProperties — kept
    // distinct from case (b)'s constructor-injected @Value: a mutable
    // `url` field plus its getter/setter, bound by prefix rather than
    // annotated directly.
    @ConfigurationProperties(prefix = "billing")
    public static class BillingProperties {
        private String url;

        public String getUrl() {
            return url;
        }

        public void setUrl(String url) {
            this.url = url;
        }
    }
}
