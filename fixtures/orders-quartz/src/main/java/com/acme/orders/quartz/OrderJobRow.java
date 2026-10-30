package com.acme.orders.quartz;

/** A row of a jobs table: what is scheduled is data, not code. */
public class OrderJobRow {
    private String name;
    private String group;
    private String cron;
    private boolean concurrent;

    public String getName() {
        return name;
    }

    public String getGroup() {
        return group;
    }

    public String getCron() {
        return cron;
    }

    public void setCron(String cron) {
        this.cron = cron;
    }

    public boolean isConcurrent() {
        return concurrent;
    }
}
