package io.github.eurikamonica.filingflows

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class FeedTest {
    private fun e(cik: Long, ticker: String, name: String, filed: String, revenue: Double = 5e9, sector: String = "technology",
                  form: String = "10-Q", yoy: Double? = 12.4) =
        Entry(cik, ticker, name, sector, "Q3 FY26", "2026-08-31", filed, form, "$5.0B", revenue, yoy, 21.0, false)

    private val list = listOf(
        e(1, "AAPL", "Apple Inc.", "2026-07-31", revenue = 9e10),
        e(2, "MU", "Micron Technology", "2026-09-24", form = "8-K"),
        e(3, "BRK-B", "Berkshire Hathaway", "2026-08-02", sector = "financials", yoy = -3.2),
        e(4, "MSFT", "Microsoft", "2026-07-31", revenue = 7e10),
    )

    @Test
    fun followingIsNewestFirstAndOnlyWhatIsFollowed() {
        val f = Follows(tickers = setOf("aapl", "MSFT", "MU"))
        assertEquals(listOf(2L, 1L, 4L), Feed.following(list, f).map { it.cik })
        assertTrue(Feed.following(list, null).isEmpty())
    }

    @Test
    fun searchPutsTheExactTickerFirst() {
        assertEquals(listOf(2L, 3L, 1L, 4L), Feed.search(list, "").map { it.cik })
        assertEquals(listOf(2L), Feed.search(list, "mu").take(1).map { it.cik })
        assertEquals(listOf(3L), Feed.search(list, "brk.b").map { it.cik })
        assertEquals(listOf(1L), Feed.search(list, "apple").map { it.cik })
    }

    @Test
    fun widgetFallsBackToNewestCharts() {
        assertEquals(false to listOf(2L, 3L, 1L), Feed.widget(list, null).let { it.first to it.second.map { x -> x.cik } })
        assertEquals(true to listOf(3L), Feed.widget(list, Follows(sectors = setOf("financials"))).let { it.first to it.second.map { x -> x.cik } })
    }

    @Test
    fun labels() {
        assertEquals("Q3 FY26 · 10-Q · filed Jul 31, 2026", Feed.subtitle(list[0]))
        assertEquals("−3% Y/Y", Feed.yoy(list[2]))
        assertEquals("8-K · preliminary", Feed.badge(list[1]))
        assertEquals("final · revised", Feed.badge(list[0].copy(afterRelease = "2026-07-20", releaseOk = false)))
        assertEquals("AAPL Q3 FY26 · \$5.0B · +12% Y/Y", Feed.line(list[0]))
        assertEquals("AAPL · Apple Inc.", Feed.title(list[0]))
    }
}
