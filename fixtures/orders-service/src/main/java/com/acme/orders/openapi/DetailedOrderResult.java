// The covariant-return case beside OrdersApiController: a subtype of the
// interface's declared OrderResult, compiled with a bridge method
// (`OrderResult find(long)`) that the name+descriptor join must not
// double-count.
//
// It also carries the INHERITED-FIELD case (F4 §5.2), and `detail` is what makes
// it one. A payload that declares no field of its own falls back to the accessor
// pass, which has walked the ancestry since W26 — so it came out right for the
// wrong reason. A payload with SOME field of its own never reaches that fallback,
// and its inherited fields were invisible: measured on `mall-admin`,
// `dto/OmsOrderDetail extends model/OmsOrder` published 2 wire fields and claimed
// `open: false` while the parent declared 45 more. This class is that shape, so
// the always-on gate holds it: the wire contract here is `detail` PLUS `orderId`
// and `status`, and reading only the first is a payload described as complete
// while most of it is missing.
package com.acme.orders.openapi;

import com.acme.orders.OrderResult;

public class DetailedOrderResult extends OrderResult {
    private String detail;

    public String getDetail() { return detail; }
}
