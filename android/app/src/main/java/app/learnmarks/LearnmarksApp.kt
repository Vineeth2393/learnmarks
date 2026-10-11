package app.learnmarks

import android.app.Application
import app.learnmarks.data.AppDatabase
import app.learnmarks.data.Repository
import app.learnmarks.sync.SyncEngine

class LearnmarksApp : Application() {
    val repository: Repository by lazy { Repository(AppDatabase.open(this)) }
    val sync: SyncEngine by lazy { SyncEngine(this, repository) }
}
