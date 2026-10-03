package io.github.eurikamonica.filingflows

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/** The site's list of latest charts (data/index.json), kept on the phone so the lists and the widget work offline. */
class ChartsRepo(context: Context) {
    private val app = context.applicationContext
    private val file = File(app.filesDir, "index.json")

    fun cached(): List<Entry> = runCatching { Store.parseIndex(file.readText()) }.getOrDefault(emptyList())

    /** Milliseconds since the cached list was saved (Long.MAX_VALUE when there is none). */
    fun age(): Long = if (file.exists()) System.currentTimeMillis() - file.lastModified() else Long.MAX_VALUE

    /** Downloads the list, saves it and returns it. Throws IOException when offline or the site is unreachable. */
    fun refresh(): List<Entry> {
        val text = Net.get(BuildConfig.SITE_URL + "data/index.json")
        val entries = try {
            Store.parseIndex(text)
        } catch (e: org.json.JSONException) {
            throw IOException("unreadable chart list", e)
        }
        file.writeText(text)
        return entries
    }
}

object Net {
    fun get(url: String): String {
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

    fun online(context: Context): Boolean {
        val cm = context.getSystemService(ConnectivityManager::class.java) ?: return true
        val caps = cm.getNetworkCapabilities(cm.activeNetwork) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }
}
