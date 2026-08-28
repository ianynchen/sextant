plugins {
    java
    // Test-only: the committed Kotlin fixture below must be compiled by Gradle,
    // so `./gradlew test` stays self-contained on a fresh checkout. No Kotlin
    // reaches the shaded jar.
    kotlin("jvm") version "2.0.21"
    id("com.gradleup.shadow") version "9.6.1"
}

repositories { mavenCentral() }

dependencies {
    implementation("org.ow2.asm:asm:9.7")
    implementation("org.ow2.asm:asm-tree:9.7")
    // The extractor's first non-ASM runtime dependency (ARCHITECTURE §9): Kotlin's
    // nullability lives only in the opaque protobuf blob the compiler writes to
    // @Metadata, and this is the library that decodes it.
    implementation("org.jetbrains.kotlin:kotlin-metadata-jvm:2.0.21")
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
    // Test scope only: the committed fixture needs an annotation to compile
    // against, and this dependency must stay out of the shaded jar.
    testImplementation("org.jspecify:jspecify:1.0.0")
}

tasks.withType<JavaCompile> {
    options.release.set(21)
    // javac is the linter here: no new dependency, and a warning that reaches
    // main is a warning nobody will read.
    options.compilerArgs.addAll(listOf("-Xlint:all", "-Werror"))
}

kotlin {
    // Pins both the JDK the Kotlin daemon runs under and its bytecode target
    // to 21, matching JavaCompile's release above — needed because Kotlin
    // 2.0.21's compiler cannot run at all on a JDK newer than it knows about
    // (see settings.gradle.kts), and because compileTestJava and
    // compileTestKotlin must agree on the bytecode version for the mixed
    // test source set.
    jvmToolchain(21)
}

tasks.test { useJUnitPlatform() }

tasks.shadowJar {
    archiveFileName.set("sextant-extractor.jar")
    manifest { attributes["Main-Class"] = "dev.sextant.extractor.Main" }
    // Straight into the Python package, because that is where the extractor
    // ships (ARCHITECTURE §9) and one location beats two. Git-ignored: it is a
    // build output that happens to live in the source tree.
    destinationDirectory.set(layout.projectDirectory.dir("../src/sextant/extractor-jvm"))
}
