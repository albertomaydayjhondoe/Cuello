package dev.nresponsive.app

import android.content.res.Configuration
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import dev.nresponsive.core.Bounds
import dev.nresponsive.core.Canvas
import dev.nresponsive.core.Layout
import dev.nresponsive.core.LayoutRepository
import dev.nresponsive.core.LayoutResult
import dev.nresponsive.core.OrientationDetector
import dev.nresponsive.core.Templates
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob

/**
 * Demo del rolling.
 *
 * La Activity declara `configChanges` para NO recrearse al girar. Asi la
 * orientacion llega como un cambio en caliente, [OrientationDetector] emite el
 * evento y el canvas anima el reordenamiento en lugar de recargar la pantalla.
 */
class MainActivity : ComponentActivity() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private lateinit var detector: OrientationDetector
    private lateinit var repository: LayoutRepository

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val initial = Canvas(
            width = resources.displayMetrics.widthPixels / resources.displayMetrics.density,
            height = resources.displayMetrics.heightPixels / resources.displayMetrics.density,
            density = resources.displayMetrics.density,
        )
        detector = OrientationDetector(initial, scope)
        // Poner aqui la URL del endpoint FastAPI para usar el modo remoto.
        // Sin endpoint, el motor corre en el dispositivo (modo sin conexion).
        repository = LayoutRepository(endpoint = null)

        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    RollingDemoScreen(detector, repository)
                }
            }
        }
    }

    /**
     * `configChanges` evita la recreacion, pero la Activity sigue recibiendo
     * este callback: es el punto donde alimentamos el detector.
     */
    override fun onConfigurationChanged(newConfig: Configuration) {
        super.onConfigurationChanged(newConfig)
        val metrics = resources.displayMetrics
        detector.onCanvasChanged(
            Canvas(
                width = metrics.widthPixels / metrics.density,
                height = metrics.heightPixels / metrics.density,
                density = metrics.density,
            ),
        )
    }
}

@Composable
private fun RollingDemoScreen(
    detector: OrientationDetector,
    repository: LayoutRepository,
) {
    var template by remember { mutableStateOf(Templates.DEFAULT) }
    var layout by remember { mutableStateOf<Layout?>(null) }
    var previousBounds by remember { mutableStateOf<Map<String, Bounds>>(emptyMap()) }
    var source by remember { mutableStateOf("-") }
    var latency by remember { mutableStateOf(0L) }
    var lastRollingMs by remember { mutableStateOf(0L) }

    // Reacciona tanto al cambio de plantilla como a cada rotacion.
    val canvasState = rememberDeviceCanvas()
    val canvas = canvasState.value

    LaunchedEffect(template, canvas) {
        val previous = layout
        val start = System.currentTimeMillis()
        val result: LayoutResult = repository.load(template, canvas, previous)
        // La medida relevante es el tiempo de replanificacion, no el de red.
        lastRollingMs = System.currentTimeMillis() - start
        previousBounds = previous?.elements?.associate { it.id to it.bounds } ?: emptyMap()
        layout = result.layout
        source = result.source
        latency = result.latencyMs
    }

    Column(modifier = Modifier.fillMaxSize()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Templates.ALL.keys.forEach { name ->
                if (name == template) {
                    Button(onClick = { template = name }) { Text(name) }
                } else {
                    OutlinedButton(onClick = { template = name }) { Text(name) }
                }
            }
        }
        Text(
            "orientacion=${canvas.orientation.name.lowercase()}  " +
                "canvas=${canvas.width.toInt()}x${canvas.height.toInt()}  " +
                "origen=$source  plan=${latency}ms  rolling=${lastRollingMs}ms",
            modifier = Modifier.padding(horizontal = 8.dp),
        )
        Box(modifier = Modifier.fillMaxSize()) {
            layout?.let {
                NresponsiveCanvas(
                    layout = it,
                    previousBounds = previousBounds,
                    modifier = Modifier.fillMaxSize(),
                )
            } ?: Text("generando layout...", modifier = Modifier.align(Alignment.Center))
        }
    }
}