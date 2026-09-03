package com.acme.billing;

/** One class, no endpoints — this sibling exists to pin reactor-child
 * inheritance and the `undetermined` kind, never to exercise a scanner
 * capability of its own. */
public class BillingUtil {
    public static int total(int a, int b) {
        return a + b;
    }
}
