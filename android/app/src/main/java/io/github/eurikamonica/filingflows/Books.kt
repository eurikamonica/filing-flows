package io.github.eurikamonica.filingflows

import java.time.LocalDate
import java.time.YearMonth
import java.time.format.DateTimeFormatter
import java.util.Locale

/*
 * Personal books: double-entry bookkeeping kept on the phone (no account, no server).
 * Every entry is a journal entry whose debits equal its credits. Everything else is computed from the entries:
 * the journal, T-accounts, the Sankey (income -> spending and savings) and the three statements.
 * Amounts are whole cents (Long), so sums are exact.
 */

/** The five kinds of account. Assets and expenses grow with debits; the others with credits. */
enum class Kind(val label: String, val debitNormal: Boolean) {
    ASSET("Assets", true), LIABILITY("Liabilities", false), EQUITY("Equity", false),
    INCOME("Income", false), EXPENSE("Expenses", true);
}

/**
 * What a balance-sheet account is, which decides where money moving through it lands in the cash flow statement.
 * Income and expense accounts use NONE.
 */
enum class Sub(val label: String, val kind: Kind?) {
    CASH("Cash & bank", Kind.ASSET),                  // counts as cash
    INVEST("Investments & property", Kind.ASSET),     // investing activities
    OTHER("Other assets", Kind.ASSET),                // deposits, money lent out: operating
    CARD("Credit card", Kind.LIABILITY),              // operating (it pays for spending)
    LOAN("Loan", Kind.LIABILITY),                     // financing
    CAPITAL("Capital", Kind.EQUITY),                  // opening balances: financing
    NONE("", null);

    companion object {
        fun forKind(k: Kind): List<Sub> = values().filter { it.kind == k }
        fun parse(s: String?): Sub = values().firstOrNull { it.name == s } ?: NONE
    }
}

enum class CashSection(val label: String) { OPERATING("Operating activities"), INVESTING("Investing activities"), FINANCING("Financing activities") }

data class Account(val id: String, val name: String, val kind: Kind, val sub: Sub = Sub.NONE, val archived: Boolean = false) {
    val isCash get() = kind == Kind.ASSET && sub == Sub.CASH
    val activity: CashSection
        get() = when (sub) {
            Sub.INVEST -> CashSection.INVESTING
            Sub.LOAN, Sub.CAPITAL -> CashSection.FINANCING
            else -> if (kind == Kind.EQUITY) CashSection.FINANCING else CashSection.OPERATING
        }

    /** A posting's effect on the balance, in the account's normal direction (a debit raises an asset). */
    fun normal(dr: Long, cr: Long): Long = if (kind.debitNormal) dr - cr else cr - dr
}

/** One line of a journal entry: either a debit or a credit, in cents. */
data class Line(val account: String, val dr: Long = 0, val cr: Long = 0)

/** A journal entry. type: how it was entered (expense, income, transfer, opening, journal). */
data class JournalEntry(val id: String, val date: String, val memo: String, val lines: List<Line>, val type: String = "journal",
                 val created: Long = 0) {
    val total: Long get() = lines.sumOf { it.dr }
}

/** A stretch of time; from or to null means open-ended. Dates are ISO strings (yyyy-MM-dd), compared as text. */
data class Period(val from: String?, val to: String?, val label: String) {
    fun has(date: String) = (from == null || date >= from) && (to == null || date <= to)

    companion object {
        private val MONTH = DateTimeFormatter.ofPattern("MMMM yyyy", Locale.US)
        fun month(m: YearMonth) = Period(m.atDay(1).toString(), m.atEndOfMonth().toString(), m.format(MONTH))
        fun year(y: Int) = Period(LocalDate.of(y, 1, 1).toString(), LocalDate.of(y, 12, 31).toString(), y.toString())
        fun all() = Period(null, null, "All time")
    }
}

data class Row(val name: String, val amount: Long, val account: String? = null)
data class Section(val title: String, val rows: List<Row>, val total: Long)

data class IncomeStatement(val period: Period, val income: List<Row>, val expenses: List<Row>) {
    val totalIncome get() = income.sumOf { it.amount }
    val totalExpenses get() = expenses.sumOf { it.amount }
    val net get() = totalIncome - totalExpenses
    /** Savings as a share of income, in percent (null without income). */
    val savingsRate: Double? get() = if (totalIncome > 0) net * 100.0 / totalIncome else null
}

data class BalanceSheet(val asOf: String?, val assets: List<Section>, val liabilities: List<Section>, val equity: List<Row>) {
    val totalAssets get() = assets.sumOf { it.total }
    val totalLiabilities get() = liabilities.sumOf { it.total }
    val totalEquity get() = equity.sumOf { it.amount }
    val balanced get() = totalAssets == totalLiabilities + totalEquity
    val netWorth get() = totalAssets - totalLiabilities
}

/**
 * Direct method: every entry with a cash or bank line moves cash; each of its other lines is the reason, classified by
 * that account (income and spending, credit cards: operating; investments and property: investing; loans and capital:
 * financing). Transfers between cash accounts cancel out. The reconciliation explains operating cash flow from savings.
 */
data class CashFlow(val period: Period, val opening: Long, val sections: List<Section>, val closing: Long,
                    val savings: Long, val workingCapital: Long, val nonCash: Long, val openingEntered: Long = 0) {
    val net get() = sections.sumOf { it.total }
    val operating get() = sections.firstOrNull { it.title == CashSection.OPERATING.label }?.total ?: 0L
    val balanced get() = opening + net == closing
}

data class Posting(val date: String, val memo: String, val other: String, val amount: Long, val entry: String)

data class TAccount(val account: Account, val opening: Long, val debits: List<Posting>, val credits: List<Posting>) {
    val totalDr get() = debits.sumOf { it.amount }
    val totalCr get() = credits.sumOf { it.amount }
    val closing get() = opening + account.normal(totalDr, totalCr)
}

/** Income -> spending and savings for the Sankey. drawn: spending beyond income, paid from savings or credit. */
data class MoneyFlow(val period: Period, val income: List<Row>, val expenses: List<Row>, val saved: Long, val drawn: Long,
                     val prevIncome: Map<String, Long> = emptyMap(), val prevExpenses: Map<String, Long> = emptyMap(),
                     val prevSaved: Long? = null) {
    val totalIncome get() = income.sumOf { it.amount }
    val totalExpenses get() = expenses.sumOf { it.amount }
    val total get() = totalIncome + drawn
}

class BookError(message: String) : Exception(message)

class Book(val accounts: List<Account>, val entries: List<JournalEntry>, val currency: String = "$") {
    private val byId: Map<String, Account> = accounts.associateBy { it.id }

    fun account(id: String): Account? = byId[id]
    fun name(id: String): String = byId[id]?.name ?: "?"

    // ------------------------------------------------------------ changes (each returns a new Book)
    fun validate(e: JournalEntry) {
        if (runCatching { LocalDate.parse(e.date) }.isFailure) throw BookError("Pick a date")
        if (e.lines.size < 2) throw BookError("An entry needs at least two lines")
        for (l in e.lines) {
            if (byId[l.account] == null) throw BookError("Pick an account on every line")
            if (l.dr < 0 || l.cr < 0 || (l.dr > 0) == (l.cr > 0)) throw BookError("Each line is either a debit or a credit, above zero")
        }
        val dr = e.lines.sumOf { it.dr }
        val cr = e.lines.sumOf { it.cr }
        if (dr != cr) throw BookError("Debits (${money(dr)}) must equal credits (${money(cr)})")
        if (e.lines.map { it.account }.toSet().size < 2) throw BookError("Use at least two different accounts")
    }

    fun put(e: JournalEntry): Book {
        validate(e)
        val rest = entries.filter { it.id != e.id }
        return Book(accounts, rest + e, currency)
    }

    fun remove(id: String) = Book(accounts, entries.filter { it.id != id }, currency)

    fun putAccount(a: Account): Book {
        if (a.name.isBlank()) throw BookError("Give the account a name")
        if (accounts.any { it.id != a.id && it.name.equals(a.name.trim(), ignoreCase = true) && !it.archived })
            throw BookError("There is already an account called ${a.name.trim()}")
        val old = byId[a.id]
        if (old != null && old.kind != a.kind && used(a.id)) throw BookError("An account with entries keeps its kind")
        val clean = a.copy(name = a.name.trim(), sub = if (a.sub.kind == a.kind) a.sub else defaultSub(a.kind))
        return Book(if (old == null) accounts + clean else accounts.map { if (it.id == a.id) clean else it }, entries, currency)
    }

    /** Unused accounts are deleted; used ones are archived (hidden from the forms, kept in the books). */
    fun dropAccount(id: String): Book =
        if (used(id)) Book(accounts.map { if (it.id == id) it.copy(archived = true) else it }, entries, currency)
        else Book(accounts.filter { it.id != id }, entries, currency)

    fun used(id: String) = entries.any { e -> e.lines.any { it.account == id } }

    fun withCurrency(c: String) = Book(accounts, entries, c.trim().take(4).ifEmpty { "$" })

    // ------------------------------------------------------------ reading
    fun inPeriod(p: Period): List<JournalEntry> = entries.filter { p.has(it.date) }.sortedWith(compareBy({ it.date }, { it.created }, { it.id }))

    /** Balance in the account's normal direction, including entries up to and including `upTo` (null: all). */
    fun balance(id: String, upTo: String?): Long {
        val a = byId[id] ?: return 0
        var dr = 0L
        var cr = 0L
        for (e in entries) if (upTo == null || e.date <= upTo) for (l in e.lines) if (l.account == id) { dr += l.dr; cr += l.cr }
        return a.normal(dr, cr)
    }

    private fun movement(id: String, p: Period): Long {
        val a = byId[id] ?: return 0
        var dr = 0L
        var cr = 0L
        for (e in entries) if (p.has(e.date)) for (l in e.lines) if (l.account == id) { dr += l.dr; cr += l.cr }
        return a.normal(dr, cr)
    }

    private fun dayBefore(date: String?): String? = date?.let { LocalDate.parse(it).minusDays(1).toString() }

    fun incomeStatement(p: Period): IncomeStatement {
        fun rows(k: Kind) = accounts.filter { it.kind == k }.map { Row(it.name, movement(it.id, p), it.id) }
            .filter { it.amount != 0L }.sortedByDescending { it.amount }
        return IncomeStatement(p, rows(Kind.INCOME), rows(Kind.EXPENSE))
    }

    fun balanceSheet(asOf: String?): BalanceSheet {
        fun section(sub: Sub, title: String = sub.label): Section? {
            val rows = accounts.filter { it.sub == sub && (it.kind == sub.kind) }.map { Row(it.name, balance(it.id, asOf), it.id) }
                .filter { it.amount != 0L }
            return if (rows.isEmpty()) null else Section(title, rows, rows.sumOf { it.amount })
        }
        val assets = listOfNotNull(section(Sub.CASH), section(Sub.INVEST), section(Sub.OTHER))
        val liabilities = listOfNotNull(section(Sub.CARD, "Credit cards"), section(Sub.LOAN, "Loans"))
        val retained = accounts.filter { it.kind == Kind.INCOME || it.kind == Kind.EXPENSE }.sumOf {
            val b = balance(it.id, asOf)
            if (it.kind == Kind.INCOME) b else -b
        }
        val capital = accounts.filter { it.kind == Kind.EQUITY }.map { Row(it.name, balance(it.id, asOf), it.id) }.filter { it.amount != 0L }
        val equity = capital + (if (retained != 0L || capital.isEmpty()) listOf(Row("Accumulated savings", retained)) else emptyList())
        return BalanceSheet(asOf, assets, liabilities, equity)
    }

    fun cashFlow(p: Period): CashFlow {
        val cash = accounts.filter { it.isCash }.map { it.id }.toSet()
        val start = dayBefore(p.from)
        var opening = if (start == null) 0L else cash.sumOf { balance(it, start) }
        val closing = cash.sumOf { balance(it, p.to) }
        var entered = 0L
        val by = LinkedHashMap<CashSection, LinkedHashMap<String, Long>>()
        CashSection.values().forEach { by[it] = LinkedHashMap() }
        var savings = 0L
        var opBalances = 0L
        var operating = 0L
        for (e in entries) {
            if (!p.has(e.date)) continue
            if (isOpening(e)) {                                // where the books start: not a flow, part of the starting cash
                val c = e.lines.filter { it.account in cash }.sumOf { it.dr - it.cr }
                opening += c
                entered += c
                continue
            }
            val touchesCash = e.lines.any { it.account in cash }
            for (l in e.lines) {
                val a = byId[l.account] ?: continue
                val effect = l.cr - l.dr                       // what this line did to cash (+ in, - out)
                if (a.kind == Kind.INCOME || a.kind == Kind.EXPENSE) savings += effect
                if (!a.isCash && a.activity == CashSection.OPERATING && (a.kind == Kind.ASSET || a.kind == Kind.LIABILITY)) opBalances += effect
                if (!touchesCash || a.isCash) continue
                val m = by.getValue(a.activity)
                m[a.id] = (m[a.id] ?: 0L) + effect
                if (a.activity == CashSection.OPERATING) operating += effect
            }
        }
        val sections = by.map { (act, m) ->
            val rows = m.filterValues { it != 0L }.map { (id, v) -> Row(name(id), v, id) }.sortedByDescending { it.amount }
            Section(act.label, rows, rows.sumOf { it.amount })
        }
        return CashFlow(p, opening, sections, closing, savings, opBalances, operating - savings - opBalances, entered)
    }

    /** An opening balance: entered as one, or any entry whose other side is only equity (capital). */
    fun isOpening(e: JournalEntry): Boolean = e.type == "opening" ||
        e.lines.filter { byId[it.account]?.isCash != true }.let { rest -> rest.isNotEmpty() && rest.all { byId[it.account]?.kind == Kind.EQUITY } }

    fun tAccounts(p: Period): List<TAccount> {
        val start = dayBefore(p.from)
        val order = Kind.values().toList()
        val list = inPeriod(p)
        return accounts.sortedWith(compareBy({ order.indexOf(it.kind) }, { it.sub.ordinal })).mapNotNull { a ->
            val dr = ArrayList<Posting>()
            val cr = ArrayList<Posting>()
            for (e in list) for (l in e.lines) if (l.account == a.id) {
                val other = e.lines.filter { it.account != a.id && (if (l.dr > 0) it.cr > 0 else it.dr > 0) }
                    .map { name(it.account) }.distinct().joinToString(", ").ifEmpty { e.lines.filter { it.account != a.id }.map { name(it.account) }.distinct().joinToString(", ") }
                if (l.dr > 0) dr += Posting(e.date, e.memo, other, l.dr, e.id)
                if (l.cr > 0) cr += Posting(e.date, e.memo, other, l.cr, e.id)
            }
            val opening = if (start == null || a.kind == Kind.INCOME || a.kind == Kind.EXPENSE) 0L else balance(a.id, start)
            if (dr.isEmpty() && cr.isEmpty() && opening == 0L) null else TAccount(a, opening, dr, cr)
        }
    }

    /** Income lines -> total -> spending lines and savings; small lines grouped so the chart stays readable. */
    fun moneyFlow(p: Period, prev: Period? = null, maxIncome: Int = 5, maxExpenses: Int = 7): MoneyFlow {
        val st = incomeStatement(p)
        // a negative income line (a loss) is spending, a negative expense line (refunds above spending) is income
        val inc = st.income.filter { it.amount > 0 } + st.expenses.filter { it.amount < 0 }.map { it.copy(amount = -it.amount) }
        val exp = st.expenses.filter { it.amount > 0 } + st.income.filter { it.amount < 0 }.map { it.copy(amount = -it.amount) }
        val income = group(inc.sortedByDescending { it.amount }, maxIncome, "income lines")
        val expenses = group(exp.sortedByDescending { it.amount }, maxExpenses, "expenses")
        val net = income.sumOf { it.amount } - expenses.sumOf { it.amount }
        val before = prev?.let { incomeStatement(it) }
        return MoneyFlow(p, income, expenses, maxOf(net, 0L), maxOf(-net, 0L),
            before?.income?.associate { (it.account ?: it.name) to it.amount } ?: emptyMap(),
            before?.expenses?.associate { (it.account ?: it.name) to it.amount } ?: emptyMap(),
            before?.net)
    }

    private fun group(rows: List<Row>, max: Int, noun: String): List<Row> =
        if (rows.size <= max) rows
        else rows.take(max - 1) + Row("${rows.size - max + 1} other $noun", rows.drop(max - 1).sumOf { it.amount })

    /** The journal as CSV (one row per line), for a spreadsheet. */
    fun csv(p: Period): String {
        val sb = StringBuilder("date,entry,memo,account,kind,debit,credit\n")
        fun q(s: String) = if (s.any { it == ',' || it == '"' || it == '\n' }) "\"" + s.replace("\"", "\"\"") + "\"" else s
        fun amt(c: Long) = if (c == 0L) "" else plain(c)
        for (e in inPeriod(p)) for (l in e.lines) {
            val a = byId[l.account]
            sb.append(listOf(e.date, e.id, q(e.memo), q(a?.name ?: l.account), a?.kind?.label ?: "", amt(l.dr), amt(l.cr)).joinToString(","))
            sb.append('\n')
        }
        return sb.toString()
    }

    fun money(cents: Long, sign: Boolean = true): String = Money.format(cents, currency, sign)

    companion object {
        fun defaultSub(k: Kind): Sub = when (k) {
            Kind.ASSET -> Sub.CASH
            Kind.LIABILITY -> Sub.CARD
            Kind.EQUITY -> Sub.CAPITAL
            else -> Sub.NONE
        }

        fun plain(cents: Long): String {
            val a = Math.abs(cents)
            return (if (cents < 0) "-" else "") + "${a / 100}.${(a % 100).toString().padStart(2, '0')}"
        }

        /** The accounts a new book starts with; add, rename or archive them under Accounts. */
        fun starter(currency: String = "$"): Book {
            val a = listOf(
                Account("cash", "Cash", Kind.ASSET, Sub.CASH),
                Account("checking", "Checking account", Kind.ASSET, Sub.CASH),
                Account("savings", "Savings account", Kind.ASSET, Sub.CASH),
                Account("invest", "Investments", Kind.ASSET, Sub.INVEST),
                Account("card", "Credit card", Kind.LIABILITY, Sub.CARD),
                Account("loan", "Loans", Kind.LIABILITY, Sub.LOAN),
                Account("opening", "Opening balances", Kind.EQUITY, Sub.CAPITAL),
                Account("salary", "Salary", Kind.INCOME),
                Account("bonus", "Bonus", Kind.INCOME),
                Account("interest-in", "Interest & dividends", Kind.INCOME),
                Account("other-in", "Other income", Kind.INCOME),
                Account("housing", "Housing", Kind.EXPENSE),
                Account("food", "Food & dining", Kind.EXPENSE),
                Account("transport", "Transport", Kind.EXPENSE),
                Account("shopping", "Shopping", Kind.EXPENSE),
                Account("utilities", "Utilities & phone", Kind.EXPENSE),
                Account("health", "Health", Kind.EXPENSE),
                Account("fun", "Entertainment", Kind.EXPENSE),
                Account("travel", "Travel", Kind.EXPENSE),
                Account("education", "Education", Kind.EXPENSE),
                Account("insurance", "Insurance", Kind.EXPENSE),
                Account("taxes", "Taxes", Kind.EXPENSE),
                Account("interest-out", "Interest paid", Kind.EXPENSE),
                Account("other-out", "Other spending", Kind.EXPENSE),
            )
            return Book(a, emptyList(), currency)
        }
    }
}

/** Ready-made entries: each kind of everyday event as its journal entry. */
object Journal {
    /** Spending: Dr the expense, Cr where the money came from (cash, bank or credit card). */
    fun expense(id: String, date: String, memo: String, amount: Long, expense: String, from: String, created: Long = 0) =
        JournalEntry(id, date, memo, listOf(Line(expense, dr = amount), Line(from, cr = amount)), "expense", created)

    /** Income: Dr where it arrived, Cr the income account. */
    fun income(id: String, date: String, memo: String, amount: Long, income: String, into: String, created: Long = 0) =
        JournalEntry(id, date, memo, listOf(Line(into, dr = amount), Line(income, cr = amount)), "income", created)

    /** Moving money between balance-sheet accounts: saving, investing, paying a card, borrowing, repaying a loan. */
    fun transfer(id: String, date: String, memo: String, amount: Long, from: String, to: String, created: Long = 0) =
        JournalEntry(id, date, memo, listOf(Line(to, dr = amount), Line(from, cr = amount)), "transfer", created)

    /** What an account held (or owed) when the books start, against Opening balances (equity). */
    fun opening(id: String, date: String, book: Book, account: String, amount: Long, equity: String, created: Long = 0): JournalEntry {
        val a = book.account(account) ?: throw BookError("Pick an account")
        val up = if (amount < 0) -amount else amount
        val lines = if (a.kind.debitNormal == (amount >= 0)) listOf(Line(account, dr = up), Line(equity, cr = up))
        else listOf(Line(equity, dr = up), Line(account, cr = up))
        return JournalEntry(id, date, "Opening balance: ${a.name}", lines, "opening", created)
    }

    /** One month of made-up entries to explore the views with (the current month). */
    fun example(book: Book, month: YearMonth, idOf: (Int) -> String): Book {
        var b = book
        var n = 0
        fun d(day: Int) = month.atDay(minOf(day, month.lengthOfMonth())).toString()
        fun c(units: Long) = units * 100
        fun add(e: JournalEntry) { b = b.put(e) }
        val start = month.atDay(1).toString()
        val equity = b.accounts.firstOrNull { it.kind == Kind.EQUITY }?.id ?: "opening"
        for ((acc, amt) in listOf("checking" to c(4200), "savings" to c(12000), "invest" to c(18500), "cash" to c(150),
                                    "card" to c(640), "loan" to c(9000))) {
            if (b.account(acc) != null) add(opening(idOf(n++), start, b, acc, amt, equity, n.toLong()))
        }
        val ex = listOf(
            Triple(1, "Rent", Triple(c(1800), "housing", "checking")), Triple(2, "Groceries", Triple(c(126), "food", "card")),
            Triple(4, "Metro card", Triple(c(60), "transport", "card")), Triple(6, "Dinner with friends", Triple(c(85), "food", "card")),
            Triple(8, "Electricity and phone", Triple(c(140), "utilities", "checking")), Triple(10, "Groceries", Triple(c(118), "food", "card")),
            Triple(12, "Concert tickets", Triple(c(95), "fun", "card")), Triple(15, "Running shoes", Triple(c(130), "shopping", "card")),
            Triple(17, "Coffee", Triple(c(24), "food", "cash")), Triple(18, "Doctor visit", Triple(c(60), "health", "checking")),
            Triple(20, "Online course", Triple(c(49), "education", "card")), Triple(22, "Groceries", Triple(c(131), "food", "card")),
            Triple(24, "Health insurance", Triple(c(210), "insurance", "checking")), Triple(26, "Taxi", Triple(c(32), "transport", "card")),
        )
        add(income(idOf(n++), d(1), "Salary", c(6200), "salary", "checking", n.toLong()))
        add(income(idOf(n++), d(15), "Freelance design job", c(450), "other-in", "checking", n.toLong()))
        add(income(idOf(n++), d(28), "Savings interest", c(31), "interest-in", "savings", n.toLong()))
        add(income(idOf(n++), d(28), "Dividends", c(64), "interest-in", "invest", n.toLong()))
        for ((day, memo, t) in ex) if (b.account(t.second) != null && b.account(t.third) != null)
            add(expense(idOf(n++), d(day), memo, t.first, t.second, t.third, n.toLong()))
        add(transfer(idOf(n++), d(5), "Pay last month's credit card", c(640), "checking", "card", n.toLong()))
        add(transfer(idOf(n++), d(3), "Cash from ATM", c(100), "checking", "cash", n.toLong()))
        add(transfer(idOf(n++), d(25), "Monthly saving", c(1000), "checking", "savings", n.toLong()))
        add(transfer(idOf(n++), d(25), "Buy index fund", c(800), "checking", "invest", n.toLong()))
        add(JournalEntry(idOf(n++), d(27), "Loan payment", listOf(Line("loan", dr = c(310)), Line("interest-out", dr = c(40)),
            Line("checking", cr = c(350))), "journal", n.toLong()))
        return b
    }
}

object Money {
    /** 1234567 -> "$12,345.67"; negative with a true minus sign. */
    fun format(cents: Long, currency: String, sign: Boolean = true): String {
        val a = Math.abs(cents)
        val whole = (a / 100).toString().reversed().chunked(3).joinToString(",").reversed()
        return (if (cents < 0 && sign) "−" else "") + currency + whole + "." + (a % 100).toString().padStart(2, '0')
    }

    /** Chart labels: whole units with separators ("$6,264"); below 10 with cents ("$4.50"). */
    fun label(cents: Long, currency: String): String {
        val a = Math.abs(cents)
        val s = if (a < 1000) String.format(Locale.US, "%.2f", a / 100.0) else String.format(Locale.US, "%,d", Math.round(a / 100.0))
        return (if (cents < 0) "\u2212" else "") + currency + s
    }

    /** Short form for chart labels: $12.3K, $1.2M, $850. */
    fun short(cents: Long, currency: String): String {
        val v = Math.abs(cents) / 100.0
        val s = when {
            v >= 999_500 -> String.format(Locale.US, "%.1fM", v / 1e6)
            v >= 9_995 -> String.format(Locale.US, "%.1fK", v / 1e3)
            v >= 100 -> String.format(Locale.US, "%,.0f", v)
            else -> String.format(Locale.US, "%.2f", v)
        }
        return (if (cents < 0) "−" else "") + currency + s
    }

    /** "12.50", "12,50", "1,234.5" or "1234" -> cents; null when it is not a positive amount. */
    fun parse(text: String): Long? {
        var t = text.trim().replace(" ", "").replace(" ", "")
        t = t.filter { it.isDigit() || it == '.' || it == ',' }
        if (t.isEmpty()) return null
        val lastDot = t.lastIndexOf('.')
        val lastComma = t.lastIndexOf(',')
        val decimal = when {
            lastDot >= 0 && lastComma >= 0 -> if (lastDot > lastComma) '.' else ','
            lastComma >= 0 && t.length - lastComma - 1 in 1..2 -> ','
            lastDot >= 0 && t.count { it == '.' } == 1 -> '.'
            else -> null
        }
        val clean = if (decimal == null) t.replace(",", "").replace(".", "")
        else t.replace(if (decimal == '.') "," else ".", "").replace(decimal, '.')
        val v = clean.toBigDecimalOrNull() ?: return null
        val cents = v.movePointRight(2).setScale(0, java.math.RoundingMode.HALF_UP).toLong()
        return if (cents > 0) cents else null
    }

    /** "+12%" / "−3%" change against an earlier amount, or null when either is not above zero. */
    fun change(now: Long, before: Long?): String? {
        if (before == null || before <= 0 || now <= 0) return null
        val g = Math.round((now.toDouble() / before - 1) * 100)
        return (if (g > 0) "+" else if (g < 0) "−" else "") + Math.abs(g) + "%"
    }
}
