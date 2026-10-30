package com.acme.shop;

import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

/**
 * A plain servlet in the module that sets a context path AND a DispatcherServlet path. The
 * container registers it beside the DispatcherServlet rather than behind it, so it is served at
 * `/shop/legacy`: the context path applies and `spring.mvc.servlet.path=/api` does not (CP-57,
 * `scripts/probes/cp57-dispatcher-prefixes/RESULT.md`).
 */
@WebServlet("/legacy")
public class LegacyServlet extends HttpServlet {

    @Override
    protected void doGet(HttpServletRequest request, HttpServletResponse response) {
        response.setStatus(200);
    }
}
