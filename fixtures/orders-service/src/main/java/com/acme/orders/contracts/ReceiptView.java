package com.acme.orders.contracts;

// A response value the messaging layer replies with: `@SendTo`'s static
// reply topic and the dynamic (`ReplyingKafkaTemplate`) reply both carry
// this. No existing contract fits — OrderResult is a controller-package
// response, and OrderView's `headers` field exists specifically to stay an
// open shape — so this stays its own small DTO.
public class ReceiptView {
    public String orderId;
    public String status;
}
