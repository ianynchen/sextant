package com.acme.shop;

import org.springframework.boot.web.server.servlet.context.ServletComponentScan;
import org.springframework.context.annotation.Configuration;

/**
 * The application class, carrying the scan that registers `LegacyServlet` with the container
 * in a Boot app.
 */
@Configuration
@ServletComponentScan
public class ShopApplication {
}
