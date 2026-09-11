package com.acme.orders;

import com.acme.orders.contracts.OrderTotals;
import com.acme.orders.contracts.OrderView;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Slice;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

// W26. Where a payload's wire contract comes from when it is not in the type's fields.
//
// `/totals` is the reachable half: `OrderTotals` is an interface this module declares,
// so its accessors are read and the shape carries real fields.
//
// The three paged handlers are the UNREACHABLE half, and they are here to stay
// unreachable: `Page` and `Slice` live in spring-data-commons, which this fixture does
// not name in `extract_libraries`, so their shapes stay open with no fields and the
// types are reported as ones nothing could expand. That is F4 §5.2's stated boundary,
// and pinning it is what keeps the accessor fallback from being mistaken for a rule
// that describes types the workspace never read.
@RestController
@RequestMapping("/v1/paged")
public class PayloadShapeController {

    @GetMapping("/totals")
    public OrderTotals totals() {
        return null;
    }

    @GetMapping("/orders")
    public Page<OrderView> pageOfOrders() {
        return null;
    }

    @GetMapping("/slice")
    public Slice<OrderView> sliceOfOrders() {
        return null;
    }

    @GetMapping("/wrapped")
    public ResponseEntity<Page<OrderView>> wrappedPageOfOrders() {
        return null;
    }
}
