package com.acme.tp;

import io.temporal.activity.ActivityInterface;
import io.temporal.activity.ActivityMethod;

/**
 * Both halves of the activity naming rule (M2/M3), plus the member fence
 * (§2c) that {@link BillingActivitiesImpl#reloadRates()} exercises negatively.
 * Implemented in this module by {@link BillingActivitiesImpl}, which carries
 * {@code @ActivityImpl} — same flip as {@link OrderWorkflow}'s.
 */
@ActivityInterface(namePrefix = "billing_")
public interface BillingActivities {

    // Explicit name -> the empty-name test (`ActivityMethod.name().isEmpty()`)
    // is false, so the prefix-composition branch is never reached: the
    // prefix is NOT applied (M2, CP-30 Q2).
    // -> "Charge"
    @ActivityMethod(name = "Charge")
    void charge(String id);

    // No explicit name -> the empty-name test is true -> prefix +
    // `getActivityNameFromMethod`'s title-casing of the member name (M3,
    // CP-30 Q3: `substring(0,1).toUpperCase() + substring(1)`).
    // -> "billing_RefundCard"
    void refundCard(String id);
}
