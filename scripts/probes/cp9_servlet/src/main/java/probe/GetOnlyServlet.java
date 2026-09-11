package probe;

import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

/**
 * Rows 7-10, 24-25, 27, 32-34: `doGet` and nothing else. What the container
 * serves on HEAD, OPTIONS and TRACE for this class is the ruling CP-9 exists
 * to settle — including TRACE over the connector that permits the method
 * (row 32), where `HttpServlet`'s own `doTrace` answers with no override
 * anywhere. It is also the class row 33 asks for under a
 * `metadata-complete="true"` descriptor, and the one that descriptor registers
 * by hand for row 34 — the control that says whether that webapp is serving at
 * all, without which row 33's 404 has two possible causes.
 */
@WebServlet(urlPatterns = "/getonly")
public class GetOnlyServlet extends HttpServlet {

    @Override
    protected void doGet(HttpServletRequest request, HttpServletResponse response) throws IOException {
        response.getWriter().write("getonly");
    }
}
