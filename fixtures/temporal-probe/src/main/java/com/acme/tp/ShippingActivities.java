package com.acme.tp;

import io.temporal.activity.ActivityInterface;

/**
 * Added per controller ruling (task-6 brief), a variance arm the plan's §4
 * sketch does not list: a second activity contract, implemented in this
 * module, whose implementor carries NO starter annotation at all. It must
 * derive nothing in either direction — see {@link ShippingActivitiesImpl}.
 */
@ActivityInterface
public interface ShippingActivities {

    void arrangePickup(String orderId);
}
