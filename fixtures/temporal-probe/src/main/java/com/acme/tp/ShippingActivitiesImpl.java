package com.acme.tp;

/**
 * Implements {@link ShippingActivities} in this module but carries NO
 * {@code @ActivityImpl} — the false-positive fence the controller ruling
 * added this arm to prove. Under the one-catalog-per-contract-kind shape
 * (`declared_on: interface` + `resolves.direction` keyed on
 * {@code owner_implemented_by_type_annotated: [ActivityImpl]}), this class's
 * absent starter annotation means the direction never flips to inbound — the
 * flip DECLINES — and because {@link ShippingActivities} IS implemented by a
 * class in this module, the outbound (SEI) fence still subtracts it, the
 * same way an interface implemented by a bean the framework serves nothing
 * through stays fenced on `spring-http-interface.yml`. Net: derives NOTHING
 * in either direction.
 */
public class ShippingActivitiesImpl implements ShippingActivities {

    @Override
    public void arrangePickup(String orderId) {
        // never runs
    }
}
