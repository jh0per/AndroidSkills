---
name: spec-driven-development
description: Spec-driven development for Android and KMP features - write the spec before the code (user stories with priorities, Given/When/Then acceptance scenarios, Android-specific edge cases such as process death, configuration change, offline, permissions denied, insets, locales and accessibility), mark open questions instead of guessing, derive a technical plan and an ordered task list from it, trace every acceptance scenario to a test, and keep the spec in sync when the code has to deviate. Tool-agnostic. Use when starting a feature or a significant change, when a request is vague, when reviewing whether an implementation matches what was asked, or when a spec and the code disagree. Do not use for the Spec Kit CLI and its slash commands (see spec-kit-workflow) or for the red-green-refactor loop itself (see android-tdd).
metadata:
  last-updated: '2026-10-16'
  keywords:
  - spec-driven development
  - SDD
  - specification
  - acceptance criteria
  - Given When Then
  - user stories
  - requirements
  - technical plan
  - task breakdown
---

# Spec-driven development

The spec is the source of truth; the plan and the code are derived from it. A feature starts as a
short document that says **what** and **why** in user terms, gets a plan that says **how** in this
codebase, then a task list, then code. When the code has to deviate, the spec changes first.
`spec-kit-workflow` runs the same flow with the Spec Kit CLI; `android-tdd` owns the test-first
loop that implements each task; `verification-discipline` owns how "done" is proven.

## Prerequisites

- Read the project's `CLAUDE.md`/`AGENTS.md` and, if present, its constitution
  (`.specify/memory/constitution.md` or `docs/constitution.md`): architecture, module rules, test
  policy and minSdk are inputs, not things the spec re-decides.
- Find where specs live (`specs/NNN-feature/`, `docs/specs/`). If nothing exists, use
  `specs/NNN-short-name/spec.md` with a zero-padded number and a matching branch name.
- One spec per feature or user-visible change. A refactor with no behaviour change needs a short
  plan, not a spec.

## Steps

### 1. Specify: what and why, no how

Write `spec.md` with the template in `references/spec-template.md`. Rules:

- **No implementation words.** No `ViewModel`, `Room`, `Ktor`, module names or class names. "The
  list survives the app being killed in the background" is a requirement; "persist in Room" is a
  plan decision.
- **User stories are independently shippable slices**, ordered P1, P2, P3. P1 alone must be a
  usable MVP; each story has its own "independent test" sentence.
- **Acceptance scenarios in Given/When/Then**, each one observable on screen or at a boundary (a
  request sent, a notification shown, a file written). These become test names later.
- **Functional requirements** are numbered (`FR-001`) and testable: "MUST show the cached list
  within 1 s when offline", not "should be fast".
- **Success criteria** are measurable and technology-free (`SC-001`: cold start to first content
  under 2 s on a mid-range device; 0 crashes in the flow on the pre-launch report).
- **Unknowns are marked, not guessed:** `[NEEDS CLARIFICATION: Do guests see prices?]`. At most a
  handful; resolve them with the requester before planning. A guess written as a requirement is
  the most expensive line in the document.

### 2. Android edge cases: walk the checklist

Every Android spec answers these, or states "not applicable" with a reason. Missing ones are where
production bugs come from:

| Area | Question the spec must answer |
|---|---|
| Lifecycle | What survives rotation, dark-mode switch, font-scale change, window resize? |
| Process death | User leaves mid-form, system kills the app: what is restored on return? |
| Offline / flaky network | What shows with no network, on timeout, on a 5xx, when the network returns? |
| Empty / loading / error | What does each look like; is there retry; is stale data shown during refresh? |
| Permissions | What happens when denied, denied permanently, or revoked while in use? |
| Background | Does work continue when the app is backgrounded; is a notification required? |
| Input | Back gesture mid-flow, unsaved changes, double tap on submit, IME covering the field? |
| Layout | Small phone, tablet/foldable, landscape, edge-to-edge, 200% font scale? |
| Accessibility | TalkBack labels, 48dp targets, contrast, no colour-only meaning? |
| Locale | Plurals, RTL, long translations, date/number formats, per-app language? |
| Accounts | Logged out, session expired mid-flow, account switched, account deleted? |
| Platforms (KMP) | Same behaviour on iOS? Which parts are platform-specific by design? |
| Data | Migration from the current version; what if stored data is from an older schema? |

### 3. Clarify

Before planning, list every `[NEEDS CLARIFICATION]` and every edge-case row answered with a guess
as numbered questions with a recommended answer. Record answers in a `## Clarifications` section
with the date; do not silently rewrite the requirement. If the requester is unavailable, proceed
with the recommended answers and say so in the plan.

### 4. Plan: how, in this codebase

`plan.md` maps the spec onto the existing architecture. It names:

- **Technical context:** Kotlin and AGP versions, targets (android, iosArm64, jvm), min/target SDK,
  libraries already in the catalog that will be used, new dependencies with a reason.
- **Constitution check:** each project rule (module boundaries, MVI pattern, test policy) and
  whether the plan complies; every exception is written down with why.
- **Structure:** modules and source sets touched (`feature/orders`, `core/data`,
  `commonMain`/`androidMain`), new files with their paths.
- **Data model and contracts:** entities, state/intent/effect types, API endpoints and DTOs, on-disk
  keys. Contracts are what tests will pin (see `architecture-guard-tests`).
- **Research:** each non-obvious choice with the alternatives rejected ("Paging 3 vs manual
  load-more: chosen because...").
- **Test strategy:** which layer each acceptance scenario is tested at (see `android-tdd`).

The plan may not add scope. A capability the spec does not ask for goes back to the spec as a
question.

### 5. Tasks: small, ordered, traceable

`tasks.md` is a checklist the implementer works top to bottom:

```markdown
## Phase 1: Setup
- [ ] T001 Add `feature/orders` module with convention plugin (settings.gradle.kts, feature/orders/build.gradle.kts)
## Phase 2: Foundation (blocks all stories)
- [ ] T002 [P] Define `Order` and `OrdersRepository` in core/data/src/commonMain/.../OrdersRepository.kt
- [ ] T003 [P] `FakeOrdersRepository` in core/testing/src/commonMain/.../FakeOrdersRepository.kt
## Phase 3: US1 See my orders offline (P1) 🎯 MVP
- [ ] T004 [US1] Test: cached orders shown when offline (FR-003, scenario US1-2) in feature/orders/src/commonTest/.../OrdersViewModelTest.kt
- [ ] T005 [US1] OrdersViewModel load + offline path in feature/orders/src/commonMain/.../OrdersViewModel.kt
- [ ] T006 [US1] OrdersUi empty/loading/error states in feature/orders/src/commonMain/.../OrdersUi.kt
## Phase N: Polish
- [ ] T020 Run ./gradlew verify; update spec if anything deviated
```

- Every task names the file it touches. `[P]` only when it touches different files and has no
  dependency on an unfinished task.
- Tests come before the code they cover and cite the FR or scenario they prove.
- Each story phase ends at a checkpoint where that story works and can be demoed alone.

### 6. Implement and keep the trace

- Work one task at a time; tick it only when its test passes and the gate is green.
- Name tests after scenarios (``fun `offline - shows cached orders`()``) or put the ID in the name,
  so `grep FR-003` finds the requirement, the task and the test.
- **Deviation rule:** if the code cannot meet the spec (API missing, platform limit), stop, update
  the spec or plan with the reason, then continue. Never let the code quietly become the spec.

### 7. Verify against the spec, not the plan

At the end, walk the spec: every FR and every acceptance scenario maps to a test or a recorded
manual check on a device, every edge-case row has an answer and a check, every success criterion
has a measurement or is marked NOT_RUN. Report with the format below.

## RIGHT / WRONG

```markdown
<!-- WRONG: implementation in the spec, untestable wording -->
- FR-001: Use Room to cache orders so the screen is fast.

<!-- RIGHT: observable, measurable, technology-free -->
- FR-001: System MUST show the last loaded orders within 1 s when the device is offline.
```
Why: the plan may pick DataStore or a file; the test can only check what is observable.

```markdown
<!-- WRONG: a guess hiding as a requirement -->
- FR-004: Orders older than 90 days are hidden.

<!-- RIGHT -->
- FR-004: Orders older than [NEEDS CLARIFICATION: retention window? 90 days, 1 year, all] are hidden.
```
Why: the number is a product decision; asking costs one message, shipping the wrong one costs a release.

```markdown
<!-- WRONG: one task per layer, nothing works until the end -->
- [ ] T005 All ViewModels   - [ ] T006 All screens   - [ ] T007 All tests

<!-- RIGHT: vertical slices per story, tests first -->
- [ ] T004 [US1] Test offline cached list  - [ ] T005 [US1] ViewModel  - [ ] T006 [US1] Screen
```
Why: a vertical slice can be demoed and reviewed; a horizontal layer cannot.

## Scope guards

- A one-line bug fix does not need a spec: write the regression test (`android-tdd`) and fix it.
- A spike to learn an API is throwaway code; its output is a "Research" entry, not a merged feature.
- Do not write specs for code that already exists unless the task is to change its behaviour; for
  legacy code start with characterisation tests.

## Report format

```
Spec: specs/012-offline-orders/spec.md   Branch: 012-offline-orders
FR-001 PASS  OrdersViewModelTest.`offline - shows cached orders`
FR-002 PASS  OrdersRepositoryTest.`refresh replaces cache`
FR-003 NOT_RUN  manual: 200% font scale on small phone (no device in CI)
SC-001 BLOCKED  needs Macrobenchmark on a physical device
Edge cases: process death PASS (SavedStateHandle test), offline PASS, permission n/a (none used)
Deviations: FR-005 changed 2026-10-16, pagination size set by server (plan.md#research)
```

## Checklist

- [ ] Spec has no implementation words; every FR is testable; P1 is a usable MVP.
- [ ] Android edge-case table answered or marked n/a with a reason.
- [ ] No `[NEEDS CLARIFICATION]` left, or the plan says which recommended answers were assumed.
- [ ] Plan has a constitution check, modules/source sets and a test layer per scenario.
- [ ] Tasks are vertical per story, name files, put tests first and cite FR/scenario IDs.
- [ ] Every FR and scenario traced to a passing test or a recorded manual check.
- [ ] Spec updated for every deviation before the PR is opened.
