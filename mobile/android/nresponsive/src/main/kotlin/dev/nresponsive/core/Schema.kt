package dev.nresponsive.core

import kotlinx.serialization.Serializable
import kotlinx.serialization.SerialName
import kotlinx.serialization.json.Json

/**
 * Schema del layout "nresponsive". Es el gemelo Kotlin de
 * `core/nresponsive/schema.py`; ambos deben evolucionar juntos.
 *
 * Las coordenadas estan en dp y son relativas al canvas.
 */
@Serializable
data class Bounds(
    val x: Float,
    val y: Float,
    val w: Float,
    val h: Float,
) {
    val right: Float get() = x + w
    val bottom: Float get() = y + h
    val area: Float get() = (w.coerceAtLeast(0f)) * (h.coerceAtLeast(0f))
    val centerX: Float get() = x + w / 2f
    val centerY: Float get() = y + h / 2f

    fun intersection(other: Bounds): Float {
        val ix = (minOf(right, other.right) - maxOf(x, other.x)).coerceAtLeast(0f)
        val iy = (minOf(bottom, other.bottom) - maxOf(y, other.y)).coerceAtLeast(0f)
        return ix * iy
    }
}

@Serializable
data class IntSize(val w: Float, val h: Float)

@Serializable
enum class Orientation {
    @SerialName("portrait") PORTRAIT,
    @SerialName("landscape") LANDSCAPE,
}

@Serializable
enum class Quadrant {
    @SerialName("top_left") TOP_LEFT,
    @SerialName("top_right") TOP_RIGHT,
    @SerialName("bottom_left") BOTTOM_LEFT,
    @SerialName("bottom_right") BOTTOM_RIGHT,
}

@Serializable
enum class ElementType {
    @SerialName("button") BUTTON,
    @SerialName("text") TEXT,
    @SerialName("image") IMAGE,
    @SerialName("input") INPUT,
    @SerialName("nav") NAV,
    @SerialName("container") CONTAINER,
    @SerialName("list") LIST,
    @SerialName("fab") FAB,
}

@Serializable
data class Canvas(
    val width: Float,
    val height: Float,
    val unit: String = "dp",
    val density: Float = 1f,
) {
    val orientation: Orientation
        get() = if (width > height) Orientation.LANDSCAPE else Orientation.PORTRAIT

    fun rotated(): Canvas = Canvas(width = height, height = width, unit = unit, density = density)
}

@Serializable
data class LayoutElement(
    val id: String,
    val type: ElementType,
    val bounds: Bounds,
    val quadrant: Quadrant? = null,
    val critical: Boolean = false,
    val priority: Float = 0.5f,
    @SerialName("min_size") val minSize: IntSize = IntSize(48f, 48f),
    @SerialName("design_size") val designSize: IntSize? = null,
    val scrollable: Boolean = false,
    val text: String? = null,
    val z: Int = 0,
) {
    val intrinsicSize: IntSize get() = designSize ?: IntSize(bounds.w, bounds.h)
}

@Serializable
enum class Easing {
    @SerialName("Linear") LINEAR,
    @SerialName("FastOutSlowIn") FAST_OUT_SLOW_IN,
    @SerialName("EaseInOut") EASE_IN_OUT,
    @SerialName("EaseOut") EASE_OUT,
}

@Serializable
data class Transition(
    @SerialName("element_id") val elementId: String,
    val from: Bounds,
    val to: Bounds,
    @SerialName("duration_ms") val durationMs: Int,
    @SerialName("delay_ms") val delayMs: Int = 0,
    val easing: Easing = Easing.FAST_OUT_SLOW_IN,
    val kind: String = "move",
)

@Serializable
data class AnimationPlan(
    val strategy: String = "rolling",
    @SerialName("budget_ms") val budgetMs: Int = 300,
    @SerialName("total_duration_ms") val totalDurationMs: Int = 0,
)

@Serializable
data class Layout(
    @SerialName("schema_version") val schemaVersion: String = "nresponsive/1.0",
    @SerialName("layout_id") val layoutId: String = "layout",
    val canvas: Canvas,
    val elements: List<LayoutElement>,
    @SerialName("quadrant_map") val quadrantMap: Map<String, List<String>> = emptyMap(),
    val metrics: Map<String, kotlinx.serialization.json.JsonElement> = emptyMap(),
    val animation: AnimationPlan = AnimationPlan(),
    val transitions: List<Transition> = emptyList(),
    @SerialName("generated_by") val generatedBy: Map<String, kotlinx.serialization.json.JsonElement> = emptyMap(),
)

val NresponsiveJson: Json = Json {
    ignoreUnknownKeys = true
    encodeDefaults = true
    prettyPrint = false
}