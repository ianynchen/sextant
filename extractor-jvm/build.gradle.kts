plugins {
    java
    id("com.gradleup.shadow") version "9.6.1"
}

repositories { mavenCentral() }

dependencies {
    implementation("org.ow2.asm:asm:9.7")
    implementation("org.ow2.asm:asm-tree:9.7")
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.withType<JavaCompile> {
    options.release.set(21)
    // javac is the linter here: no new dependency, and a warning that reaches
    // main is a warning nobody will read.
    options.compilerArgs.addAll(listOf("-Xlint:all", "-Werror"))
}

tasks.test { useJUnitPlatform() }

tasks.shadowJar {
    archiveFileName.set("sextant-extractor.jar")
    manifest { attributes["Main-Class"] = "dev.sextant.extractor.Main" }
}
