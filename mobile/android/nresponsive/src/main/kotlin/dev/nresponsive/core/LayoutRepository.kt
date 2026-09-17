package dev.nresponsive.core

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.net.HttpURLConnection

/**
 * Resultado de pedir un layout, con trazabilidad de la procedencia.
 */
data class LayoutResult(
    val layout: Layout,
    val source: String,
    val latencyMs: Long,
    val fallbackReason: String? = null,
)

/**
 * Fuente de layouts.
 *
 * Modo local (por defecto): el motor de rolling corre en el dispositivo. Es el
 * modo que cumple el requisito de funcionar sin conexion.
 *
 * Modo remoto: consulta el endpoint FastAPI (`POST /layout`). Si falla por
 * cualquier motivo, cae al motor local; la UI nunca se queda sin layout.
 */
class LayoutRepository(
    private val endpoint: String? = null,
    private val budgetMs: Int = RollingEngine.DEFAULT_BUDGET_MS,
) {
    /**
     * Pide el layout para un canvas y una plantilla.
     *
     * @param previous layout vigente; permite que el motor detecte la rotacion
     *   y arrastre los cuadrantes.
     */
    suspend fun load(
        template: String,
        canvas: Canvas,
        previous: Layout? = null,
        timeoutMs: Int = 1500,
    ): LayoutResult = withContext(Dispatchers.IO) {
        if (endpoint.isNullOrBlank()) {
            return@withContext local(template, canvas, previous)
        }
        val started = System.currentTimeMillis()
        try {
            val layout = fetchRemote(template, canvas, previous, timeoutMs)
            LayoutResult(layout, "remote", System.currentTimeMillis() - started)
        } catch (t: Throwable) {
            val fallback = local(template, canvas, previous)
            fallback.copy(
                fallbackReason = "${t::class.simpleName}: ${t.message}",
            )
        }
    }

    private fun local(template: String, canvas: Canvas, previous: Layout?): LayoutResult {
        val started = System.nanoTime()
        val elements = Templates.elements(template, canvas)
        val layout = RollingEngine.plan(
            elements = elements,
            targetCanvas = canvas,
            previous = previous,
            layoutId = "$template-${canvas.orientation.name.lowercase()}",
            budgetMs = budgetMs,
        )
        return LayoutResult(layout, "local-engine",
            (System.nanoTime() - started) / 1_000_000)
    }

    private fun fetchRemote(template: String, canvas: Canvas, previous: Layout?,
                            timeoutMs: Int): Layout {
        val body = buildJson(template, canvas, previous)
        val conn = (java.net.URI(endpoint).toURL().openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            doOutput = true
            connectTimeout = timeoutMs
            readTimeout = timeoutMs
            setRequestProperty("Content-Type", "application/json")
        }
        conn.outputStream.use { it.write(body.toByteArray()) }
        val code = conn.responseCode
        if (code !in 200..299) error("HTTP $code")
        val text = conn.inputStream.bufferedReader().use { it.readText() }
        val layout = NresponsiveJson.decodeFromString(Layout.serializer(), text)
        // Un layout remoto sin elementos utilizables se considera invalido.
        if (layout.elements.isEmpty()) error("respuesta sin elementos")
        return layout
    }

    private fun buildJson(template: String, canvas: Canvas, previous: Layout?): String {
        val prev = previous?.let {
            "\"previous_layout\":${NresponsiveJson.encodeToString(Layout.serializer(), it)}"
        } ?: ""
        val sep = if (prev.isEmpty()) "" else ","
        return """
            {"template":"$template",
             "canvas":{"width":${canvas.width},"height":${canvas.height},"density":${canvas.density}}
             $sep$prev}
        """.trimIndent()
    }
}