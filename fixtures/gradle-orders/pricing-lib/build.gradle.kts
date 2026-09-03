plugins {
    `java-library`
    `maven-publish`
}

group = "com.acme"
version = "1.0.0"

// Matches fixtures/orders-service's own `maven.compiler.release` (21) — the
// JVM extractor's ASM version does not read bytecode newer than that.
tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
}

publishing {
    publications {
        create<MavenPublication>("maven") {
            from(components["java"])
        }
    }
}
