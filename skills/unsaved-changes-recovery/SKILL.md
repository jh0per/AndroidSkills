---
name: unsaved-changes-recovery
description: Protect a person's work in long forms and editing screens - detecting unsaved changes against a saved baseline that ignores session state, a back handler that reaches the same question as the on-screen control, the Save / Discard / Cancel prompt, debounced autosave to a hidden working-session record, crash and process-death recovery offered on next launch, transactional Cancel/Apply sessions, and large state outside the Bundle. Use when building or fixing an editor, a multi-step form, or any screen where leaving can lose work.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - unsaved changes
  - dirty state
  - back handling
  - autosave
  - crash recovery
  - discard dialog
---

# Unsaved changes and recovery

## Dirty detection

```kotlin
sealed interface SavedBaseline {
    data object Unknown : SavedBaseline                 // load in flight: never ask
    data object NeverSaved : SavedBaseline              // recovered/new unsaved work: always ask
    data class Saved(val draft: DraftState) : SavedBaseline
}

fun SavedBaseline.isDirty(current: DraftState): Boolean = when (this) {
    SavedBaseline.Unknown -> false
    SavedBaseline.NeverSaved -> true
    is SavedBaseline.Saved -> current.withoutSessionState() != draft
}

/** Scroll position, focused field, expanded sections and an open picker are not the draft's changes. */
fun DraftState.withoutSessionState() = copy(scrollY = 0, focusedField = null, expandedSections = emptySet(), openPicker = null)
```

- Compare models, not serialized output (serialization is slow and noisy, and embeds attachments).
- Compare once when the person tries to leave, not on every recomposition.
- The baseline of a draft opened pre-filled (a duplicate, a hand-off from another screen) is that
  pre-filled state: backing out of an untouched pre-filled draft asks nothing.
- After saving, adopt whatever the save normalised (trimmed strings, generated ids) into the live
  state; otherwise the baseline differs by exactly those bytes and the prompt fires right after a
  save.

## Leaving

- The system back gesture and the on-screen back control reach the **same** decision.
  Compose: `NavigationBackHandler` (navigationevent) or `BackHandler`/`PredictiveBackHandler`, always
  enabled while the screen is shown; the innermost handler wins. Views: `OnBackPressedCallback`.
- The prompt has three answers: **Save** (confirm), **Discard** (neutral, placed beside Cancel, not
  under the thumb), **Cancel**. A failed save keeps the screen open and shows the error; save-and-
  leave navigates only after the save completes.
- Verify the back handler is actually installed (a navigator overload without a back handler, or a
  lenient dispatcher owner, can make every back swipe close the app). Guard it with a test.

## Autosave to a working session

```kotlin
LaunchedEffect(snapshot, loadStatus, discarding) {
    if (loadStatus != LoadStatus.Ready || discarding || !baseline.isDirty(snapshot)) return@LaunchedEffect
    delay(AUTOSAVE_DEBOUNCE_MS)                           // ~1 s; a new snapshot restarts the effect
    repository.saveWorkingSession(snapshot)              // ONE hidden row, separate from saved items
}

fun onDiscard() {
    discarding = true                                     // cancels a pending autosave debounce
    scope.launch { repository.clearWorkingSession(); navigator.pop() }   // clear BEFORE leaving
}
```

- An explicit save clears the working session.
- The working session is local only and never synced.
- Persist only while the draft differs from what was saved.

## Recovery

```kotlin
suspend fun recoverableWorkingSession(): DraftState? {
    val row = dao.findWorkingSession() ?: return null
    val usable = now() - row.updatedAt <= 7.days && row.schemaVersion == CURRENT_SCHEMA
    return (if (usable) row.decodeOrNull() else null) ?: run { dao.clearWorkingSession(); null }
}
```

- Check once per launch on the home screen; offer **Continue** / **Discard** (deletes) / **Later**
  (hides the offer only). Only an explicit discard deletes work.
- Continue opens the screen in "recover" mode, which re-reads the row itself (no large hand-off).
- Device check: kill the process mid-edit (`adb shell am kill <pkg>` while backgrounded, or force
  stop), relaunch, take the offer, confirm nothing is lost.

## Transactional tool sessions (Cancel / Apply)

Tool sheets that offer Cancel/Apply open a history transaction:

```kotlin
interface TransactionalHistory {
    fun begin()                  // remember the current position
    fun hasChanges(): Boolean    // commands recorded since begin()
    fun discard()                // undo and drop everything since begin()
    fun commit()                 // keep, end the session
}
```

While a session is open, undo/redo is limited to the session's commands. Coalesce rapid edits
(each keystroke, each drag frame) into one history entry: render intermediate states without
recording (`submit = false`), record once on release/blur (`submit = true`). See
`compose-canvas-gestures` for the history model; cap the history length.

## Large state and process death

- Never put a large draft in navigation arguments or `onSaveInstanceState`
  (`TransactionTooLargeException` around 1 MB). Keep an id there; keep the draft in memory and
  write it to a file in `onSaveInstanceState`, restoring from that file (falling back to the
  autosave) after process death.
- Validate numbers in the reducer (no NaN/Infinity reaches the model), not at save time; an encoder
  that throws on NaN will otherwise make the draft unsavable.
- Breadcrumb logs on save/restore and a non-fatal when restored state is missing help diagnose
  field reports.

## Tests

- Baseline: unknown never asks; untouched pre-filled draft does not ask; edit then undo to the saved state
  does not ask; save then immediate back does not ask.
- Autosave debounce restarts on edits; discard cancels a pending autosave; explicit save clears the row.
- Recovery: expired or wrong-schema rows are deleted, valid rows offered once.
