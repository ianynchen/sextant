package com.acme.streams;

import java.util.List;
import org.apache.kafka.streams.StreamsBuilder;
import org.apache.kafka.streams.Topology;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.KTable;
import org.apache.kafka.streams.kstream.ValueMapper;

/** A topology the way the Kafka Streams quickstart writes one. */
public class OrderTopology {

    public Topology build() {
        StreamsBuilder builder = new StreamsBuilder();
        KStream<String, String> orders = builder.stream("streams.orders.placed");
        KStream<String, String> audit = builder.stream(List.of("streams.audit.a", "streams.audit.b"));
        KTable<String, String> customers = builder.table("streams.customers");
        builder.globalTable("streams.rates");
        orders.mapValues((ValueMapper<String, String>) String::toUpperCase).to("streams.orders.shouted");
        audit.to("streams.audit.merged");
        customers.toStream().to("streams.customers.changelog");
        return builder.build();
    }

    public Topology processorApi() {
        Topology topology = new Topology();
        topology.addSource("src", "streams.pa.in.a", "streams.pa.in.b");
        topology.addSink("snk", "streams.pa.out", "src");
        return topology;
    }
}
