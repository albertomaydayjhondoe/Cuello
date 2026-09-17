package dev.nresponsive.core

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sqrt

/**
 * Motor de rolling: reasigna cuadrantes y planifica la animacion.
 *
 * Es la implementacion Kotlin equivalente a `core/nresponsive/rolling.py`.
 * Se mantiene como modulo JVM puro para poder testearlo sin emulador ni
 * dispositivo; la capa Compose solo consume el [Layout] resultante.
 *
 * El motor es puro: no muta la lista de entrada ni mantiene estado entre
 * llamadas. Internamente trabaja sobre copias mutables ([Working]) y devuelve
 * siempre objetos inmutables.
 */
object RollingEngine {

    const val NAV_BAR_THICKNESS = 64f
    const val FAB_SIZE = 56f
    const val RAIL_WIDTH = 76f
    const val DEFAULT_GUTTER = 8f
    const val DEFAULT_BUDGET_MS = 300

    // Margen para que el total planificado quede estrictamente por debajo del
    // presupuesto. El criterio de aceptacion es "< 300 ms" y la animacion real
    // anade unos milisegundos de reloj sobre el plan.
    const val TRANSITION_SAFETY_MS = 20

    val READING_ORDER = listOf(
        Quadrant.TOP_LEFT, Quadrant.TOP_RIGHT,
        Quadrant.BOTTOM_LEFT, Quadrant.BOTTOM_RIGHT,
    )

    /**
     * Reasignacion de cuadrantes al girar. El sentido se fija por la
     * orientacion destino, de modo que portrait -> landscape -> portrait es la
     * identidad exacta.
     */
    fun rotateQuadrant(q: Quadrant, clockwise: Boolean): Quadrant = when {
        clockwise -> when (q) {
            Quadrant.TOP_LEFT -> Quadrant.TOP_RIGHT
            Quadrant.TOP_RIGHT -> Quadrant.BOTTOM_RIGHT
            Quadrant.BOTTOM_RIGHT -> Quadrant.BOTTOM_LEFT
            Quadrant.BOTTOM_LEFT -> Quadrant.TOP_LEFT
        }
        else -> when (q) {
            Quadrant.TOP_RIGHT -> Quadrant.TOP_LEFT
            Quadrant.BOTTOM_RIGHT -> Quadrant.TOP_RIGHT
            Quadrant.BOTTOM_LEFT -> Quadrant.BOTTOM_RIGHT
            Quadrant.TOP_LEFT -> Quadrant.BOTTOM_LEFT
        }
    }

    fun quadrantOf(bounds: Bounds, canvas: Canvas): Quadrant {
        val left = bounds.centerX < canvas.width / 2f
        val top = bounds.centerY < canvas.height / 2f
        return when {
            top && left -> Quadrant.TOP_LEFT
            top -> Quadrant.TOP_RIGHT
            left -> Quadrant.BOTTOM_LEFT
            else -> Quadrant.BOTTOM_RIGHT
        }
    }

    /**
     * Posiciones reservadas para navegacion y accion principal. Reservarlas
     * antes de empaquetar es lo que garantiza que sigan visibles al girar.
     */
    fun anchorSlots(elements: List<LayoutElement>, canvas: Canvas,
                    gutter: Float = DEFAULT_GUTTER): Map<String, Bounds> {
        val slots = mutableMapOf<String, Bounds>()
        val navs = elements.filter { it.type == ElementType.NAV }
        val fabs = elements.filter { it.type == ElementType.FAB }
        val portrait = canvas.orientation == Orientation.PORTRAIT

        if (navs.isNotEmpty()) {
            val n = navs.size
            if (portrait) {
                val top = canvas.height - NAV_BAR_THICKNESS
                val slotW = (canvas.width - gutter * (n + 1)) / n
                navs.forEachIndexed { i, e ->
                    slots[e.id] = Bounds(
                        gutter + i * (slotW + gutter), top + gutter / 2f,
                        max(slotW, e.minSize.w),
                        max(NAV_BAR_THICKNESS - gutter, e.minSize.h),
                    )
                }
            } else {
                // En apaisado la navegacion pasa a ser un rail lateral.
                val slotH = (canvas.height - gutter * (n + 1)) / n
                navs.forEachIndexed { i, e ->
                    slots[e.id] = Bounds(
                        gutter / 2f, gutter + i * (slotH + gutter),
                        max(RAIL_WIDTH - gutter, e.minSize.w),
                        max(slotH, e.minSize.h),
                    )
                }
            }
        }

        fabs.forEach { e ->
            val size = maxOf(FAB_SIZE, e.minSize.w, e.minSize.h)
            val margin = gutter + 8f
            val y = if (navs.isNotEmpty() && portrait) {
                canvas.height - NAV_BAR_THICKNESS - size - margin
            } else {
                canvas.height - size - margin
            }
            slots[e.id] = Bounds(max(0f, canvas.width - size - margin), max(0f, y), size, size)
        }
        return slots
    }

    private fun contentBounds(canvas: Canvas): Bounds =
        if (canvas.orientation == Orientation.PORTRAIT) {
            Bounds(0f, 0f, canvas.width, max(0f, canvas.height - NAV_BAR_THICKNESS))
        } else {
            Bounds(RAIL_WIDTH, 0f, max(0f, canvas.width - RAIL_WIDTH), canvas.height)
        }

    private fun regionFor(q: Quadrant, content: Bounds): Bounds {
        val w = content.w / 2f
        val h = content.h / 2f
        val x = content.x + if (q == Quadrant.TOP_RIGHT || q == Quadrant.BOTTOM_RIGHT) w else 0f
        val y = content.y + if (q == Quadrant.BOTTOM_LEFT || q == Quadrant.BOTTOM_RIGHT) h else 0f
        return Bounds(x, y, w, h)
    }

    /** Reduce tamanos desde el tamano de diseno (no desde el layout previo). */
    private fun scaleToFit(items: List<Working>, region: Bounds, fill: Float = 0.72f) {
        if (items.isEmpty()) return
        val total = items.sumOf { (it.designW * it.designH).toDouble() }.toFloat()
        val avail = region.area * fill
        if (total <= 0f || avail <= 0f || total <= avail) return
        val k = sqrt(avail / total)
        items.forEach {
            it.w = it.designW * k
            it.h = it.designH * k
            if (it.critical) {
                it.w = max(it.w, it.minW)
                it.h = max(it.h, it.minH)
            }
        }
    }

    /** Empaqueta por estantes y compacta hacia arriba. Sin solapes. */
    private fun shelfPack(items: List<Working>, region: Bounds, gutter: Float) {
        val shelves = mutableListOf<MutableList<Working>>()
        val heights = mutableListOf<Float>()
        var current = mutableListOf<Working>()
        var x = region.x
        var shelfH = 0f

        items.forEach { e ->
            if (x + e.w > region.right + 0.01f && x > region.x + 0.01f) {
                shelves.add(current); heights.add(shelfH)
                current = mutableListOf(); shelfH = 0f
                x = region.x
            }
            e.x = x
            current.add(e)
            shelfH = max(shelfH, e.h)
            x += e.w + gutter
        }
        shelves.add(current)
        heights.add(shelfH)

        // Compactacion: los estantes suben para ocupar el hueco libre.
        var cy = region.y
        shelves.forEachIndexed { i, shelf ->
            shelf.forEach { it.y = cy }
            cy += heights[i] + gutter
        }
    }

    /** Ultima barrera: los criticos quedan dentro y respetan min_size. */
    private fun rescueCriticals(items: List<Working>, canvas: Canvas) {
        items.filter { it.critical }.forEach {
            it.w = min(max(it.w, it.minW), canvas.width)
            it.h = min(max(it.h, it.minH), canvas.height)
            it.x = it.x.coerceIn(0f, max(0f, canvas.width - it.w))
            it.y = it.y.coerceIn(0f, max(0f, canvas.height - it.h))
        }
    }

    private val priorityOrder =
        compareBy<Working>({ if (it.critical) 0 else 1 }, { -it.priority }, { it.id })

    /**
     * Genera el layout destino y el plan de transiciones.
     *
     * @param previous layout de la orientacion anterior; si su canvas es el
     *   mismo que [targetCanvas] girado 90 grados, se considera una rotacion y
     *   los cuadrantes se arrastran en lugar de recalcularse.
     */
    fun plan(
        elements: List<LayoutElement>,
        targetCanvas: Canvas,
        previous: Layout? = null,
        layoutId: String = "nresponsive",
        budgetMs: Int = DEFAULT_BUDGET_MS,
        gutter: Float = DEFAULT_GUTTER,
    ): Layout {
        val working = elements.map { Working.of(it) }

        val slots = anchorSlots(elements, targetCanvas, gutter)
        working.forEach { w -> slots[w.id]?.let { w.set(it) } }

        val rotating = previous != null &&
            previous.canvas.width == targetCanvas.height &&
            previous.canvas.height == targetCanvas.width
        val clockwise = targetCanvas.orientation == Orientation.LANDSCAPE
        val prevQuad: Map<String, Quadrant> = previous?.elements
            ?.mapNotNull { e -> e.quadrant?.let { e.id to it } }
            ?.toMap() ?: emptyMap()

        val flowing = working.filter { it.id !in slots }.sortedWith(priorityOrder)
        val quadItems = READING_ORDER.associateWith { mutableListOf<Working>() }.toMutableMap()
        flowing.forEach { w ->
            w.quadrant = if (rotating && prevQuad.containsKey(w.id)) {
                rotateQuadrant(prevQuad.getValue(w.id), clockwise)
            } else {
                quadrantOf(w.toBounds(), targetCanvas)
            }
            quadItems.getValue(w.quadrant!!).add(w)
        }

        READING_ORDER.forEach { q ->
            val items = quadItems.getValue(q)
            if (items.isEmpty()) return@forEach
            val r = regionFor(q, contentBounds(targetCanvas))
            val region = Bounds(
                r.x + gutter, r.y + gutter,
                max(1f, r.w - gutter * 2), max(1f, r.h - gutter * 2),
            )
            scaleToFit(items, region)
            shelfPack(items, region, gutter)
        }

        rescueCriticals(working, targetCanvas)
        working.forEach { it.quadrant = quadrantOf(it.toBounds(), targetCanvas) }

        val transitions = planTransitions(working, previous, budgetMs)
        val resultElements = working.map { it.toElement() }

        return Layout(
            canvas = targetCanvas,
            elements = resultElements,
            layoutId = layoutId,
            animation = AnimationPlan(
                strategy = "rolling",
                budgetMs = budgetMs,
                totalDurationMs = transitions.maxOfOrNull { it.delayMs + it.durationMs } ?: 0,
            ),
            transitions = transitions,
            quadrantMap = READING_ORDER.associate { q ->
                q.name.lowercase() to resultElements.filter { it.quadrant == q }.map { it.id }
            },
        )
    }

    /** Rotacion como operacion de primera clase. */
    fun rotate(layout: Layout, budgetMs: Int = DEFAULT_BUDGET_MS): Layout =
        plan(layout.elements, layout.canvas.rotated(), previous = layout,
            layoutId = "${layout.layoutId}-rotated", budgetMs = budgetMs)

    /** Escalona las animaciones como una onda que recorre los cuadrantes. */
    private fun planTransitions(elements: List<Working>, previous: Layout?,
                                budgetMs: Int): List<Transition> {
        val prevBounds = previous?.elements?.associate { it.id to it.bounds } ?: emptyMap()

        val staged = mutableListOf<Pair<Working, String>>()
        READING_ORDER.forEach { q ->
            elements.filter { it.quadrant == q }.sortedWith(priorityOrder).forEach { w ->
                val kind = when (val o = prevBounds[w.id]) {
                    null -> "enter"
                    else -> if (abs(o.x - w.x) > 0.5f || abs(o.y - w.y) > 0.5f ||
                        abs(o.w - w.w) > 0.5f || abs(o.h - w.h) > 0.5f
                    ) "move" else "stay"
                }
                staged.add(w to kind)
            }
        }
        if (staged.isEmpty()) return emptyList()

        val duration = min(180, max(90, budgetMs / 2))
        // Margen para que el total quede estrictamente por debajo del
        // presupuesto: el criterio es "< 300 ms" y la animacion real anade
        // unos milisegundos de reloj sobre el plan.
        val target = max(60, budgetMs - TRANSITION_SAFETY_MS)
        val maxTotalDelay = max(0, target - duration)
        val step = if (staged.size > 1) maxTotalDelay.toFloat() / staged.size else 0f

        return staged.mapIndexed { idx, (w, kind) ->
            val delay = (step * idx).toInt()
            val from = prevBounds[w.id] ?: w.toBounds()
            val dist = sqrt(
                (from.centerX - w.centerX) * (from.centerX - w.centerX) +
                    (from.centerY - w.centerY) * (from.centerY - w.centerY),
            )
            val extra = if (kind == "move") min(60f, dist / 12f).toInt() else 0
            Transition(
                elementId = w.id,
                from = from,
                to = w.toBounds(),
                durationMs = min(target - delay, duration + extra).coerceAtLeast(60),
                delayMs = delay,
                easing = if (w.critical) Easing.FAST_OUT_SLOW_IN else Easing.EASE_OUT,
                kind = kind,
            )
        }
    }

    /** Copia mutable de un elemento, usada solo dentro de [plan]. */
    private class Working(
        val id: String,
        val type: ElementType,
        val critical: Boolean,
        val priority: Float,
        val minW: Float,
        val minH: Float,
        val designW: Float,
        val designH: Float,
        val scrollable: Boolean,
        val text: String?,
        val z: Int,
        var x: Float, var y: Float, var w: Float, var h: Float,
        var quadrant: Quadrant?,
    ) {
        val centerX: Float get() = x + w / 2f
        val centerY: Float get() = y + h / 2f

        fun set(b: Bounds) { x = b.x; y = b.y; w = b.w; h = b.h }
        fun toBounds() = Bounds(x, y, w, h)

        fun toElement() = LayoutElement(
            id = id, type = type, bounds = toBounds(), quadrant = quadrant,
            critical = critical, priority = priority,
            minSize = IntSize(minW, minH),
            designSize = IntSize(designW, designH),
            scrollable = scrollable, text = text, z = z,
        )

        companion object {
            fun of(e: LayoutElement) = Working(
                id = e.id, type = e.type, critical = e.critical, priority = e.priority,
                minW = e.minSize.w, minH = e.minSize.h,
                designW = e.intrinsicSize.w, designH = e.intrinsicSize.h,
                scrollable = e.scrollable, text = e.text, z = e.z,
                x = e.bounds.x, y = e.bounds.y, w = e.bounds.w, h = e.bounds.h,
                quadrant = e.quadrant,
            )
        }
    }
}