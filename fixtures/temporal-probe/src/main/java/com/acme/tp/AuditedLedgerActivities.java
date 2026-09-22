package com.acme.tp;

/**
 * The SUB half of the {@code declared_type_methods} discriminator. It carries
 * NO {@code @ActivityInterface} of its own — the annotation reaches it only
 * through the inheritance walk from {@link LedgerActivities} — and it declares
 * a member of its own.
 *
 * <p>{@code declared_type_methods} admits a member only where the member's own
 * DECLARING type carries the gate as a real annotation row, never the synthetic
 * one the walk wrote. {@code audit} is declared here, on a type whose gate is
 * synthetic, so it derives NOTHING.
 *
 * <p>MEASURED against the shipped catalog, both ways: swapping
 * {@code members:} to {@code public_methods} derives
 * {@code outbound activity "ledger_Audit"} on {@code AuditedLedgerActivities#audit}
 * — the sub-declared member published under the BASE's {@code namePrefix}, an
 * activity name no worker polls for, at {@code resolved}/{@code compiler}.
 * {@code declared_type_methods} derives nothing. That row is what this arm
 * holds absent, and it is what makes the word load-bearing: before this arm
 * existed the swap left the whole suite green, because
 * {@code declared_on: interface} already gates the IMPLEMENTOR out one step
 * earlier and no fixture reached the interface-over-interface case.
 */
public interface AuditedLedgerActivities extends LedgerActivities {

    void audit(String entryId);
}
