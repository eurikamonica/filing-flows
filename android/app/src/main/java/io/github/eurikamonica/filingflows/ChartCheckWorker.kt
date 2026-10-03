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
import java.net.HttpURLConnection
import java.net.URL
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
            Store.parseIndex(fetch(BuildConfig.SITE_URL + "data/index.json"))
        } catch (e: IOException) {
            return@withContext Result.retry()
        } catch (e: org.json.JSONException) {
            return@withContext Result.retry()
        }
        val (fresh, seen) = NewCharts.diff(store.seen(), entries, LocalDate.now(ZoneOffset.UTC))
        store.saveSeen(seen)
        val follows = store.follows()
        if (follows != null && follows.active) {
            Notifications.show(applicationContext, fresh.filter { follows.wants(it) })
        }
        Result.success()
    }

    private fun fetch(url: String): String {
        val c = URL(url).openConnection() as HttpURLConnection
        c.connectTimeout = 20_000
        c.readTimeout = 30_000
        c.setRequestProperty("Cache-Control", "no-cache")
        c.setRequestProperty("User-Agent", "FilingFlowsApp/${BuildConfig.VERSION_NAME}")
        try {
            if (c.responseCode != 200) throw IOException("HTTP ${c.responseCode}")
            return c.inputStream.bufferedReader().use { it.readText() }
        } finally {
            c.disconnect()
        }
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
