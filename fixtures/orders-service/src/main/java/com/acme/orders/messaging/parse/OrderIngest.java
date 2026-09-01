// The one-hop delegation target (2G design §6, rung B): a package-local
// method whose own parameter carries the channel's bytes and whose body
// parses them. Two listeners call it, which is the "multi-caller is not
// ambiguity" case — both channels' bytes provably reach this parse, so both
// endpoints bind it.
package com.acme.orders.messaging.parse;

import com.example.orders.proto.OrderProtos.OrderRequest;

class OrderIngest {

    // `payload` is passed to `parseFrom` as a BARE load, deliberately: an
    // argument built by a call (`payload.clone()`) or merged from a branch
    // reads `unresolved` rather than naming the parameter (Phase 2G
    // checkpoint, Task 3), and rung B would then have nothing to join on.
    OrderRequest process(byte[] payload) throws Exception {
        return OrderRequest.parseFrom(payload);
    }
}
