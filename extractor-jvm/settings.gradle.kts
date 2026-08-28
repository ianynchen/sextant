// This machine's JDK is newer than Kotlin 2.0.21's compiler can run under
// (it crashes parsing the version string) — the toolchain below asks Gradle
// to provision a JDK the Kotlin daemon actually supports, and this resolver
// is what lets Gradle download one instead of only searching what's installed.
plugins {
    id("org.gradle.toolchains.foojay-resolver-convention") version "1.0.0"
}

rootProject.name = "sextant-extractor"
