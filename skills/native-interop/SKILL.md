---
name: native-interop
description: Native code in Android apps - JNI with C/C++ through CMake, Rust through cargo-ndk or the rust-android-gradle plugin, JNI naming versus RegisterNatives, marshalling strings and arrays, calling back into Kotlin, ABI filters, loading libraries safely, debug symbol upload, and 16 KB page-size alignment. Use when adding or debugging a .so, a JNI bridge, or a Rust/C++ library.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - JNI
  - NDK
  - CMake
  - Rust
  - cargo-ndk
  - ABI filters
  - 16 KB page size
  - native symbols
---

# Native interop (JNI, C++, Rust)

## Kotlin side

```kotlin
object AudioDsp {
    private val loaded: Boolean = runCatching { System.loadLibrary("audiodsp"); true }.getOrElse { false }

    fun spectrum(samples: FloatArray, bins: Int): FloatArray? = if (loaded) nativeSpectrum(samples, bins) else null

    @JvmStatic private external fun nativeSpectrum(samples: FloatArray, bins: Int): FloatArray
    @JvmStatic external fun runWithCallback(callback: NativeCallback)
}

fun interface NativeCallback { fun onResult(message: String) }
```

- Load once, in one object; catch `UnsatisfiedLinkError` and degrade instead of crashing.
- Keep JNI surfaces small and coarse: one call per operation, primitive arrays in/out.
- Add keep rules for classes and methods native code calls by name:
  `-keep class com.example.app.NativeCallback { *; }` and `-keepclasseswithmembernames class * { native <methods>; }`.

## C/C++ with CMake

```kotlin
android {
    defaultConfig {
        ndk { abiFilters += listOf("arm64-v8a", "x86_64") }    // add armeabi-v7a only if you still ship 32-bit
        externalNativeBuild { cmake { cppFlags += "-std=c++20" } }
    }
    externalNativeBuild { cmake { path = file("src/main/cpp/CMakeLists.txt") } }
    ndkVersion = "<pinned>"
}
```

```cpp
extern "C" JNIEXPORT jfloatArray JNICALL
Java_com_example_app_AudioDsp_nativeSpectrum(JNIEnv* env, jclass, jfloatArray samples, jint bins) {
    jsize n = env->GetArrayLength(samples);
    jfloat* in = env->GetFloatArrayElements(samples, nullptr);
    std::vector<float> out = spectrum(in, n, bins);
    env->ReleaseFloatArrayElements(samples, in, JNI_ABORT);   // always release; JNI_ABORT = no copy back
    jfloatArray result = env->NewFloatArray(static_cast<jsize>(out.size()));
    env->SetFloatArrayRegion(result, 0, static_cast<jsize>(out.size()), out.data());
    return result;
}
```

- Prefer `RegisterNatives` in `JNI_OnLoad` for larger surfaces: it survives package renames and
  R8 class renaming better than `Java_pkg_Class_method` names.
- Never cache `JNIEnv*` across threads; attach native threads with `AttachCurrentThread`. Cache
  `jclass` as a global ref and `jmethodID`s once in `JNI_OnLoad`.
- Check for pending exceptions after calling back into Java (`ExceptionCheck`).
- Link only what you use (`-ljnigraphics` for `AndroidBitmap_*`, `-llog`).

## Rust

Option A, `cargo-ndk` driven from Gradle (recommended, simple):

```bash
rustup target add aarch64-linux-android x86_64-linux-android
cargo install cargo-ndk
cargo ndk -t arm64-v8a -t x86_64 -o app/src/main/jniLibs build --release
```

Wire it as a Gradle `Exec` task that `preBuild` depends on, with inputs/outputs declared so it is
cached. Option B, the `rust-android-gradle` plugin (`cargo { module = "../core"; libname = "core";
targets = listOf("arm64", "x86_64") }`).

```rust
// Cargo.toml: [lib] crate-type = ["cdylib"]; [profile.release] lto = true, strip = true
use jni::objects::{JClass, JObject, JValue};
use jni::JNIEnv;

#[no_mangle]
pub extern "system" fn Java_com_example_app_AudioDsp_runWithCallback(mut env: JNIEnv, _class: JClass, callback: JObject) {
    let message = env.new_string("hello from rust").expect("string");
    env.call_method(&callback, "onResult", "(Ljava/lang/String;)V", &[JValue::Object(&message)])
        .expect("callback");
}
```

- Use the `jni` crate's safe wrappers; map Rust errors to a thrown Java exception
  (`env.throw_new("java/lang/IllegalStateException", msg)`) rather than panicking across FFI. Wrap
  entry points in `std::panic::catch_unwind`.
- Async Rust (tokio) runs on its own runtime thread; callbacks into Kotlin must attach that thread.

## Release

- `buildTypes.release.ndk.debugSymbolLevel = "SYMBOL_TABLE"` (or `FULL`) so Play and crash tools can
  symbolicate native crashes; upload native symbols for Crashlytics if used.
- Since Play's 16 KB page-size requirement, build with NDK r28+ (or pass
  `-Wl,-z,max-page-size=16384`) and check alignment with `zipalign -c -P 16 -v 4 app.apk`; the
  Android Studio APK analyser flags unaligned `.so` files.
- Keep `.so` files uncompressed and page-aligned (`packaging { jniLibs { useLegacyPackaging = false } }`).
- Verify each shipped ABI actually contains the library: `unzip -l app.apk | grep '\.so'`.

## Tests

- Unit-test the native library in its own language (C++ gtest / `cargo test`) on the host.
- Instrumented test calls each JNI entry point once per ABI you ship, including the callback path,
  on an emulator (x86_64) and a device (arm64).
