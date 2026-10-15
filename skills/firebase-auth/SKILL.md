---
name: firebase-auth
description: Firebase Authentication on Android (and behind a KMP interface) - Google sign-in through Credential Manager, email/password, auth state as a Flow, ID tokens for your own backend with refresh-once on 401, sign-out and account deletion order, SHA fingerprints and release builds, and a backend smoke test with a real token. Use when adding sign-in, debugging "no Google account" or 401 loops, or deleting accounts.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - Firebase Authentication
  - Credential Manager
  - Google sign-in
  - ID token
  - SHA fingerprint
  - account deletion
---

# Firebase Auth

## Common contract

```kotlin
data class AuthUser(val uid: String, val email: String?, val displayName: String?)

interface AuthClient {
    val authState: Flow<AuthUser?>
    suspend fun signInWithGoogle()
    suspend fun signInWithEmail(email: String, password: String)
    suspend fun idToken(forceRefresh: Boolean): String?
    suspend fun signOut()
}
```

Common code sees only this interface, session state and typed auth errors; Firebase types never
leave `androidMain`.

## Android implementation

```kotlin
object CurrentActivityHolder {                      // weak, set in onCreate, cleared in onDestroy only if === this
    private var ref: WeakReference<Activity>? = null
    var activity: Activity? get() = ref?.get(); set(v) { ref = v?.let(::WeakReference) }
}

class AndroidAuthClient(private val appContext: Context, private val webClientId: String) : AuthClient {
    private val auth get() = FirebaseAuth.getInstance()

    override val authState: Flow<AuthUser?> = callbackFlow {
        val listener = FirebaseAuth.AuthStateListener { trySend(it.currentUser?.toAuthUser()) }
        auth.addAuthStateListener(listener)
        awaitClose { auth.removeAuthStateListener(listener) }
    }

    override suspend fun signInWithGoogle() {
        val activity = CurrentActivityHolder.activity ?: throw AuthException("Sign-in is unavailable right now")
        val request = GetCredentialRequest.Builder()
            .addCredentialOption(GetGoogleIdOption.Builder().setServerClientId(webClientId).setFilterByAuthorizedAccounts(false).build())
            .build()
        val credential = try {
            CredentialManager.create(activity).getCredential(activity, request).credential
        } catch (e: GetCredentialCancellationException) { throw AuthException("Sign-in cancelled", e)
        } catch (e: NoCredentialException) { throw AuthException("No Google account on this device", e, recovery = AuthRecovery.AddGoogleAccount)
        } catch (e: GetCredentialException) { throw AuthException("Google sign-in failed", e) }
        val idToken = GoogleIdTokenCredential.createFrom(credential.data).idToken
        auth.signInWithCredential(GoogleAuthProvider.getCredential(idToken, null)).await()
    }

    override suspend fun idToken(forceRefresh: Boolean): String? =
        auth.currentUser?.let { runCatching { it.getIdToken(forceRefresh).await().token }.getOrNull() }
}
```

- Credential Manager needs an **Activity**: hold a weak reference, never inject an Activity into a
  singleton.
- `webClientId` is the generated `R.string.default_web_client_id`; read it once next to the
  `Application` and pass it in (adapters do not read `R`/`BuildConfig`).
- Dependencies: `androidx.credentials`, `credentials-play-services-auth`, `googleid`,
  `firebase-auth` (via BOM), `kotlinx-coroutines-play-services` for `await()`.

## Talking to your backend

- Send `Authorization: Bearer <Firebase ID token>` to **your API origin only** (see
  `ktor-api-client`).
- Ktor's bearer plugin retries a 401 once with `idToken(forceRefresh = true)`. A 401 that survives
  the refresh clears the session (sign out) instead of looping.
- Server: verify the ID token against the same Firebase project id. `checkRevoked = true` costs a
  round trip per request; it is only worth it if something revokes tokens (account deletion should
  call `revokeRefreshTokens(uid)` so other devices lose access).

## Account lifecycle

- Account deletion: erase server data → clear local account state → then sign out. A sign-out
  failure must not resurrect the deleted account in the UI. Guard in-flight fetches: a request that
  started before deletion and lands after it must be discarded, not displayed (and must not
  re-provision the account).
- Per-account local state (notices, drafts) is keyed by uid; per-device state (onboarding hints) is
  not.
- Versioned Terms: check the server's accepted version after sign-in (including restored sessions)
  and record agreement only on an explicit tap; installation is not consent.

## Release builds: fingerprints

Register SHA-1/SHA-256 of **every** signing key that installs the app in Firebase: debug, upload,
and Play App Signing's app-signing key. Missing the Play key gives "no Google account" only for
store installs (see `android-release-signing`).

## Backend smoke test with a real token

1. Prerequisites: Firebase project with Google and email/password providers; Android app registered
   with package id and SHA fingerprints; backend configured with the same project id and a service
   account file **outside the repo**.
2. Get a token for a pre-existing smoke account via the Identity Toolkit REST API
   (`accounts:signInWithPassword` with the web API key) into a local env var only.
3. Call health → a public endpoint → an authenticated endpoint without a token (expect a normalised
   401) → with the token (expect the current user) → the main business flow.
4. Classify the first failure before changing code: console/provider setup, backend credential,
   token expired/wrong project, user state gate (inactive/unverified), balance/product state,
   header issue, queue/worker, storage, runtime health.
5. Never commit tokens, service-account JSON, private keys or refresh tokens; scan the diff for
   `BEGIN PRIVATE KEY`, `refresh_token`, long token-shaped strings before committing.
