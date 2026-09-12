import org.apache.cxf.Bus;
import org.apache.cxf.bus.CXFBusFactory;
import org.apache.cxf.jaxws.support.JaxWsServiceFactoryBean;
import org.apache.cxf.service.model.OperationInfo;

/**
 * Boots a real `JaxWsServiceFactoryBean` over `BillingWebService` and prints
 * every operation CXF's own service model produced — one half of the
 * side-by-side cross-check with the RI (`RiLiveProbe`, same fixture classes),
 * the same role `cp13_inherited_members`'s Q5 compile-and-run played where
 * bytecode reading alone could not settle a question.
 */
public final class CxfLiveProbe {
    private CxfLiveProbe() {
    }

    public static void main(String[] args) throws Exception {
        Bus bus = new CXFBusFactory().createBus();
        JaxWsServiceFactoryBean serviceFactory = new JaxWsServiceFactoryBean();
        serviceFactory.setBus(bus);
        serviceFactory.setServiceClass(BillingWebService.class);
        org.apache.cxf.service.Service service = serviceFactory.create();
        System.out.println("W63_LIVE_OPERATIONS_BEGIN");
        for (OperationInfo op : service.getServiceInfos().get(0).getInterface().getOperations()) {
            String name = op.getName().getLocalPart();
            System.out.println(name);
        }
        System.out.println("W63_LIVE_OPERATIONS_END");
    }
}
