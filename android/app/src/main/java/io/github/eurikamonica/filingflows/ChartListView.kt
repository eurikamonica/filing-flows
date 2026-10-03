package io.github.eurikamonica.filingflows

import android.content.Context
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.text.InputType
import android.text.TextUtils
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.EditorInfo
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.core.widget.doAfterTextChanged
import androidx.recyclerview.widget.DividerItemDecoration
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import com.google.android.material.button.MaterialButton

private fun View.dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()
private fun View.color(id: Int): Int = ContextCompat.getColor(context, id)

/** A native list of charts: optional search box, pull to refresh, an empty state with an optional action. */
class ChartListView(context: Context, withSearch: Boolean) : FrameLayout(context) {
    var onOpen: (Entry) -> Unit = {}
    var onRefresh: () -> Unit = {}
    var onQuery: (String) -> Unit = {}

    private val adapter = ChartAdapter { onOpen(it) }
    private val swipe = SwipeRefreshLayout(context)
    private val list = RecyclerView(context)
    private val status = TextView(context)
    private val emptyBox = LinearLayout(context)
    private val emptyText = TextView(context)
    private val emptyButton = MaterialButton(context)

    init {
        setBackgroundColor(color(R.color.ground))
        val column = LinearLayout(context)
        column.orientation = LinearLayout.VERTICAL
        if (withSearch) {
            val search = EditText(context)
            search.hint = context.getString(R.string.search_hint)
            search.setSingleLine()
            search.inputType = InputType.TYPE_CLASS_TEXT
            search.imeOptions = EditorInfo.IME_ACTION_SEARCH
            search.doAfterTextChanged { onQuery(it?.toString() ?: "") }
            val lp = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            lp.setMargins(dp(16), dp(8), dp(16), dp(4))
            column.addView(search, lp)
        }
        status.textSize = 12.5f
        status.setTextColor(color(R.color.muted))
        status.setPadding(dp(16), dp(6), dp(16), dp(6))
        status.visibility = View.GONE
        column.addView(status, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))

        list.layoutManager = LinearLayoutManager(context)
        list.adapter = adapter
        list.addItemDecoration(DividerItemDecoration(context, DividerItemDecoration.VERTICAL))
        swipe.addView(list, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        swipe.setColorSchemeColors(color(R.color.accent))
        swipe.setOnRefreshListener { onRefresh() }
        column.addView(swipe, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        addView(column, LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))

        emptyBox.orientation = LinearLayout.VERTICAL
        emptyBox.gravity = Gravity.CENTER_HORIZONTAL
        emptyBox.setPadding(dp(32), dp(24), dp(32), dp(24))
        emptyText.textSize = 15f
        emptyText.gravity = Gravity.CENTER
        emptyText.setTextColor(color(R.color.ink))
        emptyBox.addView(emptyText, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        val blp = LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        blp.topMargin = dp(16)
        emptyBox.addView(emptyButton, blp)
        emptyBox.visibility = View.GONE
        addView(emptyBox, LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.CENTER))
    }

    /** Shows the charts, or the empty message (and a button) when there are none. */
    fun show(items: List<Entry>, empty: String, action: String? = null, onAction: (() -> Unit)? = null) {
        adapter.submit(items)
        emptyBox.visibility = if (items.isEmpty()) View.VISIBLE else View.GONE
        emptyText.text = empty
        emptyButton.visibility = if (action != null && onAction != null) View.VISIBLE else View.GONE
        emptyButton.text = action ?: ""
        emptyButton.setOnClickListener { onAction?.invoke() }
    }

    fun setRefreshing(on: Boolean) {
        swipe.isRefreshing = on
    }

    fun setStatus(text: String?) {
        status.text = text ?: ""
        status.visibility = if (text.isNullOrEmpty()) View.GONE else View.VISIBLE
    }
}

class ChartAdapter(private val onClick: (Entry) -> Unit) : RecyclerView.Adapter<ChartAdapter.Holder>() {
    private var items: List<Entry> = emptyList()

    fun submit(list: List<Entry>) {
        items = list
        notifyDataSetChanged()
    }

    override fun getItemCount(): Int = items.size

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): Holder = Holder(ChartRow(parent.context))

    override fun onBindViewHolder(holder: Holder, position: Int) {
        val e = items[position]
        holder.row.bind(e)
        holder.row.setOnClickListener { onClick(e) }
    }

    class Holder(val row: ChartRow) : RecyclerView.ViewHolder(row)
}

/** One chart: ticker and company, quarter · form · filing date, a badge for 8-K / final, revenue and Y/Y. */
class ChartRow(context: Context) : LinearLayout(context) {
    private val title = TextView(context)
    private val sub = TextView(context)
    private val badge = TextView(context)
    private val rev = TextView(context)
    private val yoy = TextView(context)
    private val badgeBg = GradientDrawable()

    init {
        orientation = HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        layoutParams = RecyclerView.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        setPadding(dp(16), dp(12), dp(16), dp(12))
        val tv = TypedValue()
        context.theme.resolveAttribute(android.R.attr.selectableItemBackground, tv, true)
        setBackgroundResource(tv.resourceId)
        isClickable = true
        isFocusable = true

        val left = LinearLayout(context)
        left.orientation = VERTICAL
        title.textSize = 16f
        title.setTypeface(title.typeface, Typeface.BOLD)
        title.setTextColor(color(R.color.ink))
        title.maxLines = 1
        title.ellipsize = TextUtils.TruncateAt.END
        sub.textSize = 13f
        sub.setTextColor(color(R.color.muted))
        sub.maxLines = 1
        sub.ellipsize = TextUtils.TruncateAt.END
        badge.textSize = 11f
        badge.setTextColor(color(R.color.ink))
        badge.setPadding(dp(8), dp(2), dp(8), dp(2))
        badgeBg.cornerRadius = dp(10).toFloat()
        badge.background = badgeBg
        left.addView(title)
        left.addView(sub)
        val blp = LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        blp.topMargin = dp(4)
        left.addView(badge, blp)
        addView(left, LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))

        val right = LinearLayout(context)
        right.orientation = VERTICAL
        right.gravity = Gravity.END
        rev.textSize = 16f
        rev.setTypeface(rev.typeface, Typeface.BOLD)
        rev.setTextColor(color(R.color.ink))
        yoy.textSize = 13f
        right.addView(rev)
        right.addView(yoy)
        val rlp = LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        rlp.marginStart = dp(12)
        addView(right, rlp)
    }

    fun bind(e: Entry) {
        title.text = Feed.title(e)
        sub.text = Feed.subtitle(e)
        rev.text = e.rev
        yoy.text = Feed.yoy(e) ?: ""
        yoy.setTextColor(color(if ((e.yoy ?: 0.0) >= 0) R.color.accent else R.color.neg))
        val b = Feed.badge(e)
        badge.visibility = if (b == null) View.GONE else View.VISIBLE
        badge.text = b ?: ""
        badgeBg.setColor(color(if (e.prelim) R.color.chip_prelim else R.color.chip_final))
        contentDescription = listOfNotNull(Feed.title(e), Feed.subtitle(e), b, "revenue ${e.rev}", Feed.yoy(e)).joinToString(", ")
    }
}
