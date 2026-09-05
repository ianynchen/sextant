package probe;

import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

/**
 * Rows 16-18: the three verbs `HttpServlet` also dispatches — overridden
 * EXPLICITLY here, so what the container serves for them is a question about
 * a handler the module declares, not about implicit dispatch.
 */
@WebServlet(urlPatterns = "/explicit")
public class ExplicitVerbsServlet extends HttpServlet {

    @Override
    protected void doHead(HttpServletRequest request, HttpServletResponse response) {
        response.setHeader("X-Probe", "head");
    }

    @Override
    protected void doOptions(HttpServletRequest request, HttpServletResponse response) throws IOException {
        response.getWriter().write("options");
    }

    @Override
    protected void doTrace(HttpServletRequest request, HttpServletResponse response) throws IOException {
        response.getWriter().write("trace");
    }
}
