plugins {
    alias(libs.plugins.androidApplication)
}

android {
    namespace = "com.acme.app"
    compileSdk = libs.versions.android.compileSdk.get().toInt()

    defaultConfig {
        applicationId = "com.acme.app"
        minSdk = libs.versions.android.minSdk.get().toInt()
        targetSdk = libs.versions.android.compileSdk.get().toInt()
        versionCode = 1
        versionName = "1.0"
    }

    buildFeatures {
        buildConfig = true
    }

    flavorDimensions += "tier"
    productFlavors {
        create("free") {
            dimension = "tier"
            buildConfigField("String", "API_URL", "\"https://free.api.example/\"")
        }
        create("paid") {
            dimension = "tier"
            buildConfigField("String", "API_URL", "\"https://paid.api.example/\"")
        }
    }
}

kotlin {
    jvmToolchain(21)
}

dependencies {
    implementation(project(":shared"))
    implementation(libs.retrofit)
    implementation(libs.okhttp)
}
