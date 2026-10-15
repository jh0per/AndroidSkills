---
name: play-billing
description: Integrate Google Play Billing (one-time products and subscriptions) in a Compose or KMP app with server-side verification - connection lifecycle, product queries, launching the flow, pending purchases, restoring owned purchases on reconnect, entitlement caching, ads gating, Play Console setup and diagnosing purchase failures. Use when adding or debugging in-app purchases or subscriptions.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - Play Billing
  - in-app purchases
  - subscriptions
  - server verification
  - offers
  - upgrade
  - ads gating
---

# Google Play Billing

## Principles

- **The backend verifies, grants and acknowledges/consumes.** The client never consumes first: a
  consume before the server has granted loses the purchase if the grant fails.
- Redemption must be **idempotent** on the server, because the client re-submits owned purchases
  on every reconnect to recover interrupted redemptions.
- Route subscriptions and one-time products to **different** server endpoints; sending a
  subscription to a consumable endpoint would consume it.
- Without a backend (simple "remove ads" apps): acknowledge on the client within 3 days, cache the
  entitlement locally, and re-derive it from `queryPurchasesAsync` on start.
- One code path: no test/sandbox branch in the app. Testing uses Play Console License testers.

## Common contract (KMP)

```kotlin
enum class ProductKind { ONE_TIME, SUBSCRIPTION }
data class StorePurchase(val productId: String, val token: String, val kind: ProductKind)

interface PurchaseFlow { val available: Boolean; fun buy(productId: String, kind: ProductKind, accountId: String) }
interface PlatformBillingSupport {
    @Composable fun rememberPurchaseFlow(onPurchased: (StorePurchase) -> Unit, onFailed: (String) -> Unit): PurchaseFlow
}
val LocalPlatformBillingSupport = staticCompositionLocalOf<PlatformBillingSupport> { error("billing not provided") }
```

## Android adapter

```kotlin
@Composable
override fun rememberPurchaseFlow(onPurchased: (StorePurchase) -> Unit, onFailed: (String) -> Unit): PurchaseFlow {
    val context = LocalContext.current
    val currentOnPurchased by rememberUpdatedState(onPurchased)
    val currentOnFailed by rememberUpdatedState(onFailed)
    var connected by remember { mutableStateOf(false) }
    val details = remember { mutableMapOf<String, ProductDetails>() }

    val client = remember(context) {
        BillingClient.newBuilder(context)
            .enableAutoServiceReconnection()
            .enablePendingPurchases(PendingPurchasesParams.newBuilder().enableOneTimeProducts().build())
            .setListener { result, purchases -> handle(result, purchases, details, currentOnPurchased, currentOnFailed) }
            .build()
    }
    DisposableEffect(client) {
        client.startConnection(object : BillingClientStateListener {
            override fun onBillingSetupFinished(r: BillingResult) {
                connected = r.responseCode == BillingResponseCode.OK
                if (!connected) return
                // Re-emit owned purchases: the server redeems idempotently, recovering interrupted grants.
                client.restoreOwned(ProductKind.ONE_TIME, currentOnPurchased)
                client.restoreOwned(ProductKind.SUBSCRIPTION, currentOnPurchased)
            }
            override fun onBillingServiceDisconnected() { connected = false }
        })
        onDispose { client.endConnection() }
    }
    return remember(client) {
        object : PurchaseFlow {
            override val available get() = connected
            override fun buy(productId: String, kind: ProductKind, accountId: String) {
                val activity = context.findActivity() ?: return currentOnFailed("The store cannot open from here.")
                if (!connected) return currentOnFailed("Google Play is not available on this device.")
                details[productId]?.let { return launch(client, activity, it, accountId, currentOnFailed) }
                client.queryProductDetailsAsync(
                    QueryProductDetailsParams.newBuilder().setProductList(listOf(
                        QueryProductDetailsParams.Product.newBuilder().setProductId(productId).setProductType(kind.playType()).build(),
                    )).build(),
                ) { r, result ->
                    val found = result.productDetailsList.firstOrNull()
                    if (r.responseCode != BillingResponseCode.OK || found == null) return@queryProductDetailsAsync currentOnFailed("This item is not available right now.")
                    details[productId] = found
                    launch(client, activity, found, accountId, currentOnFailed)
                }
            }
        }
    }
}

private fun launch(client: BillingClient, activity: Activity, product: ProductDetails, accountId: String, onFailed: (String) -> Unit) {
    val offerToken = product.subscriptionOfferDetails?.firstOrNull()?.offerToken
        ?: product.oneTimePurchaseOfferDetailsList?.firstOrNull()?.offerToken   // revisit when you add multiple offers
    val params = BillingFlowParams.newBuilder()
        .apply { if (accountId.isNotEmpty()) setObfuscatedAccountId(accountId) }   // ties the purchase to your account id (hash it)
        .setProductDetailsParamsList(listOf(
            BillingFlowParams.ProductDetailsParams.newBuilder().setProductDetails(product)
                .apply { offerToken?.let { setOfferToken(it) } }.build(),
        )).build()
    if (client.launchBillingFlow(activity, params).responseCode != BillingResponseCode.OK) onFailed("Google Play could not open the purchase.")
}

private fun emit(p: Purchase, kind: ProductKind, onPurchased: (StorePurchase) -> Unit) {
    if (p.purchaseState != Purchase.PurchaseState.PURCHASED) return     // skip PENDING; it arrives again when settled
    p.products.forEach { onPurchased(StorePurchase(it, p.purchaseToken, kind)) }
}

private fun Context.findActivity(): Activity? {
    var c: Context? = this
    while (c is ContextWrapper) { if (c is Activity) return c; c = c.baseContext }
    return null
}
```

Handle response codes explicitly: `USER_CANCELED` is silent, `ITEM_ALREADY_OWNED` means "restore",
everything else gets a human sentence (never a raw code).

For a ViewModel-based app, wrap the same client in a `BillingClientProvider` singleton exposing
`StateFlow<List<Purchase>>` and `StateFlow<Entitlement>`.

## Ads gating

If the app shows ads and sells their removal: **do not load ads until purchases have resolved**
(`canShowAds = purchasesResolved && !hasRemoveAds`). Showing an ad for a second to a paying user
is a refund request.

## Play Console setup

- Create products only after a build declaring `com.android.vending.BILLING` (the billing library
  adds it) has been uploaded to a track.
- **License testing** (Setup → License testing) is the only list whose accounts get test
  purchases, on any track including production. Internal/closed testers otherwise pay real money.
  It is Console-only configuration; review it before each release and before inviting testers.
- The product list can come from your backend (filtered to the Play provider and active), so
  prices and availability change without an app release.

## Diagnosing a failed purchase

Read **every** field the store returned before theorising about your own code. Log product id,
type, title, formatted price, offer token presence. A product title ending in `(unreviewed)` means
the app has not passed review: Play will not sell it to anyone, tester or not, and the query still
"succeeds". A null field that the product type can never have (subscription offers on a one-time
product) proves nothing.

## Tests

- Unit-test routing (`ProductKind` → endpoint), entitlement derivation and the "ads after
  resolve" rule with fakes.
- Server: verify tokens with the Play Developer API, refuse to boot production with a fake
  verifier, and make grant + acknowledge/consume one idempotent operation keyed by token.

## Production hardening

**Recovery by stage.** Track which step failed and retry only that step with backoff:

```kotlin
enum class BillingStage { CONNECTION, QUERY_PURCHASES, QUERY_PRODUCTS, PURCHASE_UPDATED }

private suspend fun recover(stage: BillingStage) {
    delay(backoffMs); backoffMs = (backoffMs * 2).coerceAtMost(15 * 60_000L)   // state outside flow operators
    when (stage) {
        BillingStage.CONNECTION, BillingStage.PURCHASE_UPDATED -> connect()
        BillingStage.QUERY_PURCHASES -> queryPurchases()
        BillingStage.QUERY_PRODUCTS -> queryProducts()
    }
}
// reset backoffMs on success; DEVELOPER_ERROR and USER_CANCELED never trigger recovery
```

**Typed failures** (`ConnectionFailed`, `FetchPurchasesFailed`, `FetchProductsFailed`,
`PurchaseUpdateFailed`, `ItemAlreadyOwned`, `NoAccountId`) are recorded as non-fatals with the
response code, and mapped to sentences in one place.

**Shared Google accounts.** One Google account can be used by several app accounts. Set an
obfuscated account id (a **one-way hash** of your user id, ≤ 64 chars, no PII; base64 is reversible
and not acceptable) and:

- filter `queryPurchases` results to purchases whose `accountIdentifiers.obfuscatedAccountId` matches
  the signed-in user;
- if the Google account already owns a subscription under another app account, explain that instead
  of launching a purchase that will fail.

**Offers.** Pick offers by tags and phases: trial (a phase with `priceAmountMicros == 0`) → intro
discount → base plan; show the regular price from the most expensive recurring phase; parse trial
length with `Period.parse`. Exclude limited offers by tag unless the campaign is active.

**Upgrades/downgrades.** `SubscriptionUpdateParams.setOldPurchaseToken(old)` with
`setSubscriptionReplacementMode(...)` (Billing 6+; `ProrationMode` is deprecated). Choose the mode
per product rules (e.g. `CHARGE_FULL_PRICE` for upgrades, `DEFERRED` for downgrades).

**Throttle refreshes.** Refresh entitlements on app start/foreground with a throttle, and force a
refresh after a purchase update. Do not re-query product details on every purchase update.

**Analytics.** Record the context of a purchase attempt (source screen, trial or not) when launching
the flow and attach it when the purchase is confirmed; log a non-fatal if the context is missing.
