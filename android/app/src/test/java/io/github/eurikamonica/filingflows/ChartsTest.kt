package io.github.eurikamonica.filingflows

import java.time.LocalDate
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ChartsTest {
    private fun entry(cik: Long, ticker: String, end: String, filed: String, sector: String = "technology",
                      revenue: Double = 5e9, starred: Boolean = false, form: String = "10-Q") =
        Entry(cik, ticker, "$ticker Inc.", sector, "Q3 FY26", end, filed, form, "$5.0B", revenue, 12.4, 21.0, starred)

    private val today = LocalDate.parse("2026-09-25")

    @Test
    fun firstCheckOnlyRecords() {
        val (fresh, seen) = NewCharts.diff(null, listOf(entry(1, "AAA", "2026-08-31", "2026-09-24")), today)
        assertTrue(fresh.isEmpty())
        assertEquals("2026-08-31", seen[1L])
    }

    @Test
    fun newQuarterIsAnnouncedOnce() {
        val seen = mapOf(1L to "2026-05-31")
        val e = entry(1, "AAA", "2026-08-31", "2026-09-24")
        val (fresh, next) = NewCharts.diff(seen, listOf(e), today)
        assertEquals(listOf(Fresh(e, false)), fresh)
        assertTrue(NewCharts.diff(next, listOf(e), today).first.isEmpty())
    }

    @Test
    fun tenQAfterEightKIsAnnouncedAsFinalUnlessTurnedOff() {
        val seen = mapOf(1L to "2026-08-30|8-K")
        val tenQ = entry(1, "AAA", "2026-08-30", "2026-09-24").copy(afterRelease = "2026-09-20", releaseOk = false)
        val (fresh, next) = NewCharts.diff(seen, listOf(tenQ), today)
        assertEquals(listOf(Fresh(tenQ, true)), fresh)
        assertEquals("2026-08-30", next[1L])
        assertTrue(Follows(tickers = setOf("AAA")).wants(fresh[0]))
        assertFalse(Follows(tickers = setOf("AAA"), finalToo = false).wants(fresh[0]))
        assertEquals("AAA Q3 FY26 final: revenue \$5.0B (+12% Y/Y)", NewCharts.title(tenQ, true))
        assertEquals("AAA Inc. · 10-Q, revises the earnings release · operating margin 21.0%", NewCharts.text(tenQ, true))
        // the same 8-K seen again, or a 10-Q seen again, is nothing new
        assertTrue(NewCharts.diff(mapOf(1L to "2026-08-30|8-K"), listOf(entry(1, "AAA", "2026-08-30", "2026-09-24", form = "8-K")), today).first.isEmpty())
        assertTrue(NewCharts.diff(next, listOf(tenQ), today).first.isEmpty())
    }

    @Test
    fun oldFilingsAndNewCompaniesFiledLongAgoAreSkipped() {
        val (fresh, _) = NewCharts.diff(emptyMap(), listOf(entry(2, "BBB", "2026-06-30", "2026-08-01")), today)
        assertTrue(fresh.isEmpty())
    }

    @Test
    fun followsMatchTickersSectorsSizeAndStars() {
        val brk = entry(3, "BRK-B", "2026-06-30", "2026-09-24", sector = "financials", revenue = 9e10)
        assertTrue(Follows(tickers = setOf("brk.b")).matches(brk))
        assertTrue(Follows(sectors = setOf("financials")).matches(brk))
        assertTrue(Follows(allAbove = true, minRevenue = 5e10).matches(brk))
        assertFalse(Follows(allAbove = true, minRevenue = 1e11).matches(brk))
        assertFalse(Follows(starred = true).matches(brk))
        assertTrue(Follows(starred = true).matches(brk.copy(starred = true)))
        assertFalse(Follows(tickers = setOf("AAPL"), pushOn = false).active)
    }

    @Test
    fun notificationText() {
        val e = entry(1, "AAA", "2026-08-31", "2026-09-24", form = "8-K")
        assertEquals("AAA Q3 FY26: revenue \$5.0B (+12% Y/Y)", NewCharts.title(e))
        assertEquals("AAA Inc. · earnings release (8-K), preliminary · operating margin 21.0%", NewCharts.text(e))
    }
}
