package app.learnmarks.ui

import android.net.Uri
import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import app.learnmarks.data.ExportFile
import app.learnmarks.data.Repository
import app.learnmarks.sync.SyncEngine
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.IOException

val LocalRepo = staticCompositionLocalOf<Repository> { error("Repository not provided") }
val LocalSnack = staticCompositionLocalOf<(String) -> Unit> { {} }
val LocalSync = staticCompositionLocalOf<SyncEngine> { error("SyncEngine not provided") }

private data class Tab(val route: String, val label: String, val icon: androidx.compose.ui.graphics.vector.ImageVector)

private val TABS = listOf(
    Tab("home", "Home", LmIcons.home),
    Tab("topics", "Topics", LmIcons.topics),
    Tab("add", "Add", LmIcons.add),
    Tab("search", "Search", LmIcons.search),
    Tab("sync", "Sync", LmIcons.sync),
)

@Composable
fun AppShell(repo: Repository, sync: SyncEngine, openBookmark: String? = null) {
    val nav = rememberNavController()
    val snack = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()
    val pending by repo.pendingCount().collectAsStateWithLifecycle(0)
    val c = LocalLm.current
    val current by nav.currentBackStackEntryAsState()
    val route = current?.destination?.route

    CompositionLocalProvider(LocalRepo provides repo, LocalSync provides sync, LocalSnack provides { msg -> scope.launch { snack.showSnackbar(msg) } }) {
        Scaffold(
            containerColor = c.canvas,
            snackbarHost = { SnackbarHost(snack) },
            bottomBar = {
                NavigationBar(containerColor = c.surface, tonalElevation = androidx.compose.ui.unit.Dp(0f)) {
                    for (tab in TABS) {
                        NavigationBarItem(
                            selected = route == tab.route,
                            onClick = { nav.goTab(tab.route) },
                            icon = {
                                if (tab.route == "sync" && pending > 0) {
                                    BadgedBox(badge = { Badge(containerColor = c.inverse, contentColor = c.onInverse) { Text("$pending") } }) {
                                        Icon(tab.icon, null)
                                    }
                                } else Icon(tab.icon, null)
                            },
                            label = { Text(tab.label, style = Type.meta) },
                            colors = NavigationBarItemDefaults.colors(
                                selectedIconColor = c.ink, selectedTextColor = c.ink, indicatorColor = c.active,
                                unselectedIconColor = c.muted, unselectedTextColor = c.muted,
                            ),
                        )
                    }
                }
            },
        ) { inner ->
            Box(Modifier.padding(inner)) {
                androidx.compose.runtime.LaunchedEffect(openBookmark) {
                    if (openBookmark != null) nav.navigate("bookmark/$openBookmark")
                }
                NavHost(nav, startDestination = "home") {
                    composable("home") { HomeScreen(nav) }
                    composable("topics") { TopicsScreen(nav) }
                    composable("topic/{id}") { TopicScreen(nav, it.arguments?.getString("id") ?: "") }
                    composable("search") { SearchScreen(nav) }
                    composable("add") { AddScreen(nav) }
                    composable("sync") { SyncScreen() }
                    composable("bookmark/{id}") { BookmarkScreen(nav, it.arguments?.getString("id") ?: "") }
                }
            }
        }
    }
}

fun NavHostController.goTab(route: String) = navigate(route) {
    popUpTo(graph.findStartDestination().id) { saveState = true }
    launchSingleTop = true
    restoreState = true
}

/** Opens the system file picker for a "Download export" file and loads it as the laptop's data. */
@Composable
fun rememberExportLoader(): () -> Unit {
    val repo = LocalRepo.current
    val snack = LocalSnack.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri: Uri? ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            val message = withContext(Dispatchers.IO) {
                try {
                    val name = context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)
                        ?.use { if (it.moveToFirst()) it.getString(0) else null } ?: "export file"
                    val bytes = context.contentResolver.openInputStream(uri)?.use { input ->
                        val buf = input.readNBytes(ExportFile.MAX_BYTES + 1)
                        if (buf.size > ExportFile.MAX_BYTES) throw ExportFile.Invalid("The file is larger than 20 MB.")
                        buf
                    } ?: throw IOException("Couldn't open the file")
                    val result = repo.loadSnapshot(ExportFile.parse(bytes.toString(Charsets.UTF_8)), name)
                    buildString {
                        append("Loaded ${result.bookmarks} bookmarks")
                        if (result.pendingKept > 0) append(" · kept ${result.pendingKept} phone changes")
                        if (result.skipped > 0) append(" · ${result.skipped} skipped")
                    }
                } catch (e: ExportFile.Invalid) {
                    e.message ?: "Not a Learnmarks export"
                } catch (e: IOException) {
                    "Couldn't read the file: ${e.message}"
                }
            }
            snack(message)
        }
    }
    return { launcher.launch(arrayOf("application/json", "text/plain", "application/octet-stream")) }
}
