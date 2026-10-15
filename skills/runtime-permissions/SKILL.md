---
name: runtime-permissions
description: Request and minimise Android permissions in Compose apps - merged-manifest permission inventory, least-privilege replacements (Photo Picker, SAF, camera intents, coarse location, nearby-devices, <queries> not QUERY_ALL_PACKAGES, maxSdkVersion on legacy storage), RequestPermission/RequestMultiplePermissions launchers, rationale and permanently-denied to Settings, asking in context not at launch, POST_NOTIFICATIONS, partial media access (READ_MEDIA_VISUAL_USER_SELECTED), two-step background location, foreground service types and permissions, exact alarms, ViewModel-owned permission state re-checked on resume, tests (GrantPermissionRule, adb revoke), and an audit report. Use when adding or reviewing a uses-permission, a permission prompt, a foreground service or an alarm, or raising targetSdk. Do not use for exported components or signature permissions (see android-app-security), notification prompt timing (see push-notifications), or picker and MediaStore code (see media-storage).
metadata:
  last-updated: '2026-10-15'
  keywords:
  - runtime permissions
  - uses-permission
  - RequestPermission
  - RequestMultiplePermissions
  - shouldShowRequestPermissionRationale
  - POST_NOTIFICATIONS
  - READ_MEDIA_VISUAL_USER_SELECTED
  - background location
  - foregroundServiceType
  - SCHEDULE_EXACT_ALARM
  - QUERY_ALL_PACKAGES
  - GrantPermissionRule
  - least privilege
---

# Runtime permissions

Every permission is a liability: a dialog the person can refuse, a Play declaration, a review
finding. The rule: **declare the fewest permissions the shipped features need, ask for each one
at the moment the person triggers the feature, and keep the answer in a ViewModel that re-reads
the system on every resume.** Exported components and custom `signature` permissions belong to
`android-app-security`; notification channels and the moment to ask for notifications to
`push-notifications`; picker, camera and MediaStore code to `media-storage` (in-app camera preview: `camerax-capture`); FGS work design to
`long-running-jobs`. Permission name/API tables live in `references/permission-catalog.md`;
test recipes in `references/testing-permissions.md`.

## Prerequisites

- `androidx.activity:activity-compose` (1.10+ for `LocalActivity`),
  `androidx.lifecycle:lifecycle-runtime-compose` 2.7+ (`LifecycleResumeEffect`). Do **not** add
  Accompanist Permissions: it keeps state in the composable, which this skill forbids.
- Read `targetSdk` and `minSdk` first. Behaviour changes are keyed to `targetSdk` (33: notifications
  and granular media; 34: partial media and FGS types; 31: approximate location, Bluetooth,
  exact alarms), so the same code is right or wrong depending on it.
- Know the platform facts that break naive flows: the system stops showing a dialog after the
  second refusal; revoking a permission in Settings **kills the process**; unused apps get
  permissions auto-reset (API 30+); camera, mic and location can be "only this time".

## Step 1: inventory from the merged manifest

Libraries add permissions; the source manifest lies.

```bash
./gradlew :app:processReleaseMainManifest
grep -n "uses-permission" app/build/intermediates/merged_manifest/release/AndroidManifest.xml
# or on the built artifact (path depends on AGP): apkanalyzer manifest permissions app-release.apk
```

For each permission record: who adds it (app or library, see `manifest-merger-release-report.txt`),
protection (normal/dangerous/special/appop), the feature that uses it, where it is requested, and
whether a no-permission alternative exists (step 2). Then grep the code for
`checkSelfPermission`, `RequestPermission`, `startForeground`, `setExact`, `getInstalledPackages`.
A permission with no feature is removed; one added by a library you do not need is stripped:

```xml
<uses-permission android:name="android.permission.READ_PHONE_STATE" tools:node="remove" />
```

## Step 2: least privilege first

| Need | Use instead of a permission |
|---|---|
| Pick photos/videos | Photo Picker (`PickVisualMedia`); no `READ_MEDIA_*` (`media-storage`) |
| Open/save a document | SAF: `OpenDocument`, `CreateDocument`, `OpenDocumentTree` |
| Take one photo/video | `TakePicture`/`CaptureVideo` intent; no `CAMERA` (see trap below) |
| City-level location | `ACCESS_COARSE_LOCATION` only |
| Find/connect BLE devices | `BLUETOOTH_SCAN` with `neverForLocation` + `BLUETOOTH_CONNECT`; location only on API ≤ 30 |
| Talk to specific apps | `<queries>` with packages or intent filters; never `QUERY_ALL_PACKAGES` |
| Save to the gallery on API 29+ | MediaStore insert; `WRITE_EXTERNAL_STORAGE` with `maxSdkVersion="28"` |
| Read own files | app-specific storage; no storage permission at any API level |
| Reminders | inexact alarm or WorkManager; no exact-alarm permission |

```xml
<!-- RIGHT: legacy permissions capped so new devices never see them -->
<uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE" android:maxSdkVersion="32" />
<uses-permission android:name="android.permission.WRITE_EXTERNAL_STORAGE" android:maxSdkVersion="28" />
<uses-permission android:name="android.permission.BLUETOOTH" android:maxSdkVersion="30" />
<uses-permission android:name="android.permission.BLUETOOTH_SCAN" android:usesPermissionFlags="neverForLocation" />
```

- Camera-intent trap: if the manifest declares `CAMERA` and it is not granted, launching
  `ACTION_IMAGE_CAPTURE` throws `SecurityException`. Using the intent means removing `CAMERA`
  (including a library's copy) or requesting it anyway.
- `neverForLocation` is a promise: scan results lose location-derived beacons. Drop it only when
  the feature derives location, then request location too.
- A permission that Play restricts (`QUERY_ALL_PACKAGES`, `READ_MEDIA_IMAGES`/`VIDEO` for
  non-gallery apps, `USE_EXACT_ALARM`, `MANAGE_EXTERNAL_STORAGE`, background location) needs a
  declaration; that is `account-compliance` work, and usually a sign to pick the alternative.

## Step 3: state lives in the ViewModel

The ViewModel owns a status; the composable owns only the launcher (it needs an Activity) and
reports results back. `shouldShowRequestPermissionRationale` also needs the Activity, so the UI
passes it in with the result.

```kotlin
enum class PermissionStatus { Granted, NotAsked, Rationale, Blocked }

interface PermissionChecker { fun isGranted(permission: String): Boolean }   // app Context, Koin/Hilt

class ScanViewModel(private val checker: PermissionChecker) : ViewModel() {
    private val _camera = MutableStateFlow(initial())
    val camera: StateFlow<PermissionStatus> = _camera.asStateFlow()

    private fun initial() = if (checker.isGranted(CAMERA)) Granted else NotAsked

    fun onResume() {                                         // Settings, auto-reset, one-time grants
        _camera.update { if (checker.isGranted(CAMERA)) Granted else if (it == Granted) NotAsked else it }
    }

    fun onResult(granted: Boolean, showRationale: Boolean) {
        _camera.value = when {
            granted -> Granted
            showRationale -> Rationale                       // refused once: explain, offer again
            else -> Blocked                                  // no dialog will show: offer Settings
        }
    }
}
```

```kotlin
@Composable
fun ScanRoute(vm: ScanViewModel) {
    val status by vm.camera.collectAsStateWithLifecycle()
    val activity = LocalActivity.current ?: return
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        vm.onResult(granted, ActivityCompat.shouldShowRequestPermissionRationale(activity, CAMERA))
    }
    LifecycleResumeEffect(Unit) { vm.onResume(); onPauseOrDispose { } }
    ScanScreen(
        status = status,
        onRequest = { launcher.launch(CAMERA) },
        onOpenSettings = { activity.startActivity(appDetailsIntent(activity.packageName)) },
    )
}

fun appDetailsIntent(pkg: String) =
    Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", pkg, null))
```

```kotlin
// WRONG: state in the composable, asked on first composition, lost on rotation, never re-read.
@Composable fun ScanScreen() {
    var granted by remember { mutableStateOf(false) }
    val launcher = rememberLauncherForActivityResult(RequestPermission()) { granted = it }
    LaunchedEffect(Unit) { launcher.launch(CAMERA) }       // a prompt before the person did anything
}
```

```kotlin
// WRONG: rationale read BEFORE the first request is false, so this calls a never-asked user "blocked".
if (!shouldShowRequestPermissionRationale(CAMERA)) openSettings() else launcher.launch(CAMERA)
```

- Do not persist "asked before" flags: they drift from the system (reset, reinstall, Settings).
  A launch that returns `false` immediately, with no rationale, is how you learn it is `Blocked`.
- Do not cache "granted" across process death or use it as proof: call `checkSelfPermission` (via
  the checker) right before the protected API, and still catch `SecurityException` where the
  API throws.
- Process killed by a revoke: restore screen state from `SavedStateHandle`; the ViewModel then
  starts from `initial()`.

## Step 4: ask in context

- Ask when the person taps the feature that needs it ("Scan receipt"), never at launch, in
  onboarding carousels, or for features they may never use. The screen works (degraded) without
  it: `Rationale` shows a short in-place explanation with a retry; `Blocked` shows the reason and
  a Settings button. Never loop the request or block the whole app.
- Several permissions for one feature: one `RequestMultiplePermissions` launch; evaluate the
  `Map<String, Boolean>` per permission, because the person can grant a subset.
- Location: request `ACCESS_FINE_LOCATION` **together with** `ACCESS_COARSE_LOCATION` (API 31+
  ignores fine alone) and treat "coarse only" as success with lower accuracy.

```kotlin
// RIGHT
launcher.launch(arrayOf(ACCESS_FINE_LOCATION, ACCESS_COARSE_LOCATION))
// result: precise = map[FINE] == true; usable = precise || map[COARSE] == true
```

- `POST_NOTIFICATIONS` (API 33+): ask after the person starts something whose result arrives
  later; below 33 there is nothing to request. Timing and settings fallback: `push-notifications`.

## Step 5: special cases

**Partial media (API 34+).** Only gallery-like apps read the library; everyone else uses the
picker. If you must read it, request the visual permissions with `READ_MEDIA_VISUAL_USER_SELECTED`
in one launch and handle three outcomes: full (`READ_MEDIA_IMAGES` granted), partial (only
`…_USER_SELECTED` granted: show what you can access plus a "Select more photos" action that
re-launches the same request), none. Re-query MediaStore on every resume; the selection changes
outside the app.

**Background location (two steps).** Foreground first, in context. Only after it is granted and
the person turns on the background feature, explain "Allow all the time" (label from
`packageManager.backgroundPermissionOptionLabel`) and launch `ACCESS_BACKGROUND_LOCATION` on its
own. On API 30+ that opens a Settings page, not a dialog.

```kotlin
// WRONG: on API 30+ the whole request is ignored.
launcher.launch(arrayOf(ACCESS_FINE_LOCATION, ACCESS_COARSE_LOCATION, ACCESS_BACKGROUND_LOCATION))
```

**Foreground service types (targetSdk 34+).** Every `<service>` started in the foreground
declares `android:foregroundServiceType`, the matching `FOREGROUND_SERVICE_<TYPE>` permission
(plus `FOREGROUND_SERVICE`), and passes the type to `ServiceCompat.startForeground`. Types such
as `camera`, `microphone`, `location` also need the runtime permission **granted before** the
call, or it throws `SecurityException`; start them from a visible screen. Type table and
`specialUse` property: `references/permission-catalog.md`. Prefer WorkManager (`long-running-jobs`)
before adding a service at all.

```kotlin
// RIGHT
ServiceCompat.startForeground(this, NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION)
```

**Exact alarms.** Inexact (`setAndAllowWhileIdle`, `setWindow`) or WorkManager first.
`SCHEDULE_EXACT_ALARM` (API 31+) is user-revocable and not granted by default to new installs
on recent Android versions: check `alarmManager.canScheduleExactAlarms()` before every `setExact*`,
send the person to `ACTION_REQUEST_SCHEDULE_EXACT_ALARM` in context, and reschedule on
`ACTION_SCHEDULE_EXACT_ALARM_PERMISSION_STATE_CHANGED`. `USE_EXACT_ALARM` is for alarm-clock and
calendar apps only (Play policy).

## Scope guards

- Normal permissions (`INTERNET`, `VIBRATE`, `ACCESS_NETWORK_STATE`) are granted at install: no
  request, no status, no rationale; the inventory still lists them.
- KMP: the status enum and ViewModel live in `commonMain`; the launcher and checker are
  `androidMain` (iOS has its own authorization APIs behind the same seam).
- Activity/Fragment-only screens use `registerForActivityResult` the same way; the ViewModel
  rules are identical.

## Verification (fail first)

Prove each flow fails without the fix (`verification-discipline`), then passes:

1. Inventory diff: re-run step 1 and compare the permission list before/after; removed
   permissions are gone from the merged manifest, not only the source.
2. On a device, per permission: never asked → grant; deny once → rationale; deny twice →
   Blocked → Settings → grant → back to the app shows Granted without restart. Then revoke in
   Settings while the app is backgrounded and confirm it recovers (process death).
3. Instrumented tests: `GrantPermissionRule` for granted paths; denial paths run without the
   grant and drive the system dialog; reset with `adb shell pm revoke` and
   `pm clear-permission-flags … user-set user-fixed`. Recipes: `references/testing-permissions.md`.
4. Unit-test the ViewModel with a fake `PermissionChecker`: every `onResult`/`onResume`
   transition, including Granted → revoked → NotAsked.
5. Lint at `error` for `MissingPermission` and the location, storage and package-visibility
   checks your lint version offers.

## Report format (audit mode)

```markdown
## Permission inventory
| Permission | Source (app/lib) | Level | Feature | Requested where | Alternative | Verdict |
## Findings
| # | Severity | file:line / manifest | Issue | Fix |
## Verified fine
- <permission>: <why it is needed and asked in context>
## Not checked
- <area>: <reason>
```

Verdict: **keep**, **cap** (`maxSdkVersion`), **replace** (alternative) or **remove**. Severity:
**High** = crash or feature dead (FGS without type/permission, missing `canScheduleExactAlarms`,
camera intent with undeclared grant); **Medium** = over-privilege or Play-restricted permission
with an alternative, prompt at launch, no Blocked path; **Low** = rationale copy, missing cap.

## Checklist

- [ ] Inventory taken from the merged manifest; every permission maps to a shipped feature.
- [ ] Pickers, SAF, camera intents, coarse location, nearby-devices and `<queries>` used where
      they suffice; legacy storage/Bluetooth permissions capped with `maxSdkVersion`.
- [ ] No request at launch; each request follows a user action on the screen that needs it.
- [ ] Status owned by a ViewModel, re-read on resume; no persisted "asked" flags.
- [ ] Rationale and Blocked → Settings paths exist; the feature degrades instead of blocking.
- [ ] Fine location requested with coarse; background location in a separate, later step.
- [ ] Every FGS declares its type and `FOREGROUND_SERVICE_<TYPE>`; runtime grant checked first.
- [ ] `canScheduleExactAlarms()` before every exact alarm, or alarms are inexact.
- [ ] Grant, deny, blocked and revoke-while-backgrounded verified; tests cover the ViewModel.
