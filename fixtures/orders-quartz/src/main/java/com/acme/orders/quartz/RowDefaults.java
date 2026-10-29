package com.acme.orders.quartz;

import java.util.List;

/**
 * DolphinScheduler's `CronUtils` shape: a default row this class builds for its own use. Its
 * cron is set on THIS object only, and never reaches a row read from the jobs table.
 */
public final class RowDefaults {

    private RowDefaults() {}

    public static List<OrderJobRow> orDefault(List<OrderJobRow> rows) {
        if (!rows.isEmpty()) {
            return rows;
        }
        OrderJobRow fallback = new OrderJobRow();
        fallback.setCron("0 0 0 * * ?");
        return List.of(fallback);
    }
}
