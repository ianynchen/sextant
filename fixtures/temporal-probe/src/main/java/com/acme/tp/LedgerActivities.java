package com.acme.tp;

import io.temporal.activity.ActivityInterface;

/**
 * The BASE half of the {@code declared_type_methods} discriminator (§2c, D02
 * §"the second member word"). This interface carries {@code @ActivityInterface}
 * DIRECTLY, so its own member survives the fence and derives a row; it is
 * extended by {@link AuditedLedgerActivities}, which does not.
 *
 * <p>Added by the branch review: without a sub-interface the fence changed no
 * output at all — swapping the catalog to {@code public_methods} left the whole
 * suite green, because {@code declared_on: interface} already gates the
 * IMPLEMENTOR out before any member rule runs. The interface-over-interface
 * shape is the one place the two words disagree.
 *
 * <p>MEASURED: this interface derives NO row of its own either. No class
 * implements it, but {@link AuditedLedgerActivities} EXTENDS it, and the
 * outbound (SEI) fence subtracts a contract any type in this module implements
 * — an extending interface counts. The flip to inbound then declines, since
 * nothing carries {@code @ActivityImpl}. Net zero, the same read
 * {@link ShippingActivities} gets, for a different reason. The arm's whole
 * value is the row {@link AuditedLedgerActivities} does not publish.
 */
@ActivityInterface(namePrefix = "ledger_")
public interface LedgerActivities {

    // Declared HERE, on the type that carries the gate directly -> survives the
    // member fence. It is the whole contract that is subtracted, one step
    // later, by the SEI fence above. Were nothing to extend this interface the
    // name would be `prefixed_capitalized_construct_name`'s composition,
    // "ledger_Post" (measured by deleting the `extends` and re-analysing).
    void post(String entryId);
}
