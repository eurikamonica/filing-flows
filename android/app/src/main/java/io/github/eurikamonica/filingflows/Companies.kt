package io.github.eurikamonica.filingflows

import org.json.JSONObject

/**
 * SEC's list of companies with a ticker (the site's data/companies.json, rows of [cik, ticker, name], largest first),
 * so the search also finds companies the site has not drawn yet; their page offers "Build its charts".
 */
object Companies {
    fun parse(json: String): List<Entry> {
        val rows = JSONObject(json).getJSONArray("companies")
        return (0 until rows.length()).mapNotNull { i ->
            val r = rows.optJSONArray(i) ?: return@mapNotNull null
            val cik = r.optLong(0, 0L)
            if (cik <= 0L) null else offSite(cik, r.optString(1, ""), r.optString(2, ""))
        }
    }

    fun offSite(cik: Long, ticker: String, name: String): Entry =
        Entry(cik, ticker, name, "", "", "", "", "", "", 0.0, null, null, false, onSite = false)
}
