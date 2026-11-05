plugins {
    alias(libs.plugins.kotlinJvm)
}

dependencies {
    implementation(project(":shared"))
    implementation(libs.ktor.client.cio)
}

kotlin {
    jvmToolchain(21)
}
