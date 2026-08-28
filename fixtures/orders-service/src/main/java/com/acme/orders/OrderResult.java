package com.acme.orders;

public class OrderResult {
    private String orderId;
    private String status;

    public String getOrderId() { return orderId; }
    public String getStatus() { return status; }

    // Nested, so the scanner does not read it. It is the fixture's one
    // compiled source the facts do not account for, and the run must say so
    // rather than let it disappear (M03, FR-17).
    public static class Detail {
        private String note;

        public String getNote() { return note; }
    }
}
