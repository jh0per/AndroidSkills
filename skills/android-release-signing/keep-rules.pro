# Starting keep rules for a Compose/KMP app using kotlinx.serialization, Ktor, Room and Firebase.
# Most libraries ship their own consumer rules (AndroidX, Compose, Kotlin, kotlinx, Room,
# Play services, Firebase, OkHttp, Coil). Do not add package-wide keeps for them; each one
# switches R8 off for that whole package. Check the merged config first
# (references/keep-rules-audit.md, -printconfiguration).
# Every rule below exists because something is looked up reflectively. Do not remove one without
# running the minified build on a device through the flow it protects.
# Replace com.example.app with your package and delete the sections you do not need.

# --- kotlinx.serialization -------------------------------------------------------------
# The runtime ships rules for the common case. Add these only when serializers are looked up
# reflectively across modules (serializer<T>() on classes from another module, named companions).
-keepattributes InnerClasses, Signature, RuntimeVisibleAnnotations, EnclosingMethod
-keep,includedescriptorclasses class com.example.app.model.**$$serializer { *; }
-keepclassmembers class com.example.app.model.** { *** Companion; }
-keepclasseswithmembers class com.example.app.model.** { kotlinx.serialization.KSerializer serializer(...); }

# --- Ktor -------------------------------------------------------------------------------
# Only needed when the engine is discovered via ServiceLoader, i.e. HttpClient() without an
# explicit engine. HttpClient(OkHttp) needs no rule.
-keep class * implements io.ktor.client.HttpClientEngineContainer { <init>(); }
-dontwarn org.slf4j.impl.StaticLoggerBinder

# --- Hand-written Parcelables (not @Parcelize) ------------------------------------------
-keepclassmembers class * implements android.os.Parcelable {
    public static final android.os.Parcelable$Creator CREATOR;
}

# --- Parcelable navigation keys (Circuit screens) -------------------------------------
# Parcel restores classes by name; keeping names is enough, members stay optimisable.
# -keepnames class com.example.app.**Screen

# --- Classes created by name in your own code -------------------------------------------
# Example: plugins instantiated with Class.forName(...).getDeclaredConstructor().newInstance().
# -keep class * implements com.example.app.Plugin { <init>(); }

# --- JNI --------------------------------------------------------------------------------
-keepclasseswithmembernames,includedescriptorclasses class * { native <methods>; }
