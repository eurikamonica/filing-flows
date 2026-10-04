package io.github.eurikamonica.filingflows

import android.app.DatePickerDialog
import android.content.Context
import android.content.DialogInterface
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.text.InputType
import android.text.TextUtils
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.core.content.ContextCompat
import androidx.core.widget.doAfterTextChanged
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * The Money tab's dialogs: adding and editing entries (spending, income, transfer, opening balance, any journal entry),
 * an entry's details, the accounts, the currency symbol. Every form shows the journal entry it will record.
 */
class MoneyForms(private val context: Context, private val book: () -> Book, private val onSave: (Book) -> Unit) {
    private val density = context.resources.displayMetrics.density
    private fun dp(v: Int) = (v * density).toInt()
    private fun color(id: Int) = ContextCompat.getColor(context, id)
    private val dateFmt = DateTimeFormatter.ofPattern("EEE, MMM d, yyyy", Locale.US)

    // ---------------------------------------------------------------- choosing what to add
    fun chooseNew() {
        val items = arrayOf<CharSequence>("Spending", "Income", "Transfer · save, invest, pay a card, borrow, repay",
            "Opening balance", "Journal entry · any accounts, several lines")
        MaterialAlertDialogBuilder(context)
            .setTitle("Add an entry")
            .setItems(items) { _, which ->
                when (which) {
                    0 -> expense(null)
                    1 -> income(null)
                    2 -> transfer(null)
                    3 -> opening(null)
                    else -> journal(null)
                }
            }
            .show()
    }

    private fun open(list: List<Account>) = list.filter { !it.archived }
    private fun ofKind(vararg k: Kind) = open(book().accounts.filter { it.kind in k })
    private fun payFrom() = open(book().accounts.filter { (it.kind == Kind.ASSET && it.sub != Sub.INVEST) || it.sub == Sub.CARD })
        .sortedBy { if (it.sub == Sub.CARD) 1 else 0 }

    fun expense(e: JournalEntry?) {
        val pre = e?.let { two(it) }
        pair("Spending", "expense", e, "Category", ofKind(Kind.EXPENSE), pre?.first, "Paid from", payFrom(), pre?.second,
            "What was it? (optional)") { id, date, memo, amount, cat, from ->
            Journal.expense(id, date, memo, amount, cat, from, System.currentTimeMillis())
        }
    }

    fun income(e: JournalEntry?) {
        val pre = e?.let { two(it) }
        pair("Income", "income", e, "Income type", ofKind(Kind.INCOME), pre?.second, "Received into", ofKind(Kind.ASSET), pre?.first,
            "From whom or what for (optional)") { id, date, memo, amount, inc, into ->
            Journal.income(id, date, memo, amount, inc, into, System.currentTimeMillis())
        }
    }

    fun transfer(e: JournalEntry?) {
        val pre = e?.let { two(it) }
        val all = ofKind(Kind.ASSET, Kind.LIABILITY, Kind.EQUITY)
        pair("Transfer", "transfer", e, "From", all, pre?.second, "To", all, pre?.first,
            "For example: monthly saving, pay the credit card") { id, date, memo, amount, from, to ->
            Journal.transfer(id, date, memo, amount, from, to, System.currentTimeMillis())
        }
    }

    fun opening(e: JournalEntry?) {
        val b = book()
        val equity = b.accounts.firstOrNull { it.kind == Kind.EQUITY && !it.archived }
        if (equity == null) {
            alert("Add an equity account first (Accounts → New account → Equity), for example “Opening balances”.")
            return
        }
        val other = e?.lines?.firstOrNull { it.account != equity.id }
        pair("Opening balance", "opening", e, "Account", ofKind(Kind.ASSET, Kind.LIABILITY), other?.account, null, emptyList(), equity.id,
            null, hint = "What the account held (or, for a card or loan, what you owed) when you start keeping these books.") {
                id, date, _, amount, acc, _ ->
            Journal.opening(id, date, book(), acc, amount, equity.id, System.currentTimeMillis())
        }
    }

    /** (debit account, credit account) of a two-line entry. */
    private fun two(e: JournalEntry): Pair<String?, String?> =
        Pair(e.lines.firstOrNull { it.dr > 0 }?.account, e.lines.firstOrNull { it.cr > 0 }?.account)

    /** A form with an amount, one or two accounts, a date and a note; the entry it records is shown underneath. */
    private fun pair(title: String, type: String, e: JournalEntry?, firstLabel: String, firstChoices: List<Account>, firstPre: String?,
                     secondLabel: String?, secondChoices: List<Account>, secondPre: String?, memoHint: String?, hint: String? = null,
                     build: (String, String, String, Long, String, String) -> JournalEntry) {
        val form = column()
        if (hint != null) form.addView(note(hint))
        val amount = field("Amount (${book().currency})", e?.total?.let { Book.plain(it) } ?: "", InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL)
        form.addView(label("Amount"))
        form.addView(amount)
        var first: String? = firstPre ?: firstChoices.firstOrNull()?.id
        var second: String? = secondPre ?: secondChoices.firstOrNull()?.id
        var date: String = e?.date ?: LocalDate.now().toString()
        val preview = note("")
        fun update() {
            val c = Money.parse(amount.text.toString())
            val f = first
            val s = second
            preview.text = if (c == null || f == null || s == null) "Fill in the amount to see the journal entry."
            else runCatching {
                val entry = build("preview", date, "", c, f, s)
                "Journal entry:\n" + entry.lines.sortedBy { if (it.dr > 0) 0 else 1 }.joinToString("\n") {
                    (if (it.dr > 0) "Dr  " else "      Cr  ") + book().name(it.account) + "   " + Money.format(it.dr + it.cr, book().currency)
                }
            }.getOrElse { it.message ?: "" }
        }
        form.addView(label(firstLabel))
        form.addView(chooser(firstChoices, { first }) { first = it; update() })
        if (secondLabel != null) {
            form.addView(label(secondLabel))
            form.addView(chooser(secondChoices, { second }) { second = it; update() })
        }
        form.addView(label("Date"))
        val dateField = pickField(LocalDate.parse(date).format(dateFmt))
        dateField.setOnClickListener {
            val d = LocalDate.parse(date)
            DatePickerDialog(context, { _, y, m, dd ->
                date = LocalDate.of(y, m + 1, dd).toString()
                dateField.text = LocalDate.parse(date).format(dateFmt)
                update()
            }, d.year, d.monthValue - 1, d.dayOfMonth).show()
        }
        form.addView(dateField)
        val memo = if (memoHint != null) field(memoHint, e?.memo ?: "", InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES) else null
        if (memo != null) {
            form.addView(label("Note"))
            form.addView(memo)
        }
        val error = error()
        form.addView(preview)
        form.addView(error)
        amount.doAfterTextChanged { update() }
        update()
        dialog(if (e == null) title else "Edit: ${title.lowercase(Locale.US)}", form, e) {
            val c = Money.parse(amount.text.toString()) ?: throw BookError("Type an amount above zero")
            val f = first ?: throw BookError("Pick ${firstLabel.lowercase(Locale.US)}")
            val s = second ?: throw BookError("Pick ${(secondLabel ?: "an account").lowercase(Locale.US)}")
            if (f == s) throw BookError("Pick two different accounts")
            val entry = build(e?.id ?: BooksStore.newId(), date, memo?.text?.toString()?.trim() ?: "", c, f, s)
            book().put(if (e != null) entry.copy(created = e.created) else entry)
        }
    }

    /** Any journal entry: as many lines as needed, each a debit or a credit; it saves only when debits = credits. */
    fun journal(e: JournalEntry?) {
        val b = book()
        val form = column()
        form.addView(note("Debits on the accounts that increase an asset or an expense (or decrease what you owe); credits " +
            "on the others. The entry saves when debits equal credits."))
        var date = e?.date ?: LocalDate.now().toString()
        form.addView(label("Date"))
        val dateField = pickField(LocalDate.parse(date).format(dateFmt))
        form.addView(dateField)
        form.addView(label("Note"))
        val memo = field("What happened", e?.memo ?: "", InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES)
        form.addView(memo)
        form.addView(label("Lines"))
        val linesBox = column(0)
        form.addView(linesBox)
        val totals = note("")
        class LineRow(var account: String?, var debit: Boolean, val amount: EditText, val view: View)
        val rows = ArrayList<LineRow>()
        val accounts = open(b.accounts)
        fun sums(): Pair<Long, Long> {
            var dr = 0L
            var cr = 0L
            for (r in rows) {
                val c = Money.parse(r.amount.text.toString()) ?: 0L
                if (r.debit) dr += c else cr += c
            }
            return Pair(dr, cr)
        }
        fun showTotals() {
            val (dr, cr) = sums()
            totals.text = "Debits ${b.money(dr)} · Credits ${b.money(cr)}" + if (dr == cr && dr > 0) "  ✓" else "  (must be equal)"
            totals.setTextColor(color(if (dr == cr && dr > 0) R.color.accent else R.color.muted))
        }
        fun addRow(account: String?, debit: Boolean, cents: Long?) {
            val r = LinearLayout(context)
            r.orientation = LinearLayout.HORIZONTAL
            r.gravity = Gravity.CENTER_VERTICAL
            val amount = field("0.00", cents?.let { Book.plain(it) } ?: "", InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL)
            val row = LineRow(account, debit, amount, r)
            val side = TextView(context)
            fun paintSide() {
                side.text = if (row.debit) "Dr" else "Cr"
                side.setTextColor(color(if (row.debit) R.color.ink else R.color.accent))
            }
            side.textSize = 14f
            side.setTypeface(side.typeface, Typeface.BOLD)
            side.setPadding(dp(6), dp(10), dp(6), dp(10))
            side.isClickable = true
            side.setOnClickListener { row.debit = !row.debit; paintSide(); showTotals() }
            paintSide()
            val pick = chooser(accounts, { row.account }) { row.account = it }
            r.addView(side)
            r.addView(pick, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            r.addView(amount, LinearLayout.LayoutParams(dp(96), ViewGroup.LayoutParams.WRAP_CONTENT))
            val x = TextView(context)
            x.text = "×"
            x.textSize = 18f
            x.setTextColor(color(R.color.muted))
            x.setPadding(dp(8), dp(6), dp(4), dp(6))
            x.contentDescription = "Remove line"
            x.isClickable = true
            x.setOnClickListener {
                if (rows.size > 2) {
                    rows.remove(row)
                    linesBox.removeView(r)
                    showTotals()
                }
            }
            r.addView(x)
            amount.doAfterTextChanged { showTotals() }
            rows += row
            linesBox.addView(r)
        }
        if (e != null) for (l in e.lines) addRow(l.account, l.dr > 0, l.dr + l.cr)
        else { addRow(null, true, null); addRow(null, false, null) }
        val more = TextView(context)
        more.text = "+ Add a line"
        more.textSize = 14f
        more.setTextColor(color(R.color.accent))
        more.setTypeface(more.typeface, Typeface.BOLD)
        more.setPadding(0, dp(8), 0, dp(8))
        more.isClickable = true
        more.setOnClickListener { addRow(null, sums().first <= sums().second, null); showTotals() }
        form.addView(more)
        form.addView(totals)
        dateField.setOnClickListener {
            val d = LocalDate.parse(date)
            DatePickerDialog(context, { _, y, m, dd ->
                date = LocalDate.of(y, m + 1, dd).toString()
                dateField.text = LocalDate.parse(date).format(dateFmt)
            }, d.year, d.monthValue - 1, d.dayOfMonth).show()
        }
        val error = error()
        form.addView(error)
        showTotals()
        dialog(if (e == null) "Journal entry" else "Edit: journal entry", form, e) {
            val lines = rows.mapNotNull { r ->
                val c = Money.parse(r.amount.text.toString()) ?: return@mapNotNull null
                val a = r.account ?: throw BookError("Pick an account on every line with an amount")
                if (r.debit) Line(a, dr = c) else Line(a, cr = c)
            }
            val entry = JournalEntry(e?.id ?: BooksStore.newId(), date, memo.text.toString().trim(), lines,
                if (e?.type == "opening") "opening" else "journal", e?.created ?: System.currentTimeMillis())
            book().put(entry)
        }
    }

    /** Shows the form; Save runs `make` and keeps the dialog open with the message when it throws BookError. */
    private fun dialog(title: String, form: LinearLayout, e: JournalEntry?, make: () -> Book): Pair<AlertDialog, TextView> {
        val error = (0 until form.childCount).map { form.getChildAt(it) }.lastOrNull { it is TextView && it.tag == "error" } as TextView?
            ?: error().also { form.addView(it) }
        val scroll = ScrollView(context)
        scroll.addView(form)
        val b = MaterialAlertDialogBuilder(context)
            .setTitle(title)
            .setView(scroll)
            .setPositiveButton("Save", null)
            .setNegativeButton("Cancel", null)
        if (e != null) b.setNeutralButton("Delete") { _, _ -> confirmDelete(e) }
        val d = b.show()
        d.getButton(DialogInterface.BUTTON_POSITIVE).setOnClickListener {
            try {
                onSave(make())
                d.dismiss()
            } catch (x: BookError) {
                error.text = x.message
                error.visibility = View.VISIBLE
            }
        }
        return Pair(d, error)
    }

    // ---------------------------------------------------------------- an entry
    fun details(e: JournalEntry) {
        val b = book()
        val text = StringBuilder(LocalDate.parse(e.date).format(dateFmt)).append("\n\n")
        for (l in e.lines.sortedBy { if (it.dr > 0) 0 else 1 }) {
            text.append(if (l.dr > 0) "Dr  " else "      Cr  ").append(b.name(l.account)).append("   ")
                .append(Money.format(l.dr + l.cr, b.currency)).append('\n')
        }
        MaterialAlertDialogBuilder(context)
            .setTitle(e.memo.ifBlank { "Entry" })
            .setMessage(text.toString().trim())
            .setPositiveButton("Edit") { _, _ -> edit(e) }
            .setNeutralButton("Delete") { _, _ -> confirmDelete(e) }
            .setNegativeButton("Close", null)
            .show()
    }

    private fun edit(e: JournalEntry) {
        val b = book()
        val kinds = e.lines.map { b.account(it.account)?.kind }
        val two = e.lines.size == 2 && e.lines.count { it.dr > 0 } == 1
        val dr = e.lines.firstOrNull { it.dr > 0 }?.let { b.account(it.account) }
        val cr = e.lines.firstOrNull { it.cr > 0 }?.let { b.account(it.account) }
        when {
            two && e.type == "expense" && dr?.kind == Kind.EXPENSE -> expense(e)
            two && e.type == "income" && cr?.kind == Kind.INCOME -> income(e)
            two && e.type == "transfer" && kinds.none { it == Kind.INCOME || it == Kind.EXPENSE } -> transfer(e)
            two && e.type == "opening" && dr != null && cr != null &&
                ((dr.kind.debitNormal && cr.kind == Kind.EQUITY) || (dr.kind == Kind.EQUITY && !cr.kind.debitNormal)) -> opening(e)
            else -> journal(e)
        }
    }

    private fun confirmDelete(e: JournalEntry) {
        MaterialAlertDialogBuilder(context)
            .setTitle("Delete this entry?")
            .setMessage("${e.memo.ifBlank { "Entry" }} · ${LocalDate.parse(e.date).format(dateFmt)} · ${book().money(e.total)}")
            .setPositiveButton("Delete") { _, _ -> onSave(book().remove(e.id)) }
            .setNegativeButton("Cancel", null)
            .show()
    }

    // ---------------------------------------------------------------- accounts
    fun accounts(onDone: () -> Unit) {
        val b = book()
        val list = column()
        val today = LocalDate.now().toString()
        var shown: AlertDialog? = null
        for (k in Kind.values()) {
            val acc = b.accounts.filter { it.kind == k }
            if (acc.isEmpty()) continue
            val h = TextView(context)
            h.text = k.label.uppercase(Locale.US)
            h.textSize = 12f
            h.letterSpacing = 0.08f
            h.setTextColor(color(R.color.muted))
            h.setTypeface(h.typeface, Typeface.BOLD)
            h.setPadding(0, dp(12), 0, dp(4))
            list.addView(h)
            for (a in acc) {
                val r = LinearLayout(context)
                r.orientation = LinearLayout.HORIZONTAL
                r.gravity = Gravity.CENTER_VERTICAL
                r.setPadding(0, dp(8), 0, dp(8))
                r.isClickable = true
                val name = TextView(context)
                name.text = a.name + (if (a.sub.label.isNotEmpty()) "  ·  ${a.sub.label}" else "") + if (a.archived) "  ·  archived" else ""
                name.textSize = 14.5f
                name.setTextColor(color(if (a.archived) R.color.muted else R.color.ink))
                name.maxLines = 2
                name.ellipsize = TextUtils.TruncateAt.END
                r.addView(name, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
                if (k != Kind.INCOME && k != Kind.EXPENSE) {
                    val bal = TextView(context)
                    bal.text = b.money(b.balance(a.id, today))
                    bal.textSize = 13.5f
                    bal.setFontFeatureSettings("tnum")
                    bal.setTextColor(color(R.color.muted))
                    r.addView(bal)
                }
                r.setOnClickListener {
                    shown?.dismiss()
                    editAccount(a) { accounts(onDone) }
                }
                list.addView(r)
            }
        }
        list.addView(note("Balances are as of today. Income and expense accounts are the categories; assets and liabilities " +
            "are where money is and what you owe. An account with entries can be archived but not deleted."))
        val scroll = ScrollView(context)
        scroll.addView(list)
        shown = MaterialAlertDialogBuilder(context)
            .setTitle("Accounts")
            .setView(scroll)
            .setPositiveButton("New account") { _, _ -> editAccount(null) { accounts(onDone) } }
            .setNegativeButton("Close") { _, _ -> onDone() }
            .show()
    }

    private fun editAccount(a: Account?, then: () -> Unit) {
        val b = book()
        val form = column()
        val name = field("Name", a?.name ?: "", InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_WORDS)
        form.addView(label("Name"))
        form.addView(name)
        var kind = a?.kind ?: Kind.EXPENSE
        var sub = a?.sub ?: Sub.NONE
        val locked = a != null && b.used(a.id)
        val subLabel = label("Type")
        val subField = pickField("")
        fun paintSub() {
            val subs = Sub.forKind(kind)
            if (sub.kind != kind) sub = subs.firstOrNull() ?: Sub.NONE
            subLabel.visibility = if (subs.isEmpty()) View.GONE else View.VISIBLE
            subField.visibility = if (subs.isEmpty()) View.GONE else View.VISIBLE
            subField.text = sub.label + "  ▾"
        }
        form.addView(label("Kind"))
        val kindField = pickField(kind.label + if (locked) "" else "  ▾")
        if (!locked) kindField.setOnClickListener {
            val ks = Kind.values()
            MaterialAlertDialogBuilder(context).setTitle("Kind").setItems(ks.map { it.label as CharSequence }.toTypedArray()) { _, i ->
                kind = ks[i]
                kindField.text = kind.label + "  ▾"
                paintSub()
            }.show()
        }
        form.addView(kindField)
        if (locked) form.addView(note("The kind stays: the account has entries."))
        form.addView(subLabel)
        form.addView(subField)
        subField.setOnClickListener {
            val subs = Sub.forKind(kind)
            MaterialAlertDialogBuilder(context).setTitle("Type").setItems(subs.map { s ->
                (s.label + " — " + when (s) {
                    Sub.CASH -> "counts as cash"; Sub.INVEST -> "investing activities"; Sub.OTHER -> "operating"
                    Sub.CARD -> "operating"; Sub.LOAN -> "financing"; Sub.CAPITAL -> "financing"; Sub.NONE -> ""
                }) as CharSequence
            }.toTypedArray()) { _, i ->
                sub = subs[i]
                paintSub()
            }.show()
        }
        paintSub()
        form.addView(note("The type decides where money moving through the account appears in the cash flow statement."))
        val error = error()
        form.addView(error)
        val builder = MaterialAlertDialogBuilder(context)
            .setTitle(if (a == null) "New account" else "Edit account")
            .setView(ScrollView(context).also { it.addView(form) })
            .setPositiveButton("Save", null)
            .setNegativeButton("Cancel") { _, _ -> then() }
        if (a != null) {
            val word = if (a.archived) "Restore" else if (locked) "Archive" else "Delete"
            builder.setNeutralButton(word) { _, _ ->
                onSave(if (a.archived) b.putAccount(a.copy(archived = false)) else b.dropAccount(a.id))
                then()
            }
        }
        val d = builder.show()
        d.getButton(DialogInterface.BUTTON_POSITIVE).setOnClickListener {
            try {
                val id = a?.id ?: ("a" + BooksStore.newId())
                onSave(b.putAccount(Account(id, name.text.toString(), kind, sub, a?.archived ?: false)))
                d.dismiss()
                then()
            } catch (x: BookError) {
                error.text = x.message
                error.visibility = View.VISIBLE
            }
        }
    }

    fun currency(onSet: (String) -> Unit) {
        val form = column()
        form.addView(note("Shown before every amount, for example $, ¥, €, £ or HK$. Amounts are not converted."))
        val f = field("Symbol", book().currency, InputType.TYPE_CLASS_TEXT)
        form.addView(f)
        MaterialAlertDialogBuilder(context)
            .setTitle("Currency symbol")
            .setView(form)
            .setPositiveButton("Save") { _, _ -> onSet(f.text.toString()) }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun alert(msg: String) {
        MaterialAlertDialogBuilder(context).setMessage(msg).setPositiveButton("OK", null).show()
    }

    // ---------------------------------------------------------------- form parts
    private fun column(pad: Int = 20): LinearLayout {
        val c = LinearLayout(context)
        c.orientation = LinearLayout.VERTICAL
        c.setPadding(dp(pad), dp(if (pad > 0) 8 else 0), dp(pad), dp(if (pad > 0) 4 else 0))
        return c
    }

    private fun label(s: String): TextView {
        val t = TextView(context)
        t.text = s
        t.textSize = 12.5f
        t.setTextColor(color(R.color.muted))
        t.setPadding(0, dp(10), 0, dp(2))
        return t
    }

    private fun note(s: String): TextView {
        val t = TextView(context)
        t.text = s
        t.textSize = 13f
        t.setTextColor(color(R.color.muted))
        t.setPadding(0, dp(8), 0, dp(4))
        return t
    }

    private fun error(): TextView {
        val t = TextView(context)
        t.textSize = 13.5f
        t.setTextColor(color(R.color.neg))
        t.setPadding(0, dp(8), 0, 0)
        t.visibility = View.GONE
        t.tag = "error"
        return t
    }

    private fun field(hint: String, value: String, type: Int): EditText {
        val f = EditText(context)
        f.hint = hint
        f.setText(value)
        f.inputType = type
        f.setSingleLine()
        f.setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
        return f
    }

    /** A tappable field that looks like an input. */
    private fun pickField(value: String): TextView {
        val t = TextView(context)
        t.text = value
        t.textSize = 16f
        t.setTextColor(color(R.color.ink))
        t.setPadding(dp(12), dp(10), dp(12), dp(10))
        val g = GradientDrawable()
        g.cornerRadius = dp(8).toFloat()
        g.setStroke(dp(1), color(R.color.line))
        t.background = g
        t.isClickable = true
        t.maxLines = 1
        t.ellipsize = TextUtils.TruncateAt.END
        return t
    }

    /** Picks one of the accounts from a list. */
    private fun chooser(choices: List<Account>, current: () -> String?, onPick: (String) -> Unit): TextView {
        val t = pickField("")
        fun paint() { t.text = (current()?.let { book().name(it) } ?: "Choose…") + "  ▾" }
        paint()
        t.setOnClickListener {
            if (choices.isEmpty()) {
                alert("No account of this kind yet: add one under Accounts.")
                return@setOnClickListener
            }
            val names = choices.map { (it.name + if (it.sub.label.isNotEmpty()) "  ·  ${it.sub.label}" else "") as CharSequence }.toTypedArray()
            MaterialAlertDialogBuilder(context).setItems(names) { _, i ->
                onPick(choices[i].id)
                paint()
            }.show()
        }
        val lp = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        t.layoutParams = lp
        return t
    }
}
