---
name: image-filters-gpu
description: Image filters and GPU image processing on Android - migrating RenderScript kernels to AGSL RuntimeShader, the RenderScript Intrinsics Replacement Toolkit, Vulkan compute or OpenGL ES, API-gated paths with fallback, bitmap and GPU resource lifecycle, LUT/colour-cube pipelines shared with other platforms, and verifying filters by pixels. Use when adding or porting an image filter, removing RenderScript, or debugging a shader that "looks right" but renders wrong.
metadata:
  last-updated: '2026-10-15'
  keywords:
  - AGSL
  - RuntimeShader
  - RenderScript migration
  - Vulkan
  - OpenGL ES
  - LUT
  - image filters
---

# GPU image filters

## Choosing a backend

| Need | Use |
|---|---|
| Per-pixel colour ops in Compose/Views, API 33+ | **AGSL** `RuntimeShader` via `RenderEffect` or `ShaderBrush` |
| Blur, convolve, colour matrix, blend, resize on any API | RenderScript **Intrinsics Replacement Toolkit** (C++/NEON, drop-in) |
| Heavy multi-pass compute, video frames | Vulkan compute (API 29+ realistically) or GLES 3.1 compute |
| Older devices / existing GL pipeline | OpenGL ES 2/3 with an offscreen framebuffer |
| Export at full resolution | an offscreen pass; never screenshot the on-screen preview |

RenderScript is deprecated since API 31; do not add new `.rs` kernels. Treat existing kernels
(vignette, HSL, levels, LUT, blend modes, convolution) as math to port; their shared headers (clamp,
HSL, LUT helpers) port directly to AGSL/GLSL functions.

## AGSL example

```kotlin
private const val SATURATION = """
    uniform shader image;
    uniform float amount;            // 0 = grey, 1 = unchanged
    half4 main(float2 xy) {
        half4 c = image.eval(xy);
        half l = dot(c.rgb, half3(0.2126, 0.7152, 0.0722));
        return half4(mix(half3(l), c.rgb, half(amount)), c.a);
    }
"""

@RequiresApi(33)
fun Modifier.saturation(amount: Float): Modifier = graphicsLayer {
    val shader = RuntimeShader(SATURATION).apply { setFloatUniform("amount", amount) }
    renderEffect = RenderEffect.createRuntimeShaderEffect(shader, "image").asComposeRenderEffect()
}
```

Offscreen/export on API 33+: draw into a `HardwareRenderer` + `ImageReader`, or a `Canvas` backed by
a hardware bitmap with a `RuntimeShader` paint.

## API-gated path with fallback

```kotlin
class FilterRunner(private val context: Context) {
    private val gpuAvailable = Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q && runCatching {
        System.loadLibrary("gpufilters"); true
    }.getOrDefault(false)

    suspend fun apply(input: Bitmap, params: FilterParams): Bitmap = withContext(Dispatchers.Default) {
        if (gpuAvailable) {
            repeat(MAX_GPU_ATTEMPTS) {
                runCatching { return@withContext gpuFilter(input, params) }
                    .onFailure { Log.w(TAG, "gpu filter failed, retrying", it) }
            }
        }
        cpuFilter(input, params)                 // Toolkit/CPU path; same parameters, same output contract
    }
}
```

- Load native libraries once, behind the API gate, and catch `UnsatisfiedLinkError`.
- Never run per-pixel Kotlin loops on the main thread; use `Dispatchers.Default`, and prefer
  `IntArray` bulk `getPixels`/`setPixels` over per-pixel `getPixel`.
- Release everything you allocate (`Allocation.destroy()`, GL textures/FBOs/programs, Vulkan
  buffers) in `finally`; reuse output bitmaps between frames for previews.
- Respect bitmap config: hardware bitmaps cannot be read on the CPU; copy to `ARGB_8888` first.
- Premultiplied alpha: un-premultiply before colour maths on translucent pixels, re-premultiply after.

## OpenGL ES helper

```kotlin
fun compileShader(type: Int, source: String): Int {
    val shader = GLES20.glCreateShader(type)
    GLES20.glShaderSource(shader, source)
    GLES20.glCompileShader(shader)
    val status = IntArray(1)
    GLES20.glGetShaderiv(shader, GLES20.GL_COMPILE_STATUS, status, 0)
    if (status[0] == 0) {
        val log = GLES20.glGetShaderInfoLog(shader)
        GLES20.glDeleteShader(shader)
        error("Shader compile failed: $log")
    }
    return shader
}

fun linkProgram(vertex: String, fragment: String): Int {
    val program = GLES20.glCreateProgram()
    GLES20.glAttachShader(program, compileShader(GLES20.GL_VERTEX_SHADER, vertex))
    GLES20.glAttachShader(program, compileShader(GLES20.GL_FRAGMENT_SHADER, fragment))
    GLES20.glLinkProgram(program)
    val status = IntArray(1)
    GLES20.glGetProgramiv(program, GLES20.GL_LINK_STATUS, status, 0)
    check(status[0] != 0) { "Link failed: ${GLES20.glGetProgramInfoLog(program)}" }
    return program
}
```

Keep shader sources in `res/raw` or assets; render on a `GLSurfaceView`/`TextureView` thread with a
dedicated drawing loop; never touch GL from another thread.

## Filters shared across platforms

When the same look must match on a server, web and Android:

- Compile per-pixel operations into a **3D colour cube (LUT)** with one shared implementation
  per runtime, and apply spatial effects (vignette, grain) as separate passes.
- Gate the port with byte equality of the compiled cube across implementations (hash per case),
  and **say what that does not cover**: the spatial passes need their own pixel comparison.
- Use one rounding rule and one hash/random function for grain on every platform; integer
  conversions are where ports diverge.

## Verify by rendering

A shader is not verified by reading it or by compiling it.

- Render fixtures and compare pixels against the reference with a tolerance chosen between the
  passing and the deliberately broken case (e.g. ≤1/255 when grain is involved).
- When unsure what a uniform holds, write it into an output channel and read it back. Size uniforms
  can report a **padded** texture (rounded to a power of two) instead of the output frame; geometry
  that is a fraction of the frame then scales wrong while per-pixel ops look fine.
- GLSL ES 3 features need `#version 300 es` as the very first line; some frameworks silently pick a
  compatibility dialect without it.
- Check both colour and geometry: a mask comparison cannot see a missing colour treatment.
