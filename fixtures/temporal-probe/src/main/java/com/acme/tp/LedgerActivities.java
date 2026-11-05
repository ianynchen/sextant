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
 * <p>MEASURED: this interface derives its own row, "ledger_Post". No class
 * implements it; {@link AuditedLedgerActivities} EXTENDS it, and since the
 * Android outbound fix round 2 (2026-11-05) the outbound (SEI) fence counts
 * only a CLASS: an extending interface implements nothing. Before, it counted,
 * and this interface derived nothing. The arm's other value is the row
 * {@link AuditedLedgerActivities} does not publish, for its own member.
 * (Comment only: the line count is kept, so the compiled lines are unchanged.)
 */
@ActivityInterface(namePrefix = "ledger_")
public interface LedgerActivities {

    // Declared HERE, on the type that carries the gate directly -> survives the
    // member fence, and no class implements the contract, so the SEI fence
    // keeps it too. The name is `prefixed_capitalized_construct_name`'s
    // composition, "ledger_Post", the same name it had when measured by
    // deleting the `extends` and re-analysing.
    void post(String entryId);
}
