package io.github.eurikamonica.filingflows

import android.Manifest
import android.annotation.SuppressLint
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat

object Notifications {
    private const val CHANNEL = "new_charts"
    private const val GROUP = "io.github.eurikamonica.filingflows.NEW_CHARTS"
    private const val MAX_SHOWN = 6

    fun ensureChannel(context: Context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val ch = NotificationChannel(CHANNEL, context.getString(R.string.channel_name), NotificationManager.IMPORTANCE_DEFAULT)
            ch.description = context.getString(R.string.channel_description)
            context.getSystemService(NotificationManager::class.java).createNotificationChannel(ch)
        }
    }

    fun allowed(context: Context): Boolean =
        Build.VERSION.SDK_INT < 33 ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    @SuppressLint("MissingPermission")
    fun show(context: Context, charts: List<Fresh>) {
        if (charts.isEmpty() || !allowed(context)) return
        ensureChannel(context)
        val nm = NotificationManagerCompat.from(context)
        try {
            for ((e, final) in charts.take(MAX_SHOWN)) {
                val text = NewCharts.text(e, final)
                val n = NotificationCompat.Builder(context, CHANNEL)
                    .setSmallIcon(R.drawable.ic_stat_chart)
                    .setColor(ContextCompat.getColor(context, R.color.accent))
                    .setContentTitle(NewCharts.title(e, final))
                    .setContentText(text)
                    .setStyle(NotificationCompat.BigTextStyle().bigText(text))
                    .setContentIntent(open(context, "c-${e.cik}-${e.end}", e.cik.toInt()))
                    .setAutoCancel(true)
                    .setGroup(GROUP)
                    .build()
                nm.notify(e.cik.toInt(), n)
            }
            if (charts.size > 1) {
                val inbox = NotificationCompat.InboxStyle()
                charts.take(MAX_SHOWN).forEach { inbox.addLine(NewCharts.title(it.entry, it.final)) }
                val summary = NotificationCompat.Builder(context, CHANNEL)
                    .setSmallIcon(R.drawable.ic_stat_chart)
                    .setColor(ContextCompat.getColor(context, R.color.accent))
                    .setContentTitle(context.getString(R.string.new_charts, charts.size))
                    .setStyle(inbox)
                    .setContentIntent(open(context, "home", 0))
                    .setAutoCancel(true)
                    .setGroup(GROUP)
                    .setGroupSummary(true)
                    .build()
                nm.notify(SUMMARY_ID, summary)
            }
        } catch (e: SecurityException) {
            // permission withdrawn between the check and the call
        }
    }

    private const val SUMMARY_ID = -1

    private fun open(context: Context, hash: String, requestCode: Int): PendingIntent {
        val intent = Intent(context, MainActivity::class.java)
            .putExtra(MainActivity.EXTRA_HASH, hash)
            .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        return PendingIntent.getActivity(context, requestCode, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
    }
}
