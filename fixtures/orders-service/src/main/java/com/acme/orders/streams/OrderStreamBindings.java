// Spring Cloud Stream's functional programming model (tiers 1+2, 2F design
// §0): a bean's own type — Consumer/Supplier/Function — is the binding
// shape, and `spring.cloud.function.definition` (application.yml) selects
// which beans actually bind. `handleOrder`/`auditTap`/`orphanConsumer` are
// selected; `unselectedBean` deliberately is not — the selection pin. Bodies
// are trivial lambdas: nothing here may call a template/client API, so the
// only endpoint evidence is the `config_join` binding derivation itself.
package com.acme.orders.streams;

import com.acme.orders.contracts.OrderEvent;
import java.util.function.Consumer;
import java.util.function.Supplier;
import org.springframework.context.annotation.Bean;

public class OrderStreamBindings {

    // Consumer -> "-in-0" inbound binding, key
    // spring.cloud.stream.bindings.handleOrder-in-0.destination (resolved:
    // order-events).
    @Bean
    public Consumer<OrderEvent> handleOrder() {
        return event -> {};
    }

    // Supplier -> "-out-0" outbound binding, key
    // spring.cloud.stream.bindings.auditTap-out-0.destination (resolved:
    // audit-tap).
    @Bean
    public Supplier<OrderEvent> auditTap() {
        return () -> null;
    }

    // Selected by definition, but application.yml declares no
    // orphanConsumer-in-0 binding key at all — the missing-binding-key pin
    // (Task 7): a selected bean whose destination the config just never
    // names.
    @Bean
    public Consumer<OrderEvent> orphanConsumer() {
        return event -> {};
    }

    // NOT listed in spring.cloud.function.definition — the selection pin:
    // this bean must derive no binding row at all.
    @Bean
    public Consumer<OrderEvent> unselectedBean() {
        return event -> {};
    }
}
