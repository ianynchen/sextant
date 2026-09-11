package com.example.siprobe;

import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.dsl.Amqp;
import org.springframework.integration.dsl.IntegrationFlow;

/** Q5 — where the destination comes from when it is NOT a literal. Six
 *  spellings, all of them things real applications do, each reaching the same
 *  {@code Amqp.inboundAdapter} call site by a different route. */
@Configuration
public class VarianceSources {

    /** Field-injected via `@Value`. */
    @Value("${probe.value-queue}")
    private String valueQueue;

    private final ProbeProperties properties;

    public VarianceSources(ProbeProperties properties) {
        this.properties = properties;
    }

    /** (0) a plain literal. Added with capability 9.15 so the varargs arm
     *  carries the SAME eight spellings {@link SingleStringControl}'s
     *  single-`String` arm does — the control arm's first row had no varargs
     *  counterpart here, and the two arms have to be compared row for row for
     *  "the varargs side discriminates every one" to mean anything. */
    @Bean
    public IntegrationFlow literalQueueFlow(ConnectionFactory connectionFactory) {
        return IntegrationFlow.from(Amqp.inboundAdapter(connectionFactory, "variance.literal.queue"))
                .handle(String.class, (payload, headers) -> null)
                .get();
    }

    /** (a) a compile-time constant — javac must inline it. */
    @Bean
    public IntegrationFlow constantQueueFlow(ConnectionFactory connectionFactory) {
        return IntegrationFlow.from(Amqp.inboundAdapter(connectionFactory, Destinations.ORDERS_QUEUE))
                .handle(String.class, (payload, headers) -> null)
                .get();
    }

    /** (b) a static final that is NOT a compile-time constant. */
    @Bean
    public IntegrationFlow lateConstantQueueFlow(ConnectionFactory connectionFactory) {
        return IntegrationFlow.from(Amqp.inboundAdapter(connectionFactory, Destinations.LATE_QUEUE))
                .handle(String.class, (payload, headers) -> null)
                .get();
    }

    /** (c) a `@Value`-injected field. */
    @Bean
    public IntegrationFlow valueFieldQueueFlow(ConnectionFactory connectionFactory) {
        return IntegrationFlow.from(Amqp.inboundAdapter(connectionFactory, this.valueQueue))
                .handle(String.class, (payload, headers) -> null)
                .get();
    }

    /** (d) a `@Value`-annotated bean-method parameter. */
    @Bean
    public IntegrationFlow valueParameterQueueFlow(ConnectionFactory connectionFactory,
                                                   @Value("${probe.param-queue}") String paramQueue) {
        return IntegrationFlow.from(Amqp.inboundAdapter(connectionFactory, paramQueue))
                .handle(String.class, (payload, headers) -> null)
                .get();
    }

    /** (e) a raw property placeholder passed as the literal itself — Spring
     *  Integration resolves `${...}` inside adapter arguments at runtime. */
    @Bean
    public IntegrationFlow placeholderQueueFlow(ConnectionFactory connectionFactory) {
        return IntegrationFlow.from(Amqp.inboundAdapter(connectionFactory, "${probe.placeholder-queue}"))
                .handle(String.class, (payload, headers) -> null)
                .get();
    }

    /** (f) a getter on a bound `@ConfigurationProperties` bean. */
    @Bean
    public IntegrationFlow propertiesQueueFlow(ConnectionFactory connectionFactory) {
        return IntegrationFlow.from(Amqp.inboundAdapter(connectionFactory, this.properties.getQueue()))
                .handle(String.class, (payload, headers) -> null)
                .get();
    }

    /** (g) a concatenation — an environment-prefixed queue, the most common
     *  reason a name is not a single literal. */
    @Bean
    public IntegrationFlow concatenatedQueueFlow(ConnectionFactory connectionFactory,
                                                 @Value("${probe.env}") String env) {
        return IntegrationFlow.from(Amqp.inboundAdapter(connectionFactory, env + ".orders.queue"))
                .handle(String.class, (payload, headers) -> null)
                .get();
    }
}
