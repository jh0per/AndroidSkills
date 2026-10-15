# Starting keep rules for a Compose/KMP app using kotlinx.serialization, Ktor, Room and Firebase.
# Delete the sections for libraries you do not use.
# Every rule exists because R8 removes or renames something that is looked up reflectively.
# Do not remove one without running the minified build on a device through the flow it protects.
# Replace com.example.app with your package.

# --- kotlinx.serialization -------------------------------------------------------------
-keepattributes *Annotation*, InnerClasses, Signature, RuntimeVisible*Annotations, EnclosingMethod
-dontnote kotlinx.serialization.**
-keep,includedescriptorclasses class com.example.app.**$$serializer { *; }
-keepclassmembers class com.example.app.** { *** Companion; }
-keepclasseswithmembers class com.example.app.** { kotlinx.serialization.KSerializer serializer(...); }
# DTO field names are the wire format.
-keepclassmembers @kotlinx.serialization.Serializable class com.example.app.** { <fields>; }

# --- Ktor + OkHttp ----------------------------------------------------------------------
-dontwarn org.slf4j.**
-dontwarn io.ktor.**
-keep class io.ktor.client.engine.okhttp.** { *; }
# Engines are loaded through ServiceLoader (META-INF/services).
-keep class io.ktor.client.HttpClientEngineContainer
-keep class * implements io.ktor.client.HttpClientEngineContainer

# --- Room -------------------------------------------------------------------------------
# Generated *_Impl classes are instantiated by name.
-keep class com.example.app.data.db.** { *; }
-keep class * extends androidx.room.RoomDatabase { <init>(); }
-dontwarn androidx.room.paging.**

# --- Parcelable navigation keys (only if screens/keys are Parcelable, e.g. Circuit) ------------
-keep class * implements android.os.Parcelable { public static final ** CREATOR; }
-keep class com.example.app.**Screen { *; }
-keep class com.example.app.**Screen$* { *; }

# --- Coil 3 -----------------------------------------------------------------------------
-dontwarn coil3.**
-keep class coil3.network.ktor3.** { *; }

# --- Google Play services / Firebase / Credential Manager --------------------------------
-keep class com.google.android.gms.** { *; }
-dontwarn com.google.android.gms.**
-keep class com.google.firebase.** { *; }
-dontwarn com.google.firebase.**

# --- Kotlin -----------------------------------------------------------------------------
-dontwarn kotlinx.coroutines.**
-keepclassmembers class kotlin.Metadata { public <methods>; }
