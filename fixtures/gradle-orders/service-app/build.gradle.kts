plugins {
    java
}

group = "com.acme"
version = "1.0.0"

// Matches fixtures/orders-service's own `maven.compiler.release` (21) — the
// JVM extractor's ASM version does not read bytecode newer than that.
tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework:spring-web:6.1.6")
    implementation("org.springframework:spring-context:6.1.6")
}
