import com.oracle.webservices.api.databinding.Databinding;
import com.oracle.webservices.api.databinding.DatabindingFactory;
import com.sun.xml.ws.api.model.JavaMethod;
import com.sun.xml.ws.api.model.SEIModel;
import com.sun.xml.ws.db.DatabindingImpl;

/**
 * Boots the JAX-WS REFERENCE IMPLEMENTATION's own runtime model
 * (`com.sun.xml.ws.model.RuntimeModeler`, reached through the RI's public
 * `DatabindingFactory` SPI rather than the internal class directly, the same
 * entry point `jakarta.xml.ws.Endpoint.create` uses) over `BillingWebService`
 * — the SAME two fixture classes `CxfLiveProbe` runs, so the two operation
 * lists are directly comparable. `createBuilder(null, endpointClass)` mirrors
 * `Endpoint.create(Object implementor)`'s own call: no separate SEI, the
 * implementor class doubles as its own contract, exactly `jakarta-jws.yml`'s
 * `declared_on: class` scenario.
 */
public final class RiLiveProbe {
    private RiLiveProbe() {
    }

    public static void main(String[] args) throws Exception {
        DatabindingFactory factory = DatabindingFactory.newInstance();
        Databinding databinding = factory.createBuilder(null, BillingWebService.class).build();
        SEIModel model = ((DatabindingImpl) databinding).getModel();
        System.out.println("W63_LIVE_OPERATIONS_BEGIN");
        for (JavaMethod jm : model.getJavaMethods()) {
            System.out.println(jm.getOperationName());
        }
        System.out.println("W63_LIVE_OPERATIONS_END");
    }
}
