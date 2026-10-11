package app.learnmarks

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.lifecycle.lifecycleScope
import app.learnmarks.ui.AppShell
import app.learnmarks.ui.LearnmarksTheme
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val repo = (application as LearnmarksApp).repository
        lifecycleScope.launch { repo.ensureDevice() }
        val open = intent.getStringExtra(EXTRA_OPEN)
        val sync = (application as LearnmarksApp).sync
        setContent { LearnmarksTheme { AppShell(repo, sync, openBookmark = open) } }
    }

    companion object {
        /** Bookmark id to open on launch (e.g. "Already saved · Open it" from the share sheet). */
        const val EXTRA_OPEN = "app.learnmarks.OPEN_BOOKMARK"
    }
}
