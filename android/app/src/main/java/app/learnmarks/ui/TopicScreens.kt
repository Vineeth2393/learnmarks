package app.learnmarks.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavHostController
import app.learnmarks.data.TopicWithCounts

@Composable
fun TopicsScreen(nav: NavHostController) {
    val repo = LocalRepo.current
    val c = LocalLm.current
    val groups by repo.groups().collectAsStateWithLifecycle(emptyList())
    val topics by repo.topicsWithCounts().collectAsStateWithLifecycle(emptyList())
    val sections = groups.map { g -> g.name to topics.filter { it.t.groupId == g.id } } +
        listOf("Other topics" to topics.filter { t -> t.t.groupId == null || groups.none { it.id == t.t.groupId } })

    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Lbl("Library · ${topics.size} topics")
            Text("Topics", style = Type.heading, color = c.ink, modifier = Modifier.padding(top = 4.dp))
        }
        if (topics.isEmpty()) item { Text("No topics yet. Load the laptop export from Home or Sync.", style = Type.body, color = c.soft) }
        for ((name, list) in sections) {
            if (list.isEmpty()) continue
            item(key = "h-$name") { SectionHeader("Track · $name", "${list.sumOf { it.total }} bookmarks") }
            itemsIndexed(list, key = { _, t -> t.t.id }) { i, t -> TopicCard(t, i + 1, i) { nav.navigate("topic/${t.t.id}") } }
        }
    }
}

@Composable
private fun TopicCard(t: TopicWithCounts, number: Int, pattern: Int, onClick: () -> Unit) {
    val c = LocalLm.current
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(c.pastel(t.t.color)).clickable(onClick = onClick).padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        TopicCover(c.pastel(t.t.color), number.toString().padStart(2, '0'), pattern = pattern)
        Text(t.t.name, style = Type.title.copy(fontSize = 18.sp, lineHeight = 22.sp), color = c.onPastel)
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("${t.total} saved · ${t.learned} learned · ${t.inProgress} doing".uppercase(), style = Type.label.copy(fontSize = 9.5.sp),
                color = c.onPastel.copy(alpha = 0.75f), modifier = Modifier.weight(1f))
            Text("Open →", style = Type.bodySmall, color = c.onPastel)
        }
        ProgressBar(if (t.total == 0) 0f else t.learned / t.total.toFloat(), c.onPastel.copy(alpha = 0.12f), c.onPastel)
    }
}

@Composable
fun TopicScreen(nav: NavHostController, topicId: String) {
    val repo = LocalRepo.current
    val c = LocalLm.current
    val topic by repo.topic(topicId).collectAsStateWithLifecycle(null)
    val items by repo.topicBookmarks(topicId).collectAsStateWithLifecycle(emptyList())
    var filter by rememberSaveable { mutableStateOf("all") }
    val shown = if (filter == "all") items else items.filter { it.b.status == filter }
    val t = topic

    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(start = 18.dp, end = 18.dp, bottom = 18.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = { nav.popBackStack() }) { Icon(LmIcons.back, "Back", tint = c.ink) }
                Lbl("Topic · learning order", Modifier.weight(1f))
            }
        }
        if (t == null) return@LazyColumn
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(t.name, style = Type.headingMono, color = c.ink)
                t.description?.let { Text(it, style = Type.body, color = c.soft) }
            }
        }
        item {
            Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), horizontalArrangement = Arrangement.spacedBy(3.dp)) {
                for (b in items) {
                    val color = when (b.b.status) { "to_learn" -> c.todoLine; "in_progress" -> c.ink; "learned" -> androidx.compose.ui.graphics.Color(0xFF5FAF7E); else -> c.lineStrong }
                    Box(Modifier.weight(1f).height(8.dp).clip(RoundedCornerShape(3.dp)).background(color))
                }
            }
        }
        item {
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                ToggleChip("All ${items.size}", filter == "all", { filter = "all" })
                for (s in STATUSES) ToggleChip("${STATUS_LABEL[s]} ${items.count { it.b.status == s }}", filter == s, { filter = s })
            }
        }
        if (shown.isEmpty()) item { Text(if (items.isEmpty()) "No bookmarks in this topic yet." else "Nothing with this status.", style = Type.body, color = c.soft) }
        items(shown, key = { it.b.id }) { item ->
            BookmarkRow(item, onClick = { nav.navigate("bookmark/${item.b.id}") }, number = items.indexOf(item) + 1, showTopic = false)
        }
    }
}
