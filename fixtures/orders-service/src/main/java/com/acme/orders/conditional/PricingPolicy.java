package com.acme.orders.conditional;

public interface PricingPolicy {
    long price(String sku);
}
