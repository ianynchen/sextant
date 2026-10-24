// Two schedules set in configuration (spec 2026-10-23-configured-schedules §3e). Both stay
// `unresolved` in `scheduled_work` — the schedule that runs is the deployment's — and each
// gets one `resolved_schedules` row per environment, which the document states under its row:
//
//   * `sweep`'s key is set in application-prod.yml ONLY, so `prod` reads `0 */5 * * * *`
//     and `default` falls back to the annotation's own `:0 0 * * * *`;
//   * `purge`'s key is set nowhere and carries no default, so every environment reads
//     `missing_key`.
//
// The bodies are empty on purpose: what is pinned is the schedule, not the work.
package com.acme.orders.scheduling;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class OrderSweeper {

    @Scheduled(cron = "${orders.sweep.cron:0 0 * * * *}")
    public void sweep() {
    }

    @Scheduled(fixedRateString = "${orders.purge.rate}")
    public void purge() {
    }
}
