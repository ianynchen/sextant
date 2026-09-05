package probe;

import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

/**
 * Rows 41-43 (round-1 review, MAJOR 5): `service()` overridden AND `doGet`/`doPost`
 * declared, with the override NOT delegating — no `super.service(req, resp)` anywhere.
 *
 * <p>This is the configuration rows 35-40 were generalised past in the other direction.
 * Those measured the DELEGATING wrapper and concluded that a `service()` override
 * declaring `doXxx` serves exactly those verbs; the fix pass then applied that verdict
 * to every `service()` override declaring `doXxx`, which is §5.4's failure with the
 * arrow reversed.
 *
 * <p>Row 43 is the discriminator, and it is the mirror of row 37: if `HttpServlet`'s
 * dispatch never runs, a verb this class declares no `doXxx` for must be SERVED (200)
 * rather than refused (405) — because the override answers it itself. A 405 there would
 * mean the dispatch ran after all and the two shapes are one.
 *
 * <p>The `doGet`/`doPost` methods are deliberately unreachable: that is the point. They
 * are what a scanner sees, and what a fact stream with no call sites cannot tell apart
 * from the reachable ones in {@link DelegatingServiceServlet}.
 */
@WebServlet(urlPatterns = "/non-delegating")
public class NonDelegatingServiceServlet extends HttpServlet {

    @Override
    protected void service(HttpServletRequest request, HttpServletResponse response)
            throws IOException {
        response.getWriter().write("non-delegating " + request.getMethod());
    }

    @Override
    protected void doGet(HttpServletRequest request, HttpServletResponse response) throws IOException {
        response.getWriter().write("non-delegating get");
    }

    @Override
    protected void doPost(HttpServletRequest request, HttpServletResponse response) throws IOException {
        response.getWriter().write("non-delegating post");
    }
}
