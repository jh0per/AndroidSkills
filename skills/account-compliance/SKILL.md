---
name: account-compliance
description: Account and policy features an Android app needs for Google Play and privacy law - in-app account deletion with the right ordering and a guard against re-provisioning, versioned Terms acceptance that only an explicit tap records, legal links from a configured site origin, user content reporting for apps with generated content, ads/advertising-ID declarations, and data-safety consistency. Use when implementing sign-up/sign-out/deletion, Terms prompts, legal pages, reporting, or preparing a Play policy review.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - Google Play policy
  - account deletion
  - Terms of Service
  - content reporting
  - data safety
  - advertising ID
---

# Account and policy compliance

## Account deletion (required when accounts can be created)

Order matters:

1. Delete on the server (and revoke refresh tokens so other devices lose access).
2. Clear local account state: per-account caches, DB rows, prefs keyed by the account, push token
   registration.
3. Sign out of the identity provider.

```kotlin
class UserRepository(private val api: UserApi, private val session: SessionStore) {
    @Volatile private var deletedPendingSignOut = false

    suspend fun deleteAccount(): ApiResult<Unit> = api.deleteMe().onSuccess {
        deletedPendingSignOut = true                  // released only by OBSERVING signed-out, not by a cache reset
        clearLocalAccountState()
        runCatching { session.signOut() }             // a failure here must not resurrect the account
    }

    suspend fun currentUser(): ApiResult<User> =
        if (deletedPendingSignOut && session.isSignedIn()) ApiResult.Failure(ApiError.AccountDeleted)
        else api.me()                                 // otherwise a still-valid token would auto-provision a NEW account
}
```

- Discard results of requests that were in flight when the account was deleted (check an epoch or
  the uid when the response lands).
- Provide a web URL for deletion as well (Play requires one reachable without the app).

## Versioned Terms

- The server holds `{ currentVersion, acceptedVersion }` per account. Installing the app, or a local
  flag, never counts as assent.
- After sign-in (including restored sessions) check the status; if not accepted, show the Terms
  dialog. Only an explicit **Agree** posts `{ version, accepted: true, accountId }`, capturing the
  version and account that were **displayed**, so a stale tap cannot accept newer Terms.
- Cancel keeps local, account-free browsing usable.
- Re-check right before an action that requires agreement (e.g. a paid job), reusing the same dialog
  if the version changed meanwhile.
- One app-scoped controller above navigation owns this flow; serialize its state changes, invalidate
  in-flight requests when the account changes, retry reads only (never replay a POST).

## Legal links

Build privacy policy, terms and deletion links from a **configured site origin** (build-time value)
plus fixed paths, optionally with the Terms version. Staging builds then link to staging wording.
Never hard-code production URLs in UI code.

## Reporting generated or user content

Apps that generate content with AI or host user content must let people report it in-app:

```kotlin
enum class ReportReason(val wireName: String) { Offensive("OFFENSIVE"), Sexual("SEXUAL"), Violence("VIOLENCE"), Other("OTHER") }

suspend fun report(contentId: String, reason: ReportReason, details: String?) =
    safeApiCall<Unit>(session) {
        client.post("/v1/reports") { setBody(ReportDto(contentId, reason.wireName, details?.trim()?.ifBlank { null })) }
    }
```

- Wire names match the backend enum exactly (anything else is a 400); labels are localized resources.
- The server enforces ownership and rate limits.

## Ads and identifiers

- If the app shows no ads: remove `AD_ID` and ad-services permissions merged by SDKs, set analytics
  ad-ID collection/personalisation flags off, guard the **merged** manifest in CI
  (`gradle-quality-gate`), and declare "no advertising ID" in Play Console.
- If it shows ads: consent (UMP) before loading ads, no ads before purchases resolve for "remove
  ads" buyers (`play-billing`).

## Data safety and permissions

- Keep a short internal table of every data type collected, by which SDK, why, and whether it is
  shared; update it with each SDK addition. Play's Data safety form and the privacy policy must match.
- Request runtime permissions at the moment of use with a reason; prefer permission-less APIs
  (photo picker, MediaStore writes on API 29+).
- Minimum SDK changes driven by store policy are platform-support changes: note them in release notes.

## Tests

- Deletion: server success → local cleared, sign-out failure does not restore the user, a late
  `me()` response after deletion is ignored.
- Terms: agree posts the displayed version; stale version rejected; cancel keeps browsing.
- Reporting: each reason serializes to its wire name; blank details become null.
