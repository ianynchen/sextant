package probe;

import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

/**
 * Rows 18 and 26: the LANGUAGE rule (GUIDELINES §8.1). A method named `doGet` whose
 * parameter types are not `(HttpServletRequest, HttpServletResponse)` is not
 * an override of anything — Java identifies a method by name AND parameter
 * types in order — so `HttpServlet`'s own `doGet` still applies and the
 * container serves a 405. A member selector keyed on the NAME alone would
 * publish `GET /decoy` here.
 */
@WebServlet(urlPatterns = "/decoy")
public class DecoyOverloadServlet extends HttpServlet {

    protected void doGet(String path, HttpServletResponse response) throws IOException {
        response.getWriter().write("never dispatched");
    }
}
