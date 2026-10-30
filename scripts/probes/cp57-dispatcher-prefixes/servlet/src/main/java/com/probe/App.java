package com.probe;

import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import org.glassfish.jersey.server.ResourceConfig;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.servlet.ServletComponentScan;
import org.springframework.context.annotation.Bean;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.RouterFunctions;
import org.springframework.web.servlet.function.ServerResponse;

@SpringBootApplication
@ServletComponentScan
public class App {
    public static void main(String[] args) { SpringApplication.run(App.class, args); }

    @RestController
    public static class Mvc {
        @GetMapping("/mvc") public String mvc() { return "mvc"; }
    }

    @Bean
    RouterFunction<ServerResponse> routes() {
        return RouterFunctions.route().GET("/fn", r -> ServerResponse.ok().body("fn")).build();
    }

    @WebServlet("/legacy")
    public static class Legacy extends HttpServlet {
        @Override protected void doGet(HttpServletRequest q, HttpServletResponse s) throws java.io.IOException {
            s.getWriter().write("legacy");
        }
    }

    @Component
    @Path("/jersey")
    public static class JerseyRes {
        @GET public String get() { return "jersey"; }
    }

    @Component
    public static class JerseyConfig extends ResourceConfig {
        public JerseyConfig() { register(JerseyRes.class); }
    }
}
