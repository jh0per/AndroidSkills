---
name: android-release-signing
description: Release mechanics for an Android app - keystore and secrets handling that never reaches git, optional signing config with fail-fast checks, R8/resource shrinking and keep rules, verifying the AAB signature, versionCode from the store, Play App Signing fingerprints for Google sign-in, crash-symbol upload, and Play or Firebase App Distribution publishing. Use when building a release, configuring signing, debugging a store upload refusal, or a release-only crash.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - release build
  - keystore
  - signing config
  - R8
  - keep rules
  - AAB
  - versionCode
  - Play App Signing
---

# Android release and signing

Publishing is outward-facing: building and verifying an artifact is fine to do on your own;
uploading it to a store track needs the owner's explicit go-ahead.

## Secrets never enter git

`.gitignore` must contain:

```gitignore
local.properties
keystore.properties
*.jks
*.keystore
keystore/
google-services.json      # unless deliberately committed; it is not a secret but is project-identifying
*.p12
play-publisher*.json
```

Commit `keystore.properties.example` with empty values. Service-account keys live outside the repo
(e.g. `~/.config/<app>/`, mode 600). Audit an existing repo with
`git ls-files | grep -Ei '\.jks|\.keystore|keystore\.properties|service-account|\.p12'` and
`git log --all --diff-filter=A --name-only | grep -Ei 'jks|keystore'`; a key that was ever pushed
must be treated as leaked (rotate upload key via Play Console, rotate tokens).

The owner's signing file is theirs: agents never write `local.properties`/`keystore.properties`,
never print secret values (check presence with `sed 's/=.*/=<set>/'`), and never pass passwords as
command-line arguments. Provide an interactive script for the owner that prompts securely and
verifies store password, alias and key password before writing.

## Optional signing config, with a loud failure

```kotlin
val signingFile = rootProject.file("keystore.properties")
val signing = Properties().apply { if (signingFile.exists()) signingFile.inputStream().use(::load) }
fun secret(key: String): String =
    providers.gradleProperty(key).orNull ?: signing.getProperty(key) ?: System.getenv(key.replace('.', '_').uppercase()) ?: ""

val storeFilePath = secret("release.storeFile")
val storePass = secret("release.storePassword")
val keyAlias = secret("release.keyAlias")
val keyPass = secret("release.keyPassword").ifBlank { storePass }
val releaseSigningReady = storeFilePath.isNotBlank() && rootProject.file(storeFilePath).exists() &&
    storePass.isNotBlank() && keyAlias.isNotBlank() && keyPass.isNotBlank()

android {
    signingConfigs {
        if (releaseSigningReady) create("release") {
            storeFile = rootProject.file(storeFilePath); storePassword = storePass
            this.keyAlias = keyAlias; keyPassword = keyPass
            enableV1Signing = true; enableV2Signing = true; enableV3Signing = true   // v3 keeps key rotation possible
        }
    }
    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            ndk { debugSymbolLevel = "SYMBOL_TABLE" }
            signingConfig = signingConfigs.findByName("release")
        }
        debug { isMinifyEnabled = false }
    }
}

// An incomplete config is a mistake, not a CI machine: say so before building.
tasks.matching { it.name == "preReleaseBuild" }.configureEach {
    doFirst { if (signingFile.exists() && !releaseSigningReady) error("Release signing config is incomplete: fill keystore.properties") }
}
```

**Trap:** with signing absent, `bundleRelease` succeeds and produces an **unsigned** bundle. Git
worktrees and fresh clones do not have the gitignored keystore. Build releases in the checkout
that owns the keystore, then verify the certificate, not the exit code:

```bash
jarsigner -verify -certs -verbose app-release.aab | grep -m1 'X.509'     # expect your CN=
./gradlew :app:signingReport                                             # store/alias/fingerprints, no passwords
apksigner verify --print-certs --max-sdk-version 33 installed.apk       # cap avoids v3.x hybrid-signature failures
```

`keytool -list` can print entries without a valid password and only warns; it does not prove the
password. Aliases are case-sensitive.

## R8 keep rules

R8 failures surface at the point of use, not at build time. Keep a commented `proguard-rules.pro`
(or `src/main/keepRules/*.keep`) and never delete a rule without exercising its flow on a minified
build. Typical set: `keep-rules.pro` in this folder.

Before shipping, install the **minified** build and walk the critical flows: network fetch and
decode, opening/saving persisted data, process death and restore (`adb shell am kill` while
backgrounded), sign-in, purchase screen. A green build does not prove reflection survived.

## versionCode: ask the store

Play refuses a `versionCode` it has seen on **any** track. A comment saying "N is free" is a stale
snapshot. Before uploading, list what each track serves (Play Developer API
`edits.tracks.list`, or your publish script's dry run) and take the next free number.

## Google sign-in after Play App Signing

Play re-signs uploads with the **app-signing key**. Register Play's app-signing SHA-1/SHA-256 in
Firebase/Google Cloud, not only the local debug and upload fingerprints; otherwise store installs
report "no Google account" while local builds sign in fine. Read the fingerprint from Play Console
or from an installed APK (`adb shell pm path <pkg>` → `apksigner --print-certs`). Registration is
server-side; no rebuild needed.

## Store-side refusals worth knowing

- Play automatic protection requires a minimum SDK floor; raising `minSdk` is a platform-support
  change and belongs in the release notes.
- A one-time product cannot be created until an uploaded build declares the billing permission.
- Products of an app that has not passed review show `(unreviewed)` in their title and cannot be
  bought, even by testers (see `play-billing`).

## Crash reporting

- Release builds upload the R8 mapping file (Crashlytics plugin `mappingFileUploadEnabled = true`
  for release, false for debug). Disable crash collection in debug.
- Symbol upload succeeding does not prove a real release crash arrives deobfuscated; trigger one in
  an internal build once.

## Privacy declarations

If the app shows no ads, remove the advertising-ID permissions merged by analytics SDKs
(`tools:node="remove"`) and set the analytics ad-ID collection/personalisation meta-data to
`false`, guarded by a merged-manifest check (see `gradle-quality-gate`). Re-read the final AAB's
manifest before filling store declarations.

## Distribution

- Internal testing: Firebase App Distribution via CLI or Fastlane lane (`firebase appdistribution:distribute app.apk --app <id> --groups qa --release-notes-file CHANGELOG.txt`).
- Play: upload through the Developer API with a dedicated publisher service account; check which
  account has release permission by its `client_email`, not by the key file's name. Never revoke a
  key that production also uses as a troubleshooting step.
- Who pays: every track charges real money except accounts on Play Console's License testing list;
  review that list before inviting testers.
