package com.example.siprobe;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportResource;
import org.springframework.integration.config.EnableIntegration;

/** The application class. `@ImportResource` pulls in the XML-configured flow,
 *  which is deliberately present so the probe can say what an XML flow
 *  contributes to the fact stream. */
@Configuration
@EnableIntegration
@EnableConfigurationProperties(ProbeProperties.class)
@ImportResource("classpath:integration-context.xml")
public class ProbeApplication {
}
