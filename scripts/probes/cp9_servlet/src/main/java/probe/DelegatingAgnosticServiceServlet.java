package probe;

import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

/**
 * Rows 38-40 (principles sweep `A-M2`): the SECOND bypass signature, delegating.
 *
 * <p>`bypassed_by` lists two entries because `HttpServlet` has two `service` methods —
 * the protected `service(HttpServletRequest, HttpServletResponse)` that dispatches on the
 * verb, and the public `service(ServletRequest, ServletResponse)` it inherits from
 * `GenericServlet` and implements by casting and calling the first. Rows 35-37 measure a
 * delegating override of the protected one; these rows measure the public one, because a
 * verdict about "a `service()` override" that was read against one signature must not be
 * applied to the other without measuring it (§5.4, and `A-M2` is that mistake exactly).
 */
@WebServlet(urlPatterns = "/delegating-agnostic")
public class DelegatingAgnosticServiceServlet extends HttpServlet {

    @Override
    public void service(ServletRequest request, ServletResponse response)
            throws ServletException, IOException {
        response.setCharacterEncoding("UTF-8");
        super.service(request, response);
    }

    @Override
    protected void doGet(HttpServletRequest request, HttpServletResponse response) throws IOException {
        response.getWriter().write("agnostic get");
    }

    @Override
    protected void doPost(HttpServletRequest request, HttpServletResponse response) throws IOException {
        response.getWriter().write("agnostic post");
    }
}
