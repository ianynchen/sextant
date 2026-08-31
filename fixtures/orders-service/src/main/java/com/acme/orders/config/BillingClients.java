// Half-2 of base-address resolution (2F design §4, amended at review round 1
// commit 461d35d): every base URL below reaches
// `WebClient.builder().baseUrl(...)` imperatively — through a field, a
// constructor parameter, and a bound properties object — rather than
// InventoryWebClient's already-injected WebClient. TODAY (before Tasks
// 5/8), `baseUrl()` is not a declared step in the shipped fluent catalog,
// so each row below derives off its own `.uri()` literal alone, peer NULL
// — pinned exactly as the live run emits it (Task 3 report). Task 8 adds a
// `base` capture with base+path composition; these rows are expected to
// change again then, which is re-freezing, not a bug. Each method's own
// `.uri()` literal is deliberately distinct (`/invoices`, `/refunds`,
// `/statements`) so the three real rows survive `fluent.py`'s cross-caller
// wire-identity dedup rather than collapsing into one. The fourth case
// defeats every future field-ladder rung on purpose: a concatenation the
// ladder cannot trace back to a single key.
package com.acme.orders.config;

import com.acme.orders.contracts.OrderView;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

public class BillingClients {

    // (a) field-level @Value — the field ladder's rung 1: the field's own
    // annotation names the placeholder expression directly.
    @Value("${billing.url}")
    private String fieldUrl;

    private final String constructorUrl;
    private final BillingProperties billingProperties;

    // (b) constructor-injected final field, fed by a @Value-annotated
    // parameter — rung 2: a field_write fact traces the assignment straight
    // back to the annotated parameter.
    public BillingClients(@Value("${billing.url}") String url, BillingProperties billingProperties) {
        this.constructorUrl = url;
        this.billingProperties = billingProperties;
    }

    public Mono<OrderView> fieldFedInvoice() {
        return WebClient.builder()
                .baseUrl(fieldUrl)
                .build()
                .get()
                .uri("/invoices")
                .retrieve()
                .bodyToMono(OrderView.class);
    }

    public Mono<OrderView> constructorFedInvoice() {
        return WebClient.builder()
                .baseUrl(constructorUrl)
                .build()
                .get()
                .uri("/refunds")
                .retrieve()
                .bodyToMono(OrderView.class);
    }

    // (c) @ConfigurationProperties(prefix = "billing") — rung 3: prefix
    // plus the relaxed-bound field name (`url`) synthesizes the
    // ${billing.url} expression with no @Value annotation anywhere on this
    // path.
    public Mono<OrderView> propertiesFedInvoice() {
        return WebClient.builder()
                .baseUrl(billingProperties.getUrl())
                .build()
                .get()
                .uri("/statements")
                .retrieve()
                .bodyToMono(OrderView.class);
    }

    // (d) the computed-base miss: concatenation defeats every rung — rung
    // 4's unchanged answer, `unresolved` (the
    // computed_base_addresses_not_traced gap).
    public Mono<OrderView> computedBaseInvoice() {
        return WebClient.builder()
                .baseUrl(this.fieldUrl + "/v2")
                .build()
                .get()
                .uri("/adjustments")
                .retrieve()
                .bodyToMono(OrderView.class);
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
