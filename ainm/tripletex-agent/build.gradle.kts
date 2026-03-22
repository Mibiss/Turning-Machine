plugins {
    alias(libs.plugins.kotlin.jvm)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.shadow)
    application
}

group = "no.ainm"
version = "1.0.0"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.okhttp)
}

application {
    mainClass.set("no.ainm.tripletex.LocalServerKt")
}

tasks.named<JavaExec>("run") {
    standardOutput = System.out
    errorOutput = System.err
}

tasks.shadowJar {
    archiveBaseName.set("tripletex-agent")
    archiveClassifier.set("")
    archiveVersion.set("")
    mergeServiceFiles()
}
