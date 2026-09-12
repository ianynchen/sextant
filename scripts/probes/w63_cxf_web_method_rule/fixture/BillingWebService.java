import jakarta.jws.WebMethod;
import jakarta.jws.WebService;

/**
 * `jakarta-jws.yml`'s own scenario: `declared_on: class` (the annotation sits on
 * the implementor, no separate SEI interface), one ordinary operation, one
 * INHERITED public operation from a plain superclass, one `final` method, one
 * `static` method and one `@WebMethod(exclude = true)` method — the four things
 * the catalog's `members: public_methods` rule and its RI citation (CP-13 Q3/Q4)
 * claim about the JAX-WS reference implementation. W63 asks CXF the same four
 * questions.
 */
@WebService(targetNamespace = "http://soap.example.com/")
public class BillingWebService extends AbstractBilling {

    public String charge(String orderId) {
        return "charged:" + orderId;
    }

    public final String reconcile(String orderId) {
        return "reconciled:" + orderId;
    }

    public static String staticHelper(String orderId) {
        return "static:" + orderId;
    }

    @WebMethod(exclude = true)
    public String internalOnly(String orderId) {
        return "internal:" + orderId;
    }
}
