package dev.nresponsive.core

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Evento de cambio de orientacion que expone el motor de layout.
 *
 * El detector es agnostico de la fuente: en Android lo alimenta
 * `OrientationEventListener` / `LocalConfiguration`; en tests se puede emitir
 * manualmente. El motor solo ve este flujo.
 */
data class OrientationEvent(
    val from: Orientation,
    val to: Orientation,
    /** Canvas de origen y destino, en dp, ya con ancho/alto intercambiados. */
    val fromCanvas: Canvas,
    val toCanvas: Canvas,
    /** Momento del evento en milisegundos mono-tonicos. */
    val timestampMs: Long,
) {
    val isRotation: Boolean get() = from != to
}

/**
 * Fuente de eventos de orientacion. Mantiene el canvas actual y emite un
 * [OrientationEvent] cada vez que cambia.
 */
class OrientationDetector(
    initialCanvas: Canvas,
    private val scope: CoroutineScope,
) {
    private val _events = MutableSharedFlow<OrientationEvent>(
        replay = 0, extraBufferCapacity = 8,
    )

    /** Flujo de cambios de orientacion. Solo emite rotaciones reales. */
    val events: SharedFlow<OrientationEvent> = _events.asSharedFlow()

    /** Orientacion actual, observable (sin repeticiones). */
    private val _orientation = MutableStateFlow(initialCanvas.orientation)
    val orientation: StateFlow<Orientation> = _orientation.asStateFlow()

    @Volatile
    var currentCanvas: Canvas = initialCanvas
        private set

    /**
     * Notifica un canvas nuevo (por ejemplo desde `onConfigurationChanged`).
     * Devuelve el evento emitido, o `null` si la orientacion no cambio.
     */
    fun onCanvasChanged(canvas: Canvas, timestampMs: Long = System.currentTimeMillis()): OrientationEvent? {
        val previous = currentCanvas
        if (previous.width == canvas.width && previous.height == canvas.height) {
            return null
        }
        val event = OrientationEvent(
            from = previous.orientation,
            to = canvas.orientation,
            fromCanvas = previous,
            toCanvas = canvas,
            timestampMs = timestampMs,
        )
        currentCanvas = canvas
        _orientation.value = canvas.orientation
        _events.tryEmit(event)
        return event
    }

    /** Atajo para el caso tipico: girar 90 grados el canvas actual. */
    fun onRotated(timestampMs: Long = System.currentTimeMillis()): OrientationEvent? =
        onCanvasChanged(currentCanvas.rotated(), timestampMs)
}