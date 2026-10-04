package io.github.eurikamonica.filingflows

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Typeface
import android.util.TypedValue
import android.view.View
import androidx.core.content.ContextCompat

/** Draws MoneySankey's layout: bands, node bars and labels, in the app's day or night colours. */
class MoneySankeyView(context: Context) : View(context) {
    private var flow: MoneyFlow? = null
    private var currency = "$"
    private var prevName: String? = null
    private var sk: SkLayout? = null
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val text = Paint(Paint.ANTI_ALIAS_FLAG)
    private val path = Path()
    private val dp = resources.displayMetrics.density
    private val sp = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_SP, 1f, resources.displayMetrics)   // follows the font size setting
    private fun c(id: Int) = ContextCompat.getColor(context, id)
    private val nodeColor = mapOf(Tone.INCOME to c(R.color.sk_income), Tone.SAVED to c(R.color.sk_saved),
        Tone.SPENT to c(R.color.sk_spent), Tone.DRAWN to c(R.color.sk_drawn))
    private val bandColor = mapOf(Tone.INCOME to c(R.color.sk_income_band), Tone.SAVED to c(R.color.sk_saved_band),
        Tone.SPENT to c(R.color.sk_spent_band), Tone.DRAWN to c(R.color.sk_drawn_band))
    private val ink = c(R.color.ink)
    private val muted = c(R.color.muted)

    fun show(f: MoneyFlow, currency: String, prevName: String?) {
        flow = f
        this.currency = currency
        this.prevName = prevName
        sk = null
        requestLayout()
        invalidate()
    }

    private fun build(width: Int): SkLayout? {
        val f = flow ?: return null
        val have = sk
        if (have != null && have.width == width.toFloat()) return have
        val bold = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
        val measure = { s: String, size: Float ->
            text.textSize = size
            text.typeface = bold
            text.measureText(s)
        }
        return MoneySankey.layout(f, currency, width.toFloat(), dp, sp, prevName, measure).also { sk = it }
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val w = MeasureSpec.getSize(widthMeasureSpec)
        val l = if (w > 0) build(w) else null
        setMeasuredDimension(w, l?.height?.toInt() ?: 0)
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val l = build(width) ?: return
        fill.style = Paint.Style.FILL
        for (b in l.bands) {
            val xm = (b.x0 + b.x1) / 2f
            path.reset()
            path.moveTo(b.x0, b.y0)
            path.cubicTo(xm, b.y0, xm, b.y1, b.x1, b.y1)
            path.lineTo(b.x1, b.y1 + b.w)
            path.cubicTo(xm, b.y1 + b.w, xm, b.y0 + b.w, b.x0, b.y0 + b.w)
            path.close()
            fill.color = bandColor.getValue(b.tone)
            canvas.drawPath(path, fill)
        }
        for (n in l.nodes) {
            fill.color = nodeColor.getValue(n.tone)
            canvas.drawRect(n.x, n.y, n.x + n.w, n.y + maxOf(n.h, 2f * dp), fill)
            var y = n.label.top
            text.textAlign = when (n.label.align) { -1 -> Paint.Align.RIGHT; 0 -> Paint.Align.CENTER; else -> Paint.Align.LEFT }
            for ((i, line) in n.label.lines.withIndex()) {
                val size = n.label.sizes[i]
                y += size * SkLabel.LINE
                text.textSize = size
                text.typeface = if (i == 0) Typeface.create(Typeface.DEFAULT, Typeface.BOLD) else Typeface.DEFAULT
                text.color = if (n.label.muted[i]) muted else ink
                canvas.drawText(line, n.label.x, y - size * 0.32f, text)
            }
        }
    }
}
