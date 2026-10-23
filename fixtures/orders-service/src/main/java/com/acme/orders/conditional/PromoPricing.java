package com.acme.orders.conditional;

public class PromoPricing implements PricingPolicy {
    @Override
    public long price(String sku) {
        return 80;
    }
}
