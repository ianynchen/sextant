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
    // An inter-project dependency (2M Task 3 fix round 1, I3): pins that
    // GradleDetector gives this classpath entry its own honest treatment —
    // internal wiring, not an unresolved library — rather than the generic
    // path-only reason a real local file()/flatDir dependency gets.
    implementation(project(":pricing-lib"))
}
