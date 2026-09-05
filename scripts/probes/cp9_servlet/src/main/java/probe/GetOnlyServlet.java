package probe;

import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

/**
 * Rows 6-9: `doGet` and nothing else. What the container serves on HEAD,
 * OPTIONS and TRACE for this class is the ruling CP-9 exists to settle.
 */
@WebServlet(urlPatterns = "/getonly")
public class GetOnlyServlet extends HttpServlet {

    @Override
    protected void doGet(HttpServletRequest request, HttpServletResponse response) throws IOException {
        response.getWriter().write("getonly");
    }
}
