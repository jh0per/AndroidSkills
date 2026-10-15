---
name: gradle-build-setup
description: Set up or maintain the Gradle build of an Android or Kotlin Multiplatform project - version catalog, JDK toolchain, AGP 9 built-in Kotlin and its KMP opt-out, build-logic convention plugins for multi-module apps, build-time configuration values, Compose compiler reports, and dependency upgrade policy. Use when creating a project, adding a module, bumping AGP/Kotlin/Compose, or when build files are being copy-pasted between modules.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - Gradle
  - version catalog
  - AGP 9
  - convention plugins
  - JDK toolchain
  - BuildConfig
  - build speed
---

# Gradle build setup

## Version catalog

All versions in `gradle/libs.versions.toml`; build files reference `libs.*` aliases only.

```toml
[versions]
agp = "<stable>"
kotlin = "<stable>"
compose-multiplatform = "<stable>"
coroutines = "<stable>"

[libraries]
kotlinx-coroutines-core = { module = "org.jetbrains.kotlinx:kotlinx-coroutines-core", version.ref = "coroutines" }
firebase-bom = { module = "com.google.firebase:firebase-bom", version = "<stable>" }
firebase-auth = { module = "com.google.firebase:firebase-auth" }   # versioned by the BOM

[plugins]
android-application = { id = "com.android.application", version.ref = "agp" }
kotlin-multiplatform = { id = "org.jetbrains.kotlin.multiplatform", version.ref = "kotlin" }
```

- Comment *why* an entry is pinned away from what a transitive dependency asks for (e.g. a test
  library forced forward because an older one calls an API removed on new Android versions).
- Prefer stable releases. When a library ships on a decoupled track (Compose Multiplatform's
  Material3 pairs with its own version), use the plugin's accessor instead of hand-pinning a
  pre-release coordinate.
- Declare a dependency directly when your code uses it directly, even if it arrives transitively.

## Toolchain

```kotlin
// settings.gradle.kts
plugins { id("org.gradle.toolchains.foojay-resolver-convention") version "<stable>" }
```

Pin the JVM target explicitly on both Kotlin and Java (`JvmTarget.JVM_17` and
`compileOptions { sourceCompatibility = VERSION_17; targetCompatibility = VERSION_17 }`). Generated
Java sources (BuildConfig) otherwise compile with a different default target than Kotlin.

`gradle.properties` baseline:

```properties
android.useAndroidX=true
kotlin.code.style=official
org.gradle.jvmargs=-Xmx4096M -Dfile.encoding=UTF-8
kotlin.daemon.jvmargs=-Xmx4096M
```

## AGP 9

- Android-only modules use AGP's **built-in Kotlin**: no `org.jetbrains.kotlin.android` plugin.
  `compileSdk { version = release(36) { minorApiLevel = 1 } }` is the new DSL for minor SDKs.
- AGP 9's new DSL forbids applying `kotlin.multiplatform` and `com.android.application` in the same
  module. The supported fix is splitting into an app entry-point module plus a
  `com.android.kotlin.multiplatform.library` module. Until that is planned deliberately, the
  documented temporary opt-out is:

  ```properties
  android.newDsl=false
  android.builtInKotlin=false
  ```

  Record it as debt; do not fold the module split into a routine version bump. Plan it before the
  opt-out is removed.
- New R8 keep-rule layout: `src/main/keepRules/*.keep` is picked up automatically.
- `compileSdk` may be forced up by library AAR metadata; `targetSdk` is a behaviour opt-in and
  moves only in its own change, with the behaviour changes reviewed.

## Build-time configuration values

```kotlin
val localProperties = Properties().apply {
    rootProject.file("local.properties").takeIf { it.exists() }?.inputStream()?.use(::load)
}
fun config(key: String): String? =
    providers.gradleProperty(key).orNull
        ?: localProperties.getProperty(key)
        ?: System.getenv(key.replace('.', '_').uppercase())

val apiOrigin = config("app.apiOrigin") ?: "https://api.example.com"

android {
    buildFeatures { buildConfig = true }
    defaultConfig {
        buildConfigField("String", "API_ORIGIN", "\"$apiOrigin\"")
        manifestPlaceholders["adsAppId"] = config("ads.appId") ?: "ca-app-pub-0000000000000000~0000000000"
    }
}
```

- Escape values before putting them in `buildConfigField` (backslashes and quotes).
- A value that already lives in a committed config file (e.g. a project number inside
  `google-services.json`) can be read from it at build time instead of being a manual step that
  silently falls back to a "not configured" default.
- Secrets never go in `BuildConfig` of a release build unless they are public by nature (API keys
  that are restricted server-side). Signing secrets: see `android-release-signing`.
- Commit `*.properties.example` files listing every key with empty values.

## Multi-module: convention plugins, not copy-paste

When a second module appears, move shared configuration into an included build, not into
`subprojects {}` blocks or `buildSrc` helper functions:

```text
build-logic/
  settings.gradle.kts            # dependencyResolutionManagement { versionCatalogs { create("libs") { from(files("../gradle/libs.versions.toml")) } } }
  convention/build.gradle.kts    # `kotlin-dsl`; compileOnly(libs.android.gradlePlugin), compileOnly(libs.kotlin.gradlePlugin)
  convention/src/main/kotlin/
    AndroidApplicationConventionPlugin.kt
    AndroidLibraryConventionPlugin.kt
    ComposeConventionPlugin.kt
    QualityConventionPlugin.kt   # detekt + ktlint with shared config
```

```kotlin
// settings.gradle.kts
pluginManagement { includeBuild("build-logic") }

// build-logic/convention/build.gradle.kts
gradlePlugin {
    plugins {
        register("androidLibrary") { id = "app.android.library"; implementationClass = "AndroidLibraryConventionPlugin" }
        register("compose") { id = "app.compose"; implementationClass = "ComposeConventionPlugin" }
    }
}

// feature/orders/build.gradle.kts
plugins { id("app.android.library"); id("app.compose") }
android { namespace = "com.example.feature.orders" }
dependencies { implementation(projects.core.ui) }
```

Each convention plugin sets `compileSdk`, `minSdk`, Java/Kotlin targets, lint options and test
options once. Enable type-safe project accessors (`enableFeaturePreview("TYPESAFE_PROJECT_ACCESSORS")`).

Keep modules justified: one per feature screen plus `core:*` (ui, network, data) is common; a
module per backend service is only worth it with independent owners.

## Compose compiler reports (opt-in)

```kotlin
composeCompiler {
    if (providers.gradleProperty("composeCompilerReports").isPresent) {
        reportsDestination = layout.buildDirectory.dir("compose_compiler")
        metricsDestination = layout.buildDirectory.dir("compose_compiler")
    }
}
```

Run with `-PcomposeCompilerReports=true` when investigating recomposition and stability.

## Version name from CI

Deriving a version-name suffix from the branch (e.g. ticket id) is fine for internal distribution
builds. Store builds use an explicit `versionCode` that has been checked against the store (see
`android-release-signing`).

## Upgrades

- One toolchain bump per change; read the release notes of AGP, Kotlin and Compose for migration
  steps and deprecated flags.
- After a Compose bump, exercise rotation/resize and lists on a device; after any bump, run
  `verifyRelease` because R8 behaviour changes with AGP.
- Do not remove imports that the IDE flags as unused if the compiler needs them (delegate
  `getValue`/`setValue` imports are a common false positive).

## Custom Gradle tasks (translations, assets, fonts)

```kotlin
abstract class CheckTranslationsTask : DefaultTask() {
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE) abstract val resDir: DirectoryProperty
    @get:Input abstract val failOnError: Property<Boolean>
    @get:OutputFile abstract val report: RegularFileProperty            // makes the task cacheable / up-to-date aware

    @TaskAction fun check() {
        val errors = buildList {
            resDir.get().asFile.listFiles { f -> f.name.startsWith("values") }.orEmpty().forEach { dir ->
                val file = File(dir, "strings.xml").takeIf(File::exists) ?: return@forEach
                val text = file.readText()
                if (" % " in text) add("${dir.name}: broken format specifier")
                if ("%@" in text) add("${dir.name}: iOS format specifier")
                if (Regex("<item quantity=\"\\w+\">\\s*</item>").containsMatchIn(text)) add("${dir.name}: empty plural")
            }
        }
        report.get().asFile.writeText(errors.joinToString("\n"))
        errors.forEach(logger::error)
        if (errors.isNotEmpty() && failOnError.get()) throw GradleException("${errors.size} translation problems")
    }
}

tasks.register<CheckTranslationsTask>("checkTranslations") {
    resDir.set(layout.projectDirectory.dir("src/main/res"))
    failOnError.set(providers.gradleProperty("strict").map { true }.orElse(false))
    report.set(layout.buildDirectory.file("reports/translations.txt"))
}
```

- Declare inputs/outputs with `DirectoryProperty`/`RegularFileProperty`; never annotate a client
  object as `@Input`. Network calls only inside `@TaskAction`. Credentials from
  `providers.gradleProperty`/`environmentVariable`, never hard-coded in build logic.
- Tasks that download assets (fonts, translations) write to an `@OutputDirectory` and are run
  explicitly (`./gradlew updateTranslations`), not on every build.

## Build performance

```properties
org.gradle.caching=true
org.gradle.configuration-cache=true
org.gradle.parallel=true
android.nonTransitiveRClass=true
android.enableJetifier=false
kotlin.incremental=true
```

- KSP instead of kapt; if kapt remains, `kapt.include.compile.classpath=false` and
  `kapt { useBuildCache = true }`.
- `configureondemand` is deprecated; remove it.
- Core library desugaring when using `java.time` on minSdk < 26.
