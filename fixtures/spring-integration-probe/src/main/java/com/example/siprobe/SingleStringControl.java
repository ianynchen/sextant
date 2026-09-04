package com.example.siprobe;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;

/** The control arm for Q5. `VarianceSources` sends the same seven destination
 *  expressions into a `String...` parameter, where they all erase to one
 *  `unresolved`. This class sends the SAME seven into a single-`String`
 *  parameter — `JmsOutboundChannelAdapterSpec#destination(String)` — so the
 *  probe can say what each expression looks like when the varargs array is not
 *  in the way, measured rather than predicted. */
@Configuration
public class SingleStringControl {

    @Value("${probe.value-queue}")
    private String valueQueue;

    private final ProbeProperties properties;

    public SingleStringControl(ProbeProperties properties) {
        this.properties = properties;
    }

    @Bean
    public IntegrationFlow controlLiteral(jakarta.jms.ConnectionFactory cf) {
        return flow -> flow.handle(Jms.outboundAdapter(cf).destination("control.literal.queue"));
    }

    @Bean
    public IntegrationFlow controlCompileTimeConstant(jakarta.jms.ConnectionFactory cf) {
        return flow -> flow.handle(Jms.outboundAdapter(cf).destination(Destinations.ORDERS_QUEUE));
    }

    @Bean
    public IntegrationFlow controlLateConstant(jakarta.jms.ConnectionFactory cf) {
        return flow -> flow.handle(Jms.outboundAdapter(cf).destination(Destinations.LATE_QUEUE));
    }

    @Bean
    public IntegrationFlow controlValueField(jakarta.jms.ConnectionFactory cf) {
        return flow -> flow.handle(Jms.outboundAdapter(cf).destination(this.valueQueue));
    }

    @Bean
    public IntegrationFlow controlValueParameter(jakarta.jms.ConnectionFactory cf,
                                                 @Value("${probe.param-queue}") String paramQueue) {
        return flow -> flow.handle(Jms.outboundAdapter(cf).destination(paramQueue));
    }

    @Bean
    public IntegrationFlow controlPlaceholder(jakarta.jms.ConnectionFactory cf) {
        return flow -> flow.handle(Jms.outboundAdapter(cf).destination("${probe.placeholder-queue}"));
    }

    @Bean
    public IntegrationFlow controlPropertiesGetter(jakarta.jms.ConnectionFactory cf) {
        return flow -> flow.handle(Jms.outboundAdapter(cf).destination(this.properties.getQueue()));
    }

    @Bean
    public IntegrationFlow controlConcatenation(jakarta.jms.ConnectionFactory cf,
                                                @Value("${probe.env}") String env) {
        return flow -> flow.handle(Jms.outboundAdapter(cf).destination(env + ".orders.queue"));
    }
}
