plugins {
    java
    // Test-only: the committed Kotlin fixture below must be compiled by Gradle,
    // so `./gradlew test` stays self-contained on a fresh checkout. No Kotlin
    // reaches the shaded jar.
    kotlin("jvm") version "2.2.0"
    id("com.gradleup.shadow") version "9.6.1"
}

repositories { mavenCentral() }

dependencies {
    // 9.7 -> 9.10.1 (Critical 1, approved by the user 2026-09-06). ASM's
    // version is the CLASS-FILE CEILING this extractor can read at all, and
    // 9.7's is major 67 (JDK 23): a module built on JDK 24, 25 or 26 was
    // refused outright, and the refusal killed the whole scan — measured,
    // `byte-buddy-1.18.11.jar` from the local repository, exit 1 and zero fact
    // files. 9.10.1 reads majors 45 through 71 (JDK 27) and throws at 72 —
    // measured at every major from 45 to 72 by rewriting the two
    // `major_version` bytes JVMS 4.1 fixes at offset 6 of a real class file,
    // never taken from ASM's own constant set, which runs ahead of its reader.
    // That range is pinned by a test in this same source tree, so a later bump
    // that moves it is caught rather than silently skipping class files ASM
    // could have read. The API LEVEL the
    // visitors declare (`Opcodes.ASM9`) is a separate concept and deliberately
    // unchanged: it says which visitor callbacks this code is written against,
    // not which class files ASM will parse.
    implementation("org.ow2.asm:asm:9.10.1")
    implementation("org.ow2.asm:asm-tree:9.10.1")
    // The dataflow half of ASM: Analyzer/SourceInterpreter, which is how a call
    // site learns which instruction produced each value it consumes (D00 §5).
    // Pinned to the same 9.10.1 as the rest — a split ASM version is a
    // NoSuchMethodError at scan time, not a compile error here.
    implementation("org.ow2.asm:asm-analysis:9.10.1")
    // The extractor's first non-ASM runtime dependency (ARCHITECTURE §9): Kotlin's
    // nullability lives only in the opaque protobuf blob the compiler writes to
    // @Metadata, and this is the library that decodes it.
    implementation("org.jetbrains.kotlin:kotlin-metadata-jvm:2.2.0")
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
    // Only the bytecode target needs pinning: Kotlin 2.2.0's compiler runs fine
    // on this JDK, but without this it targets whatever bytecode version this
    // JDK defaults to, which then disagrees with JavaCompile's release(21) above
    // for the mixed test source set (compileTestJava and compileTestKotlin must
    // produce the same class file version).
    compilerOptions.jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_21)
}

tasks.test { useJUnitPlatform() }

// The third-party libraries that actually read a class file, with the versions
// Gradle RESOLVED — not the ones declared, which conflict resolution is free to
// move. Handed to the extractor through the jar manifest so nothing in Java
// maintains a copy: `scanner_version` was a hand-typed literal and it drifted to
// "9.18", a CAPABILITY number, while the pinned library was 9.10.1. A build that
// bumps a dependency now moves this without anyone remembering to.
//
// Derived from the DECLARED coordinates rather than a list written here, so
// adding a scanning library cannot silently escape provenance; the version comes
// from the resolved runtime classpath, so it is what will actually load.
val scannerLibraries: Provider<String> = provider {
    val declared = configurations.implementation.get().dependencies
        .mapNotNull { d -> d.group?.let { "$it:${d.name}" } }
        .toSet()
    configurations.runtimeClasspath.get().resolvedConfiguration.resolvedArtifacts
        .map { it.moduleVersion.id }
        .filter { "${it.group}:${it.name}" in declared }
        .distinctBy { "${it.group}:${it.name}" }
        // Sorted so the manifest — and every fact document downstream — is
        // byte-identical between builds (NFR-1).
        .sortedBy { "${it.group}:${it.name}" }
        .joinToString(",") { "${it.group}:${it.name}:${it.version}" }
}

tasks.shadowJar {
    archiveFileName.set("sextant-extractor.jar")
    manifest {
        attributes["Main-Class"] = "dev.sextant.extractor.Main"
        attributes["Sextant-Scanner-Libraries"] = scannerLibraries.get()
    }
    // Straight into the Python package, because that is where the extractor
    // ships (ARCHITECTURE §9) and one location beats two. Git-ignored: it is a
    // build output that happens to live in the source tree.
    destinationDirectory.set(layout.projectDirectory.dir("../src/sextant/extractor-jvm"))
}
