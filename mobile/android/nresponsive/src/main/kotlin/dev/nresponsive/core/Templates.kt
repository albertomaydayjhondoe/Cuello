package dev.nresponsive.core

/**
 * Plantillas de pantalla. Espejo de `TEMPLATES` en
 * `core/nresponsive/generator.py`.
 *
 * Las posiciones se declaran como fracciones del canvas para que la misma
 * plantilla sirva en retrato, en apaisado y en cualquier tamano de panel.
 */
object Templates {

    data class Spec(
        val id: String,
        val type: ElementType,
        val fx: Float? = null,
        val fy: Float? = null,
        val fw: Float? = null,
        val fh: Float? = null,
        val priority: Float = 0.5f,
        val critical: Boolean = false,
        val minW: Float = 48f,
        val minH: Float = 48f,
        val scrollable: Boolean = false,
        val text: String? = null,
    )

    val MEDIA_PLAYER = listOf(
        Spec("header", ElementType.TEXT, 0.04f, 0.03f, 0.92f, 0.06f, 0.6f, text = "Now playing"),
        Spec("cover", ElementType.IMAGE, 0.10f, 0.11f, 0.80f, 0.42f, 0.9f),
        Spec("progress", ElementType.CONTAINER, 0.10f, 0.56f, 0.80f, 0.03f, 0.7f),
        Spec("play", ElementType.BUTTON, 0.40f, 0.62f, 0.20f, 0.08f, 1.0f,
            critical = true, minW = 56f, minH = 48f, text = "Play"),
        Spec("prev", ElementType.BUTTON, 0.16f, 0.62f, 0.14f, 0.08f, 0.8f,
            critical = true),
        Spec("next", ElementType.BUTTON, 0.70f, 0.62f, 0.14f, 0.08f, 0.8f,
            critical = true),
        Spec("related", ElementType.LIST, 0.04f, 0.72f, 0.92f, 0.16f, 0.5f, scrollable = true),
        // Los anclajes no llevan fracciones: los coloca el motor.
        Spec("nav", ElementType.NAV, priority = 1.0f, critical = true, minW = 48f, minH = 56f),
        Spec("fab", ElementType.FAB, priority = 1.0f, critical = true, minW = 56f, minH = 56f),
    )

    val DASHBOARD = listOf(
        Spec("title", ElementType.TEXT, 0.04f, 0.03f, 0.60f, 0.05f, 0.7f, text = "Dashboard"),
        Spec("kpi1", ElementType.CONTAINER, 0.04f, 0.10f, 0.44f, 0.14f, 0.8f),
        Spec("kpi2", ElementType.CONTAINER, 0.52f, 0.10f, 0.44f, 0.14f, 0.8f),
        Spec("chart", ElementType.IMAGE, 0.04f, 0.26f, 0.92f, 0.34f, 0.9f),
        Spec("search", ElementType.INPUT, 0.04f, 0.62f, 0.92f, 0.06f, 0.6f,
            critical = true, minW = 120f),
        Spec("list", ElementType.LIST, 0.04f, 0.70f, 0.92f, 0.18f, 0.5f, scrollable = true),
        Spec("nav", ElementType.NAV, priority = 1.0f, critical = true, minW = 48f, minH = 56f),
    )

    val ALL: Map<String, List<Spec>> = mapOf(
        "media_player" to MEDIA_PLAYER,
        "dashboard" to DASHBOARD,
    )

    const val DEFAULT = "media_player"

    /** Instancia la plantilla en un canvas concreto. */
    fun elements(name: String, canvas: Canvas): List<LayoutElement> {
        val spec = ALL[name] ?: error("plantilla desconocida: $name")
        return spec.map { s ->
            val b = if (s.fx != null) {
                Bounds(
                    s.fx * canvas.width, s.fy!! * canvas.height,
                    s.fw!! * canvas.width, s.fh!! * canvas.height,
                )
            } else {
                // Los anclajes reciben un tamano minimo; el motor los situa.
                Bounds(0f, 0f, s.minW, s.minH)
            }
            LayoutElement(
                id = s.id, type = s.type, bounds = b,
                critical = s.critical, priority = s.priority,
                minSize = IntSize(s.minW, s.minH),
                designSize = IntSize(b.w, b.h),
                scrollable = s.scrollable, text = s.text,
            )
        }
    }
}