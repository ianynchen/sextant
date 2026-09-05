package probe;

import jakarta.servlet.ServletContext;
import java.nio.file.Path;
import org.apache.catalina.Context;
import org.apache.catalina.connector.Connector;
import org.apache.catalina.startup.Tomcat;

/**
 * CP-9's probe launcher: embedded Tomcat over a real webapp directory, so the
 * container's OWN annotation deployment scan is what discovers every
 * `@WebServlet` in `WEB-INF/classes`. Nothing here registers a servlet.
 *
 * <p>The identity line is the whole of §5.4's "record identity from the run's
 * own output": the RUNNING container is asked what it is (`getServerInfo`),
 * which Servlet level it implements, and which servlet API PACKAGE it actually
 * loaded — the last because the `javax`/`jakarta` spelling is a configuration
 * this probe claims a column for, so it has to be observed rather than
 * inferred from the coordinate the build asked for. `run.sh` aborts when any
 * of the three disagrees with what the build asked for.
 *
 * <p>Two connectors, and the second one is evidence rather than convenience.
 * TRACE is refused by a Tomcat connector before dispatch unless `allowTrace`
 * is set, which is DEPLOYMENT configuration and not a property of the servlet
 * the module declares; the second connector sets it so the specification's own
 * `service()` -> `doTrace` dispatch can be measured instead of the connector
 * default masking it.
 *
 * <p>Two webapps, for the same reason in the other direction. The second is
 * the same `WEB-INF/classes` under a deployment descriptor declaring
 * `metadata-complete="true"`, which the specification says switches the
 * annotation scan off wholesale — the shape in which every `@WebServlet` in a
 * module is inert. That descriptor (written by `run.sh`, not here) also
 * registers ONE servlet by hand, because `metadata-complete` suppresses the
 * annotation scan and not the descriptor's own declarations: the 200 it serves
 * is what tells row 33's 404 apart from a context that never started.
 */
public final class ProbeApplication {

    public static void main(String[] args) throws Exception {
        int port = Integer.parseInt(args[0]);
        Path docBase = Path.of(args[1]).toAbsolutePath();
        Path metadataCompleteDocBase = Path.of(args[2]).toAbsolutePath();
        Tomcat tomcat = new Tomcat();
        tomcat.setBaseDir(docBase.resolveSibling("tomcat-base").toString());
        tomcat.setPort(port);
        tomcat.getConnector();
        Connector tracing = new Connector();
        tracing.setPort(port + 1);
        tracing.setAllowTrace(true);
        tomcat.getService().addConnector(tracing);
        Context context = tomcat.addWebapp("", docBase.toString());
        tomcat.addWebapp("/metadata-complete", metadataCompleteDocBase.toString());
        tomcat.start();
        ServletContext servletContext = context.getServletContext();
        System.out.println("PROBE-IDENTITY container=" + servletContext.getServerInfo()
            + " servletSpec=" + servletContext.getMajorVersion()
            + "." + servletContext.getMinorVersion()
            + " servletApi=" + ServletContext.class.getPackage().getName());
        System.out.flush();
        tomcat.getServer().await();
    }
}
