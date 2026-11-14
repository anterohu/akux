import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

// Versio luetaan Python-paketista, jotta työpöytä- ja Android-versio pysyvät samoina
val akuxVersion: String = Regex("VERSIO\\s*=\\s*\"([^\"]+)\"")
    .find(rootDir.resolve("../akux/__init__.py").readText())!!.groupValues[1]
val versionParts = akuxVersion.split(".").map { it.toIntOrNull() ?: 0 } + listOf(0, 0, 0)
val akuxVersionCode = versionParts[0] * 10000 + versionParts[1] * 100 + versionParts[2]

val signing = Properties().apply {
    val f = rootDir.resolve("signing.properties")
    if (f.exists()) f.inputStream().use { load(it) }
}
// Google Playn latausavain. Ei koskaan versionhallinnassa: CI kirjoittaa tiedoston GitHub-salaisuuksista.
// Ilman sitä julkaisuversio allekirjoitetaan testiavaimella (akux.jks), jota ei saa käyttää Playssa.
val playSigning = Properties().apply {
    val f = rootDir.resolve("signing-play.properties")
    if (f.exists()) f.inputStream().use { load(it) }
}

android {
    namespace = "fi.akux.app"
    // Google Play vaatii 31.8.2026 alkaen uusilta sovelluksilta ja päivityksiltä kohdetason Android 16 (API 36).
    compileSdk = 36

    defaultConfig {
        // Google Playn sovellustunnus. Koodin sisäinen nimiavaruus (namespace) on edelleen fi.akux.app, se ei näy käyttäjälle.
        applicationId = "fi.akveri.app"
        minSdk = 29
        targetSdk = 36
        versionCode = akuxVersionCode
        versionName = akuxVersion
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        ndk {
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }

    signingConfigs {
        create("akux") {
            storeFile = rootDir.resolve(signing.getProperty("storeFile", "akux.jks"))
            storePassword = signing.getProperty("storePassword")
            keyAlias = signing.getProperty("keyAlias")
            keyPassword = signing.getProperty("keyPassword")
        }
        if (!playSigning.isEmpty) create("play") {
            storeFile = rootDir.resolve(playSigning.getProperty("storeFile"))
            storePassword = playSigning.getProperty("storePassword")
            keyAlias = playSigning.getProperty("keyAlias")
            keyPassword = playSigning.getProperty("keyPassword")
        }
    }

    buildTypes {
        getByName("release") {
            isMinifyEnabled = false
            signingConfig = signingConfigs.findByName("play") ?: signingConfigs.getByName("akux")
        }
        getByName("debug") {
            signingConfig = signingConfigs.getByName("akux")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    packaging {
        resources.excludes += listOf("META-INF/*.kotlin_module")
    }
}

// Akuxin Python-koodi kopioidaan repositorion juuresta, jotta kaikilla alustoilla on sama koodi
val copyAkux by tasks.registering(Copy::class) {
    from(rootDir.resolve("../akux")) {
        exclude("**/__pycache__/**")
    }
    into(layout.buildDirectory.dir("pysrc/akux"))
}
tasks.named("preBuild") { dependsOn(copyAkux) }
tasks.matching { it.name.contains("Python") && it.name != "copyAkux" }.configureEach { dependsOn(copyAkux) }

chaquopy {
    defaultConfig {
        version = "3.11"
        pip {
            install("numpy")
            install("pillow")
            install("matplotlib")
            install("reportlab")
            install("certifi")
        }
        extractPackages("akux")
    }
    sourceSets {
        getByName("main") {
            srcDir("build/pysrc")
        }
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.activity:activity-ktx:1.9.3")
    // Play Billing tuo mukanaan vanhan Fragment-kirjaston; registerForActivityResult (tiedoston valinta) vaatii vähintään 1.3.0.
    implementation("androidx.fragment:fragment-ktx:1.8.5")
    implementation("com.github.mik3y:usb-serial-for-android:3.8.0")
    // Krediittien osto Google Playssa. Palvelin (akveri.fi) tarkistaa jokaisen oston Googlelta ennen kuin krediitit lisätään.
    implementation("com.android.billingclient:billing-ktx:8.0.0")

    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test:rules:1.6.1")
}
