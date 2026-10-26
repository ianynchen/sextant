package com.acme.quarkus.quotes;

import io.grpc.BindableService;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.quarkus.grpc.GrpcService;
import io.quarkus.grpc.MutinyBean;
import io.smallrye.mutiny.Uni;

// Quarkus's generated server bean for `Quotes`: Quarkus serves it as delegating to the
// `@GrpcService` class that implements its `delegate` field's type (CP-53). It carries no
// class annotation, and is never itself a handler.
public class QuotesBean extends MutinyQuotesGrpc.QuotesImplBase implements BindableService, MutinyBean {
    private final Quotes delegate;

    QuotesBean(@GrpcService Quotes delegate) {
        this.delegate = delegate;
    }

    @Override
    public Uni<String> getQuote(String request) {
        try {
            return delegate.getQuote(request);
        } catch (UnsupportedOperationException e) {
            throw new StatusRuntimeException(Status.UNIMPLEMENTED);
        }
    }
}
