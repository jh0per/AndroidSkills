# Spec template (Android / KMP)

Copy into `specs/NNN-short-name/spec.md`. Delete sections that do not apply only after writing why
in one line.

```markdown
# Feature: <short name>

Branch: `NNN-short-name` · Created: YYYY-MM-DD · Status: Draft | Clarified | Planned | Done
Input: "<the request, verbatim>"

## User scenarios and testing

### US1 - <title> (P1)
<One paragraph in the user's words: who, what, why.>

Why P1: <why this slice alone is valuable>
Independent test: <how to demo this story with nothing else built>

Acceptance scenarios:
1. Given <state>, When <action>, Then <observable outcome>
2. Given the device is offline and orders were loaded before, When the user opens Orders,
   Then the last loaded orders are shown with an "Offline" notice

### US2 - <title> (P2)
...

### Edge cases
| Area | Behaviour |
|---|---|
| Rotation / resize | |
| Process death | |
| Offline / timeout / 5xx | |
| Empty / loading / error | |
| Permissions denied / revoked | |
| Background | |
| Back / unsaved changes / double submit | |
| Small phone / tablet / foldable / 200% font | |
| Accessibility (TalkBack, targets, contrast) | |
| Locale (plurals, RTL, long strings) | |
| Session expired / logged out / account switch | |
| iOS parity (KMP) | |
| Upgrade from previous version's data | |

## Requirements

### Functional
- FR-001: System MUST ...
- FR-002: Users MUST be able to ...
- FR-003: System MUST ... [NEEDS CLARIFICATION: ...]

### Key entities (no storage or types)
- Order: what the user ordered; has a status and a date; belongs to one account.

## Success criteria (measurable, technology-free)
- SC-001: ...
- SC-002: ...

## Out of scope
- ...

## Clarifications
### Session YYYY-MM-DD
- Q: <question> → A: <answer> (updated FR-003)

## Assumptions
- <assumption made because the requester was unavailable; revisit before release>
```

## Quality checks before planning

- Each scenario can fail: there is a concrete state in which its "Then" is false.
- No requirement mentions a library, class, module, table or endpoint path.
- Success criteria carry a number and a measuring condition (device class, network, data size).
- Out of scope lists at least the obvious neighbours (editing, sharing, sync on other devices).
