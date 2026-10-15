# Permission catalog

Facts the agent needs while auditing or changing permissions. API levels are the platform
release that introduced the behaviour; most of it applies only once `targetSdk` reaches that
level. When unsure of a detail for a newer release, check the current platform behaviour-change
notes rather than guessing.

## Dangerous permissions commonly seen in apps

| Permission | Introduced / changed | Prefer instead | Notes |
|---|---|---|---|
| `CAMERA` | 23 | `TakePicture` / `CaptureVideo` intent | Declared-but-denied `CAMERA` makes `ACTION_IMAGE_CAPTURE` throw. In-app preview (CameraX) needs it. |
| `RECORD_AUDIO` | 23 | system recorder intent if a file is enough | Can be one-time (API 30+). |
| `ACCESS_COARSE_LOCATION` | 23; user choice API 31 | — | Request with fine on API 31+; the person may grant coarse only. |
| `ACCESS_FINE_LOCATION` | 23 | coarse | Requesting it alone is ignored when targeting 31+. |
| `ACCESS_BACKGROUND_LOCATION` | 29; separate request 30 | geofencing/WorkManager with foreground grant, or none | Only after foreground is granted; opens Settings on API 30+. Play declaration. |
| `READ_EXTERNAL_STORAGE` | until 32 | Photo Picker, SAF | Cap `maxSdkVersion="32"`. Ignored for media when targeting 33+. |
| `WRITE_EXTERNAL_STORAGE` | until 28 (29 with legacy flag) | MediaStore insert | Cap `maxSdkVersion="28"`. Grants nothing on 30+. |
| `READ_MEDIA_IMAGES` / `READ_MEDIA_VIDEO` | 33 | Photo Picker | Play restricts to apps whose core use is broad media access. Images and video share one dialog. |
| `READ_MEDIA_AUDIO` | 33 | SAF `OpenDocument("audio/*")` | Separate dialog. |
| `READ_MEDIA_VISUAL_USER_SELECTED` | 34 | Photo Picker | Declare with the media permissions to opt in to partial-access handling; without it the app runs in a compatibility mode with temporary grants. |
| `POST_NOTIFICATIONS` | 33 | — | See `push-notifications`. Below 33 notifications are on unless the person turned them off; check `NotificationManagerCompat.areNotificationsEnabled()`. |
| `BLUETOOTH_SCAN` / `BLUETOOTH_CONNECT` / `BLUETOOTH_ADVERTISE` | 31 ("Nearby devices") | Companion Device Manager pairing for one device | `neverForLocation` on SCAN when location is not derived. Legacy `BLUETOOTH`, `BLUETOOTH_ADMIN` and the location permission for scanning capped at `maxSdkVersion="30"`. |
| `NEARBY_WIFI_DEVICES` | 33 | — | `neverForLocation` when applicable; location capped at 32 for the same calls. |
| `READ_CONTACTS` | 23 | `PickContact` contract | The picker returns one contact URI with a temporary grant. |
| `READ_PHONE_STATE` | 23 | usually nothing | Often added by old libraries; strip with `tools:node="remove"` if unused. |
| `BODY_SENSORS` | 20/23 | — | Background reading needs a separate permission on recent releases. |
| `ACTIVITY_RECOGNITION` | 29 | — | Runtime on 29+. |

## Special and app-op permissions (no runtime dialog)

| Permission | How the person grants it | Check |
|---|---|---|
| `SCHEDULE_EXACT_ALARM` (31+) | `Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM` | `AlarmManager.canScheduleExactAlarms()` |
| `USE_EXACT_ALARM` (33+) | granted at install; Play allows only alarm/calendar apps | — |
| `SYSTEM_ALERT_WINDOW` | `Settings.ACTION_MANAGE_OVERLAY_PERMISSION` | `Settings.canDrawOverlays()` |
| `MANAGE_EXTERNAL_STORAGE` (30+) | `ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION` | `Environment.isExternalStorageManager()`; Play declaration, file managers/backup only |
| `REQUEST_INSTALL_PACKAGES` | `ACTION_MANAGE_UNKNOWN_APP_SOURCES` | `packageManager.canRequestPackageInstalls()` |
| `QUERY_ALL_PACKAGES` (30+) | install-time, Play-restricted | replace with `<queries>` |

```xml
<!-- RIGHT: declare only what you interact with -->
<queries>
    <package android:name="com.example.partner" />
    <intent>
        <action android:name="android.intent.action.VIEW" />
        <data android:scheme="https" />
    </intent>
</queries>
```

Opening a URL or sharing with `startActivity` needs no `<queries>`; it is for
`resolveActivity`/`queryIntentActivities`/`getPackageInfo` on other apps.

## Foreground service types (targetSdk 34+)

Each type needs `android:foregroundServiceType` on the `<service>`, `FOREGROUND_SERVICE`, and the
type permission below. Pass the same type(s) to `ServiceCompat.startForeground`.

| Type | Type permission | Also required at start |
|---|---|---|
| `camera` | `FOREGROUND_SERVICE_CAMERA` | `CAMERA` granted |
| `microphone` | `FOREGROUND_SERVICE_MICROPHONE` | `RECORD_AUDIO` granted |
| `location` | `FOREGROUND_SERVICE_LOCATION` | a location permission granted |
| `connectedDevice` | `FOREGROUND_SERVICE_CONNECTED_DEVICE` | a Bluetooth/USB/NFC/etc. prerequisite permission or state |
| `health` | `FOREGROUND_SERVICE_HEALTH` | a body-sensor/activity-recognition style prerequisite |
| `dataSync` | `FOREGROUND_SERVICE_DATA_SYNC` | — (runtime limit on newer releases; prefer WorkManager) |
| `mediaPlayback` | `FOREGROUND_SERVICE_MEDIA_PLAYBACK` | — |
| `mediaProjection` | `FOREGROUND_SERVICE_MEDIA_PROJECTION` | a `MediaProjection` consent obtained first |
| `phoneCall` | `FOREGROUND_SERVICE_PHONE_CALL` | default dialer or `MANAGE_OWN_CALLS` |
| `remoteMessaging` | `FOREGROUND_SERVICE_REMOTE_MESSAGING` | — |
| `shortService` | none | must finish quickly; timeout is enforced |
| `specialUse` | `FOREGROUND_SERVICE_SPECIAL_USE` | `<property android:name="android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE" android:value="…"/>` and a Play justification |
| `systemExempted` | `FOREGROUND_SERVICE_SYSTEM_EXEMPTED` | system/privileged apps only |

Newer releases add types (for example `mediaProcessing`) and time limits; check the current
platform notes when raising `targetSdk`.

```xml
<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_LOCATION" />
<service
    android:name=".tracking.AppTrackingService"
    android:exported="false"
    android:foregroundServiceType="location" />
```

## Grant lifetime

- One-time grants (camera, mic, location, API 30+) end shortly after the app leaves the
  foreground.
- Auto-reset (API 30+, backported to 23+ via Play services) revokes runtime permissions of apps
  unused for months.
- Revoking in Settings kills the app process; the next launch restores from saved state.
- Two refusals of the same permission (API 30+) suppress the dialog; launches return denied
  immediately.
