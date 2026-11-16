# State restoration: what is saved, and how to prove it

Read this when wiring the navigation host, when a screen is lost after the app returns from the
background, or when writing the tests for it. `SKILL.md` has the rules; this file has the detail.

## Three lifetimes

| Holder | Survives recreation | Survives Android process death | Survives the end of the process on iOS |
|---|---|---|---|
| `remember` | no | no | no |
| `rememberRetained` | yes | no | no |
| The navigation stack (`rememberSaveableNavStack` with a `CircuitSaver`) | yes | yes | no |
| The data layer (Room, DataStore) | yes | yes | yes |

With Compose Multiplatform on iOS the saved state does not come back after the process ends: the
app starts from its root screen. Anything the user must find again there, a draft or an
unfinished flow, is written through the data layer and offered again on start. Do not design a
flow that relies on the stack coming back on both platforms.

## The saver

`SerializableCircuitSaver` writes each screen as saved state through its kotlinx serializer. It
knows a screen only when the screen is registered for polymorphic serialization, which is what
the list of `CircuitSerializerRegistration` does. Three failure modes, each seen on a device or in
a test:

| Mistake | What happens | When |
|---|---|---|
| `@Serializable` and no registration | `IllegalArgumentException: Unable to save class …` | when state is saved: on Android, as the app leaves the foreground |
| Registration and no `@Serializable` | it compiles; building the `Circuit` instance throws | wherever the instance is built: in every graph test too |
| The saved stack names a screen the app no longer lists | the stack is dropped, the app starts from the root | on restore, silently |

To keep some screens `Parcelable` next to serialized ones, combine savers; the first that claims
a value saves it:

```kotlin
import com.slack.circuit.runtime.screen.plus

Circuit.Builder()
    .setCircuitSaver { fallback -> SerializableCircuitSaver(savedScreens) + fallback }
```

`fallback` is Circuit's default saver, which passes through what the platform can save itself
(`Parcelable` on Android). A value that no saver claims fails the save with
`No CircuitSaver in this composite can save …`. Appending `CircuitSaver.NoOp` or
`CircuitSaver.Dropping { … }` makes the save succeed without that screen, and the restore then
gives the stack up when the screen was the current one or below it. Do it only with a report to
crash analytics inside `Dropping`.

`SerializableCircuitSaver` also takes `onRestoreError`: pass a reporter there, so that a screen
that could not be read back is visible somewhere.

## Tests

**Registration, on the JVM.** `saver.save(screen)` throws for a screen that is not listed, so a
loop over all screens in the graph test is the guard (shown in `SKILL.md`). Pair it with a control.

**Reading a stack back.** In a JVM unit test of an Android target the saved state is an
`android.os.Bundle` from the stub `android.jar`: with `isReturnDefaultValues = true` it accepts
writes and returns nothing, so `restoreScreen` gives `null` for every screen and a round-trip
assertion can never pass there. Put the round trip where saved state is real: in `iosTest` of a
KMP project (it runs on a simulator), or in an Android instrumented test.

```kotlin
// iosTest, or androidInstrumentedTest
private val saver = SerializableCircuitSaver(
    savedScreens + CircuitSerializerRegistration { it.subclass(KeyedScreen::class) },
)

@Test fun `every screen comes back equal`() {
    for (screen in everyScreen) {
        val saved = assertNotNull(saver.save(screen))
        assertEquals(screen, saver.restoreScreen<Screen>(saved))
    }
}

@Test fun `a stack comes back with its order and its keys`() {
    val stack = SaveableNavStack(HomeScreen).apply { push(KeyedScreen(id = 42)) }
    val stackSaver = SaveableNavStack.Saver(saver)
    val saved = assertNotNull(with(stackSaver) { SaverScope { true }.save(stack) })

    // The newest screen is first.
    assertEquals(listOf(KeyedScreen(id = 42), HomeScreen), stackSaver.restore(saved)?.map { it.screen })
}

// Control: restore the same saved value with a saver that does not list KeyedScreen -> null.
```

**Presenter state across recreation.** `Presenter.test(vararg locals)` accepts
`LocalRetainedStateRegistry provides registry`; call `registry.saveAll()` before the first block
ends and present again with the same registry (shown in `SKILL.md`). Two `test` blocks share
nothing unless they are given the same registry, which is what the control relies on.

## Process death by hand (Android)

A unit test does not put the saved state through a `Parcel`; a device does.

```bash
# 1. Start the way the launcher does. Starting by component name alone puts a second Activity
#    on top of the restored one later, and the result looks like "not restored".
adb shell am start -a android.intent.action.MAIN -c android.intent.category.LAUNCHER \
  -f 0x10200000 -n com.example.app/.MainActivity
# 2. Navigate two levels deep, change some state.
adb shell input keyevent KEYCODE_HOME          # the state is saved here
adb shell am kill com.example.app              # kills only a background process
adb shell pidof com.example.app                # must print nothing
# 3. Start again with the command from step 1.
```

Expect the same screen with its key, state held in `rememberRetained` reset, and system back
leading to the screen below. Read `adb logcat -b events` for `am_kill` and `wm_restart_activity`
to be sure the process really died and the Activity was restored rather than started fresh.

For recreation, rotate with `adb shell settings put system user_rotation 1` (auto-rotate off) and
look for `wm_on_destroy_called` followed by `wm_on_create_called` in the same log.
