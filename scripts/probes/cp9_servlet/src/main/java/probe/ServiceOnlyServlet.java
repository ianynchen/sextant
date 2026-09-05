package probe;

import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

/**
 * Rows 10-12: `service()` overridden, no `doXxx` anywhere. The verb dispatch
 * `HttpServlet.service` performs is exactly what this class replaces, so the
 * verb map cannot describe what it serves.
 */
@WebServlet(urlPatterns = "/service-only")
public class ServiceOnlyServlet extends HttpServlet {

    @Override
    protected void service(HttpServletRequest request, HttpServletResponse response) throws IOException {
        response.getWriter().write("service " + request.getMethod());
    }
}
