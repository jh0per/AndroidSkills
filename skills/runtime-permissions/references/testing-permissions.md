# Testing permission flows

## ViewModel (JVM, fast, first)

```kotlin
class FakePermissionChecker(var granted: Set<String> = emptySet()) : PermissionChecker {
    override fun isGranted(permission: String) = permission in granted
}

@Test fun deniedTwiceBecomesBlocked_thenSettingsGrantIsPickedUpOnResume() {
    val checker = FakePermissionChecker()
    val vm = ScanViewModel(checker)
    vm.onResult(granted = false, showRationale = true)
    assertEquals(PermissionStatus.Rationale, vm.camera.value)
    vm.onResult(granted = false, showRationale = false)
    assertEquals(PermissionStatus.Blocked, vm.camera.value)
    checker.granted = setOf(Manifest.permission.CAMERA)   // person granted it in Settings
    vm.onResume()
    assertEquals(PermissionStatus.Granted, vm.camera.value)
}
```

Cover: initial Granted/NotAsked, Rationale, Blocked, resume after Settings grant, revoke while
Granted → NotAsked. The UI mapping (`status` → which card/button) is a plain composable test.

## Instrumented: granted path

```kotlin
@get:Rule val permissions: GrantPermissionRule = GrantPermissionRule.grant(Manifest.permission.CAMERA)
```

- `androidx.test:rules`. The grant applies before the test and persists for the package until
  revoked or the app is reinstalled/cleared, so order-dependent suites need a reset (below).
- Grant only permissions valid on the device's API level: build the array conditionally
  (`POST_NOTIFICATIONS` only on 33+), otherwise the rule fails.
- There is no rule to revoke: revoking kills the app process, which is also the instrumentation
  process.

## Instrumented: denied and blocked paths

1. Start from a clean state outside the test process (CI step or Orchestrator with
   `clearPackageData`):

```bash
adb shell pm revoke com.example.app android.permission.CAMERA
adb shell pm clear-permission-flags com.example.app android.permission.CAMERA user-set user-fixed
```

   Clearing `user-set`/`user-fixed` removes the "don't ask again" state so the dialog shows.
2. Tap the in-app request button, then answer the system dialog with UiAutomator. Resource ids
   of the permission controller (`com.android.permissioncontroller:id/permission_deny_button`,
   `…/permission_allow_button`, `…/permission_allow_foreground_only_button`) vary by release and
   OEM; wrap them in one helper with a text fallback and fail loudly when neither matches.
3. Assert the screen shows the rationale after the first denial and the Settings action after the
   second.

## Revoke while backgrounded (manual or scripted)

```bash
adb shell am start -n com.example.app/.MainActivity
adb shell input keyevent KEYCODE_HOME
adb shell pm revoke com.example.app android.permission.CAMERA   # process is killed
adb shell am start -n com.example.app/.MainActivity              # or return via Recents
```

Expect: no crash, screen restored from saved state, status NotAsked, request button visible.
Repeat with a grant made in Settings while backgrounded: the screen shows Granted on return.

## Special permissions

```bash
adb shell appops set com.example.app SCHEDULE_EXACT_ALARM deny    # canScheduleExactAlarms() == false
adb shell appops set com.example.app SCHEDULE_EXACT_ALARM default
adb shell dumpsys package com.example.app | grep -A3 "runtime permissions"   # current grants
```

Foreground service types: start each service on an API 34+ emulator with the runtime permission
revoked and confirm the app handles the `SecurityException` path (does not start, tells the
person) instead of crashing.
