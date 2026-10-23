// Two bean shapes beyond a conditional component (spec 2026-10-22-conditional-beans):
//  * `auditClient` — a `@Bean` method under `@Profile("prod")`: the bean, and so every row its class
//    derives, exists in `prod` only.
//  * `defaultPricing` / `promoPricing` — a `@ConditionalOnMissingBean` default beside a `@Profile`
//    override. Whether the default exists depends on beans from OUTSIDE this module too, which
//    Sextant cannot see, so its presence is `partial`: decided from this module's beans only.
package com.acme.orders.conditional;

import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.web.client.RestTemplate;

@Configuration
public class ConditionalClientsConfig {
    @Bean
    @Profile("prod")
    public AuditClient auditClient() {
        return new HttpAuditClient(new RestTemplate());
    }

    @Bean
    @ConditionalOnMissingBean
    public PricingPolicy defaultPricing() {
        return new StandardPricing();
    }

    @Bean
    @Profile("prod")
    public PricingPolicy promoPricing() {
        return new PromoPricing();
    }
}
