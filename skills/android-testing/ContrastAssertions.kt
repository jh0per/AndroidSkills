package com.example.app.test

import android.graphics.Bitmap
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.SemanticsNodeInteraction
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.performScrollTo
import org.junit.Assert.assertTrue
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow

/**
 * WCAG contrast assertions for instrumented screenshot tests.
 *
 * A band of pixels is assumed to hold text on a flat background: the most frequent colour is the
 * background and the colour furthest from it in luminance is the ink. This catches text drawn in a
 * default colour that disappears on one theme. It cannot tell whether the right colour was chosen,
 * only that the text is readable. Do not use it on photographs or artwork.
 */
private fun channel(v: Int): Double = (v / 255.0).let { if (it <= 0.03928) it / 12.92 else ((it + 0.055) / 1.055).pow(2.4) }

fun luminance(argb: Int): Double =
    0.2126 * channel((argb shr 16) and 0xFF) + 0.7152 * channel((argb shr 8) and 0xFF) + 0.0722 * channel(argb and 0xFF)

fun contrastRatio(foreground: Int, background: Int): Double {
    val a = luminance(foreground)
    val b = luminance(background)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)
}

fun assertReadableBand(
    bitmap: Bitmap,
    topFraction: Double,
    bottomFraction: Double,
    minimumRatio: Double = 3.0,
    label: String,
) {
    val top = (bitmap.height * topFraction).toInt().coerceIn(0, bitmap.height - 1)
    val bottom = (bitmap.height * bottomFraction).toInt().coerceIn(top + 1, bitmap.height)
    val counts = HashMap<Int, Int>()
    for (y in top until bottom) {
        for (x in 0 until bitmap.width) {
            val pixel = bitmap.getPixel(x, y) or (0xFF shl 24)
            counts[pixel] = (counts[pixel] ?: 0) + 1
        }
    }
    val background = counts.maxByOrNull { it.value }!!.key
    val ink = counts.keys.maxByOrNull { abs(luminance(it) - luminance(background)) }!!
    val ratio = contrastRatio(ink, background)
    assertTrue(
        "$label: text contrast is ${"%.2f".format(ratio)}:1, below $minimumRatio:1 " +
            "(ink #${Integer.toHexString(ink)}, background #${Integer.toHexString(background)})",
        ratio >= minimumRatio,
    )
}

fun assertReadableNode(node: SemanticsNodeInteraction, minimumRatio: Double = 3.0, label: String) {
    runCatching { node.performScrollTo() }
    assertReadableBand(node.captureToImage().asAndroidBitmap(), 0.0, 1.0, minimumRatio, label)
}
