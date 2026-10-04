package io.github.eurikamonica.filingflows

import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.text.TextUtils
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.core.content.ContextCompat
import com.google.android.material.button.MaterialButton
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import java.time.LocalDate
import java.time.YearMonth
import java.time.format.DateTimeFormatter
import java.util.Locale

private fun View.dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()
private fun View.color(id: Int): Int = ContextCompat.getColor(context, id)

/** What the Money tab needs from the activity: sharing a file it made, and picking a backup to restore. */
interface MoneyHost {
    fun shareMoneyFile(name: String, mime: String, text: String)
    fun pickMoneyBackup()
}

/**
 * The Money tab: personal books kept on this phone, no sign-in. Journal are journal entries (debits = credits);
 * the tab shows them as the journal, T-accounts, a Sankey of income into spending and savings, and the three statements.
 */
class MoneyView(context: Context, private val host: MoneyHost) : FrameLayout(context) {
    private enum class Scope { MONTH, YEAR, ALL }
    private enum class Page { JOURNAL, TACCOUNTS, SANKEY, STATEMENTS }
    private enum class Stmt { INCOME, BALANCE, CASH }

    private val store = BooksStore(context)
    private var book: Book = store.load()
    private var scope = Scope.MONTH
    private var month: YearMonth = YearMonth.now()
    private var page = Page.JOURNAL
    private var stmt = Stmt.INCOME
    private val body = LinearLayout(context)
    private val scroll = ScrollView(context)
    private val periodLabel = TextView(context)
    private val prevBtn = TextView(context)
    private val nextBtn = TextView(context)
    private val stmtSeg: Seg
    private val forms = MoneyForms(context, { book }, { save(it) })

    init {
        setBackgroundColor(color(R.color.ground))
        val column = LinearLayout(context)
        column.orientation = LinearLayout.VERTICAL

        val head = LinearLayout(context)
        head.orientation = LinearLayout.HORIZONTAL
        head.gravity = Gravity.CENTER_VERTICAL
        head.setPadding(dp(16), dp(10), dp(8), 0)
        val title = TextView(context)
        title.text = "Money"
        title.textSize = 20f
        title.setTypeface(title.typeface, Typeface.BOLD)
        title.setTextColor(color(R.color.ink))
        head.addView(title, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        head.addView(link("Accounts") { forms.accounts { render() } })
        head.addView(link("More") { more() })
        column.addView(head)

        val note = TextView(context)
        note.text = "Kept on this phone only · no sign-in"
        note.textSize = 12.5f
        note.setTextColor(color(R.color.muted))
        note.setPadding(dp(16), 0, dp(16), dp(8))
        column.addView(note)

        val periodRow = LinearLayout(context)
        periodRow.orientation = LinearLayout.HORIZONTAL
        periodRow.gravity = Gravity.CENTER_VERTICAL
        periodRow.setPadding(dp(16), 0, dp(16), dp(8))
        val scopeSeg = Seg(context, listOf("Month", "Year", "All"), 0) { scope = Scope.values()[it]; render() }
        periodRow.addView(scopeSeg, LinearLayout.LayoutParams(dp(150), ViewGroup.LayoutParams.WRAP_CONTENT))
        val spacer = View(context)
        periodRow.addView(spacer, LinearLayout.LayoutParams(0, 1, 1f))
        for (b in listOf(prevBtn, nextBtn)) {
            b.textSize = 18f
            b.setTextColor(color(R.color.ink))
            b.setPadding(dp(8), dp(2), dp(8), dp(4))
            b.isClickable = true
        }
        prevBtn.text = "‹"
        nextBtn.text = "›"
        prevBtn.contentDescription = "Previous"
        nextBtn.contentDescription = "Next"
        prevBtn.setOnClickListener { step(-1) }
        nextBtn.setOnClickListener { step(1) }
        periodLabel.textSize = 13.5f
        periodLabel.maxLines = 1
        periodLabel.setTextColor(color(R.color.ink))
        periodLabel.setTypeface(periodLabel.typeface, Typeface.BOLD)
        periodRow.addView(prevBtn)
        periodRow.addView(periodLabel)
        periodRow.addView(nextBtn)
        column.addView(periodRow)

        val pageSeg = Seg(context, listOf("Journal", "T-accounts", "Sankey", "Statements"), 0) { page = Page.values()[it]; render() }
        val plp = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        plp.setMargins(dp(16), 0, dp(16), dp(6))
        column.addView(pageSeg, plp)
        stmtSeg = Seg(context, listOf("Income", "Balance sheet", "Cash flow"), 0) { stmt = Stmt.values()[it]; render() }
        val slp = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        slp.setMargins(dp(16), 0, dp(16), dp(6))
        column.addView(stmtSeg, slp)

        body.orientation = LinearLayout.VERTICAL
        body.setPadding(dp(16), dp(4), dp(16), dp(96))
        scroll.addView(body, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        column.addView(scroll, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        addView(column, LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))

        val add = MaterialButton(context)
        add.text = "+  Add entry"
        add.cornerRadius = dp(28)
        add.backgroundTintList = ColorStateList.valueOf(color(R.color.accent))
        add.setTextColor(color(R.color.paper))
        add.elevation = dp(4).toFloat()
        add.setPadding(dp(20), dp(12), dp(20), dp(12))
        add.setOnClickListener { forms.chooseNew() }
        val alp = LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.BOTTOM or Gravity.END)
        alp.setMargins(dp(16), dp(16), dp(16), dp(16))
        addView(add, alp)
        render()
    }

    // ---------------------------------------------------------------- state
    private fun save(b: Book) {
        book = b
        try {
            store.save(b)
        } catch (e: Exception) {
            Toast.makeText(context, "Could not save: ${e.message}", Toast.LENGTH_LONG).show()
        }
        render()
    }

    private fun period(): Period = when (scope) {
        Scope.MONTH -> Period.month(month)
        Scope.YEAR -> Period.year(month.year)
        Scope.ALL -> Period.all()
    }

    private fun previous(): Period? = when (scope) {
        Scope.MONTH -> Period.month(month.minusMonths(1))
        Scope.YEAR -> Period.year(month.year - 1)
        Scope.ALL -> null
    }

    private fun prevName(): String? = when (scope) {
        Scope.MONTH -> month.minusMonths(1).format(DateTimeFormatter.ofPattern("MMM", Locale.US))
        Scope.YEAR -> (month.year - 1).toString()
        Scope.ALL -> null
    }

    private fun step(d: Int) {
        month = if (scope == Scope.YEAR) month.plusYears(d.toLong()) else month.plusMonths(d.toLong())
        render()
    }

    /** Called by the activity with the text of a backup file the reader picked. */
    fun restore(text: String) {
        val b = try {
            BooksJson.read(text)
        } catch (e: Exception) {
            Toast.makeText(context, "That file is not a Money backup", Toast.LENGTH_LONG).show()
            return
        }
        MaterialAlertDialogBuilder(context)
            .setTitle("Restore this backup?")
            .setMessage("It has ${b.entries.size} entries and ${b.accounts.size} accounts. It replaces the books on this phone " +
                "(${book.entries.size} entries).")
            .setPositiveButton("Restore") { _, _ -> save(b) }
            .setNegativeButton("Cancel", null)
            .show()
    }

    fun refresh() {
        book = store.load()
        render()
    }

    // ---------------------------------------------------------------- pages
    private fun render() {
        val p = period()
        periodLabel.text = p.label
        val stepping = scope != Scope.ALL
        prevBtn.visibility = if (stepping) View.VISIBLE else View.GONE
        nextBtn.visibility = if (stepping) View.VISIBLE else View.GONE
        stmtSeg.visibility = if (page == Page.STATEMENTS) View.VISIBLE else View.GONE
        body.removeAllViews()
        if (book.entries.isEmpty()) {
            welcome()
            return
        }
        when (page) {
            Page.JOURNAL -> journal(p)
            Page.TACCOUNTS -> tAccounts(p)
            Page.SANKEY -> sankey(p)
            Page.STATEMENTS -> when (stmt) {
                Stmt.INCOME -> incomeStatement(p)
                Stmt.BALANCE -> balanceSheet(p)
                Stmt.CASH -> cashFlow(p)
            }
        }
    }

    private fun welcome() {
        body.addView(text("Your books are empty", 18f, bold = true), wrap(top = 12))
        body.addView(text("Start with what you have today: opening balances for your cash, bank accounts, investments, credit " +
            "cards and loans. Then add income and spending as it happens. Each one is recorded as a journal entry " +
            "(debits = credits), and the journal, T-accounts, Sankey and statements follow from them.", 14.5f, muted = true), wrap(top = 6))
        body.addView(button("Set opening balances") { forms.opening(null) }, wrap(top = 16))
        body.addView(button("Add an entry") { forms.chooseNew() }, wrap(top = 8))
        body.addView(button("Try an example month") { example() }, wrap(top = 8))
    }

    private fun emptyPeriod(p: Period) {
        body.addView(text("No entries in ${p.label}.", 15f), wrap(top = 16))
        body.addView(button("Add an entry") { forms.chooseNew() }, wrap(top = 12))
    }

    private fun journal(p: Period) {
        val list = book.inPeriod(p)
        if (list.isEmpty()) return emptyPeriod(p)
        val total = list.sumOf { it.total }
        body.addView(text("${list.size} ${if (list.size == 1) "entry" else "entries"} · debits = credits = ${book.money(total)}",
            13f, muted = true), wrap(top = 4, bottom = 6))
        body.addView(row3("Account", "Debit", "Credit", size = 12f, muted = true))
        for (e in list) {
            val card = card()
            val top = LinearLayout(context)
            top.orientation = LinearLayout.HORIZONTAL
            val date = text(day(e.date), 13f, bold = true)
            top.addView(date, LinearLayout.LayoutParams(dp(56), ViewGroup.LayoutParams.WRAP_CONTENT))
            val memo = text(e.memo.ifBlank { kindWord(e.type) }, 14f)
            memo.maxLines = 2
            memo.ellipsize = TextUtils.TruncateAt.END
            top.addView(memo, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            card.addView(top)
            for (l in e.lines.sortedBy { if (it.dr > 0) 0 else 1 }) {
                val name = book.name(l.account)
                card.addView(row3(if (l.dr > 0) name else "      $name", amt(l.dr), amt(l.cr), size = 13.5f))
            }
            card.setOnClickListener { forms.details(e) }
            body.addView(card, wrap(top = 8))
        }
    }

    private fun tAccounts(p: Period) {
        val ts = book.tAccounts(p)
        if (ts.isEmpty()) return emptyPeriod(p)
        body.addView(text("Each account as a T: debits on the left, credits on the right. Balance-sheet accounts open with " +
            "the balance brought forward; income and spending start each period at zero.", 13f, muted = true), wrap(top = 4, bottom = 4))
        var kind: Kind? = null
        for (t in ts) {
            if (t.account.kind != kind) {
                kind = t.account.kind
                body.addView(eyebrow(kind.label), wrap(top = 14))
            }
            body.addView(tCard(t), wrap(top = 8))
        }
    }

    private fun tCard(t: TAccount): View {
        val a = t.account
        val card = card()
        val head = LinearLayout(context)
        head.orientation = LinearLayout.HORIZONTAL
        head.addView(text(a.name + if (a.archived) " (archived)" else "", 15f, bold = true),
            LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        head.addView(text(a.sub.label.ifEmpty { a.kind.label }, 12f, muted = true))
        card.addView(head)
        val bar = View(context)
        bar.setBackgroundColor(color(R.color.ink))
        card.addView(bar, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(2)).also { it.topMargin = dp(6) })
        val cols = LinearLayout(context)
        cols.orientation = LinearLayout.HORIZONTAL
        val dr = LinearLayout(context)
        dr.orientation = LinearLayout.VERTICAL
        dr.setPadding(0, dp(4), dp(8), dp(4))
        val cr = LinearLayout(context)
        cr.orientation = LinearLayout.VERTICAL
        cr.setPadding(dp(8), dp(4), 0, dp(4))
        dr.addView(text("Dr", 11.5f, muted = true))
        cr.addView(text("Cr", 11.5f, muted = true))
        val normalSide = if (a.kind.debitNormal) dr else cr
        val otherSide = if (a.kind.debitNormal) cr else dr
        if (t.opening != 0L) (if (t.opening > 0) normalSide else otherSide).addView(tRow("Opening balance", Math.abs(t.opening), bold = true))
        for (x in t.debits) dr.addView(tRow("${day(x.date)} · ${x.other}", x.amount))
        for (x in t.credits) cr.addView(tRow("${day(x.date)} · ${x.other}", x.amount))
        cols.addView(dr, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        val line = View(context)
        line.setBackgroundColor(color(R.color.ink))
        cols.addView(line, LinearLayout.LayoutParams(dp(1), ViewGroup.LayoutParams.MATCH_PARENT))
        cols.addView(cr, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        card.addView(cols)
        val rule = View(context)
        rule.setBackgroundColor(color(R.color.line))
        card.addView(rule, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(1)))
        val sums = LinearLayout(context)
        sums.orientation = LinearLayout.HORIZONTAL
        val drOpen = if (t.opening > 0 == a.kind.debitNormal) Math.abs(t.opening) else 0L
        val crOpen = Math.abs(t.opening) - drOpen
        sums.addView(tRow("Total", t.totalDr + drOpen, muted = true).also { it.setPadding(0, dp(4), dp(8), 0) },
            LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        sums.addView(tRow("Total", t.totalCr + crOpen, muted = true).also { it.setPadding(dp(9), dp(4), 0, 0) },
            LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        card.addView(sums)
        val bal = LinearLayout(context)
        bal.orientation = LinearLayout.HORIZONTAL
        val closing = t.closing
        val onDebit = (closing >= 0) == a.kind.debitNormal
        val left = if (onDebit) tRow("Balance", Math.abs(closing), bold = true) else View(context)
        val right = if (!onDebit) tRow("Balance", Math.abs(closing), bold = true) else View(context)
        left.setPadding(0, dp(2), dp(8), 0)
        right.setPadding(dp(9), dp(2), 0, 0)
        bal.addView(left, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        bal.addView(right, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        card.addView(bal)
        return card
    }

    private fun tRow(label: String, amount: Long, bold: Boolean = false, muted: Boolean = false): LinearLayout {
        val r = LinearLayout(context)
        r.orientation = LinearLayout.HORIZONTAL
        r.setPadding(0, dp(2), 0, dp(2))
        val l = text(label, 12f, bold = bold, muted = muted)
        l.maxLines = 1
        l.ellipsize = TextUtils.TruncateAt.END
        r.addView(l, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        val v = text(amt(amount), 12f, bold = bold, muted = muted)
        v.setFontFeatureSettings("tnum")
        v.setPadding(dp(4), 0, 0, 0)
        r.addView(v)
        return r
    }

    private fun sankey(p: Period) {
        val f = book.moneyFlow(p, previous())
        if (f.total <= 0L) return emptyPeriod(p)
        val stats = LinearLayout(context)
        stats.orientation = LinearLayout.HORIZONTAL
        val rate = if (f.totalIncome > 0) " · ${Math.round((f.totalIncome - f.totalExpenses) * 100.0 / f.totalIncome)}%" else ""
        for ((label, value) in listOf("Income" to Money.label(f.totalIncome, book.currency),
                                       "Spending" to Money.label(f.totalExpenses, book.currency),
                                       (if (f.drawn > 0) "Savings used" else "Saved") to
                                           Money.label(if (f.drawn > 0) f.drawn else f.saved, book.currency) + (if (f.drawn > 0) "" else rate))) {
            val box = LinearLayout(context)
            box.orientation = LinearLayout.VERTICAL
            box.addView(text(label, 12f, muted = true))
            box.addView(text(value, 16f, bold = true))
            stats.addView(box, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        }
        body.addView(stats, wrap(top = 6, bottom = 4))
        val chart = MoneySankeyView(context)
        chart.show(f, book.currency, prevName())
        body.addView(chart, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        val legend = LinearLayout(context)
        legend.orientation = LinearLayout.HORIZONTAL
        legend.gravity = Gravity.CENTER_VERTICAL
        for ((c, l) in listOf(R.color.sk_income to "Income", R.color.sk_saved to "Saved", R.color.sk_spent to "Spending",
                               R.color.sk_drawn to "Savings used")) {
            val dot = View(context)
            val g = GradientDrawable()
            g.cornerRadius = dp(2).toFloat()
            g.setColor(color(c))
            dot.background = g
            legend.addView(dot, LinearLayout.LayoutParams(dp(10), dp(10)).also { it.setMargins(0, 0, dp(5), 0) })
            legend.addView(text(l, 12f, muted = true), LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT).also { it.setMargins(0, 0, dp(12), 0) })
        }
        body.addView(legend, wrap(top = 6))
        body.addView(text("Band width is the amount. Each share is of the total in the middle" +
            (prevName()?.let { "; “vs $it” compares with the period before" } ?: "") +
            ". Spending is what the expense accounts recorded in the period, wherever it was paid from (a credit card too). " +
            "Small lines are grouped.", 12.5f, muted = true), wrap(top = 8))
    }

    // ---------------------------------------------------------------- the three statements
    private fun statementHead(title: String, sub: String, cur: String?, prev: String?) {
        body.addView(text(title, 18f, bold = true), wrap(top = 6))
        body.addView(text(sub, 12.5f, muted = true), wrap(bottom = 6))
        if (cur != null) body.addView(stRow("", cur, prev, Style.COLHEAD))
    }

    private enum class Style { NORMAL, HEADING, SUB, TOTAL, GRAND, COLHEAD, NOTE }

    private fun stRow(label: String, value: String?, prev: String? = null, style: Style = Style.NORMAL, indent: Int = 0): View {
        val r = LinearLayout(context)
        r.orientation = LinearLayout.HORIZONTAL
        r.gravity = Gravity.CENTER_VERTICAL
        val pad = when (style) { Style.HEADING -> dp(12); Style.TOTAL, Style.GRAND -> dp(6); else -> dp(3) }
        r.setPadding(dp(indent * 14), pad, 0, dp(3))
        val bold = style == Style.HEADING || style == Style.TOTAL || style == Style.GRAND || style == Style.SUB
        val muted = style == Style.COLHEAD || style == Style.NOTE
        val size = when (style) { Style.GRAND -> 15f; Style.HEADING -> 14.5f; Style.COLHEAD, Style.NOTE -> 12f; else -> 13.5f }
        val l = text(label, size, bold = bold, muted = muted)
        r.addView(l, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        for ((i, v) in listOf(value, prev).withIndex()) {
            if (v == null) continue
            val t = text(v, size, bold = bold && i == 0, muted = muted || i == 1)
            t.gravity = Gravity.END
            t.setFontFeatureSettings("tnum")
            r.addView(t, LinearLayout.LayoutParams(dp(if (prev != null) 92 else 120), ViewGroup.LayoutParams.WRAP_CONTENT))
        }
        if (style == Style.TOTAL || style == Style.GRAND) {
            val box = LinearLayout(context)
            box.orientation = LinearLayout.VERTICAL
            val rule = View(context)
            rule.setBackgroundColor(color(if (style == Style.GRAND) R.color.ink else R.color.line))
            box.addView(rule, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(if (style == Style.GRAND) 2 else 1))
                .also { it.topMargin = dp(4) })
            box.addView(r)
            return box
        }
        return r
    }

    private fun shortLabel(p: Period?): String? = p?.let {
        when (scope) {
            Scope.MONTH -> YearMonth.parse(it.from!!.substring(0, 7)).format(DateTimeFormatter.ofPattern("MMM yyyy", Locale.US))
            Scope.YEAR -> it.label
            Scope.ALL -> "All time"
        }
    }

    private fun incomeStatement(p: Period) {
        val s = book.incomeStatement(p)
        val prevP = previous()
        val ps = prevP?.let { book.incomeStatement(it) }
        statementHead("Income statement", "${p.label} · in ${book.currency} · income and spending recorded in the period",
            shortLabel(p), shortLabel(prevP))
        fun lines(cur: List<Row>, prev: List<Row>?) {
            val ids = (cur.map { it.account } + (prev?.map { it.account } ?: emptyList())).distinct()
            for (id in ids) {
                val c = cur.firstOrNull { it.account == id }?.amount ?: 0L
                val pv = prev?.firstOrNull { it.account == id }?.amount
                body.addView(stRow(book.name(id ?: ""), amt(c, true), prev?.let { amt(pv ?: 0L, true) }, indent = 1))
            }
        }
        body.addView(stRow("Income", null, style = Style.HEADING))
        lines(s.income, ps?.income)
        body.addView(stRow("Total income", amt(s.totalIncome, true), ps?.let { amt(it.totalIncome, true) }, Style.TOTAL))
        body.addView(stRow("Expenses", null, style = Style.HEADING))
        lines(s.expenses, ps?.expenses)
        body.addView(stRow("Total expenses", amt(s.totalExpenses, true), ps?.let { amt(it.totalExpenses, true) }, Style.TOTAL))
        body.addView(stRow(if (s.net >= 0) "Net savings" else "Net shortfall", amt(s.net, true), ps?.let { amt(it.net, true) }, Style.GRAND))
        val rate = s.savingsRate
        body.addView(stRow("Savings rate", rate?.let { "${Math.round(it)}%" } ?: "—", ps?.let { x -> x.savingsRate?.let { "${Math.round(it)}%" } ?: "—" },
            Style.NOTE))
        body.addView(text("Net savings is income minus expenses: what the period added to your net worth (it is the " +
            "“Accumulated savings” line of the balance sheet).", 12.5f, muted = true), wrap(top = 10))
    }

    private fun balanceSheet(p: Period) {
        val end = p.to
        val prevP = previous()
        val bs = book.balanceSheet(end)
        val pb = prevP?.let { book.balanceSheet(it.to) }
        val at = end?.let { LocalDate.parse(it).format(DateTimeFormatter.ofPattern("MMMM d, yyyy", Locale.US)) } ?: "today"
        statementHead("Balance sheet", "At $at · in ${book.currency} · what you own, what you owe and the difference",
            end?.let { day(it, true) } ?: "Now", prevP?.to?.let { day(it, true) })
        fun prevOf(id: String?, name: String, rows: List<Row>?): String? = if (pb == null) null
            else amt(rows?.firstOrNull { if (id != null) it.account == id else it.name == name }?.amount ?: 0L, true)
        fun sections(cur: List<Section>, prev: List<Section>?) {
            val titles = (cur.map { it.title } + (prev?.map { it.title } ?: emptyList())).distinct()
            for (t in titles) {
                val c = cur.firstOrNull { it.title == t }
                val pv = prev?.firstOrNull { it.title == t }
                body.addView(stRow(t, null, style = Style.SUB, indent = 1))
                val ids = ((c?.rows ?: emptyList()) + (pv?.rows ?: emptyList())).map { it.account }.distinct()
                for (id in ids) {
                    val cv = c?.rows?.firstOrNull { it.account == id }?.amount ?: 0L
                    body.addView(stRow(book.name(id ?: ""), amt(cv, true), prevOf(id, "", pv?.rows ?: emptyList()), indent = 2))
                }
            }
        }
        body.addView(stRow("Assets", null, style = Style.HEADING))
        sections(bs.assets, pb?.assets)
        body.addView(stRow("Total assets", amt(bs.totalAssets, true), pb?.let { amt(it.totalAssets, true) }, Style.TOTAL))
        body.addView(stRow("Liabilities", null, style = Style.HEADING))
        sections(bs.liabilities, pb?.liabilities)
        body.addView(stRow("Total liabilities", amt(bs.totalLiabilities, true), pb?.let { amt(it.totalLiabilities, true) }, Style.TOTAL))
        body.addView(stRow("Equity", null, style = Style.HEADING))
        val names = (bs.equity.map { it.name } + (pb?.equity?.map { it.name } ?: emptyList())).distinct()
        for (n in names) {
            val c = bs.equity.firstOrNull { it.name == n }?.amount ?: 0L
            body.addView(stRow(n, amt(c, true), prevOf(null, n, pb?.equity), indent = 1))
        }
        body.addView(stRow("Total equity", amt(bs.totalEquity, true), pb?.let { amt(it.totalEquity, true) }, Style.TOTAL))
        body.addView(stRow("Total liabilities and equity", amt(bs.totalLiabilities + bs.totalEquity, true),
            pb?.let { amt(it.totalLiabilities + it.totalEquity, true) }, Style.GRAND))
        body.addView(stRow("Net worth (assets − liabilities)", amt(bs.netWorth, true), pb?.let { amt(it.netWorth, true) }, Style.SUB))
        body.addView(check(bs.balanced, "Assets = liabilities + equity",
            "Out of balance by ${book.money(bs.totalAssets - bs.totalLiabilities - bs.totalEquity)}"))
        body.addView(text("Equity is your net worth: the opening balances you started with, plus the savings recorded " +
            "since (all income minus all expenses up to this date).", 12.5f, muted = true), wrap(top = 10))
    }

    private fun cashFlow(p: Period) {
        val cf = book.cashFlow(p)
        statementHead("Cash flow statement", "${p.label} · in ${book.currency} · cash = the Cash & bank accounts", null, null)
        body.addView(stRow("Cash at the start", amt(cf.opening, true), style = Style.SUB))
        if (cf.openingEntered != 0L) body.addView(stRow("includes opening balances entered in this period", amt(cf.openingEntered, true),
            style = Style.NOTE, indent = 1))
        for (s in cf.sections) {
            body.addView(stRow(s.title, null, style = Style.HEADING))
            if (s.rows.isEmpty()) body.addView(stRow("None", null, style = Style.NOTE, indent = 1))
            for (r in s.rows) body.addView(stRow(r.name, amt(r.amount, true), indent = 1))
            body.addView(stRow("Net cash from ${s.title.substringBefore(" ").lowercase(Locale.US)} activities", amt(s.total, true), style = Style.TOTAL))
        }
        body.addView(stRow("Net change in cash", amt(cf.net, true), style = Style.TOTAL))
        body.addView(stRow("Cash at the end", amt(cf.closing, true), style = Style.GRAND))
        body.addView(check(cf.balanced, "Start + net change = end",
            "Does not add up by ${book.money(cf.opening + cf.net - cf.closing)}"))
        body.addView(stRow("From savings to operating cash flow", null, style = Style.HEADING))
        body.addView(stRow("Net savings (income statement)", amt(cf.savings, true), indent = 1))
        body.addView(stRow("Change in credit cards and other balances", amt(cf.workingCapital, true), indent = 1))
        body.addView(stRow("Income and spending not paid in cash", amt(cf.nonCash, true), indent = 1))
        body.addView(stRow("Net cash from operating activities", amt(cf.operating, true), style = Style.TOTAL))
        body.addView(text("Inflows are positive, outflows negative. An entry with no cash or bank line (spending on a credit " +
            "card, dividends kept in a brokerage account) is not a cash flow; paying the card later is. Moves between " +
            "your own cash and bank accounts cancel out.", 12.5f, muted = true), wrap(top = 10))
    }

    private fun check(ok: Boolean, good: String, bad: String): View {
        val t = text(if (ok) "✓  $good" else "⚠  $bad", 13f, bold = true)
        t.setTextColor(color(if (ok) R.color.accent else R.color.neg))
        t.setPadding(0, dp(10), 0, 0)
        return t
    }

    // ---------------------------------------------------------------- more
    private fun more() {
        val items = mutableListOf("Export the journal (CSV)", "Back up everything (JSON)", "Restore from a backup", "Currency symbol (${book.currency})")
        if (book.entries.isEmpty()) items += "Try an example month" else items += "Erase all entries"
        MaterialAlertDialogBuilder(context)
            .setTitle("Money")
            .setItems(items.toTypedArray<CharSequence>()) { _, which ->
                when (items[which].substringBefore(" (").substringBefore(" ")) {
                    "Export" -> {
                        val p = period()
                        host.shareMoneyFile("journal-${p.label.replace(" ", "-").lowercase(Locale.US)}.csv", "text/csv", book.csv(p))
                    }
                    "Back" -> host.shareMoneyFile("money-backup-${LocalDate.now()}.json", "application/json", BooksJson.write(book))
                    "Restore" -> host.pickMoneyBackup()
                    "Currency" -> forms.currency { save(book.withCurrency(it)) }
                    "Try" -> example()
                    "Erase" -> MaterialAlertDialogBuilder(context)
                        .setTitle("Erase all entries?")
                        .setMessage("This deletes every entry on this phone (accounts stay). Back up first if you may want them again.")
                        .setPositiveButton("Erase") { _, _ -> save(Book(book.accounts, emptyList(), book.currency)) }
                        .setNegativeButton("Cancel", null)
                        .show()
                }
            }
            .show()
    }

    private fun example() {
        try {
            save(Journal.example(book, YearMonth.now()) { BooksStore.newId() })
            scope = Scope.MONTH
            month = YearMonth.now()
            render()
            Toast.makeText(context, "Example month added. Erase all entries under More when you are done exploring.", Toast.LENGTH_LONG).show()
        } catch (e: BookError) {
            Toast.makeText(context, "The example needs the starting accounts: ${e.message}", Toast.LENGTH_LONG).show()
        }
    }

    // ---------------------------------------------------------------- small views
    private fun amt(c: Long, sign: Boolean = false): String = if (c == 0L && !sign) "" else Money.format(c, "", true)

    private fun day(d: String, year: Boolean = false): String =
        LocalDate.parse(d).format(DateTimeFormatter.ofPattern(if (year) "MMM d, yyyy" else "MMM d", Locale.US))

    private fun kindWord(t: String) = when (t) {
        "expense" -> "Spending"; "income" -> "Income"; "transfer" -> "Transfer"; "opening" -> "Opening balance"; else -> "Journal entry"
    }

    private fun text(s: String, size: Float, bold: Boolean = false, muted: Boolean = false): TextView {
        val t = TextView(context)
        t.text = s
        t.textSize = size
        t.setTextColor(color(if (muted) R.color.muted else R.color.ink))
        if (bold) t.setTypeface(t.typeface, Typeface.BOLD)
        return t
    }

    private fun eyebrow(s: String): TextView {
        val t = text(s.uppercase(Locale.US), 12f, bold = true, muted = true)
        t.letterSpacing = 0.08f
        return t
    }

    private fun row3(a: String, b: String, c: String, size: Float, muted: Boolean = false): LinearLayout {
        val r = LinearLayout(context)
        r.orientation = LinearLayout.HORIZONTAL
        r.setPadding(0, dp(2), 0, dp(2))
        val first = text(a, size, muted = muted)
        first.maxLines = 1
        first.ellipsize = TextUtils.TruncateAt.END
        r.addView(first, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        for (v in listOf(b, c)) {
            val t = text(v, size, muted = muted)
            t.gravity = Gravity.END
            t.setFontFeatureSettings("tnum")
            r.addView(t, LinearLayout.LayoutParams(dp(88), ViewGroup.LayoutParams.WRAP_CONTENT))
        }
        return r
    }

    private fun card(): LinearLayout {
        val c = LinearLayout(context)
        c.orientation = LinearLayout.VERTICAL
        c.setPadding(dp(12), dp(10), dp(12), dp(10))
        val g = GradientDrawable()
        g.cornerRadius = dp(10).toFloat()
        g.setColor(color(R.color.paper))
        g.setStroke(dp(1), color(R.color.line))
        c.background = g
        c.isClickable = true
        return c
    }

    private fun link(label: String, onClick: () -> Unit): TextView {
        val t = text(label, 14f, bold = true)
        t.setTextColor(color(R.color.accent))
        t.setPadding(dp(10), dp(8), dp(10), dp(8))
        t.isClickable = true
        t.setOnClickListener { onClick() }
        return t
    }

    private fun button(label: String, onClick: () -> Unit): MaterialButton {
        val b = MaterialButton(context)
        b.text = label
        b.cornerRadius = dp(20)
        b.setOnClickListener { onClick() }
        return b
    }

    private fun wrap(top: Int = 0, bottom: Int = 0): LinearLayout.LayoutParams {
        val lp = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        lp.topMargin = dp(top)
        lp.bottomMargin = dp(bottom)
        return lp
    }
}

/** A segmented control: equal-width options, the chosen one tinted. */
class Seg(context: Context, labels: List<String>, private var selected: Int, private val onPick: (Int) -> Unit) : LinearLayout(context) {
    private val items: List<TextView> = labels.map { TextView(context) }

    init {
        orientation = HORIZONTAL
        val bg = GradientDrawable()
        bg.cornerRadius = dp(9).toFloat()
        bg.setColor(color(R.color.paper))
        bg.setStroke(dp(1), color(R.color.line))
        background = bg
        setPadding(dp(2), dp(2), dp(2), dp(2))
        items.forEachIndexed { i, t ->
            t.text = labels[i]
            t.textSize = 13f
            t.gravity = Gravity.CENTER
            t.maxLines = 1
            t.setPadding(dp(4), dp(7), dp(4), dp(7))
            t.isClickable = true
            t.setOnClickListener { pick(i) }
            addView(t, LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        }
        paint()
    }

    private fun pick(i: Int) {
        if (i == selected) return
        selected = i
        paint()
        onPick(i)
    }

    private fun paint() {
        items.forEachIndexed { i, t ->
            val on = i == selected
            t.setTextColor(color(if (on) R.color.ink else R.color.muted))
            t.setTypeface(null, if (on) Typeface.BOLD else Typeface.NORMAL)
            t.background = if (on) GradientDrawable().also {
                it.cornerRadius = dp(7).toFloat()
                it.setColor(color(R.color.accent_soft))
            } else null
        }
    }
}
