// Bytes-only channels, where the payload TYPE is nowhere in the handler's
// signature and the only evidence is the parse call in the code (2G design
// §6). Every destination here is unique to this file: two listeners sharing
// one destination would merge into a single endpoint row, and the pins below
// are per row.
package com.acme.orders.messaging.parse;

import com.acme.orders.contracts.OrderView;
import com.example.orders.proto.OrderProtos.OrderRequest;
import io.awspring.cloud.sqs.annotation.SqsListener;
import org.springframework.jms.annotation.JmsListener;
import tools.jackson.databind.json.JsonMapper;

public class ParsedPayloadListeners {

    private static final JsonMapper MAPPER = new JsonMapper();

    private final OrderIngest ingest = new OrderIngest();
    private final OrderRelay relay = new OrderRelay();

    // Rung A: the parse is in the handler's own body and its bytes argument
    // is a bare load of the payload parameter. `void`, deliberately: a
    // handler RETURNING the parsed type would put the schema-described type
    // in `response_shape` off the signature alone, and the format ladder's
    // rung 4 would then answer this row whether or not the binding worked —
    // the pin would prove nothing.
    @SqsListener("parsed-orders-inbound")
    public void onParsed(byte[] body) throws Exception {
        OrderRequest.parseFrom(body);
    }

    // Rung B: the payload parameter is handed, bare, to a module-local
    // method that parses its corresponding parameter.
    @JmsListener(destination = "parsed-audit-queue")
    public void onDelegated(byte[] body) throws Exception {
        ingest.process(body);
    }

    // Rung B again, from a second channel into the SAME callee: multi-caller
    // is not ambiguity (2G design §6) — both destinations' bytes reach that
    // one parse, so both rows bind it.
    @SqsListener("parsed-shared-inbound")
    public void onShared(byte[] body) throws Exception {
        ingest.process(body);
    }

    // Real ambiguity: one payload parameter, two different parses naming two
    // different types. Written as two SEQUENTIAL, unconditional statements
    // rather than a ternary or a try/catch fallback — a value merged from a
    // parameter and any other producer reads `unresolved` rather than naming
    // the parameter (Phase 2G checkpoint, Task 3), so a conditional form
    // would bind nothing for a reason that has nothing to do with ambiguity
    // and would test the wrong thing.
    @SqsListener("parsed-mixed-inbound")
    public void onMixed(byte[] body) throws Exception {
        OrderRequest.parseFrom(body);
        MAPPER.readValue(body, OrderView.class);
    }

    // Two hops: the parse lives in what THIS callee calls, not in the callee.
    @JmsListener(destination = "parsed-relay-queue")
    public void onRelayed(byte[] body) throws Exception {
        relay.forward(body);
    }
}
