package app.learnmarks.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavHostController
import app.learnmarks.data.TopicWithCounts

@Composable
fun HomeScreen(nav: NavHostController) {
    val repo = LocalRepo.current
    val c = LocalLm.current
    val counts by repo.statusCounts().collectAsStateWithLifecycle(emptyMap())
    val cont by repo.continueItem().collectAsStateWithLifecycle(null)
    val upNext by repo.byStatus("to_learn", 3).collectAsStateWithLifecycle(emptyList())
    val topics by repo.topicsWithCounts().collectAsStateWithLifecycle(emptyList())
    val total = counts.values.sum()
    val loadExport = rememberExportLoader()

    LazyColumn(
        Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(18.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(LmIcons.logo, null, tint = c.ink, modifier = Modifier.size(24.dp))
                Spacer(Modifier.width(10.dp))
                Text("learnmarks", style = Type.title.copy(fontFamily = Mono, fontSize = 16.sp), color = c.ink, modifier = Modifier.weight(1f))
                Pill("$total on this phone", c.surface, c.sub, c.lineStrong)
            }
        }
        item {
            Row(
                Modifier
                    .fillMaxWidth()
                    .heightIn(min = 48.dp)
                    .clip(RoundedCornerShape(14.dp))
                    .background(c.surface)
                    .border(1.dp, c.lineStrong, RoundedCornerShape(14.dp))
                    .clickable(role = Role.Button) { nav.goTab("search") }
                    .padding(horizontal = 14.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(LmIcons.search, null, tint = c.muted, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(10.dp))
                Text("Search $total bookmarks offline", style = Type.body, color = c.muted)
            }
        }

        if (total == 0) {
            item {
                Card(Modifier.fillMaxWidth(), padding = 18.dp) {
                    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Lbl("Get started")
                        Text("Bring your bookmarks from the laptop", style = Type.title.copy(fontSize = 18.sp), color = c.ink)
                        Text(
                            "On the laptop open Import · Backup · Sync and press Download export. Copy the file to this phone, then load it here. " +
                                "(USB sync replaces this step in Phase 4.)",
                            style = Type.bodySmall, color = c.soft,
                        )
                        LmButton("Load laptop export", loadExport, dark = true, modifier = Modifier.fillMaxWidth())
                        LmButton("Save a link instead", { nav.goTab("add") }, modifier = Modifier.fillMaxWidth())
                    }
                }
            }
            return@LazyColumn
        }

        cont?.let { item ->
            item {
                Column(
                    Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(18.dp))
                        .background(c.inverse)
                        .clickable { nav.navigate("bookmark/${item.b.id}") }
                        .padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    Lbl("Continue" + (item.topicName?.let { " · $it" } ?: ""), color = c.inverseMuted)
                    Text(item.b.title, style = Type.title.copy(fontSize = 19.sp, lineHeight = 24.sp), color = c.onInverse,
                        maxLines = 3, overflow = TextOverflow.Ellipsis)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Pill("In progress", c.inverse, c.onInverse, c.inverseMuted)
                        Spacer(Modifier.weight(1f))
                        Text("Open →", style = Type.bodySmall, color = c.onInverse)
                    }
                }
            }
        }

        item {
            Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).border(1.dp, c.line, RoundedCornerShape(14.dp))) {
                Stat("To learn", "${counts["to_learn"] ?: 0}")
                Box(Modifier.width(1.dp).height(64.dp).background(c.line))
                Stat("Doing", "${counts["in_progress"] ?: 0}")
                Box(Modifier.width(1.dp).height(64.dp).background(c.line))
                Stat("Learned", "${counts["learned"] ?: 0}")
            }
        }

        if (upNext.isNotEmpty()) {
            item { SectionHeader("Up next · To learn", "${counts["to_learn"] ?: 0}") }
            items(upNext, key = { it.b.id }) { BookmarkRow(it, onClick = { nav.navigate("bookmark/${it.b.id}") }) }
        }

        item { SectionHeader("Topics", "All ${topics.size} →") { nav.goTab("topics") } }
        val shown = topics.sortedByDescending { it.inProgress * 10 + it.toLearn }.take(6)
        items(shown.chunked(2)) { pair ->
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                for (t in pair) MiniTopic(t, Modifier.weight(1f)) { nav.navigate("topic/${t.t.id}") }
                if (pair.size == 1) Spacer(Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun MiniTopic(t: TopicWithCounts, modifier: Modifier, onClick: () -> Unit) {
    val c = LocalLm.current
    Column(
        modifier
            .heightIn(min = 104.dp)
            .clip(RoundedCornerShape(14.dp))
            .background(c.pastel(t.t.color))
            .clickable(onClick = onClick)
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Text(t.t.name, style = Type.title.copy(fontSize = 14.sp, lineHeight = 18.sp), color = c.onPastel, maxLines = 2, overflow = TextOverflow.Ellipsis)
        Spacer(Modifier.weight(1f))
        Text("${t.total} saved · ${t.learned} learned".uppercase(), style = Type.label.copy(fontSize = 9.5.sp), color = c.onPastel.copy(alpha = 0.75f))
        ProgressBar(if (t.total == 0) 0f else t.learned / t.total.toFloat(), c.onPastel.copy(alpha = 0.12f), c.onPastel)
    }
}
