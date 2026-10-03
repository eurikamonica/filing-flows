package io.github.eurikamonica.filingflows

import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import java.io.IOException
import java.time.LocalDate
import java.time.ZoneOffset
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Every 30 minutes (when online): read the site's list of latest charts and notify about new ones that match
 * what the reader follows. No server push is involved; the site itself is the source.
 */
class ChartCheckWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val store = Store(applicationContext)
        val entries = try {
            ChartsRepo(applicationContext).refresh()             // also keeps the lists and the widget current offline
        } catch (e: IOException) {
            return@withContext Result.retry()
        }
        val (fresh, seen) = NewCharts.diff(store.seen(), entries, LocalDate.now(ZoneOffset.UTC))
        store.saveSeen(seen)
        val follows = store.follows()
        if (follows != null && follows.active) {
            Notifications.show(applicationContext, fresh.filter { follows.wants(it) })
        }
        FollowingWidget.updateAll(applicationContext)
        Result.success()
    }

    companion object {
        private const val NAME = "chart-check"

        fun schedule(context: Context) {
            val request = PeriodicWorkRequestBuilder<ChartCheckWorker>(30, TimeUnit.MINUTES)
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(NAME, ExistingPeriodicWorkPolicy.KEEP, request)
        }
    }
}
