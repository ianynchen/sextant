package com.acme.httpsvc;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.service.registry.ImportHttpServices;

/** Spring 7's registration: the interfaces named here become beans, proxied over a
 *  client. Before 7.0 each interface was wired by hand through `HttpServiceProxyFactory`. */
@Configuration
@ImportHttpServices(group = "inventory", types = InventoryClient.class)
public class HttpServicesConfig {}
