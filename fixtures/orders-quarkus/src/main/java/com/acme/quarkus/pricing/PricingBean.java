package com.acme.quarkus.pricing;

import io.grpc.BindableService;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.quarkus.grpc.GrpcService;
import io.quarkus.grpc.MutinyBean;
import io.smallrye.mutiny.Uni;

// The server bean Quarkus's generator emits for every service of a compiled `.proto`,
// called or served. No module class implements `Pricing` with `@GrpcService`, so Quarkus
// does not serve it (CP-53), and it fences no client (spec 2026-10-25 §3c).
public class PricingBean extends MutinyPricingGrpc.PricingImplBase implements BindableService, MutinyBean {
    private final Pricing delegate;

    PricingBean(@GrpcService Pricing delegate) {
        this.delegate = delegate;
    }

    @Override
    public Uni<String> quote(String request) {
        try {
            return delegate.quote(request);
        } catch (UnsupportedOperationException e) {
            throw new StatusRuntimeException(Status.UNIMPLEMENTED);
        }
    }
}
