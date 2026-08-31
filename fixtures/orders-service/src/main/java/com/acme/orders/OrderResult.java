package com.acme.orders;

public class OrderResult {
    private String orderId;
    private String status;

    public String getOrderId() { return orderId; }
    public String getStatus() { return status; }

    // Nested, so it compiles to a class file of its own and gets a document of
    // its own (D00 §2): its own `document_id`, from the class-relative path,
    // and this file as its `relative_path`.
    public static class Detail {
        private String note;

        public String getNote() { return note; }
    }
}
