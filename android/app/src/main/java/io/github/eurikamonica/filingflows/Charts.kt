package io.github.eurikamonica.filingflows

import java.time.LocalDate
import java.time.temporal.ChronoUnit
import kotlin.math.abs
import kotlin.math.roundToInt

/** One company's latest chart, as listed in the site's data/index.json. */
data class Entry(
    val cik: Long,
    val ticker: String,
    val name: String,
    val sector: String,
    val label: String,
    val end: String,
    val filed: String,
    val form: String,
    val rev: String,
    val revenue: Double,
    val yoy: Double?,
    val om: Double?,
    val starred: Boolean,
    val afterRelease: String? = null,      // filing date of the 8-K whose preliminary chart this 10-Q/10-K replaces
    val releaseOk: Boolean? = null,        // the release's figures matched the filing
) {
    val prelim: Boolean get() = form == "8-K"
}

/** A chart to announce; final = the 10-Q/10-K version of a quarter first seen as an 8-K chart. */
data class Fresh(val entry: Entry, val final: Boolean)

/** What the reader follows; saved by the website through the app bridge, same fields as the alerts settings. */
data class Follows(
    val tickers: Set<String> = emptySet(),
    val sectors: Set<String> = emptySet(),
    val allAbove: Boolean = false,
    val minRevenue: Double = 1e9,
    val starred: Boolean = false,
    val pushOn: Boolean = true,
    val finalToo: Boolean = true,          // after an 8-K chart, also announce the 10-Q/10-K version
) {
    /** Follows anything at all (for the native lists). */
    val any: Boolean
        get() = tickers.isNotEmpty() || sectors.isNotEmpty() || allAbove || starred

    /** Wants notifications. */
    val active: Boolean
        get() = pushOn && any

    fun matches(e: Entry): Boolean =
        (e.ticker.isNotEmpty() && normTicker(e.ticker) in tickers.map(::normTicker)) ||
            e.sector in sectors ||
            (allAbove && e.revenue >= minRevenue) ||
            (starred && e.starred)

    fun wants(f: Fresh): Boolean = matches(f.entry) && (!f.final || finalToo)
}

fun normTicker(t: String): String = t.trim().uppercase().replace('.', '-')

object NewCharts {
    const val MAX_AGE_DAYS = 3L
    const val SAME_QUARTER_DAYS = 10L      // an 8-K quarter and the 10-Q/10-K that replaces it are one chart

    /**
     * seen: company CIK -> "quarter end" of the chart already known, with "|8-K" for an earnings-release chart
     * (null on the very first check). Returns the charts to announce and the updated map.
     * The first check only records what exists.
     */
    fun diff(seen: Map<Long, String>?, entries: List<Entry>, today: LocalDate): Pair<List<Fresh>, Map<Long, String>> {
        val next = (seen ?: emptyMap()).toMutableMap()
        val fresh = mutableListOf<Fresh>()
        for (e in entries) {
            val mark = e.end + if (e.prelim) "|8-K" else ""
            val prev = seen?.get(e.cik)
            next[e.cik] = mark
            if (seen == null || prev == mark) continue
            var final = false
            if (prev != null) {
                val prevEnd = prev.substringBefore('|')
                val sameQuarter = abs(days(prevEnd, e.end)) <= SAME_QUARTER_DAYS
                if (sameQuarter && (e.prelim || !prev.endsWith("|8-K"))) continue    // nothing new about the quarter
                final = sameQuarter                                                   // 8-K chart -> 10-Q/10-K
            }
            val age = runCatching { ChronoUnit.DAYS.between(LocalDate.parse(e.filed), today) }.getOrDefault(Long.MAX_VALUE)
            if (age <= MAX_AGE_DAYS) fresh += Fresh(e, final)
        }
        fresh.sortWith(compareByDescending<Fresh> { it.entry.filed }.thenByDescending { it.entry.revenue })
        return fresh to next
    }

    private fun days(a: String, b: String): Long =
        runCatching { ChronoUnit.DAYS.between(LocalDate.parse(a), LocalDate.parse(b)) }.getOrDefault(Long.MAX_VALUE)

    private fun pct(v: Double): String = (if (v >= 0) "+" else "−") + abs(v).roundToInt() + "%"

    fun title(e: Entry, final: Boolean = false): String =
        listOf(e.ticker.ifEmpty { e.name }, e.label).joinToString(" ") + (if (final) " final" else "") +
            ": revenue ${e.rev}" + (e.yoy?.let { " (${pct(it)} Y/Y)" } ?: "")

    fun text(e: Entry, final: Boolean = false): String {
        val form = when {
            e.prelim -> "earnings release (8-K), preliminary"
            final || e.afterRelease != null -> e.form + when (e.releaseOk) {
                true -> ", matches the earnings release"
                false -> ", revises the earnings release"
                null -> ", replaces the earnings-release chart"
            }
            else -> e.form
        }
        return listOfNotNull(e.name, form, e.om?.let { String.format(java.util.Locale.US, "operating margin %.1f%%", it) }).joinToString(" · ")
    }
}
