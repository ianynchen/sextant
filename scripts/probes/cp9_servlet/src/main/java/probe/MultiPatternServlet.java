package probe;

import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

/** Rows 1-2 and 20-21: an array-valued `urlPatterns`. Two patterns, one class. */
@WebServlet(urlPatterns = {"/multi-a", "/multi-b"})
public class MultiPatternServlet extends HttpServlet {

    @Override
    protected void doGet(HttpServletRequest request, HttpServletResponse response) throws IOException {
        response.getWriter().write("multi");
    }
}
