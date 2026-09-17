package dev.nresponsive.app

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.EaseInOut
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.key
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import dev.nresponsive.core.Bounds
import dev.nresponsive.core.Easing
import dev.nresponsive.core.ElementType
import dev.nresponsive.core.Layout
import dev.nresponsive.core.Transition
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.launch

/**
 * Renderiza un layout nresponsive y anima el "rolling" cuando cambia.
 *
 * Cada elemento tiene sus propias [Animatable] en dp. Al recibir un layout
 * nuevo no se salta al destino: se anima desde las coordenadas del layout
 * anterior siguiendo el plan de transiciones (`delayMs`, `durationMs`,
 * `easing`) que produjo el motor.
 *
 * @param previousBounds posiciones del layout vigente antes de este cambio.
 *   Es lo que da continuidad visual al girar el dispositivo.
 */
@Composable
fun NresponsiveCanvas(
    layout: Layout,
    previousBounds: Map<String, Bounds>,
    modifier: Modifier = Modifier,
    animate: Boolean = true,
) {
    BoxWithConstraints(modifier = modifier.fillMaxSize()) {
        // El motor trabaja sobre el canvas declarado; aqui se ajusta al
        // tamano efectivo de la ventana.
        val sx = maxWidth.value / layout.canvas.width
        val sy = maxHeight.value / layout.canvas.height

        layout.elements.sortedBy { it.z }.forEach { element ->
            key(element.id) {
                AnimatedElement(
                    fromBounds = previousBounds[element.id] ?: element.bounds,
                    toBounds = element.bounds,
                    transition = layout.transitions.find { it.elementId == element.id },
                    sx = sx,
                    sy = sy,
                    type = element.type,
                    label = element.text,
                    critical = element.critical,
                    animate = animate,
                )
            }
        }
    }
}

@Composable
private fun AnimatedElement(
    fromBounds: Bounds,
    toBounds: Bounds,
    transition: Transition?,
    sx: Float,
    sy: Float,
    type: ElementType,
    label: String?,
    critical: Boolean,
    animate: Boolean,
) {
    val animX = remember { Animatable(fromBounds.x * sx) }
    val animY = remember { Animatable(fromBounds.y * sy) }
    val animW = remember { Animatable(fromBounds.w * sx) }
    val animH = remember { Animatable(fromBounds.h * sy) }

    LaunchedEffect(toBounds.x, toBounds.y, toBounds.w, toBounds.h, animate) {
        if (!animate) {
            animX.snapTo(toBounds.x * sx)
            animY.snapTo(toBounds.y * sy)
            animW.snapTo(toBounds.w * sx)
            animH.snapTo(toBounds.h * sy)
            return@LaunchedEffect
        }
        val spec = tween<Float>(
            durationMillis = transition?.durationMs ?: 180,
            delayMillis = transition?.delayMs ?: 0,
            easing = (transition?.easing ?: Easing.FAST_OUT_SLOW_IN).toComposeEasing(),
        )
        // Las cuatro propiedades del mismo elemento viajan juntas; el
        // escalonado entre elementos ya lo aporta delayMs.
        coroutineScope {
            launch { animX.animateTo(toBounds.x * sx, spec) }
            launch { animY.animateTo(toBounds.y * sy, spec) }
            launch { animW.animateTo(toBounds.w * sx, spec) }
            launch { animH.animateTo(toBounds.h * sy, spec) }
        }
    }

    val shape = RoundedCornerShape(if (critical) 16.dp else 8.dp)

    Box(
        modifier = Modifier
            .offset(x = animX.value.dp, y = animY.value.dp)
            .size(
                width = animW.value.dp.coerceAtLeast(1.dp),
                height = animH.value.dp.coerceAtLeast(1.dp),
            )
            .clip(shape)
            .background(backgroundFor(type))
            .border(if (critical) 2.dp else 1.dp, borderFor(type), shape),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = label ?: type.name.lowercase(),
            fontSize = if (critical) 13.sp else 11.sp,
            color = Color.White.copy(alpha = 0.95f),
        )
    }
}

private fun Easing.toComposeEasing() = when (this) {
    Easing.LINEAR -> LinearEasing
    Easing.FAST_OUT_SLOW_IN -> FastOutSlowInEasing
    Easing.EASE_IN_OUT -> EaseInOut
    Easing.EASE_OUT -> FastOutSlowInEasing
}

private fun backgroundFor(type: ElementType): Color = when (type) {
    ElementType.BUTTON -> Color(0xFF1E88E5)
    ElementType.NAV -> Color(0xFF37474F)
    ElementType.FAB -> Color(0xFFD81B60)
    ElementType.IMAGE -> Color(0xFF5E35B1)
    ElementType.TEXT -> Color(0xFF455A64)
    ElementType.INPUT -> Color(0xFF00897B)
    ElementType.LIST -> Color(0xFF6D4C41)
    ElementType.CONTAINER -> Color(0xFF90A4AE)
}

private fun borderFor(type: ElementType): Color =
    if (type == ElementType.BUTTON || type == ElementType.FAB || type == ElementType.NAV) {
        Color.White.copy(alpha = 0.9f)
    } else {
        Color.White.copy(alpha = 0.35f)
    }