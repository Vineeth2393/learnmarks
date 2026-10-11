package app.learnmarks.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import app.learnmarks.R

/** Same tokens as the web app (web/src/styles.css, DESIGN §6). The phone follows the system theme. */
@Immutable
data class LmColors(
    val dark: Boolean,
    val canvas: Color, val surface: Color, val ink: Color, val sub: Color, val soft: Color, val muted: Color,
    val line: Color, val lineStrong: Color, val hover: Color, val active: Color,
    val inverse: Color, val onInverse: Color, val inverseMuted: Color, val inverseTrack: Color,
    val todoBg: Color, val todoLine: Color, val todoInk: Color,
    val doneBg: Color, val doneLine: Color, val doneInk: Color,
    val warnBg: Color, val warnLine: Color, val warnInk: Color,
) {
    val onPastel = Color(0xFF272727)

    /** Topic colours stay pastel; in dark mode they are softened so they don't glare. */
    fun pastel(hex: String?): Color {
        val c = parseHex(hex) ?: Color(0xFFD9D9DC)
        return if (dark) lerp(c, Color(0xFF131315), 0.2f) else c
    }
}

fun parseHex(hex: String?): Color? =
    hex?.removePrefix("#")?.takeIf { it.length == 6 }?.toLongOrNull(16)?.let { Color(0xFF000000 or it) }

val LightColors = LmColors(
    dark = false,
    canvas = Color(0xFFF7F7F8), surface = Color.White, ink = Color(0xFF272727), sub = Color(0xFF3F3F46),
    soft = Color(0xFF4B4B52), muted = Color(0xFF5F5F66), line = Color(0xFFE4E4E7), lineStrong = Color(0xFFD4D4D8),
    hover = Color(0xFFEDEDEF), active = Color(0xFFE7E7EA),
    inverse = Color(0xFF272727), onInverse = Color.White, inverseMuted = Color(0xFFC9C9CF), inverseTrack = Color(0xFF4A4A50),
    todoBg = Color(0xFFF3E2A0), todoLine = Color(0xFFE3CD78), todoInk = Color(0xFF4A3B00),
    doneBg = Color(0xFFDCEFE2), doneLine = Color(0xFFB9DCC5), doneInk = Color(0xFF1F5C36),
    warnBg = Color(0xFFFCE3D6), warnLine = Color(0xFFF0C0A6), warnInk = Color(0xFF8A2E0C),
)

val DarkColors = LmColors(
    dark = true,
    canvas = Color(0xFF131315), surface = Color(0xFF1C1C1F), ink = Color(0xFFECECEE), sub = Color(0xFFD4D4D8),
    soft = Color(0xFFC4C4CC), muted = Color(0xFFA1A1AA), line = Color(0xFF2E2E33), lineStrong = Color(0xFF3F3F46),
    hover = Color(0xFF26262A), active = Color(0xFF2C2C31),
    inverse = Color(0xFFECECEE), onInverse = Color(0xFF18181B), inverseMuted = Color(0xFF52525B), inverseTrack = Color(0xFFC4C4CC),
    todoBg = Color(0xFF4A3F12), todoLine = Color(0xFF6B5A1A), todoInk = Color(0xFFF3E2A0),
    doneBg = Color(0xFF173B25), doneLine = Color(0xFF2B5C3D), doneInk = Color(0xFF9FD9B3),
    warnBg = Color(0xFF4A2416), warnLine = Color(0xFF7A3A22), warnInk = Color(0xFFF5B89A),
)

val Grotesk = FontFamily(
    Font(R.font.hanken_grotesk_regular, FontWeight.Normal),
    Font(R.font.hanken_grotesk_medium, FontWeight.Medium),
    Font(R.font.hanken_grotesk_semibold, FontWeight.SemiBold),
    Font(R.font.hanken_grotesk_bold, FontWeight.Bold),
)

val Mono = FontFamily(
    Font(R.font.jetbrains_mono_regular, FontWeight.Normal),
    Font(R.font.jetbrains_mono_medium, FontWeight.Medium),
    Font(R.font.jetbrains_mono_semibold, FontWeight.SemiBold),
)

object Type {
    val label = TextStyle(fontFamily = Mono, fontSize = 10.5.sp, letterSpacing = 0.08.em, fontWeight = FontWeight.Normal)
    val body = TextStyle(fontFamily = Grotesk, fontSize = 15.sp, lineHeight = 21.sp)
    val bodySmall = TextStyle(fontFamily = Grotesk, fontSize = 13.5.sp, lineHeight = 19.sp)
    val title = TextStyle(fontFamily = Grotesk, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, lineHeight = 20.sp)
    val heading = TextStyle(fontFamily = Grotesk, fontSize = 28.sp, fontWeight = FontWeight.SemiBold, letterSpacing = (-0.03).em, lineHeight = 31.sp)
    val headingMono = TextStyle(fontFamily = Mono, fontSize = 24.sp, fontWeight = FontWeight.Medium, letterSpacing = (-0.04).em, lineHeight = 28.sp)
    val meta = TextStyle(fontFamily = Mono, fontSize = 11.sp, lineHeight = 15.sp)
    val number = TextStyle(fontFamily = Mono, fontSize = 22.sp, fontWeight = FontWeight.Medium, letterSpacing = (-0.04).em)
}

val LocalLm = staticCompositionLocalOf { LightColors }

@Composable
fun LearnmarksTheme(content: @Composable () -> Unit) {
    val c = if (isSystemInDarkTheme()) DarkColors else LightColors
    val scheme = (if (c.dark) darkColorScheme() else lightColorScheme()).copy(
        primary = c.inverse, onPrimary = c.onInverse, secondary = c.sub, onSecondary = c.surface,
        background = c.canvas, onBackground = c.ink, surface = c.surface, onSurface = c.ink,
        surfaceVariant = c.hover, onSurfaceVariant = c.muted, surfaceContainer = c.surface,
        surfaceContainerHigh = c.surface, surfaceContainerLow = c.canvas, surfaceContainerLowest = c.surface,
        outline = c.lineStrong, outlineVariant = c.line, error = c.warnInk, onError = c.surface,
        secondaryContainer = c.active, onSecondaryContainer = c.ink,
    )
    val typography = Typography().let { t ->
        Typography(
            bodyLarge = t.bodyLarge.copy(fontFamily = Grotesk), bodyMedium = t.bodyMedium.copy(fontFamily = Grotesk),
            bodySmall = t.bodySmall.copy(fontFamily = Grotesk), labelLarge = t.labelLarge.copy(fontFamily = Grotesk),
            labelMedium = t.labelMedium.copy(fontFamily = Grotesk), labelSmall = t.labelSmall.copy(fontFamily = Grotesk),
            titleMedium = t.titleMedium.copy(fontFamily = Grotesk), titleLarge = t.titleLarge.copy(fontFamily = Grotesk),
        )
    }
    CompositionLocalProvider(LocalLm provides c) {
        MaterialTheme(colorScheme = scheme, typography = typography, content = content)
    }
}
