---
name: gradle-quality-gate
description: Define and run one named Gradle verification gate for an Android or KMP project (unit tests, ktlint, both detekt variants, Android Lint, debug assemble, instrumented-source compile, merged-manifest checks) and run the exact same task in CI, including emulator tests on Gradle Managed Devices. Use when setting up checks, before pushing, when CI and local results disagree, or when adding a lint/detekt rule.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - verify task
  - detekt
  - ktlint
  - Android Lint
  - Gradle Managed Devices
  - quality gate
  - CI parity
---

# One gate, the same everywhere

"Did you run the checks?" must have one answer: `./gradlew verify`. CI runs that task and nothing
else. A hand-copied task list in CI drifts, and it always drifts toward passing.

## Root `build.gradle.kts`

```kotlin
plugins {
    alias(libs.plugins.ktlint)                     // applied at root so build scripts are linted too
    alias(libs.plugins.kotlin.multiplatform) apply false
    alias(libs.plugins.android.application) apply false
    // …
}

tasks.register("verify") {
    group = "verification"
    description = "Full pre-push gate: unit tests, ktlint, detekt, lint and a debug build."
    dependsOn(
        ":app:testDebugUnitTest",
        ":app:ktlintCheck",
        ":ktlintCheck",                            // root build scripts
        ":app:detekt",                             // fast, every source set, no type resolution
        ":app:detektAndroidDebug",                 // type resolution: the rules that find real bugs
        ":app:lintDebug",                          // manifest, resource and API-level problems
        ":app:assembleDebug",                      // catches resource/manifest/packaging failures compile misses
        ":app:checkDebugNoAdvertisingId",          // example merged-manifest policy check (below)
        ":app:assembleDebugAndroidTest",           // the only thing that compiles instrumented tests without a device
    )
}

tasks.register("verifyOnDevice") {
    group = "verification"
    dependsOn("verify", ":app:connectedDebugAndroidTest")
}

tasks.register("verifyRelease") {
    group = "verification"
    dependsOn("verify", ":app:assembleRelease", ":app:checkReleaseNoAdvertisingId")
}
```

Deliberately not a git hook: a hook that adds a minute to every push gets bypassed with
`--no-verify` and then protects nothing.

## detekt

```kotlin
detekt {
    buildUponDefaultConfig = true
    allRules = true
    config.setFrom(rootProject.files("config/detekt/detekt.yml"))
    source.setFrom(files("src/commonMain/kotlin", "src/commonTest/kotlin", "src/androidMain/kotlin", "src/iosMain/kotlin"))
}

// A glob exclude does not work (detekt hands the task bare file names); the predicate sees the path.
tasks.withType<io.gitlab.arturbosch.detekt.Detekt>().configureEach {
    exclude { it.file.absolutePath.contains("/build/generated/") }
}

// By default detektAndroidDebug analyses only androidMain. The Android compilation already contains
// the common sources, so list them to get type-resolved checks on the code that matters.
afterEvaluate {
    tasks.named<io.gitlab.arturbosch.detekt.Detekt>("detektAndroidDebug") {
        setSource(files("src/commonMain/kotlin", "src/androidMain/kotlin", "src/commonTest/kotlin"))
    }
}
```

`config/detekt/detekt.yml` starting point: see `config-detekt.yml` in this folder. Highlights:
`maxIssues: 0`, `InjectDispatcher` on (excluding tests), `ForbiddenImport` for APIs you have banned
with a reason string, `CyclomaticComplexMethod.ignoreSingleWhenExpression: true`, Composable
functions exempt from `FunctionNaming`. Turn a rule off only with a comment explaining why (e.g. a
rule that produces only false positives under type resolution); otherwise use a targeted
`@Suppress` with a reason at the call site.

## ktlint

```kotlin
ktlint {
    android.set(true)
    outputToConsole.set(true)
    filter {
        exclude { it.file.path.contains("/build/generated/") }
        exclude { it.file.name == "GeneratedFixture.kt" }   // generator output the formatter must not rewrite
    }
}
```

Use `.editorconfig` for style (`ktlint_code_style = ktlint_official`, `max_line_length`), and add
the Compose ktlint/detekt rule sets in Compose projects.

## Merged-manifest policy checks

Source-manifest checks miss what a dependency merges back in. Read each variant's **merged**
manifest:

```kotlin
androidComponents {
    onVariants { variant ->
        val merged = variant.artifacts.get(com.android.build.api.artifact.SingleArtifact.MERGED_MANIFEST)
        tasks.register("check${variant.name.replaceFirstChar { it.uppercase() }}NoAdvertisingId") {
            group = "verification"
            inputs.file(merged)
            doLast {
                val ns = "http://schemas.android.com/apk/res/android"
                val doc = javax.xml.parsers.DocumentBuilderFactory.newInstance().apply { isNamespaceAware = true }
                    .newDocumentBuilder().parse(merged.get().asFile)
                val perms = doc.getElementsByTagName("uses-permission").let { n ->
                    (0 until n.length).map { (n.item(it) as org.w3c.dom.Element).getAttributeNS(ns, "name") }
                }
                val forbidden = listOf("com.google.android.gms.permission.AD_ID",
                    "android.permission.ACCESS_ADSERVICES_AD_ID", "android.permission.ACCESS_ADSERVICES_ATTRIBUTION")
                    .filter { it in perms }
                check(forbidden.isEmpty()) { "${variant.name} manifest requests: $forbidden" }
            }
        }
    }
}
```

Pair it with `tools:node="remove"` entries in the source manifest. Permission absence is not proof of
what an SDK collects; re-read the final AAB manifest before store declarations.

## CI

```yaml
# any CI: one job, same command as a developer
- run: ./gradlew --no-daemon verify
  working-directory: <android root>
  env: { GRADLE_USER_HOME: /gradle-cache, GRADLE_OPTS: "-Dorg.gradle.daemon=false" }
```

- Print the toolchain first (`ls $ANDROID_HOME/platforms`); a CI image that lacks the
  `compileSdk` platform fails in confusing ways.
- Cache the Gradle home and, for emulator jobs, the system images and AVD directory.

### Emulator tests in CI: Gradle Managed Devices

```kotlin
android {
    testOptions {
        managedDevices {
            localDevices {
                create("ciPhoneApi34") {
                    device = "Pixel 6"
                    apiLevel = 34
                    systemImageSource = "google_apis"   // not aosp_atd if the app needs Play services/Firebase
                    testedAbi = "x86_64"                // name it, so an AGP default change is visible
                }
            }
        }
    }
}
```

```bash
test -c /dev/kvm && exec 3<>/dev/kvm   # prove KVM is usable before blaming the tests
./gradlew --no-daemon :app:ciPhoneApi34DebugAndroidTest \
  -Pandroid.testInstrumentationRunnerArguments.notAnnotation=com.example.app.RequiresPhysicalDevice
```

Run with container `--device /dev/kvm`. Exclude tests that need hardware features with a runner
argument and a marker annotation rather than deleting them.

## Before trusting the gate

- **Watch it fail.** Break what each task guards (a call to a missing function in
  `androidInstrumentedTest`, a detekt violation) and confirm the gate goes red. A gate never seen
  failing is a claim, not a check.
- Read the output; do not `grep -c error` over it. "Command not found" has zero error lines.
- A skipped source-set task is not proof that source was checked.
- Report every check as PASS / FAIL / NOT_RUN / BLOCKED, including what CI does not cover.

## Checklist

- [ ] One named task (`verify`) aggregates unit tests, ktlint, both detekt variants, Android Lint,
      debug assemble, instrumented-source compile and manifest checks; CI calls that task and
      nothing else.
- [ ] Every new module is wired into the gate by the convention plugin, not by hand.
- [ ] Lint and detekt baselines only shrink; a new rule lands with its baseline in the same change.
- [ ] Merged-manifest checks run on the merged output, not on the source manifest.
- [ ] Emulator tests run on Gradle Managed Devices from the same task, with KVM in CI.
- [ ] Each task was watched failing once; results reported as PASS / FAIL / NOT_RUN / BLOCKED.
- [ ] Local and CI use the same JDK, Gradle and SDK versions (toolchain + pinned image).
