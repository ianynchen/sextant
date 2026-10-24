package com.acme.quarkus.hello;

import io.grpc.MethodDescriptor;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;

// The marshaller the two generated stand-ins share, in place of protobuf's.
enum Utf8 implements MethodDescriptor.Marshaller<String> {
    INSTANCE;

    @Override
    public InputStream stream(String value) {
        return new ByteArrayInputStream(value.getBytes(StandardCharsets.UTF_8));
    }

    @Override
    public String parse(InputStream stream) {
        try {
            return new String(stream.readAllBytes(), StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }
}
