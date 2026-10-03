package io.github.eurikamonica.filingflows

import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.abs
import kotlin.math.roundToInt

/** What the native lists show: pure functions over the site's list of latest charts, so they can be unit-tested. */
object Feed {
    private val newestFirst = compareByDescending<Entry> { it.filed }.thenByDescending { it.revenue }
    private val dateFormat = DateTimeFormatter.ofPattern("MMM d, yyyy", Locale.US)

    /** Charts of the companies and sectors the reader follows, newest filing first. */
    fun following(entries: List<Entry>, follows: Follows?): List<Entry> =
        if (follows == null) emptyList() else entries.filter { follows.matches(it) }.sortedWith(newestFirst)

    /**
     * Every company's latest chart; a query matches the ticker exactly first, then ticker or name. With SEC's company
     * list, a query also finds companies without a chart yet (after the charts, exact tickers first, at most maxOff).
     */
    fun search(entries: List<Entry>, query: String, companies: List<Entry> = emptyList(), maxOff: Int = 30): List<Entry> {
        val all = entries.sortedWith(newestFirst)
        val q = query.trim()
        if (q.isEmpty()) return all
        val ticker = normTicker(q)
        val exact = { e: Entry -> e.ticker.isNotEmpty() && normTicker(e.ticker) == ticker }
        val hit = { e: Entry -> exact(e) || e.ticker.contains(q, ignoreCase = true) || e.name.contains(q, ignoreCase = true) }
        val here = all.filter(hit)
        val have = entries.mapTo(HashSet()) { it.cik }
        val there = companies.asSequence().filter { it.cik !in have && hit(it) }.take(maxOff).toList()
        return here.filter(exact) + there.filter(exact) + here.filterNot(exact) + there.filterNot(exact)
    }

    /** For the home-screen widget: followed charts, or the newest charts when nothing is followed yet. */
    fun widget(entries: List<Entry>, follows: Follows?, n: Int = 3): Pair<Boolean, List<Entry>> {
        val mine = following(entries, follows)
        return if (mine.isNotEmpty()) true to mine.take(n) else false to search(entries, "").take(n)
    }

    fun date(iso: String): String = runCatching { LocalDate.parse(iso).format(dateFormat) }.getOrDefault(iso)

    fun title(e: Entry): String = listOf(e.ticker, e.name).filter { it.isNotBlank() }.joinToString(" · ")

    fun subtitle(e: Entry): String =
        if (!e.onSite) "No chart yet · open it to have it built"
        else listOf(e.label, e.form, if (e.filed.isNotBlank()) "filed ${date(e.filed)}" else "").filter { it.isNotBlank() }.joinToString(" · ")

    fun yoy(e: Entry): String? = e.yoy?.let { (if (it >= 0) "+" else "−") + abs(it).roundToInt() + "% Y/Y" }

    fun badge(e: Entry): String? = when {
        !e.onSite -> "no chart yet"
        e.prelim -> "8-K · preliminary"
        e.afterRelease != null -> if (e.releaseOk == false) "final · revised" else "final"
        else -> null
    }

    /** One line for the widget and the share text: "AAPL Q3 FY26 · $109.4B · +16% Y/Y". */
    fun line(e: Entry): String = if (!e.onSite) title(e) else
        listOfNotNull("${e.ticker.ifEmpty { e.name }} ${e.label}".trim(), e.rev.ifBlank { null }, yoy(e)).joinToString(" · ")
}
