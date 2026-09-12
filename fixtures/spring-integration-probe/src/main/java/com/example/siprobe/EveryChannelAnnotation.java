package com.example.siprobe;

import java.util.List;
import org.springframework.integration.annotation.Aggregator;
import org.springframework.integration.annotation.BridgeFrom;
import org.springframework.integration.annotation.BridgeTo;
import org.springframework.integration.annotation.Filter;
import org.springframework.integration.annotation.Router;
import org.springframework.integration.annotation.Splitter;
import org.springframework.integration.annotation.Transformer;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;
import org.springframework.stereotype.Component;

/** The seven channel-bearing annotations Spring Integration ships beside `@ServiceActivator`
 *  and `@InboundChannelAdapter` — each the ordinary way to declare that kind of component,
 *  and each naming the channel it reads from or writes to. Attributes are the ones each
 *  annotation ACTUALLY declares, read with `javap` at spring-integration-core 6.2.4:
 *  `@Router` has no `outputChannel`; `@BridgeFrom`/`@BridgeTo` take `value`. */
@Component
public class EveryChannelAnnotation {

    @Transformer(inputChannel = "raw.orders", outputChannel = "clean.orders")
    public String normalise(String payload) { return payload.trim(); }

    @Filter(inputChannel = "clean.orders", outputChannel = "valid.orders")
    public boolean isValid(String payload) { return !payload.isEmpty(); }

    @Splitter(inputChannel = "valid.orders", outputChannel = "order.lines")
    public List<String> lines(String payload) { return List.of(payload.split(",")); }

    @Aggregator(inputChannel = "order.lines", outputChannel = "order.totals")
    public String total(List<String> lines) { return String.join("+", lines); }

    @Router(inputChannel = "order.totals")
    public String route(String total) { return total.isEmpty() ? "empty.totals" : "priced.totals"; }

    @BridgeFrom("priced.totals")
    public MessageChannel pricedBridge() { return new DirectChannel(); }

    @BridgeTo("archive.orders")
    public MessageChannel archiveBridge() { return new DirectChannel(); }
}
