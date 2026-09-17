package dev.nresponsive.app

import android.content.res.Configuration
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.State
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalDensity
import dev.nresponsive.core.Canvas

/**
 * Puente entre la configuracion de Android y el motor de layout.
 *
 * Observa la orientacion y el tamano reales de la ventana y los entrega como
 * un [Canvas] en dp. El motor no conoce Android: solo recibe canvas.
 *
 * La Activity declara `configChanges` para no recrearse al girar, de modo que
 * este composable reacciona al cambio en caliente y el rolling se anima.
 */
@Composable
fun rememberDeviceCanvas(): State<Canvas> {
    val configuration = LocalConfiguration.current
    val density = LocalDensity.current.density

    val canvas = remember(configuration.orientation,
        configuration.screenWidthDp, configuration.screenHeightDp, density) {
        mutableStateOf(
            Canvas(
                width = configuration.screenWidthDp.toFloat(),
                height = configuration.screenHeightDp.toFloat(),
                density = density,
            ),
        )
    }
    return canvas
}

/**
 * Densidad de pantalla, util para pasar dp a px en el renderizador.
 */
@Composable
fun rememberDensityValue(): Float = LocalDensity.current.density

/**
 * Observa cambios de configuracion crudos (incluida la orientacion) y llama a
 * [onChange]. Se usa para registrar metricas de cuanto tarda el rolling.
 */
@Composable
fun ObserveConfiguration(onChange: (Configuration) -> Unit) {
    val configuration = LocalConfiguration.current
    DisposableEffect(configuration) {
        onChange(configuration)
        onDispose { }
    }
}