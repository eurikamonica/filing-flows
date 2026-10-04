package io.github.eurikamonica.filingflows

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.Currency
import java.util.Locale
import java.util.UUID

/**
 * The personal books on this phone only: files/books.json (no account, nothing sent anywhere). Android's own backup
 * (Settings -> Google -> Backup) includes it; Export makes a copy to keep elsewhere.
 */
class BooksStore(context: Context) {
    private val dir = context.applicationContext.filesDir
    private val file = File(dir, "books.json")

    fun load(): Book {
        if (!file.exists()) return Book.starter(defaultCurrency())
        return try {
            BooksJson.read(file.readText())
        } catch (e: Exception) {                           // keep the unreadable file aside, never write over it
            file.renameTo(File(dir, "books-unreadable-${System.currentTimeMillis()}.json"))
            Book.starter(defaultCurrency())
        }
    }

    fun save(b: Book) {
        val tmp = File(dir, "books.json.tmp")
        tmp.writeText(BooksJson.write(b))
        if (!tmp.renameTo(file)) {
            file.delete()
            tmp.renameTo(file)
        }
    }

    companion object {
        fun newId(): String = UUID.randomUUID().toString().replace("-", "").take(12)

        fun defaultCurrency(): String = runCatching {
            val c = Currency.getInstance(Locale.getDefault())
            when (c.currencyCode) {
                "CNY", "JPY" -> "¥"
                "USD", "CAD", "AUD", "NZD", "HKD", "SGD", "TWD" -> "$"
                else -> c.getSymbol(Locale.getDefault()).take(4)
            }
        }.getOrDefault("$")
    }
}

/** books.json: {"v":1,"currency":"$","accounts":[…],"entries":[{"id","date","memo","type","created","lines":[{"a","dr","cr"}]}]} */
object BooksJson {
    fun write(b: Book): String {
        val accounts = JSONArray()
        for (a in b.accounts) {
            accounts.put(JSONObject().put("id", a.id).put("name", a.name).put("kind", a.kind.name).put("sub", a.sub.name)
                .put("archived", a.archived))
        }
        val entries = JSONArray()
        for (e in b.entries) {
            val lines = JSONArray()
            for (l in e.lines) lines.put(JSONObject().put("a", l.account).put("dr", l.dr).put("cr", l.cr))
            entries.put(JSONObject().put("id", e.id).put("date", e.date).put("memo", e.memo).put("type", e.type)
                .put("created", e.created).put("lines", lines))
        }
        return JSONObject().put("v", 1).put("currency", b.currency).put("accounts", accounts).put("entries", entries).toString()
    }

    fun read(text: String): Book {
        val o = JSONObject(text)
        val acc = o.getJSONArray("accounts")
        val accounts = (0 until acc.length()).map { i ->
            val a = acc.getJSONObject(i)
            val kind = Kind.valueOf(a.getString("kind"))
            Account(a.getString("id"), a.getString("name"), kind, Sub.parse(a.optString("sub", "")).let { if (it.kind == kind) it else Book.defaultSub(kind) },
                a.optBoolean("archived", false))
        }
        val ent = o.optJSONArray("entries") ?: JSONArray()
        val entries = (0 until ent.length()).map { i ->
            val e = ent.getJSONObject(i)
            val ls = e.getJSONArray("lines")
            JournalEntry(e.getString("id"), e.getString("date"), e.optString("memo", ""),
                (0 until ls.length()).map { j ->
                    val l = ls.getJSONObject(j)
                    Line(l.getString("a"), l.optLong("dr", 0L), l.optLong("cr", 0L))
                }, e.optString("type", "journal"), e.optLong("created", 0L))
        }
        return Book(accounts, entries, o.optString("currency", "$").ifEmpty { "$" })
    }
}
