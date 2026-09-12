/**
 * A PLAIN superclass — no `@WebService`, no JAX-WS annotation at all — declaring
 * one public method. `BillingWebService` below inherits it without overriding it,
 * the exact shape `jakarta-jws.yml`'s own comment names for the JAX-WS RI
 * (`A-M15`, CP-13 Q3): "a `@WebService public class BillingWebService extends
 * AbstractBilling` published none of the base's operations, silently" before the
 * RI-side fix. W63 asks whether CXF's rule agrees with the RI's fixed rule.
 */
public abstract class AbstractBilling {
    public String refund(String orderId) {
        return "refunded:" + orderId;
    }
}
