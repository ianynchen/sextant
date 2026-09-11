package probe;

import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

/**
 * Rows 19 and 29: extends `HttpServlet`, overrides `doGet`, and carries NO
 * `@WebServlet`. The class is on the classpath and compiles to a class file
 * exactly like every servlet above; nothing registers it.
 */
public class UnannotatedServlet extends HttpServlet {

    @Override
    protected void doGet(HttpServletRequest request, HttpServletResponse response) throws IOException {
        response.getWriter().write("unannotated");
    }
}
