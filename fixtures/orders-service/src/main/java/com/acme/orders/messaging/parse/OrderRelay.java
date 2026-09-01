// The second hop (2G design §6's `payload_parsed_beyond_horizon`): a
// package-local method that only PASSES the bytes on. A listener delegating
// here reaches the parse in `OrderIngest` at hop two, which is past the line
// the design draws — so the binding is refused and the candidate is
// ledgered for 2K instead of guessed at.
package com.acme.orders.messaging.parse;

class OrderRelay {

    private final OrderIngest ingest = new OrderIngest();

    void forward(byte[] payload) throws Exception {
        ingest.process(payload);
    }
}
