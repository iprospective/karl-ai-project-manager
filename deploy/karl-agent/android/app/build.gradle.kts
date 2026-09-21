import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Signature release : fichier HORS du repo (défaut ~/.config/karl-android/signing.properties,
// créé par build-apk.sh ; à archiver dans Vaultwarden avec le .jks). Absent → APK release non signé.
val signingFile = file(
    (project.findProperty("karl.signing") as String?)
        ?: "${System.getProperty("user.home")}/.config/karl-android/signing.properties"
)
val signing = Properties().apply { if (signingFile.exists()) signingFile.inputStream().use { load(it) } }

android {
    namespace = "fr.iprospective.karl"
    compileSdk = 36

    defaultConfig {
        applicationId = "fr.iprospective.karl"
        minSdk = 26
        // 34 et pas 36 : au-delà, Android impose l'affichage bord-à-bord (edge-to-edge)
        // et la barre d'action recouvrirait le haut du cockpit. Sideload : aucune
        // contrainte de store sur la cible.
        targetSdk = 34
        versionCode = 1
        versionName = "1.0.0"
    }

    signingConfigs {
        if (signing.getProperty("storeFile") != null) {
            create("release") {
                storeFile = file(signing.getProperty("storeFile"))
                storePassword = signing.getProperty("storePassword")
                keyAlias = signing.getProperty("keyAlias")
                keyPassword = signing.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfigs.findByName("release")?.let { signingConfig = it }
        }
    }

    buildFeatures { buildConfig = true }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

kotlin {
    compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) }
}

dependencies {
    implementation("androidx.appcompat:appcompat:1.7.1")
    implementation("androidx.activity:activity-ktx:1.10.1")
    implementation("androidx.webkit:webkit:1.14.0")
    implementation("androidx.biometric:biometric:1.1.0")
}
