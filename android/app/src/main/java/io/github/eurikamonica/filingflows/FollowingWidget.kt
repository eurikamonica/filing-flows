package io.github.eurikamonica.filingflows

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.view.View
import android.widget.RemoteViews
import androidx.core.app.TaskStackBuilder

/** Home-screen widget: the newest charts of what the reader follows (or the newest charts overall). */
class FollowingWidget : AppWidgetProvider() {
    override fun onUpdate(context: Context, appWidgetManager: AppWidgetManager, appWidgetIds: IntArray) {
        render(context, appWidgetManager, appWidgetIds)
    }

    companion object {
        private val ROWS = intArrayOf(R.id.widget_row1, R.id.widget_row2, R.id.widget_row3)
        private const val FLAGS = PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE

        fun updateAll(context: Context) {
            val manager = AppWidgetManager.getInstance(context) ?: return
            val ids = manager.getAppWidgetIds(ComponentName(context, FollowingWidget::class.java))
            if (ids != null && ids.isNotEmpty()) render(context, manager, ids)
        }

        /** Opens a chart with the app's home underneath, so Back returns to the lists. */
        fun chartIntent(context: Context, e: Entry, requestCode: Int): PendingIntent? =
            TaskStackBuilder.create(context).addNextIntentWithParentStack(Links.chart(context, e)).getPendingIntent(requestCode, FLAGS)

        private fun render(context: Context, manager: AppWidgetManager, ids: IntArray) {
            val (mine, items) = Feed.widget(ChartsRepo(context).cached(), Store(context).follows())
            val views = RemoteViews(context.packageName, R.layout.widget_following)
            views.setTextViewText(R.id.widget_title, context.getString(if (mine) R.string.widget_following else R.string.widget_latest))
            views.setOnClickPendingIntent(R.id.widget_title,
                PendingIntent.getActivity(context, 0, Links.home(context, if (mine) "following" else "latest"), FLAGS))
            ROWS.forEachIndexed { i, id ->
                val e = items.getOrNull(i)
                if (e == null) {
                    views.setViewVisibility(id, View.GONE)
                } else {
                    views.setViewVisibility(id, View.VISIBLE)
                    views.setTextViewText(id, Feed.line(e))
                    chartIntent(context, e, 100 + i)?.let { views.setOnClickPendingIntent(id, it) }
                }
            }
            views.setViewVisibility(R.id.widget_empty, if (items.isEmpty()) View.VISIBLE else View.GONE)
            manager.updateAppWidget(ids, views)
        }
    }
}
