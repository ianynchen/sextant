package com.acme.tp;

import io.temporal.spring.boot.ActivityImpl;

/**
 * {@code @ActivityImpl(taskQueues = {"billing", "billing-retry"})} is what
 * flips {@link BillingActivities}'s row to INBOUND and what
 * {@code metadata_from} turns into two `task_queue` metadata rows, one per
 * array element (§2d).
 */
@ActivityImpl(taskQueues = {"billing", "billing-retry"})
public class BillingActivitiesImpl implements BillingActivities {

    @Override
    public void charge(String id) {
        // never runs
    }

    @Override
    public void refundCard(String id) {
        // never runs
    }

    // Declared HERE, not on `BillingActivities` — the `declared_type_methods`
    // member fence (§2c) admits only members whose declaring type carries the
    // catalog's type annotation DIRECTLY, never by inheritance from an
    // implemented interface reaching down onto the class. This is the
    // negative half of that fence: `public_methods` would mint
    // "billing_ReloadRates", an endpoint nothing polls; `declared_type_methods`
    // must not. -> derives NOTHING.
    public void reloadRates() {
        // never runs
    }
}
