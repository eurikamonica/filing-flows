package io.github.eurikamonica.filingflows

import java.util.Locale

/*
 * The personal Sankey, laid out without Android so it can be tested: income lines on the left flow into the total,
 * which splits into savings (green, on top) and spending lines (red, peeling downward). When spending is larger than
 * income, the gap enters on the left as "Savings used" (slate) and nothing is ever drawn with a negative width.
 * Colours follow the earnings charts: grey income, green savings, red spending, slate savings used.
 */

enum class Tone { INCOME, SAVED, SPENT, DRAWN }

/** A label: its lines (top to bottom), each with a text size in px and whether it is muted. align: -1 right, 0 centre, 1 left. */
data class SkLabel(val lines: List<String>, val sizes: List<Float>, val muted: List<Boolean>, val x: Float, val top: Float,
                   val align: Int) {
    val height: Float get() = sizes.sumOf { (it * LINE).toDouble() }.toFloat()

    companion object { const val LINE = 1.32f }
}

data class SkNode(val id: String, val col: Int, val value: Long, val tone: Tone, val x: Float, val y: Float, val h: Float,
                  val w: Float, val label: SkLabel)

/** A band of constant thickness `w` from (x0, y0) on its source to (x1, y1) on its target (top edges). */
data class SkBand(val from: String, val to: String, val value: Long, val tone: Tone, val x0: Float, val y0: Float,
                  val x1: Float, val y1: Float, val w: Float)

class SkLayout(val width: Float, val height: Float, val nodes: List<SkNode>, val bands: List<SkBand>) {
    val empty get() = nodes.isEmpty()
}

object MoneySankey {
    /**
     * f: the period's flows; prevName: what the change line compares with ("Sep", "2025") or null;
     * dp, sp: pixels per dp and per sp; measure(text, sizePx): the text's width in px.
     */
    fun layout(f: MoneyFlow, currency: String, width: Float, dp: Float, sp: Float, prevName: String?,
               measure: (String, Float) -> Float): SkLayout {
        val total = f.total
        if (total <= 0L) return SkLayout(width, 0f, emptyList(), emptyList())
        val nameSize = 12.5f * sp
        val valueSize = 11.5f * sp
        val noteSize = 10.5f * sp
        val nw = 10f * dp
        val gap = 10f * dp
        val pad = 8f * dp
        val leftW = minOf(width * 0.30f, 140f * dp)
        val rightW = minOf(width * 0.34f, 170f * dp)
        val x0 = leftW + 6f * dp
        val x2 = width - rightW - 6f * dp - nw
        val xc = (x0 + nw + x2) / 2f - nw / 2f

        fun share(v: Long): String {
            val p = v * 100.0 / total
            return if (p < 9.95) String.format(Locale.US, "%.1f%%", p) else String.format(Locale.US, "%.0f%%", p)
        }
        fun fitName(s: String, room: Float): String {
            if (measure(s, nameSize) <= room) return s
            var t = s
            while (t.length > 2 && measure("$t…", nameSize) > room) t = t.dropLast(1)
            return t.trimEnd() + "…"
        }
        fun change(now: Long, before: Long?): String? =
            if (prevName == null) null else Money.change(now, before)?.let { "vs $prevName $it" }

        // what goes in each column, top to bottom
        data class Item(val id: String, val name: String, val value: Long, val tone: Tone, val note: String?)
        val left = f.income.map { Item("in:" + (it.account ?: it.name), it.name, it.amount, Tone.INCOME,
            change(it.amount, it.account?.let { a -> f.prevIncome[a] })) } +
            (if (f.drawn > 0) listOf(Item("drawn", "Savings used", f.drawn, Tone.DRAWN, null)) else emptyList())
        val right = (if (f.saved > 0) listOf(Item("saved", "Saved", f.saved, Tone.SAVED, change(f.saved, f.prevSaved))) else emptyList()) +
            f.expenses.map { Item("out:" + (it.account ?: it.name), it.name, it.amount, Tone.SPENT,
                change(it.amount, it.account?.let { a -> f.prevExpenses[a] })) }

        fun label(it: Item, x: Float, align: Int, room: Float): SkLabel {
            val short = "${Money.label(it.value, currency)} · ${share(it.value)}"      // shares are of the total (centre)
            val value = if (measure(short, valueSize) <= room) short else Money.label(it.value, currency)
            val lines = mutableListOf(fitName(it.name, room), value)
            val sizes = mutableListOf(nameSize, valueSize)
            val muted = mutableListOf(false, false)
            if (it.note != null) { lines += it.note; sizes += noteSize; muted += true }
            return SkLabel(lines, sizes, muted, x, 0f, align)
        }
        val leftLabels = left.map { label(it, x0 - 6f * dp, -1, leftW - 2f * dp) }
        val rightLabels = right.map { label(it, x2 + nw + 6f * dp, 1, rightW - 2f * dp) }
        val centerName = if (f.drawn > 0) "Income + savings used" else "Income"
        val center = SkLabel(listOf(centerName, Money.label(total, currency)), listOf(nameSize, valueSize), listOf(false, false),
            xc + nw / 2f, pad, 0)

        // node area: tall enough for the chart and for every label in a column
        val top = pad + center.height + 6f * dp
        val labelGap = 4f * dp
        fun need(ls: List<SkLabel>) = ls.sumOf { it.height.toDouble() }.toFloat() + labelGap * (ls.size - 1).coerceAtLeast(0)
        val area = maxOf(220f * dp, width * 0.6f, need(leftLabels), need(rightLabels))
        val most = maxOf(left.size, right.size)
        val scale = (area - gap * (most - 1).coerceAtLeast(0)) / total

        // each node and its label share a block as tall as the larger of the two; blocks stack in order, centred
        // where the plain stack would put them, so every label sits level with its own node
        fun stack(items: List<Item>, x: Float, col: Int, labels: List<SkLabel>): List<SkNode> {
            val hs = items.map { it.value * scale }
            val height = hs.sum() + gap * (items.size - 1).coerceAtLeast(0)
            val blocks = items.indices.map { maxOf(hs[it], labels[it].height) }
            val want = ArrayList<Float>()
            var y = top + (area - height) / 2f
            for (i in items.indices) {
                want += y + hs[i] / 2f - blocks[i] / 2f
                y += hs[i] + gap
            }
            val tops = relax(want, blocks, top, 6f * dp)
            return items.mapIndexed { i, it ->
                val mid = tops[i] + blocks[i] / 2f
                SkNode(it.id, col, it.value, it.tone, x, mid - hs[i] / 2f, hs[i], nw, labels[i].copy(top = mid - labels[i].height / 2f))
            }
        }
        val lNodes = stack(left, x0, 0, leftLabels)
        val rNodes = stack(right, x2, 2, rightLabels)
        val ch = total * scale
        val cy = top + (area - ch) / 2f
        val cNode = SkNode("total", 1, total, Tone.INCOME, xc, cy, ch, nw, center)      // its label sits above the node area

        val bands = ArrayList<SkBand>()
        var off = cy
        for (n in lNodes) { bands += SkBand(n.id, "total", n.value, n.tone, x0 + nw, n.y, xc, off, n.h); off += n.h }
        off = cy
        for (n in rNodes) { bands += SkBand("total", n.id, n.value, n.tone, xc + nw, off, x2, n.y, n.h); off += n.h }

        val all = lNodes + cNode + rNodes
        val bottom = maxOf(top + area, all.maxOf { maxOf(it.label.top + it.label.height, it.y + it.h) })
        return SkLayout(width, bottom + pad, all, bands)
    }

    /**
     * Tops for blocks of the given heights, kept in order and never overlapping, each run of blocks that would collide
     * centred on where its blocks want to be (and not above minTop).
     */
    fun relax(want: List<Float>, heights: List<Float>, minTop: Float, gap: Float): List<Float> {
        class Run(val first: Int, var last: Int, var top: Float)
        fun offset(r: Run, i: Int): Float { var o = 0f; for (j in r.first until i) o += heights[j] + gap; return o }
        fun height(r: Run): Float = offset(r, r.last) + heights[r.last]
        fun settle(r: Run) {
            var sum = 0f
            for (i in r.first..r.last) sum += want[i] - offset(r, i)
            r.top = maxOf(sum / (r.last - r.first + 1), minTop)
        }
        val runs = ArrayList<Run>()
        for (i in want.indices) {
            val r = Run(i, i, 0f)
            settle(r)
            runs += r
            while (runs.size > 1) {
                val b = runs[runs.size - 1]
                val a = runs[runs.size - 2]
                if (b.top >= a.top + height(a) + gap) break
                a.last = b.last
                runs.removeAt(runs.size - 1)
                settle(a)
            }
        }
        val out = FloatArray(want.size)
        for (r in runs) for (i in r.first..r.last) out[i] = r.top + offset(r, i)
        return out.toList()
    }
}
