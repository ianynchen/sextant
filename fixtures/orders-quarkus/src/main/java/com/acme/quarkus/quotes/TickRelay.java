package com.acme.quarkus.quotes;

import io.smallrye.mutiny.Multi;
import java.time.Duration;
import org.eclipse.microprofile.reactive.messaging.Incoming;
import org.eclipse.microprofile.reactive.messaging.Outgoing;

// An IN-MEMORY pair (spec §3e): `ticks` is produced and consumed in this module, so it
// is not an orphan, Quarkus attaches no connector to it (CP-50 rows 1, 11), and it
// crosses no wire. It gives no row.
public class TickRelay {
    @Outgoing("ticks")
    public Multi<Long> ticks() {
        return Multi.createFrom().ticks().every(Duration.ofSeconds(1));
    }

    @Incoming("ticks")
    public void onTick(long tick) {
        System.out.println(tick);
    }
}
