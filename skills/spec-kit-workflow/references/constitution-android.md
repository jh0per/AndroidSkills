# Android / KMP constitution starter

Pass this to `/speckit.constitution` after deleting every line the project does not already
practise or has not agreed to adopt. Unrealistic rules make every plan fail its Constitution Check
and teach people to ignore it.

```markdown
# <App> Constitution

## Core Principles

### I. Test-First (NON-NEGOTIABLE)
Every behaviour change starts with a failing test that names the acceptance scenario or FR it
proves. Red, green, refactor. Bug fixes start with a regression test that fails on the old code.
Tests run at the lowest layer that can observe the behaviour: commonTest/test before Robolectric,
Robolectric before instrumented. tasks.md always contains test tasks before implementation tasks.

### II. Module boundaries
Features live in `:feature:*` modules and depend only on `:core:*` APIs, never on another feature.
Navigation between features goes through route keys in `:core:navigation`. New modules use the
existing convention plugins; no per-module copies of build logic.

### III. One screen pattern
Screens use MVI on AndroidX ViewModel: immutable State, sealed Intent, one-shot Effect, a stateless
`XUi(state, onIntent)` composable. Dependencies come from Koin; no service locators in composables.

### IV. Shared code first (KMP)
Domain, data and ViewModels live in commonMain. Platform code sits behind interfaces provided by
the platform's composition root; expect/actual only for leaf platform facts.

### V. Offline and lifecycle are requirements
Every screen defines its loading, empty, error and offline states. State that the user typed
survives configuration changes and process death.

### VI. Accessible and localised by default
Every user-visible string is a resource with plurals where counts appear. Interactive elements are
at least 48dp and have content descriptions. Layouts are verified at 200% font scale.

### VII. Simplicity
No new dependency, module or abstraction without a written reason in plan.md research. Prefer the
platform and libraries already in the version catalog.

## Platform constraints
- minSdk <N>, targetSdk <N>, compileSdk <N>; Kotlin <version>; JDK toolchain <N>.
- Edge-to-edge on all screens; predictive back supported.
- No secrets in the repo; release signing from CI secrets only.
- Permissions: least privilege, requested in context, with a denied path.

## Quality gates
- `./gradlew verify` (lint, detekt, ktlint, unit tests) passes locally and in CI before review.
- New user-facing flows have a Compose UI test for the stateless Ui and a recorded device check.
- Performance-sensitive changes include a Macrobenchmark or a written NOT_RUN reason.

## Governance
The constitution overrides other conventions; CLAUDE.md/AGENTS.md hold project facts, not rules.
Amendments go through a PR that updates this file, bumps the version (MAJOR: principle removed or
redefined, MINOR: principle added, PATCH: wording) and states which specs are affected.
Completed specs under specs/ are <immutable history | living contracts updated with the code>.

**Version**: 1.0.0 | **Ratified**: YYYY-MM-DD | **Last Amended**: YYYY-MM-DD
```

Notes:

- Replace module names (`:feature:*`, `:core:*`) with the project's real ones, or drop
  principle II for single-module apps.
- Circuit projects replace principle III with Presenter + Ui (see `circuit-screen`).
- Projects without KMP drop principle IV and the iOS lines.
