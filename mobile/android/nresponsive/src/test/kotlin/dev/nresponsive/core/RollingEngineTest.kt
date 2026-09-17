package dev.nresponsive.core

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue
import kotlin.test.assertFalse

/**
 * Tests del motor Kotlin. Verifican los mismos criterios que
 * `tests/test_rolling.py` para que ambas implementaciones no divergan.
 */
class RollingEngineTest {

    private val portrait = Canvas(width = 411f, height = 914f)
    private val landscape = Canvas(width = 914f, height = 411f)

    private fun plan(template: String, canvas: Canvas, previous: Layout? = null): Layout =
        RollingEngine.plan(
            Templates.elements(template, canvas), canvas,
            previous = previous, layoutId = template,
        )

    @Test
    fun `rotacion conserva todos los elementos`() {
        Templates.ALL.keys.forEach { template ->
            val p = plan(template, portrait)
            val l = plan(template, landscape, previous = p)
            assertEquals(p.elements.map { it.id }.sorted(), l.elements.map { it.id }.sorted())
            assertEquals(Orientation.LANDSCAPE, l.canvas.orientation)
        }
    }

    @Test
    fun `rotacion mantiene visibles los elementos criticos`() {
        Templates.ALL.keys.forEach { template ->
            val p = plan(template, portrait)
            val l = plan(template, landscape, previous = p)

            val critical = l.elements.filter { it.critical }
            assertTrue(critical.isNotEmpty(), "$template deberia tener criticos")

            critical.forEach { e ->
                assertTrue(e.bounds.x >= -0.01f, "${e.id} fuera a la izquierda")
                assertTrue(e.bounds.y >= -0.01f, "${e.id} fuera arriba")
                assertTrue(e.bounds.right <= l.canvas.width + 0.01f, "${e.id} fuera a la derecha")
                assertTrue(e.bounds.bottom <= l.canvas.height + 0.01f, "${e.id} fuera abajo")
                assertTrue(e.bounds.w >= e.minSize.w - 0.01f, "${e.id} bajo min ancho")
                assertTrue(e.bounds.h >= e.minSize.h - 0.01f, "${e.id} bajo min alto")
            }
        }
    }

    @Test
    fun `la navegacion pasa de barra inferior a rail lateral`() {
        val p = plan("media_player", portrait)
        val navPortrait = assertNotNull(p.elements.find { it.id == "nav" })
        assertTrue(navPortrait.bounds.y > portrait.height * 0.8f, "en retrato la nav va abajo")

        val l = plan("media_player", landscape, previous = p)
        val navLandscape = assertNotNull(l.elements.find { it.id == "nav" })
        assertTrue(navLandscape.bounds.x < landscape.width * 0.15f, "en apaisado la nav va al rail")

        val fab = assertNotNull(l.elements.find { it.id == "fab" })
        assertEquals(0f, fab.bounds.intersection(navLandscape.bounds))
    }

    @Test
    fun `la animacion cabe en el presupuesto`() {
        Templates.ALL.keys.forEach { template ->
            val p = plan(template, portrait)
            val l = plan(template, landscape, previous = p)
            assertTrue(l.transitions.isNotEmpty())
            val total = l.transitions.maxOf { it.delayMs + it.durationMs }
            assertTrue(total < 300, "$template: animacion $total ms no es < 300 ms")
        }
    }

    @Test
    fun `los criticos usan la curva rapida`() {
        val p = plan("media_player", portrait)
        val l = plan("media_player", landscape, previous = p)
        val critIds = l.elements.filter { it.critical }.map { it.id }.toSet()
        l.transitions.filter { it.elementId in critIds }
            .forEach { assertEquals(Easing.FAST_OUT_SLOW_IN, it.easing) }
    }

    @Test
    fun `ida y vuelta no produce deriva`() {
        Templates.ALL.keys.forEach { template ->
            val p = plan(template, portrait)
            val l = plan(template, landscape, previous = p)
            val back = plan(template, portrait, previous = l)

            assertEquals(p.elements.map { it.id }.sorted(), back.elements.map { it.id }.sorted())
            // Los criticos vuelven a su cuadrante original.
            p.elements.filter { it.critical }.forEach { original ->
                val now = assertNotNull(back.elements.find { it.id == original.id })
                assertEquals(original.bounds.x, now.bounds.x, 1f, "${original.id} x deriva")
                assertEquals(original.bounds.y, now.bounds.y, 1f, "${original.id} y deriva")
            }
        }
    }

    @Test
    fun `sin solapes tras la rotacion`() {
        Templates.ALL.keys.forEach { template ->
            val p = plan(template, portrait)
            val l = plan(template, landscape, previous = p)
            // Se ignoran los contenedores, que actuan de fondo.
            val pool = l.elements.filter { it.type != ElementType.CONTAINER && it.type != ElementType.IMAGE }
            var overlap = 0f
            for (i in pool.indices) {
                for (j in i + 1 until pool.size) {
                    overlap += pool[i].bounds.intersection(pool[j].bounds)
                }
            }
            val area = l.canvas.width * l.canvas.height
            assertTrue(overlap / area < 0.02f, "$template: solape ${overlap / area}")
        }
    }

    @Test
    fun `el motor no muta la entrada`() {
        val elements = Templates.elements("media_player", portrait)
        val snapshot = elements.map { it.bounds }
        RollingEngine.plan(elements, landscape, previous = null)
        elements.forEachIndexed { i, e ->
            assertEquals(snapshot[i].x, e.bounds.x)
            assertEquals(snapshot[i].y, e.bounds.y)
        }
    }

    @Test
    fun `el JSON generado se puede releer`() {
        val p = plan("dashboard", portrait)
        val text = NresponsiveJson.encodeToString(Layout.serializer(), p)
        val back = NresponsiveJson.decodeFromString(Layout.serializer(), text)
        assertEquals(p.elements.size, back.elements.size)
        assertEquals(p.canvas.width, back.canvas.width)
        assertEquals(p.quadrantMap, back.quadrantMap)
    }

    @Test
    fun `los cuadrantes cubren todos los elementos`() {
        val p = plan("dashboard", portrait)
        val mapped = p.quadrantMap.values.sumOf { it.size }
        assertEquals(p.elements.size, mapped)
    }

    @Test
    fun `el detector de orientacion emite solo rotaciones reales`() {
        val scope = kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.Dispatchers.Unconfined)
        val detector = OrientationDetector(portrait, scope)

        assertNotNull(detector.onRotated(), "debe emitir al girar")
        assertFalse(detector.currentCanvas.orientation == Orientation.PORTRAIT)
        // Repetir el mismo canvas no debe emitir.
        assertEquals(null, detector.onCanvasChanged(landscape))
        // Y una rotacion inversa vuelve a retrato.
        assertNotNull(detector.onRotated())
        assertEquals(Orientation.PORTRAIT, detector.currentCanvas.orientation)
    }
}