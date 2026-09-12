package com.acme.httpsvc;

import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;

@HttpExchange("/inventory")
public interface InventoryClient {
    @GetExchange("/levels/{sku}")
    String level(String sku);
}
