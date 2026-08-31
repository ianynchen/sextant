// The messaging-composition mirror of ComposedController: the ONLY listener
// mapping here comes through `@OrderTopicListener`.
package com.acme.orders.composed;

import com.acme.orders.contracts.OrderEvent;

public class ComposedListener {

    @OrderTopicListener
    public void onComposedEvent(OrderEvent event) {
    }
}
