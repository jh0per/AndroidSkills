---
name: android-ci-distribution
description: CI pipelines and tester distribution for Android - GitHub Actions or GitLab CI running the project's single verify gate, Gradle and SDK caching, a pinned build image, merge-request rules and interruptible pipelines, submodule checkout with job tokens, versionCode/versionName from the pipeline, release signing from CI secrets, Fastlane lanes, and Firebase App Distribution or Play internal tracks with changelogs. Use when creating or fixing a CI pipeline, speeding it up, or setting up builds for testers.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - CI
  - GitHub Actions
  - GitLab CI
  - Gradle cache
  - Fastlane
  - Firebase App Distribution
  - Play internal track
---

# Android CI and distribution

The pipeline runs the same named gate developers run (`./gradlew verify`, see `gradle-quality-gate`).
CI adds caching, artifacts, signing and distribution; it never runs a hand-picked subset.

## GitHub Actions

```yaml
name: android
on:
  pull_request:
  push: { branches: [main, develop] }
concurrency: { group: android-${{ github.ref }}, cancel-in-progress: true }

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { submodules: recursive }
      - uses: actions/setup-java@v4
        with: { distribution: temurin, java-version: 17 }
      - uses: gradle/actions/setup-gradle@v4            # caches ~/.gradle, wrapper, configuration cache
      - run: ./gradlew --no-daemon verify
      - uses: actions/upload-artifact@v4
        if: always()
        with: { name: reports, path: '**/build/reports/**' }

  distribute:
    needs: verify
    if: github.ref == 'refs/heads/develop'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with: { distribution: temurin, java-version: 17 }
      - uses: gradle/actions/setup-gradle@v4
      - name: Decode keystore
        run: echo "$KEYSTORE_B64" | base64 -d > "$RUNNER_TEMP/release.jks"
        env: { KEYSTORE_B64: '${{ secrets.RELEASE_KEYSTORE_B64 }}' }
      - run: ./gradlew --no-daemon :app:assembleRelease -Pci.versionCode=${{ github.run_number }}
        env:
          RELEASE_STOREFILE: ${{ runner.temp }}/release.jks
          RELEASE_STOREPASSWORD: ${{ secrets.RELEASE_STORE_PASSWORD }}
          RELEASE_KEYALIAS: ${{ secrets.RELEASE_KEY_ALIAS }}
          RELEASE_KEYPASSWORD: ${{ secrets.RELEASE_KEY_PASSWORD }}
      - name: Firebase App Distribution
        run: |
          npx firebase-tools appdistribution:distribute app/build/outputs/apk/release/app-release.apk \
            --app "$FIREBASE_APP_ID" --groups testers --release-notes "$(git log -5 --pretty='- %h %s')"
        env:
          FIREBASE_APP_ID: ${{ secrets.FIREBASE_APP_ID }}
          GOOGLE_APPLICATION_CREDENTIALS: ${{ runner.temp }}/fad-sa.json   # service account, written from a secret
```

## GitLab CI

```yaml
default:
  interruptible: true                                   # a newer pipeline cancels the older one
  image: registry.example.com/android-build:v7          # pinned, prebuilt image (SDK, build-tools, JDK)

variables:
  GRADLE_USER_HOME: $CI_PROJECT_DIR/.gradle
  GIT_SUBMODULE_STRATEGY: recursive                     # needs job-token access to the submodule project

cache:
  key: { files: [gradle/wrapper/gradle-wrapper.properties, gradle/libs.versions.toml] }
  paths: [.gradle/caches, .gradle/wrapper]

.mr_rules:
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
    - if: $CI_COMMIT_BRANCH && $CI_OPEN_MERGE_REQUESTS   # avoid duplicate branch + MR pipelines
      when: never
    - if: $CI_COMMIT_BRANCH =~ /^(main|develop)$/

stages: [verify, distribute]

verify:
  stage: verify
  rules: !reference [.mr_rules, rules]
  script: ./gradlew --no-daemon verify
  artifacts: { when: always, paths: ['**/build/reports/'], expire_in: 7 days }

distribute_debug:
  stage: distribute
  needs: [verify]
  rules: [{ if: '$CI_COMMIT_BRANCH == "develop"' }]
  script:
    - ./gradlew --no-daemon :app:assembleDebug -Pci.versionCode=$CI_PIPELINE_IID
    - bundle exec fastlane distribute_debug
```

- Build the CI image separately (manual job, versioned tag), with pinned tool versions and checksum-
  verified downloads; do not install the SDK in every job.
- Submodules over HTTPS with the job token:
  `git config --global url."https://gitlab-ci-token:${CI_JOB_TOKEN}@gitlab.example.com/".insteadOf "git@gitlab.example.com:"`
  and allow the parent project in the submodule's job-token settings.
- Don't mix legacy `only:` with `rules:`.

## Fastlane (optional)

```ruby
lane :distribute_debug do
  firebase_app_distribution(
    app: ENV["FAD_APP_ID"],                     # from CI variables, not the Fastfile
    android_artifact_path: "app/build/outputs/apk/debug/app-debug.apk",
    groups: "testers",
    release_notes: changelog_from_git_commits(between: [last_git_tag, "HEAD"], pretty: "- %h %s", merge_commit_filtering: "exclude_merges"),
  )
end

lane :internal do
  upload_to_play_store(track: "internal", aab: "app/build/outputs/bundle/release/app-release.aab",
                       json_key: ENV["PLAY_SA_JSON_PATH"], release_status: "draft")
end
```

## Versions

```kotlin
android {
    defaultConfig {
        versionCode = providers.gradleProperty("ci.versionCode").map(String::toInt).orElse(1).get()
        versionName = "1.4.0"
    }
    buildTypes {
        debug {
            applicationIdSuffix = ".debug"            // installs side by side with release
            versionNameSuffix = providers.gradleProperty("ci.branch").map { "-$it" }.orElse("-local").get()
        }
    }
}
```

- Pipeline counters (`run_number`, `CI_PIPELINE_IID`) give monotonic versionCodes for tester builds.
  Store builds: check the store for used codes before uploading (`android-release-signing`).
- Use `providers.exec {}` / `providers.environmentVariable` instead of running `git` with
  `ProcessBuilder` at configuration time (breaks the configuration cache). Handle branch names that
  do not match an expected ticket pattern.

## Secrets

- Keystore as a base64 secret or secure file, decoded to the runner's temp dir; passwords as masked
  variables; never echo them. Service-account JSON written to a temp file and referenced by path.
- `--token` style CLI auth is deprecated for Firebase; use a service account.
- Signing only in protected branches/tags.

## Speed

- Gradle build cache and configuration cache on (`org.gradle.caching=true`,
  `org.gradle.configuration-cache=true`), daemon off in CI, enough heap (`-Xmx4g`+).
- Split long emulator suites into a separate job (Gradle Managed Devices + KVM, see
  `gradle-quality-gate`) so `verify` stays fast.
- Upload test and lint reports as artifacts on failure.
