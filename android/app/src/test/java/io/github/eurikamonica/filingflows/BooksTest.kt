package io.github.eurikamonica.filingflows

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.time.YearMonth

class BooksTest {
    private val oct = Period.month(YearMonth.of(2026, 10))
    private val sep = Period.month(YearMonth.of(2026, 9))

    /** September: opening balances; October: a month of everyday entries. */
    private fun book(): Book {
        var b = Book.starter("$")
        var n = 0
        fun id() = "e${n++}"
        fun add(e: JournalEntry) { b = b.put(e) }
        add(Journal.opening(id(), "2026-09-01", b, "checking", 300000, "opening"))
        add(Journal.opening(id(), "2026-09-01", b, "card", 50000, "opening"))
        add(Journal.opening(id(), "2026-09-01", b, "loan", 900000, "opening"))
        add(Journal.opening(id(), "2026-09-01", b, "invest", 1000000, "opening"))
        add(Journal.income(id(), "2026-09-30", "September pay", 500000, "salary", "checking"))
        add(Journal.income(id(), "2026-10-01", "Salary", 620000, "salary", "checking"))
        add(Journal.expense(id(), "2026-10-02", "Rent", 180000, "housing", "checking"))
        add(Journal.expense(id(), "2026-10-03", "Groceries", 12600, "food", "card"))
        add(Journal.expense(id(), "2026-10-04", "Coffee, beans", 2400, "food", "cash"))
        add(Journal.transfer(id(), "2026-10-03", "ATM", 10000, "checking", "cash"))
        add(Journal.transfer(id(), "2026-10-05", "Pay the card", 50000, "checking", "card"))
        add(Journal.transfer(id(), "2026-10-25", "Index fund", 80000, "checking", "invest"))
        add(Journal.income(id(), "2026-10-28", "Dividends", 6400, "interest-in", "invest"))
        add(JournalEntry(id(), "2026-10-27", "Loan payment", listOf(Line("loan", dr = 31000), Line("interest-out", dr = 4000),
            Line("checking", cr = 35000))))
        return b
    }

    @Test
    fun entriesMustBalance() {
        val b = Book.starter()
        for (bad in listOf(
            JournalEntry("x", "2026-10-01", "", listOf(Line("food", dr = 100), Line("cash", cr = 90))),
            JournalEntry("x", "2026-10-01", "", listOf(Line("food", dr = 100))),
            JournalEntry("x", "2026-10-01", "", listOf(Line("food", dr = 100, cr = 100), Line("cash", cr = 0))),
            JournalEntry("x", "2026-10-01", "", listOf(Line("food", dr = 100), Line("food", cr = 100))),
            JournalEntry("x", "not a date", "", listOf(Line("food", dr = 100), Line("cash", cr = 100))),
            JournalEntry("x", "2026-10-01", "", listOf(Line("nope", dr = 100), Line("cash", cr = 100))),
        )) {
            try {
                b.put(bad)
                fail("accepted $bad")
            } catch (e: BookError) {
                assertTrue(e.message!!.isNotEmpty())
            }
        }
        assertEquals(1, b.put(Journal.expense("x", "2026-10-01", "Lunch", 1250, "food", "cash")).entries.size)
    }

    @Test
    fun incomeStatementIsTheMonthOnly() {
        val s = book().incomeStatement(oct)
        assertEquals(626400L, s.totalIncome)                         // salary + dividends, not September's pay
        assertEquals(199000L, s.totalExpenses)                       // rent, groceries, coffee, loan interest
        assertEquals(427400L, s.net)
        assertEquals("Salary", s.income.first().name)
        assertEquals(68.2, s.savingsRate!!, 0.05)
    }

    @Test
    fun balanceSheetBalances() {
        val b = book()
        val bs = b.balanceSheet(oct.to)
        assertTrue(bs.balanced)
        assertEquals(bs.totalAssets, bs.totalLiabilities + bs.totalEquity)
        // checking: 3000 + 5000 + 6200 - 1800 - 100 - 500 - 800 - 350 = 10,650.00
        assertEquals(1065000L, b.balance("checking", oct.to))
        assertEquals(12600L, b.balance("card", oct.to))               // 500 owed, paid, then 126 of groceries
        val saved = bs.equity.first { it.name == "Accumulated savings" }.amount
        assertEquals(500000L + 427400L, saved)                        // September's pay and October's savings
        assertEquals(bs.totalAssets - bs.totalLiabilities, bs.netWorth)
        assertTrue(b.balanceSheet(sep.to).balanced)
    }

    @Test
    fun cashFlowExplainsTheChangeInCash() {
        val cf = book().cashFlow(oct)
        assertTrue(cf.balanced)
        assertEquals(800000L, cf.opening)                             // checking 3000 + 5000 at the end of September
        val byName = cf.sections.associate { it.title to it.rows.associate { r -> r.name to r.amount } }
        val op = byName.getValue(CashSection.OPERATING.label)
        assertEquals(620000L, op["Salary"])
        assertEquals(-50000L, op["Credit card"])                      // paying the card is operating cash out
        assertEquals(-2400L, op["Food & dining"])                     // coffee paid in cash (groceries went on the card)
        assertEquals(-80000L, byName.getValue(CashSection.INVESTING.label)["Investments"])
        assertEquals(-31000L, byName.getValue(CashSection.FINANCING.label)["Loans"])
        assertNull(op["Cash"])                                        // ATM: cash to cash, no flow
        // savings + change in card balance + non-cash income (dividends kept in the brokerage) = operating cash flow
        assertEquals(cf.operating, cf.savings + cf.workingCapital + cf.nonCash)
        assertEquals(-6400L, cf.nonCash)
        assertEquals(12600L - 50000L, cf.workingCapital)
        assertEquals(cf.opening + cf.net, cf.closing)
    }

    @Test
    fun tAccountsOpenWithTheBalanceBroughtForward() {
        val ts = book().tAccounts(oct).associateBy { it.account.id }
        val checking = ts.getValue("checking")
        assertEquals(800000L, checking.opening)
        assertEquals(1065000L, checking.closing)
        assertEquals(listOf(620000L), checking.debits.map { it.amount })
        assertEquals("Salary", checking.debits.first().other)
        assertEquals(5, checking.credits.size)
        val food = ts.getValue("food")
        assertEquals(0L, food.opening)                               // income and expense accounts start each period at zero
        assertEquals(15000L, food.closing)
        assertTrue("savings" !in ts)                                  // no balance, no activity: left out
    }

    @Test
    fun moneyFlowSplitsIncomeIntoSpendingAndSavings() {
        val f = book().moneyFlow(oct, sep)
        assertEquals(626400L, f.totalIncome)
        assertEquals(f.totalIncome, f.totalExpenses + f.saved)
        assertEquals(0L, f.drawn)
        assertEquals(500000L, f.prevIncome["salary"])
        assertEquals(500000L, f.prevSaved)
        // a month spending more than it earned: the gap comes from savings, nothing is negative
        var b = book()
        b = b.put(Journal.expense("big", "2026-10-30", "New laptop", 900000, "shopping", "card"))
        val g = b.moneyFlow(oct)
        assertEquals(0L, g.saved)
        assertEquals(g.totalExpenses - g.totalIncome, g.drawn)
        assertEquals(g.total, g.totalExpenses)
        // many small lines are grouped
        var many = Book.starter()
        many.accounts.filter { it.kind == Kind.EXPENSE }.forEachIndexed { i, a ->
            many = many.put(Journal.expense("m$i", "2026-10-02", a.name, 1000L + i, a.id, "cash"))
        }
        val h = many.moneyFlow(oct)
        assertEquals(7, h.expenses.size)
        assertEquals("7 other expenses", h.expenses.last().name)
        assertEquals(many.incomeStatement(oct).totalExpenses, h.totalExpenses)
    }

    @Test
    fun exampleMonthIsConsistent() {
        var n = 0
        val b = Journal.example(Book.starter(), YearMonth.of(2026, 10)) { "x${n++}" }
        assertTrue(b.entries.size > 20)
        assertTrue(b.balanceSheet(oct.to).balanced)
        assertTrue(b.cashFlow(oct).balanced)
        val cf = b.cashFlow(oct)
        assertEquals(cf.operating, cf.savings + cf.workingCapital + cf.nonCash)
        // opening balances entered in the month are where the cash starts, not money flowing in from "financing"
        assertEquals(1635000L, cf.opening)                         // checking 4,200 + savings 12,000 + cash 150
        assertEquals(1635000L, cf.openingEntered)
        assertTrue(cf.sections.flatMap { it.rows }.none { it.name == "Opening balances" })
        assertEquals(-6400L, cf.nonCash)                           // dividends kept in the brokerage account
        assertEquals(82600L - 64000L, cf.workingCapital)           // spending on the card, less paying last month's bill
    }

    @Test
    fun accountsAreArchivedNotLostWhenUsed() {
        val b = book()
        val a = b.dropAccount("food")
        assertTrue(a.account("food")!!.archived)
        assertEquals(b.incomeStatement(oct).totalExpenses, a.incomeStatement(oct).totalExpenses)
        assertNull(b.dropAccount("travel").account("travel"))
        try {
            b.putAccount(Account("new", "salary", Kind.INCOME))
            fail("duplicate name accepted")
        } catch (e: BookError) { }
        try {
            b.putAccount(b.account("food")!!.copy(kind = Kind.INCOME))
            fail("kind of a used account changed")
        } catch (e: BookError) { }
        val pet = b.putAccount(Account("pet", " Pet care ", Kind.EXPENSE, Sub.CASH)).account("pet")!!
        assertEquals("Pet care", pet.name)
        assertEquals(Sub.NONE, pet.sub)
    }

    @Test
    fun moneyIsFormattedAndParsed() {
        assertEquals("$1,234.50", Money.format(123450, "$"))
        assertEquals("−¥0.07", Money.format(-7, "¥"))
        assertEquals("$12.3K", Money.short(1234567, "$"))
        assertEquals("$850", Money.short(85000, "$"))
        assertEquals(1250L, Money.parse("12.5"))
        assertEquals(1250L, Money.parse("12,50"))
        assertEquals(123450L, Money.parse("1,234.5"))
        assertEquals(123400L, Money.parse("1,234"))
        assertEquals(500L, Money.parse("¥5"))
        assertNull(Money.parse("0"))
        assertNull(Money.parse("abc"))
        assertEquals("+12%", Money.change(112, 100))
        assertEquals("−3%", Money.change(97, 100))
        assertNull(Money.change(10, 0))
    }

    @Test
    fun csvHasOneRowPerLine() {
        val csv = book().csv(oct).trim().lines()
        assertEquals("date,entry,memo,account,kind,debit,credit", csv.first())
        assertTrue(csv.any { it.contains("\"Coffee, beans\"") })
        assertEquals(1 + book().inPeriod(oct).sumOf { it.lines.size }, csv.size)
    }

    @Test
    fun jsonRoundTrip() {
        val b = book().withCurrency("€").dropAccount("food").putAccount(Account("pet", "Pet care", Kind.EXPENSE))
        val back = BooksJson.read(BooksJson.write(b))
        assertEquals(b.accounts, back.accounts)
        assertEquals(b.entries, back.entries)
        assertEquals("€", back.currency)
    }
}

class MoneySankeyTest {
    private val measure = { s: String, size: Float -> s.length * size * 0.56f }

    private fun check(l: SkLayout) {
        // every node's bands carry exactly its value; nothing leaves the canvas; labels in a column never overlap
        val total = l.nodes.first { it.id == "total" }
        assertEquals(total.value, l.bands.filter { it.to == "total" }.sumOf { it.value })
        assertEquals(total.value, l.bands.filter { it.from == "total" }.sumOf { it.value })
        for (n in l.nodes) {
            assertTrue("${n.id} inside", n.y >= 0f && n.y + n.h <= l.height && n.x >= 0f && n.x + n.w <= l.width)
            assertTrue("${n.id} label inside", n.label.top >= 0f && n.label.top + n.label.height <= l.height)
        }
        for (col in listOf(0, 2)) {
            val ls = l.nodes.filter { it.col == col }.map { it.label }
            for (i in 1 until ls.size) assertTrue("labels overlap in column $col", ls[i].top >= ls[i - 1].top + ls[i - 1].height)
        }
        for (b in l.bands) assertTrue(b.w >= 0f && b.x1 > b.x0)
    }

    @Test
    fun layoutKeepsFlowsAndLabelsApart() {
        var n = 0
        val b = Journal.example(Book.starter(), YearMonth.of(2026, 10)) { "x${n++}" }
        val f = b.moneyFlow(Period.month(YearMonth.of(2026, 10)), Period.month(YearMonth.of(2026, 9)))
        for (w in listOf(1080f, 1440f, 720f)) check(MoneySankey.layout(f, "$", w, w / 360f, w / 360f, "Sep", measure))
        val l = MoneySankey.layout(f, "$", 1080f, 3f, 3f, "Sep", measure)
        assertEquals("Saved", l.nodes.first { it.col == 2 }.label.lines[0])         // savings on top
        assertTrue(l.nodes.first { it.id == "saved" }.label.lines[1].matches(Regex("\\$[0-9,]+ · [0-9.]+%")))
    }

    @Test
    fun spendingMoreThanIncomeShowsSavingsUsed() {
        val f = MoneyFlow(Period.all(), listOf(Row("Salary", 300000, "salary")),
            listOf(Row("Travel", 450000, "travel"), Row("Housing", 180000, "housing")), 0, 330000)
        val l = MoneySankey.layout(f, "¥", 1080f, 3f, 3f, null, measure)
        check(l)
        assertTrue(l.nodes.any { it.id == "drawn" && it.tone == Tone.DRAWN && it.col == 0 })
        assertTrue(l.nodes.none { it.id == "saved" })
        assertEquals("Income + savings used", l.nodes.first { it.id == "total" }.label.lines[0])
        assertTrue(MoneySankey.layout(MoneyFlow(Period.all(), emptyList(), emptyList(), 0, 0), "$", 1080f, 3f, 3f, null, measure).empty)
    }

    @Test
    fun relaxSpreadsCrowdedLabels() {
        // three labels that all want to sit near 100 are spread around their average; the fourth stays put
        val t = MoneySankey.relax(listOf(100f, 101f, 102f, 400f), listOf(30f, 30f, 30f, 30f), 0f, 4f).map { it.toDouble() }
        assertEquals(67.0, t[0], 0.01)
        assertEquals(t[0] + 34.0, t[1], 0.01)
        assertEquals(t[1] + 34.0, t[2], 0.01)
        assertEquals(400.0, t[3], 0.01)
        assertEquals(0.0, MoneySankey.relax(listOf(-50f, -40f), listOf(30f, 30f), 0f, 4f)[0].toDouble(), 0.01)
    }
}
