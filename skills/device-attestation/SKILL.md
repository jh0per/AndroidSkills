---
name: device-attestation
description: Play Integrity (Standard API) device attestation behind a KMP-friendly seam - preparing the token provider once, binding the request hash to the account, distinguishing permanent unavailability from transient failure, unknown error codes treated as transient, server-side verdict decisions, and wording outcomes without exposing codes. Use when gating free grants, promotions, sign-up or sensitive actions on device integrity.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - Play Integrity
  - attestation
  - device integrity
  - fraud prevention
  - request hash
---

# Device attestation (Play Integrity)

## Result type: three outcomes, not two

```kotlin
sealed interface AttestationResult {
    data class Token(val value: String) : AttestationResult
    data object Unavailable : AttestationResult      // permanent on this install: the person is owed an explanation
    data object Failed : AttestationResult           // transient: stay quiet, retry later
}
interface PlatformAttestation { suspend fun token(requestHashInput: String): AttestationResult }
```

A `String?` cannot tell "no Play services on this device" from "the network dropped", and those
must produce opposite UI.

## Android adapter

```kotlin
class AndroidAttestation(private val context: Context, private val cloudProjectNumber: Long) : PlatformAttestation {
    private val lock = Mutex()
    private var provider: StandardIntegrityManager.StandardIntegrityTokenProvider? = null

    override suspend fun token(requestHashInput: String): AttestationResult {
        if (cloudProjectNumber <= 0) return AttestationResult.Unavailable          // not configured for this build
        return try {
            val p = lock.withLock { provider ?: prepare().also { provider = it } }  // preparation is rate-limited: once
            val token = p.request(
                StandardIntegrityManager.StandardIntegrityTokenRequest.builder().setRequestHash(sha256Base64Url(requestHashInput)).build(),
            ).await().token()
            AttestationResult.Token(token)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            lock.withLock { provider = null }                                     // providers expire; re-prepare next time
            classify(e)
        }
    }

    private suspend fun prepare() = IntegrityManagerFactory.createStandard(context)
        .prepareIntegrityToken(PrepareIntegrityTokenRequest.builder().setCloudProjectNumber(cloudProjectNumber).build()).await()

    private fun classify(e: Throwable): AttestationResult {
        val code = generateSequence(e) { it.cause }.filterIsInstance<StandardIntegrityException>().firstOrNull()?.errorCode
            ?: return AttestationResult.Failed
        return if (code in PERMANENT) AttestationResult.Unavailable else AttestationResult.Failed   // unknown codes: transient
    }

    private companion object {
        val PERMANENT = setOf(
            StandardIntegrityErrorCode.API_NOT_AVAILABLE, StandardIntegrityErrorCode.PLAY_STORE_NOT_FOUND,
            StandardIntegrityErrorCode.PLAY_SERVICES_NOT_FOUND, StandardIntegrityErrorCode.APP_NOT_INSTALLED,
            StandardIntegrityErrorCode.APP_UID_MISMATCH, StandardIntegrityErrorCode.CLOUD_PROJECT_NUMBER_IS_INVALID,
            StandardIntegrityErrorCode.PLAY_STORE_VERSION_OUTDATED, StandardIntegrityErrorCode.PLAY_SERVICES_VERSION_OUTDATED,
            StandardIntegrityErrorCode.REQUEST_HASH_TOO_LONG,
        )
    }
}

fun sha256Base64Url(input: String): String =
    Base64.encodeToString(MessageDigest.getInstance("SHA-256").digest(input.toByteArray()), Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP)
```

- **Bind the request hash** to the account id (and the action) so a token cannot be replayed for
  another account.
- The cloud project number is a build-time value handed to the adapter (it is public; read it from
  the committed Firebase config if that is where it lives). A silent default of 0 means "never
  attested" on every build: make the unconfigured state visible in logs/tests.
- iOS/no-Play builds: an implementation that answers `Unavailable` (or App Attest via a Swift bridge).

## Using it

```kotlin
class GrantClaimer(private val attestation: PlatformAttestation, private val api: GrantApi, private val session: SessionStore) {
    private val attempted = mutableSetOf<String>()
    suspend fun claimFor(uid: String): GrantStatus {
        if (!attempted.add(uid)) return GrantStatus.NotApplicable
        val result = when (val a = attestation.token(requestHashInput = "grant:$uid")) {
            is AttestationResult.Token -> api.claim(a.value)
            AttestationResult.Unavailable -> api.claimWithoutAttestation()        // server decides; usually refuses
            AttestationResult.Failed -> { attempted.remove(uid); return GrantStatus.Unresolved }   // retry next launch
        }
        if (session.currentUid() != uid) return GrantStatus.NotApplicable          // session moved on: ignore
        return result.toStatus()                                                   // unknown server outcome → NotApplicable (silence)
    }
}
```

- The **server** decrypts and evaluates the verdict (device, app, account licensing) and decides;
  the client never interprets verdicts.
- Wording: say what happened and what the person can do ("this device can't receive the free
  credits"), never error codes or the attestation vendor's name; another platform will produce
  different causes with the same effect and reuse the strings.
- Persist a dismissal of the explanation per account; keep it findable in settings/profile.

## Tests

- Classification table: each permanent code → Unavailable, unknown code → Failed, no integrity
  exception → Failed, cancellation rethrown.
- Provider reset after failure; preparation happens once under concurrency.
- Request hash is URL-safe base64 without padding and differs per account.
- Instrumented on a real device with Play services for the happy path.
