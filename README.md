# Android Skills

Reusable [Claude skills](https://docs.claude.com/en/docs/claude-code/skills) for Android and Kotlin
Multiplatform development. Each skill is a folder with a `SKILL.md` (YAML frontmatter `name` +
`description`, then instructions) and optional supporting files. The agent loads a skill when its
description matches the task.

## Skills

Nothing here requires Circuit. The shared skills assume ViewModel + Navigation Compose; only
`circuit-screen` is Circuit-specific (skip it if your project does not use Circuit).

### Architecture and screens

| Skill | Use it for |
|---|---|
| [kmp-compose-architecture](skills/kmp-compose-architecture/SKILL.md) | Package layout, layer boundaries, platform seams without expect/actual, Koin wiring; works with or without Circuit |
| [android-multimodule](skills/android-multimodule/SKILL.md) | Module graph, routes module, per-service network modules, dependency inversion at module edges, embedding a library |
| [compose-mvi-viewmodel](skills/compose-mvi-viewmodel/SKILL.md) | Default screen pattern: MVI on ViewModel (Android or KMP), Koin, Navigation Compose, effects, tests |
| [circuit-screen](skills/circuit-screen/SKILL.md) | Optional, only for projects already on Circuit: Screen/Presenter/Ui, parcelize shim, presenter tests |
| [views-compose-interop](skills/views-compose-interop/SKILL.md) | Fragments + XML + Compose, SafeArgs navigation from ViewModels, deep links, migration plan |
| [kmp-ios-interop](skills/kmp-ios-interop/SKILL.md) | iOS composition root, Swift callback bridges, Xcode/framework setup, Kotlin/Native gotchas |
| [navigation3-compose](skills/navigation3-compose/SKILL.md) | Navigation 3: owned NavKey back stack, per-feature entry providers with Koin, scenes, list-detail, deep links, migration from Navigation Compose |
| [predictive-back](skills/predictive-back/SKILL.md) | One back owner per screen, BackHandler vs PredictiveBackHandler vs NavigationBackHandler, dispatcher scoping, gesture testing |

### UI

| Skill | Use it for |
|---|---|
| [material3-guidelines](skills/material3-guidelines/SKILL.md) | Which Material 3 component for which job, colour/type/shape roles, window size classes, motion, accessibility |
| [compose-ui-practices](skills/compose-ui-practices/SKILL.md) | Component reuse, tokens, 48dp targets, inset ownership, one list-state owner, messages, adaptive layout |
| [edge-to-edge-insets](skills/edge-to-edge-insets/SKILL.md) | enableEdgeToEdge and SDK 35+ enforcement, one inset owner per edge, IME without double padding, scrims, dialogs, gesture/3-button verification |
| [compose-performance-audit](skills/compose-performance-audit/SKILL.md) | Evidence-based Compose performance: phase deferral, stability without cargo cult, lazy layout rules, effects, drawing, Modifier.Node, audit report |
| [design-system-module](skills/design-system-module/SKILL.md) | Tokens and theme, skeletons/shimmer, loaders, dialogs and notices, previews, splash and launcher icon |
| [compose-text-input](skills/compose-text-input/SKILL.md) | Validated fields, clamping steppers, forms, custom rich-text input and IME quirks |
| [compose-canvas-gestures](skills/compose-canvas-gestures/SKILL.md) | Whiteboard/diagram canvases: single-detector gestures, hit testing, snapping, modal tools, undo/redo with submit semantics |
| [paging3-compose](skills/paging3-compose/SKILL.md) | PagingSource, Pager placement, grid load states, retry vs refresh, refresh on reconnect |
| [fonts-management](skills/fonts-management/SKILL.md) | App typography, font registry, verified downloads, priority queues, variable fonts |
| [localization](skills/localization/SKILL.md) | Strings and plurals, locale reading, per-app language, Accept-Language, error wording from codes |

### Data, network and platform

| Skill | Use it for |
|---|---|
| [ktor-api-client](skills/ktor-api-client/SKILL.md) | Ktor client, origin-scoped bearer, refresh-once, one error mapper, connectivity, MockEngine tests |
| [local-persistence](skills/local-persistence/SKILL.md) | Room KMP, DataStore over a path provider, on-disk contracts, migrations, local-first sync |
| [long-running-jobs](skills/long-running-jobs/SKILL.md) | Upload validation, presigned uploads, job polling with backoff, push fallback, one-shot hand-off |
| [unsaved-changes-recovery](skills/unsaved-changes-recovery/SKILL.md) | Dirty baseline, back handling, Save/Discard/Cancel, autosave, crash recovery, transactions |
| [media-storage](skills/media-storage/SKILL.md) | MediaStore saves, sharing, pickers and capture, bounded decoding, Coil, WorkManager uploads |
| [media-video-audio](skills/media-video-audio/SKILL.md) | Media3 players and cache, thumbnails, waveforms, trim, Transformer transcoding |
| [image-filters-gpu](skills/image-filters-gpu/SKILL.md) | RenderScript migration, AGSL, Vulkan/GL fallbacks, colour LUT pipelines, pixel verification |
| [on-device-ml](skills/on-device-ml/SKILL.md) | ML Kit behind a seam, model availability, LiteRT, server fallback |
| [native-interop](skills/native-interop/SKILL.md) | JNI with CMake or Rust, callbacks, ABI filters, symbols, 16 KB alignment |
| [push-notifications](skills/push-notifications/SKILL.md) | FCM data messages, channels, permission timing, token registration, tap routing |

### Accounts, money and policy

| Skill | Use it for |
|---|---|
| [firebase-auth](skills/firebase-auth/SKILL.md) | Credential Manager Google sign-in, ID tokens for your backend, fingerprints, smoke test |
| [oauth-browser-login](skills/oauth-browser-login/SKILL.md) | OAuth/OIDC with PKCE in Custom Tabs, token storage and refresh, web logout |
| [play-billing](skills/play-billing/SKILL.md) | Play Billing with server verification, recovery, shared accounts, offers, upgrades, ads gating |
| [device-attestation](skills/device-attestation/SKILL.md) | Play Integrity behind a seam, permanent vs transient failures, request hash binding |
| [account-compliance](skills/account-compliance/SKILL.md) | Account deletion, versioned Terms, legal links, content reporting, ads ID and data safety |
| [analytics-feature-flags](skills/analytics-feature-flags/SKILL.md) | Typed analytics slices, consent, remote flags, A/B tests, force update, OTA strings |
| [android-app-security](skills/android-app-security/SKILL.md) | Exported components, Intent redirection, PendingIntent flags, deep-link validation, signature permissions, FileProvider, WebView, network config, secrets, audit report |

### Build, quality and release

| Skill | Use it for |
|---|---|
| [gradle-build-setup](skills/gradle-build-setup/SKILL.md) | Version catalog, toolchain, AGP 9 notes, config values, convention plugins, custom tasks, build speed |
| [gradle-quality-gate](skills/gradle-quality-gate/SKILL.md) | One `verify` task for local and CI, detekt, ktlint, lint, merged-manifest checks, managed devices |
| [android-ci-distribution](skills/android-ci-distribution/SKILL.md) | GitHub Actions / GitLab CI, caching, signing from secrets, Fastlane, App Distribution |
| [android-release-signing](skills/android-release-signing/SKILL.md) | Secrets out of git, optional signing with fail-fast, R8 keep rules, AAB verification, versionCode |
| [android-testing](skills/android-testing/SKILL.md) | Test dispatchers, ViewModel tests, Robolectric/Room, Compose instrumented tests, contrast and touch checks |
| [app-startup-performance](skills/app-startup-performance/SKILL.md) | Macrobenchmark, Baseline/Startup Profiles, reportFullyDrawn, startup hygiene, tracing, JankStats, ANR triage, before/after report |
| [architecture-guard-tests](skills/architecture-guard-tests/SKILL.md) | Source-level guards: one owner, banned APIs, ratchets, contracts, each with a control |
| [debug-tooling](skills/debug-tooling/SKILL.md) | HTTP inspector, logging, hidden debug menu, mock overrides, StrictMode, keeping release clean |
| [verification-discipline](skills/verification-discipline/SKILL.md) | Making gates fail first, probe controls, printing wire bytes, honest reporting |

Code samples use `com.example.app` and `App*` names. Replace them with your own package and prefix.

## Plug into a project

**As a Claude Code plugin (recommended):**

```
/plugin marketplace add jh0per/AndroidSkills
/plugin install android-kmp-skills@android-kmp-skills
```

**Project-level (shared with the team):** copy or link the skills into the project's
`.claude/skills/` directory.

```bash
git clone https://github.com/jh0per/AndroidSkills.git ~/AndroidSkills
mkdir -p .claude/skills
cp -R ~/AndroidSkills/skills/* .claude/skills/          # or pick only the ones you need
```

**As a git submodule (stays updatable):**

```bash
git submodule add https://github.com/jh0per/AndroidSkills.git tools/android-skills
mkdir -p .claude/skills
for s in tools/android-skills/skills/*/; do ln -s "../../$s" ".claude/skills/$(basename "$s")"; done
git submodule update --remote tools/android-skills       # later, to pull updates
```

**Personal (every project on your machine):**

```bash
mkdir -p ~/.claude/skills
ln -s ~/AndroidSkills/skills/* ~/.claude/skills/
```

Other agents that read the same `SKILL.md` format can point at the same folders (for example
`.agents/skills/`).

## Make them yours

- Put project-specific facts (package names, component registry, API origin, commands) in the
  project's own `CLAUDE.md`/`AGENTS.md`; keep these skills generic.
- When a skill disagrees with a decision your project made deliberately, record the decision in the
  project docs; the project wins.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md): one folder per skill, frontmatter with `name`,
`description` and `metadata`, the body structure we use, and `scripts/validate_skills.py`.

## License

[MIT](LICENSE). Copy the skills into any project, commercial or not; keep the notice.
