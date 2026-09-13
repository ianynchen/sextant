package dev.sextant.extractor;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import org.junit.jupiter.api.Test;

class KotlinCaptureTest {

    @Test
    void a_kotlin_lambda_capturing_this_has_one_leading_parameter() throws Exception {
        List<String> lines = KotlinMetadataTest.scan("KotlinCaptureSample");
        String site = lines.stream()
            .filter(line -> line.contains("\"kind\":\"call_site\"") && line.contains("\"name\":\"forEach\""))
            .findFirst()
            .orElseThrow(() -> new AssertionError("no forEach call site in " + lines));
        assertTrue(site.contains("\"captures\":1,\"kind\":\"lambda\""), site);
    }
}
