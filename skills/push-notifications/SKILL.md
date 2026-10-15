---
name: push-notifications
description: Push notifications on Android (and behind a KMP seam) - FCM data versus notification messages, posting notifications yourself on channels created at startup, POST_NOTIFICATIONS permission timing and settings fallback, token registration tied to sign-in transitions, routing a tap to a destination for cold/warm/foreground starts, and tests. Use when adding FCM, notification channels, permission prompts, or notification deep links.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - FCM
  - Firebase Cloud Messaging
  - notification channels
  - POST_NOTIFICATIONS
  - token registration
  - deep link
---

# Push notifications

## Seams

```kotlin
interface PushMessaging {                          // Koin; reports, never prompts
    suspend fun registrationToken(): String?       // null is a normal answer (no Play services, not ready)
}

interface NotificationPermission {                 // CompositionLocal: asking needs an Activity launcher
    @Composable fun rememberRequest(): () -> Unit
    @Composable fun rememberEnabled(): State<Boolean>   // re-read on every ON_RESUME
    @Composable fun rememberOpenSettings(): () -> Unit  // ACTION_APP_NOTIFICATION_SETTINGS, app details below O
}
```

- A no-op implementation answers `enabled = true` so the UI never shows a warning that has no fix.
- Start "enabled" as true and flip only on a real "no", so a "notifications are off" card does not
  flash while the answer loads.

## Permission timing (Android 13+)

Ask for `POST_NOTIFICATIONS` when the reason is obvious (the person started something that will
finish in the background), never at launch. Android stops showing the dialog after two refusals;
from then on, offer a settings shortcut with an explanation.

## Channels

```kotlin
object NotificationChannels {
    const val RESULTS = "results"
    fun ensure(context: Context) {
        if (Build.VERSION.SDK_INT < 26) return
        context.getSystemService<NotificationManager>()?.createNotificationChannel(
            NotificationChannel(RESULTS, context.getString(R.string.channel_results), NotificationManager.IMPORTANCE_DEFAULT)
                .apply { description = context.getString(R.string.channel_results_description) },
        )
    }
}
// Application.onCreate: NotificationChannels.ensure(this) BEFORE DI/startup that may post.
```

```xml
<meta-data android:name="com.google.firebase.messaging.default_notification_channel_id"
           android:value="results" />
```

- Channel names/descriptions are Android `res` strings (the system Settings app renders them).
- Importance DEFAULT unless the content is genuinely urgent; a channel's importance cannot be
  raised by the app after creation.
- Test: the manifest channel id equals the code constant; channels are created before anything posts.

## Message types

- A message with a `notification` block is displayed by the system when the app is in background
  and `onMessageReceived` is **not** called. Use **data-only** messages (`priority: high`) when the
  app must decide what to show, deduplicate, or route.
- Post the notification yourself with a stable notification id per subject (e.g. job id) so updates
  replace instead of stacking.

```kotlin
class AppMessagingService : FirebaseMessagingService() {
    override fun onMessageReceived(message: RemoteMessage) {
        val jobId = message.data["jobId"] ?: return
        val tap = PendingIntent.getActivity(
            this, jobId.hashCode(),
            Intent(this, MainActivity::class.java).setAction(Intent.ACTION_VIEW).setData("app://result/$jobId".toUri())
                .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val notification = NotificationCompat.Builder(this, NotificationChannels.RESULTS)
            .setSmallIcon(R.drawable.ic_notification).setContentTitle(getString(R.string.result_ready))
            .setContentIntent(tap).setAutoCancel(true).build()
        if (NotificationManagerCompat.from(this).areNotificationsEnabled()) {
            NotificationManagerCompat.from(this).notify(jobId.hashCode(), notification)
        }
    }
    override fun onNewToken(token: String) { /* hand to the registrar via the app scope */ }
}
```

## Routing a tap

The destination must work for a cold start (`onCreate` intent), warm start (`onNewIntent`) and
foreground (show in-app, e.g. a banner, instead of only a system notification):

- Parse the URI into a typed route; keep it **pending** until the app is ready (signed in, start
  destination resolved), then navigate once. Preserve it across a sign-in screen.
- Persist the pending job id if the result must survive process death.
- "Not yours" and "not found" are indistinguishable to the client (one message).
- Make the route idempotent so repeated taps do not stack duplicate screens.

## Token registration

```kotlin
class PushTokenRegistrar(session: SessionStore, private val push: PushMessaging, private val api: PushTokenApi, appScope: CoroutineScope) {
    private var registered: String? = null
    private var signedInUid: String? = null
    init {
        appScope.launch {
            session.state.map { (it as? SessionState.SignedIn)?.uid }.distinctUntilChanged().collect { uid ->
                when {
                    uid != null -> register()
                    signedInUid != null -> forget()        // only on the transition to signed-out, never at cold start
                }
                signedInUid = uid
            }
        }
    }
    suspend fun register() {
        val token = push.registrationToken() ?: return
        if (token == registered) return
        if (api.register(token, platform = "ANDROID") is ApiResult.Success) registered = token
    }
    private suspend fun forget() {
        val token = registered ?: push.registrationToken() ?: return
        api.forget(token); registered = null
    }
}
```

- Send an explicit `platform` (ANDROID/IOS) so the server routes APNs and FCM tokens correctly.
- Registration failures are silent and retried on the next sign-in/token refresh; they never block UI.
- Delete the token server-side on sign-out and account deletion.

## Long jobs

For "your result is ready" flows, combine push with a polling fallback while the screen is open
(see `long-running-jobs`); push alone is not delivered reliably (Doze, restricted apps, no Play
services).

## Tests

- Registrar: sign-in registers once, token unchanged is not re-sent, sign-out after sign-in forgets,
  cold start signed-out does nothing.
- Route parser: valid, malformed and foreign URIs.
- Instrumented: tapping a posted notification opens the destination from a killed process.
