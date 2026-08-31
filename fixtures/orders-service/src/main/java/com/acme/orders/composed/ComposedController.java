// The ONLY mapping here is the `@ApiGet` composition -- a plain mapping
// alongside it would derive a row today and break the zero-new-rows
// invariant (the composed-annotation pre-pass doesn't exist until Tasks
// 5-9).
package com.acme.orders.composed;

import com.acme.orders.OrderResult;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ComposedController {

    @ApiGet
    public OrderResult composed() {
        return new OrderResult();
    }
}
