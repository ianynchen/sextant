package probe;

import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

/**
 * Rows 7-10, 24-25, 27, 32-33: `doGet` and nothing else. What the container
 * serves on HEAD, OPTIONS and TRACE for this class is the ruling CP-9 exists
 * to settle — including TRACE over the connector that permits the method
 * (row 32), where `HttpServlet`'s own `doTrace` answers with no override
 * anywhere. It is also the class row 33 asks for under a
 * `metadata-complete="true"` descriptor.
 */
@WebServlet(urlPatterns = "/getonly")
public class GetOnlyServlet extends HttpServlet {

    @Override
    protected void doGet(HttpServletRequest request, HttpServletResponse response) throws IOException {
        response.getWriter().write("getonly");
    }
}
