// The covariant-return case beside OrdersApiController: a subtype of the
// interface's declared OrderResult, compiled with a bridge method
// (`OrderResult find(long)`) that the name+descriptor join must not
// double-count.
package com.acme.orders.openapi;

import com.acme.orders.OrderResult;

public class DetailedOrderResult extends OrderResult {
}
