# Keep-rule audit

Every keep rule is a hole in R8's optimisation: what it keeps cannot be removed, renamed, inlined
or merged. The audit finds the holes that buy nothing and narrows the ones that are needed. It is
research first: produce the report, then change rules one at a time, each followed by a minified
run through the flow it protects.

## Step 1: configuration

| Check | Expect |
|---|---|
| Release (and benchmark) build type | `isMinifyEnabled = true`, `isShrinkResources = true` |
| Default file | `proguard-android-optimize.txt`, never `proguard-android.txt` |
| `gradle.properties` | no `android.enableR8.fullMode=false` (full mode is the default since AGP 8.0) |
| AGP 8.6 to 8.x | `android.r8.optimizedResourceShrinking=true` (default from AGP 9) |
| Library modules | keep rules in `consumerProguardFiles`, never global options there |

## Step 2: see the merged configuration

The app's `proguard-rules.pro` is a fraction of what R8 applies. Add to a **local-only** rules
file (never commit it):

```proguard
-printconfiguration build/outputs/r8/full-config.txt   # every rule, including library consumer rules
-printusage build/outputs/r8/removed.txt               # what R8 deleted
```

Then `./gradlew :app:assembleRelease` and read `full-config.txt` before judging any app rule:
a rule the library already ships is redundant, not "extra safety".

To learn why something survives, use `-whyareyoukeeping class com.example.app.Foo` and read the
chain R8 prints.

## Step 3: rank rules by blast radius (widest first)

1. Global switches: `-dontshrink`, `-dontoptimize`, `-dontobfuscate`. Remove; they disable R8 for
   the whole app. A library that ships them in consumer rules is a bug to report and override.
2. Negated patterns: `-keep class !com.example.app.Foo { *; }` keeps **everything else**.
3. Package wildcards with all members: `-keep class com.example.app.data.** { *; }`,
   `-keep class androidx.** { *; }`, `-keep class com.google.firebase.** { *; }`.
4. Whole class with all members: `-keep class com.example.app.Foo { *; }`.
5. `-keepclassmembers class Foo { *; }`.
6. `-keep,allowobfuscation` / `allowshrinking` on a whole class with `{ *; }`.
7. Specific members: `-keep class Foo { void bar(); }`.
8. Class name only: `-keep class Foo`.
9. Conditional: `-keepclassmembers class * { @com.example.app.Reflective <methods>; }`,
   `-keepclasseswithmembers class * { native <methods>; }`. Narrowest; the goal for every rule.

## Step 4: remove what is already covered

Delete, after confirming in `full-config.txt` that the library ships the rule:

- Manifest components and views: `-keep class * extends android.app.Activity` / `Service` /
  `View`, Fragment `onClick` handlers. AAPT2 generates these from the manifest and layouts.
- AndroidX, Kotlin, kotlinx (coroutines, serialization runtime), Compose: their AARs/JARs ship
  consumer rules.
- Google Play services and Firebase: consumer rules ship in each artifact. `com.google.**` package
  keeps are always too wide.
- Room: generated `_Impl` classes are kept by Room's own rules. Keep only entities you read by
  reflection yourself (you should not).
- Retrofit 2.9+, OkHttp 4+, Gson 2.11+, Moshi with codegen: bundled rules. Gson models need
  `@SerializedName` on every field instead of a package keep.
- Enum keeps (`-keepclassmembers enum * { *; }`): the optimize default already keeps `values()`
  and `valueOf`.
- `@Parcelize` classes: the plugin generates `CREATOR`; only hand-written Parcelables need a rule
  for `CREATOR`.

## Step 5: keep what reflection really needs, narrowly

| Code pattern | Rule shape |
|---|---|
| `Class.forName(name).getDeclaredConstructor().newInstance()` on an interface | `-keep class * implements com.example.app.Plugin { <init>(); }` |
| `ServiceLoader.load(X::class.java)` | `-keep class * implements X { <init>(); }` (check the library first) |
| Optional dependency probed with `Class.forName` | keep that one class and its constructor |
| `getDeclaredField("x")` / `getDeclaredMethod` | `-keepclassmembers class Foo { private java.lang.String x; }` |
| Custom annotation scanned at runtime | `-keepclassmembers class * { @com.example.app.Reflective *; }` |
| JNI called from native code | `-keepclasseswithmembers class * { native <methods>; }` plus the Kotlin methods native calls back |
| kotlinx.serialization with `serializer<T>()` on a class in another module, named companions, or polymorphic registration by reflection | the specific `Companion`/`$$serializer` rule for that package, not `com.example.app.**` |

Prefer an annotation the code already has (`@Keep` from `androidx.annotation`) on the one member
that is looked up by name over a rule file entry; it moves with the code.

## Step 6: prove each change

1. Change one rule.
2. Build the minified variant, install it, and walk the flow the rule protected (decode a real
   response, open persisted data, restore after process death, sign in, the purchase screen).
3. Compare APK/AAB size (`apkanalyzer apk file-size`, or the Play size report) and, for
   startup-sensitive changes, the Macrobenchmark numbers from `app-startup-performance`.
4. A crash with `ClassNotFoundException`, `NoSuchMethodException`, a serializer lookup failure or
   an empty field after decoding means the rule was needed: restore it **narrowed**, not as it was.

## Report format

```markdown
## Keep-rule audit: <module>, AGP <x>, <date>

Configuration: <ok | list of missing switches>
Size: <before> -> <after> (if changes were applied)

| # | Rule (file:line) | Radius | Finding | Action |
|---|---|---|---|---|
| 1 | -keep class com.google.firebase.** { *; } (proguard-rules.pro:41) | package, all members | shipped by the library | remove |
| 2 | -keep class com.example.app.data.db.** { *; } | package, all members | only `AppDatabase_Impl` needs it, already kept by Room | remove |
| 3 | -keep class com.example.app.plugins.** { *; } | package, all members | loaded via Class.forName | narrow to `-keep class * implements com.example.app.Plugin { <init>(); }` |

Verified flows on minified build: <list, or "not yet run">
```

Leave a section out when it has no entries; never report a rule as safe to remove without the
minified run.
