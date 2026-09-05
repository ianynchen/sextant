package probe;

import jakarta.servlet.GenericServlet;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.annotation.WebServlet;
import java.io.IOException;

/**
 * Rows 13-14: a `GenericServlet` subclass. `GenericServlet` is protocol-
 * agnostic — it declares no HTTP verb dispatch at all — so no verb map applies
 * to it even though it carries the same `@WebServlet` address annotation.
 */
@WebServlet(urlPatterns = "/generic")
public class GenericProbeServlet extends GenericServlet {

    @Override
    public void service(ServletRequest request, ServletResponse response) throws IOException {
        response.getWriter().write("generic");
    }
}
