package com.acme.sv;

import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

// HANDLER-BODY READS on the Servlet API (`request_reads`, spec 2026-09-19 §5d; CP-25 rows
// 16–17). `req.getParameter("q")` → `param` (the API reads the query string and a form body
// through one method), `req.getHeader("X-Api")` → `header`; both `requirement` NULL — the
// methods are abstract on the API and the container returns null for an absent name, so the
// handler reads and nothing refuses (A3). `resp.setHeader(...)` is a SET on the RESPONSE: a
// different owner, no entry, no row. The handler is `doGet`, the row `GET /sv/orders`.
@WebServlet("/sv/orders")
public class OrderServlet extends HttpServlet {

    @Override
    protected void doGet(HttpServletRequest req, HttpServletResponse resp) throws IOException {
        String q = req.getParameter("q");
        String api = req.getHeader("X-Api");
        resp.setHeader("X-Api", api == null ? "1" : api);
        resp.getWriter().write(q == null ? "" : q);
    }
}
