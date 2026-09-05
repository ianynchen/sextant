package probe;

import jakarta.servlet.ServletContext;
import java.nio.file.Path;
import org.apache.catalina.Context;
import org.apache.catalina.startup.Tomcat;

/**
 * CP-9's probe launcher: embedded Tomcat over a real webapp directory, so the
 * container's OWN annotation deployment scan is what discovers every
 * `@WebServlet` in `WEB-INF/classes`. Nothing here registers a servlet.
 *
 * <p>The identity line is the whole of §5.4's "record identity from the run's
 * own output": the RUNNING container is asked what it is (`getServerInfo`) and
 * which Servlet level it implements, and `run.sh` aborts when what it reports
 * disagrees with the version the build asked for.
 */
public final class ProbeApplication {

    public static void main(String[] args) throws Exception {
        int port = Integer.parseInt(args[0]);
        Path docBase = Path.of(args[1]).toAbsolutePath();
        Tomcat tomcat = new Tomcat();
        tomcat.setBaseDir(docBase.resolveSibling("tomcat-base").toString());
        tomcat.setPort(port);
        tomcat.getConnector();
        Context context = tomcat.addWebapp("", docBase.toString());
        tomcat.start();
        ServletContext servletContext = context.getServletContext();
        System.out.println("PROBE-IDENTITY container=" + servletContext.getServerInfo()
            + " servletSpec=" + servletContext.getMajorVersion()
            + "." + servletContext.getMinorVersion());
        System.out.flush();
        tomcat.getServer().await();
    }
}
