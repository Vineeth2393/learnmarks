package app.learnmarks.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.learnmarks.data.BookmarkItem

// ---------- icons (same strokes as the web app) ----------

object LmIcons {
    private fun icon(name: String, vararg paths: String): ImageVector =
        ImageVector.Builder(name, 24.dp, 24.dp, 24f, 24f).apply {
            for (d in paths) addPath(
                pathData = PathParser().parsePathString(d).toNodes(),
                stroke = SolidColor(Color.Black), strokeLineWidth = 1.9f,
                strokeLineCap = StrokeCap.Round, strokeLineJoin = StrokeJoin.Round,
            )
        }.build()

    val home = icon("home", "M4 11 12 4l8 7v9h-5v-6H9v6H4z")
    val topics = icon("topics", "M4 6h7l2 2h7v11H4z")
    val search = icon("search", "M11 4a7 7 0 1 0 0 14a7 7 0 1 0 0-14z", "m20 20-3.5-3.5")
    val add = icon("add", "M12 5v14M5 12h14")
    val sync = icon("sync", "M12 3v12M8 7l4-4 4 4M6 13v4a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2v-4")
    val back = icon("back", "M15 5 8 12l7 7")
    val close = icon("close", "M6 6l12 12M18 6 6 18")
    val external = icon("external", "M14 4h6v6", "M20 4 10 14", "M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5")
    val edit = icon("edit", "M4 20h4L19 9l-4-4L4 16z", "m13.5 6.5 4 4")
    val logo = icon("logo", "M5 10.4a2.6 2.6 0 1 0 0 5.2a2.6 2.6 0 1 0 0-5.2z", "M20 2.4a2.6 2.6 0 1 0 0 5.2a2.6 2.6 0 1 0 0-5.2z",
        "M20 10.4a2.6 2.6 0 1 0 0 5.2a2.6 2.6 0 1 0 0-5.2z", "M20 18.4a2.6 2.6 0 1 0 0 5.2a2.6 2.6 0 1 0 0-5.2z", "M7.5 12 17.5 6M7.6 13h9.8M7.5 14l10 6")
}

// ---------- text ----------

@Composable
fun Lbl(text: String, modifier: Modifier = Modifier, color: Color = LocalLm.current.muted) =
    Text(text.uppercase(), modifier = modifier, style = Type.label, color = color, maxLines = 1, overflow = TextOverflow.Ellipsis)

// ---------- pills ----------

val STATUS_LABEL = mapOf("saved" to "Saved", "to_learn" to "To learn", "in_progress" to "In progress", "learned" to "Learned")
val STATUSES = listOf("saved", "to_learn", "in_progress", "learned")
val PRIORITY_LABEL = mapOf(1 to "Low", 2 to "Medium", 3 to "High")
val PLATFORM_LABEL = mapOf("x" to "X", "linkedin" to "LinkedIn", "other" to "Web")

@Composable
fun Pill(text: String, bg: Color, fg: Color, border: Color, modifier: Modifier = Modifier) {
    Box(
        modifier
            .clip(CircleShape)
            .background(bg)
            .border(1.dp, border, CircleShape)
            .padding(horizontal = 8.dp, vertical = 3.dp)
    ) { Text(text.uppercase(), style = Type.label.copy(fontSize = 9.5.sp, letterSpacing = 0.06.sp), color = fg, maxLines = 1) }
}

@Composable
fun StatusPill(status: String, modifier: Modifier = Modifier) {
    val c = LocalLm.current
    val (bg, fg, line) = when (status) {
        "to_learn" -> Triple(c.todoBg, c.todoInk, c.todoLine)
        "in_progress" -> Triple(c.inverse, c.onInverse, c.inverse)
        "learned" -> Triple(c.doneBg, c.doneInk, c.doneLine)
        else -> Triple(c.surface, c.sub, c.lineStrong)
    }
    Pill(STATUS_LABEL[status] ?: status, bg, fg, line, modifier)
}

@Composable
fun PendingDot(modifier: Modifier = Modifier) {
    val c = LocalLm.current
    Box(
        modifier
            .size(8.dp)
            .clip(CircleShape)
            .background(if (c.dark) Color(0xFFE0B341) else Color(0xFFB7791F))
            .semantics { contentDescription = "Not yet on the laptop" }
    )
}

// ---------- buttons, chips, segmented controls ----------

@Composable
fun LmButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    dark: Boolean = false,
    enabled: Boolean = true,
    icon: ImageVector? = null,
) {
    val c = LocalLm.current
    val bg = if (dark) c.inverse else c.surface
    val fg = if (dark) c.onInverse else c.ink
    Row(
        modifier
            .heightIn(min = 48.dp)
            .clip(RoundedCornerShape(14.dp))
            .background(if (enabled) bg else bg.copy(alpha = 0.5f))
            .border(1.dp, if (dark) bg else c.lineStrong, RoundedCornerShape(14.dp))
            .clickable(enabled = enabled, role = Role.Button, onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 12.dp),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (icon != null) {
            Icon(icon, null, tint = fg, modifier = Modifier.size(18.dp))
            Spacer(Modifier.width(8.dp))
        }
        Text(text, style = Type.title, color = if (enabled) fg else fg.copy(alpha = 0.6f))
    }
}

@Composable
fun ToggleChip(text: String, selected: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier, leading: Color? = null) {
    val c = LocalLm.current
    Row(
        modifier
            .heightIn(min = 36.dp)
            .clip(CircleShape)
            .background(if (selected) c.inverse else c.surface)
            .border(1.dp, if (selected) c.inverse else c.lineStrong, CircleShape)
            .clickable(role = Role.Checkbox, onClick = onClick)
            .semantics { this.selected = selected }
            .padding(horizontal = 12.dp, vertical = 7.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (leading != null) {
            Box(Modifier.size(10.dp).clip(RoundedCornerShape(3.dp)).background(leading))
            Spacer(Modifier.width(7.dp))
        }
        Text(text, style = Type.bodySmall, color = if (selected) c.onInverse else c.sub, maxLines = 1)
    }
}

@Composable
fun <T> Segmented(options: List<Pair<T, String>>, selected: T, onSelect: (T) -> Unit, modifier: Modifier = Modifier) {
    val c = LocalLm.current
    Row(
        modifier
            .clip(RoundedCornerShape(12.dp))
            .border(1.dp, c.lineStrong, RoundedCornerShape(12.dp))
            .background(c.surface)
    ) {
        options.forEachIndexed { i, (value, label) ->
            val on = value == selected
            Box(
                Modifier
                    .weight(1f)
                    .heightIn(min = 44.dp)
                    .background(if (on) c.inverse else Color.Transparent)
                    .clickable(role = Role.RadioButton) { onSelect(value) }
                    .semantics { this.selected = on },
                contentAlignment = Alignment.Center,
            ) {
                Text(label, style = Type.bodySmall.copy(fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal),
                    color = if (on) c.onInverse else c.sub, maxLines = 1)
            }
            if (i < options.lastIndex && !on && options[i + 1].first != selected) {
                Box(Modifier.width(1.dp).height(44.dp).background(c.line))
            }
        }
    }
}

// ---------- surfaces ----------

@Composable
fun Card(modifier: Modifier = Modifier, onClick: (() -> Unit)? = null, padding: Dp = 14.dp, content: @Composable () -> Unit) {
    val c = LocalLm.current
    Box(
        modifier
            .clip(RoundedCornerShape(14.dp))
            .background(c.surface)
            .border(BorderStroke(1.dp, c.line), RoundedCornerShape(14.dp))
            .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier)
            .padding(padding)
    ) { content() }
}

@Composable
fun SectionHeader(label: String, trailing: String? = null, onTrailing: (() -> Unit)? = null) {
    Row(Modifier.fillMaxWidth().padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        Lbl(label, Modifier.weight(1f))
        if (trailing != null) {
            Text(
                trailing.uppercase(), style = Type.label, color = LocalLm.current.ink,
                modifier = Modifier
                    .then(if (onTrailing != null) Modifier.clickable(onClick = onTrailing) else Modifier)
                    .padding(vertical = 6.dp, horizontal = 2.dp),
            )
        }
    }
}

@Composable
fun BookmarkRow(item: BookmarkItem, onClick: () -> Unit, number: Int? = null, showTopic: Boolean = true) {
    val c = LocalLm.current
    val b = item.b
    Card(onClick = onClick, modifier = Modifier.fillMaxWidth(), padding = 12.dp) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (number != null) {
                Text(number.toString().padStart(2, '0'), style = Type.meta.copy(fontSize = 13.sp), color = c.muted,
                    modifier = Modifier.width(28.dp))
            } else {
                Box(Modifier.width(6.dp).height(40.dp).clip(RoundedCornerShape(3.dp)).background(c.pastel(item.topicColor)))
                Spacer(Modifier.width(12.dp))
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(b.title, style = Type.title, color = c.ink, maxLines = 3, overflow = TextOverflow.Ellipsis)
                val meta = buildList {
                    add(b.authorHandle?.let { "@$it" } ?: if (b.url.isBlank()) "Checklist" else PLATFORM_LABEL[b.sourcePlatform] ?: "")
                    if (showTopic && item.topicName != null) add(item.topicName)
                    if (number != null && !item.tagNames.isNullOrBlank()) add(item.tagNames)
                }.filter { it.isNotBlank() }.joinToString(" · ")
                Text(meta, style = Type.meta, color = c.muted, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            Spacer(Modifier.width(10.dp))
            Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(6.dp)) {
                StatusPill(b.status)
                if (item.pending) PendingDot()
            }
        }
    }
}

/** Folder-like cover with a pattern, like the web topic cards. */
@Composable
fun TopicCover(color: Color, number: String, modifier: Modifier = Modifier, height: Dp = 64.dp, pattern: Int = 0) {
    val c = LocalLm.current
    Box(modifier.fillMaxWidth().height(height).clip(RoundedCornerShape(10.dp)).background(Color.White.copy(alpha = 0.28f))) {
        Canvas(Modifier.fillMaxSize()) {
            val ink = c.onPastel.copy(alpha = 0.16f)
            when (pattern % 3) {
                0 -> { // dots
                    var y = 6f
                    while (y < size.height) { var x = 6f; while (x < size.width) { drawCircle(ink, 1.6f, Offset(x, y)); x += 18f }; y += 18f }
                }
                1 -> { // diagonal lines
                    var x = -size.height
                    while (x < size.width) { drawLine(ink, Offset(x, size.height), Offset(x + size.height, 0f), 1.5f); x += 16f }
                }
                else -> { // grid
                    var x = 0f; while (x < size.width) { drawLine(ink, Offset(x, 0f), Offset(x, size.height), 1.2f); x += 22f }
                    var y = 0f; while (y < size.height) { drawLine(ink, Offset(0f, y), Offset(size.width, y), 1.2f); y += 22f }
                }
            }
        }
        Text(number, style = Type.number, color = c.onPastel, modifier = Modifier.align(Alignment.BottomStart).padding(10.dp))
    }
}

@Composable
fun ProgressBar(fraction: Float, track: Color, fill: Color, modifier: Modifier = Modifier) {
    Box(modifier.fillMaxWidth().height(4.dp).clip(CircleShape).background(track)) {
        Box(Modifier.fillMaxWidth(fraction.coerceIn(0f, 1f)).height(4.dp).background(fill))
    }
}

@Composable
fun RowScope.Stat(label: String, value: String) {
    val c = LocalLm.current
    Column(Modifier.weight(1f).background(c.surface).padding(12.dp)) {
        Lbl(label)
        Text(value, style = Type.number, color = c.ink, modifier = Modifier.padding(top = 4.dp))
    }
}
