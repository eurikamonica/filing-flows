package io.github.eurikamonica.filingflows

import android.content.ClipData
import android.content.ClipboardManager
import android.content.ContentValues
import android.content.Context
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.util.Base64
import android.webkit.JavascriptInterface
import android.widget.Toast
import java.io.File

/**
 * window.FilingFlowsApp in the web page. The site calls it when it runs inside the app:
 *   setFollows(json)              what the signed-in reader follows (for notifications)
 *   saveFile(name, mime, base64)  chart exports (PNG, JPG, PDF) into Downloads
 *   copyText(text)                the Copy buttons
 * Only pages from the site are ever loaded in the app (other links open in the browser).
 */
class Bridge(private val activity: MainActivity) {
    private val context: Context = activity.applicationContext

    @JavascriptInterface
    fun setFollows(json: String?) {
        val store = Store(context)
        store.saveFollows(json)
        if (store.follows()?.active == true) activity.runOnUiThread { activity.askNotificationPermission() }
    }

    @JavascriptInterface
    fun saveFile(name: String, mime: String, base64: String): Boolean {
        val safe = name.replace(Regex("[^A-Za-z0-9._-]+"), "-").trim('-').take(120).ifEmpty { "chart" }
        return try {
            val bytes = Base64.decode(base64, Base64.DEFAULT)
            val where = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                val resolver = context.contentResolver
                val values = ContentValues().apply {
                    put(MediaStore.Downloads.DISPLAY_NAME, safe)
                    put(MediaStore.Downloads.MIME_TYPE, mime)
                    put(MediaStore.Downloads.IS_PENDING, 1)
                }
                val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                    ?: throw IllegalStateException("no Downloads folder")
                resolver.openOutputStream(uri)?.use { it.write(bytes) } ?: throw IllegalStateException("cannot write")
                values.clear()
                values.put(MediaStore.Downloads.IS_PENDING, 0)
                resolver.update(uri, values, null, null)
                context.getString(R.string.saved_downloads, safe)
            } else {
                val dir = context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS) ?: context.filesDir
                val f = File(dir, safe)
                f.writeBytes(bytes)
                context.getString(R.string.saved_at, f.absolutePath)
            }
            toast(where)
            true
        } catch (e: Exception) {
            toast(context.getString(R.string.save_failed))
            false
        }
    }

    @JavascriptInterface
    fun copyText(text: String) {
        activity.runOnUiThread {
            val cm = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            cm.setPrimaryClip(ClipData.newPlainText("Filing Flows", text))
            if (Build.VERSION.SDK_INT < 33) toast(context.getString(R.string.copied))   // newer Android shows its own
        }
    }

    private fun toast(msg: String) = activity.runOnUiThread { Toast.makeText(context, msg, Toast.LENGTH_SHORT).show() }
}
