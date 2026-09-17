// Raiz de la build. La logica de layout vive en :nresponsive (modulo Kotlin/JVM
// puro, testeable sin emulador) y la UI Compose en :app.
plugins {
    id("com.android.application") version "8.5.2" apply false
    id("org.jetbrains.kotlin.android") version "1.9.24" apply false
    id("org.jetbrains.kotlin.jvm") version "1.9.24" apply false
    id("org.jetbrains.kotlin.plugin.serialization") version "1.9.24" apply false
}