package probe;

import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

/**
 * Rows 35-37 (principles sweep `A-M2`): `service()` overridden AND `doGet`/`doPost`
 * declared, with the override DELEGATING through `super.service(req, resp)`.
 *
 * <p>This is the configuration CP-9's verdict 8 was generalised past. Rows 14-15 measured
 * `ServiceOnlyServlet` — `service()` overridden with NO `doXxx` anywhere — and the verdict
 * "a class overriding `service()` derives nothing" was then applied to every `service()`
 * override. The commonest real form is this one: a cross-cutting wrapper (timing, logging,
 * a header) that calls `super.service` and lets `HttpServlet`'s own dispatch run. That
 * class serves exactly the verbs its `doXxx` methods declare and no others, which is what
 * rows 35-37 ask.
 *
 * <p>PUT is row 37 and is the discriminator: if `super.service` really does dispatch, a
 * verb with no `doXxx` must be refused (405) exactly as it is on a plain servlet, and the
 * bypass rule would have been describing something real.
 */
@WebServlet(urlPatterns = "/delegating")
public class DelegatingServiceServlet extends HttpServlet {

    @Override
    protected void service(HttpServletRequest request, HttpServletResponse response)
            throws jakarta.servlet.ServletException, IOException {
        response.setHeader("X-Wrapped", "yes");
        super.service(request, response);
    }

    @Override
    protected void doGet(HttpServletRequest request, HttpServletResponse response) throws IOException {
        response.getWriter().write("delegating get");
    }

    @Override
    protected void doPost(HttpServletRequest request, HttpServletResponse response) throws IOException {
        response.getWriter().write("delegating post");
    }
}
