package com.acme.orders.conditional;

public class StandardPricing implements PricingPolicy {
    @Override
    public long price(String sku) {
        return 100;
    }
}
