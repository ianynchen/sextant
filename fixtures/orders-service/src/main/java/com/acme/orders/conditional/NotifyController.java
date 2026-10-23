// A handler whose call narrows: `sender.send` is declared on `NotificationSender`, which has two
// implementations that never exist together (`orders.notify`), so the trace states which one
// is the callee in each environment.
package com.acme.orders.conditional;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class NotifyController {
    @Autowired
    private NotificationSender sender;

    @PostMapping("/notify")
    public String notify(String message) {
        sender.send(message);
        return "sent";
    }
}
