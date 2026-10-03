package io.github.eurikamonica.filingflows

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/** Small on-device state: what the reader follows (from the website) and which charts were already seen. */
class Store(context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences("filing-flows", Context.MODE_PRIVATE)

    fun saveFollows(json: String?) {
        val clean = json?.trim()
        if (clean.isNullOrEmpty() || clean == "null") prefs.edit().remove(KEY_FOLLOWS).apply()
        else prefs.edit().putString(KEY_FOLLOWS, clean).apply()
    }

    fun follows(): Follows? {
        val raw = prefs.getString(KEY_FOLLOWS, null) ?: return null
        return runCatching {
            val o = JSONObject(raw)
            Follows(
                tickers = strings(o.optJSONArray("tickers")),
                sectors = strings(o.optJSONArray("sectors")),
                allAbove = o.optBoolean("all_above", false),
                minRevenue = o.optDouble("min_revenue", 1e9),
                starred = o.optBoolean("starred", false),
                pushOn = o.optBoolean("push_on", true),
                finalToo = o.optBoolean("final_too", true),
            )
        }.getOrNull()
    }

    fun seen(): Map<Long, String>? {
        val raw = prefs.getString(KEY_SEEN, null) ?: return null
        return runCatching {
            val o = JSONObject(raw)
            o.keys().asSequence().associate { it.toLong() to o.getString(it) }
        }.getOrNull()
    }

    fun saveSeen(seen: Map<Long, String>) {
        val o = JSONObject()
        seen.forEach { (cik, end) -> o.put(cik.toString(), end) }
        prefs.edit().putString(KEY_SEEN, o.toString()).apply()
    }

    private fun strings(a: JSONArray?): Set<String> =
        if (a == null) emptySet() else (0 until a.length()).map { a.optString(it) }.filter { it.isNotBlank() }.toSet()

    companion object {
        private const val KEY_FOLLOWS = "follows"
        private const val KEY_SEEN = "seen"

        /** data/index.json -> one entry per company (its latest chart). */
        fun parseIndex(json: String): List<Entry> {
            val list = JSONObject(json).getJSONArray("companies")
            return (0 until list.length()).map { i ->
                val o = list.getJSONObject(i)
                Entry(
                    cik = o.getLong("cik"),
                    ticker = o.optString("ticker", ""),
                    name = o.optString("name", ""),
                    sector = o.optString("sector", ""),
                    label = o.optString("label", ""),
                    end = o.optString("end", ""),
                    filed = o.optString("filed", ""),
                    form = o.optString("form", ""),
                    rev = o.optString("rev", ""),
                    revenue = o.optDouble("revenue", 0.0).let { if (it.isNaN()) 0.0 else it },
                    yoy = if (o.isNull("yoy")) null else o.optDouble("yoy").takeUnless { it.isNaN() },
                    om = if (o.isNull("om")) null else o.optDouble("om").takeUnless { it.isNaN() },
                    starred = o.optBoolean("starred", false),
                    afterRelease = if (o.isNull("after_release")) null else o.optString("after_release").ifEmpty { null },
                    releaseOk = if (o.has("release_ok") && !o.isNull("release_ok")) o.optBoolean("release_ok") else null,
                )
            }
        }
    }
}
