package io.github.eurikamonica.filingflows

import android.Manifest
import android.annotation.SuppressLint
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.result.ActivityResultLauncher
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat

/** What the web pages can ask of the screen that shows them (see Bridge). */
interface AppHost {
    fun askNotificationPermission()
    fun onFollowsChanged()
}

/** The interactive chart pages, sectors and sign-in are the site itself, shown in a WebView configured here. */
object Web {
    private val site: Uri = Uri.parse(BuildConfig.SITE_URL)

    @SuppressLint("SetJavaScriptEnabled")
    fun configure(activity: AppCompatActivity, web: WebView) {
        if (BuildConfig.DEBUG) WebView.setWebContentsDebuggingEnabled(true)
        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true                         // keeps the sign-in between launches
            setSupportZoom(true)
            builtInZoomControls = true
            displayZoomControls = false
            // offline: charts already opened once come from the cache
            cacheMode = if (Net.online(activity)) WebSettings.LOAD_DEFAULT else WebSettings.LOAD_CACHE_ELSE_NETWORK
            userAgentString = "$userAgentString FilingFlowsApp/${BuildConfig.VERSION_NAME}"
        }
        web.addJavascriptInterface(Bridge(activity), "FilingFlowsApp")
        web.webChromeClient = WebChromeClient()
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                if (isOurs(request.url)) return false
                openOutside(activity, request.url)
                return true
            }

            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (request.isForMainFrame) view.loadDataWithBaseURL(null, offlineHtml(), "text/html", "utf-8", null)
            }
        }
    }

    fun isOurs(u: Uri): Boolean =
        u.scheme == "https" && u.host.equals(site.host, ignoreCase = true) && (u.path ?: "/").startsWith(site.path ?: "/")

    fun openOutside(context: Context, u: Uri) {
        try {
            context.startActivity(Intent(Intent.ACTION_VIEW, u))
        } catch (e: ActivityNotFoundException) {
            // nothing on the phone handles this link
        }
    }

    fun url(hash: String): String = BuildConfig.SITE_URL + "#" + hash

    fun offlineHtml(): String = """<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1">
        <style>body{font:16px/1.5 sans-serif;margin:0;padding:48px 24px;color:#1d1d1b;background:#f3f2ee}
        @media (prefers-color-scheme:dark){body{color:#ecebe6;background:#151514}}
        button{font:inherit;padding:10px 18px;border:0;border-radius:8px;background:#17734a;color:#fff}</style>
        <h2>No connection</h2><p>This page has not been opened on this phone before. The lists in the app still show the last charts it loaded.</p>
        <button onclick="history.back()">Back</button>"""

    /** Android 13+: ask once per screen visit, after the reader follows something. */
    fun askNotifications(activity: AppCompatActivity, launcher: ActivityResultLauncher<String>, asked: Boolean): Boolean {
        if (Build.VERSION.SDK_INT < 33 || asked) return asked
        if (ContextCompat.checkSelfPermission(activity, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED) return asked
        launcher.launch(Manifest.permission.POST_NOTIFICATIONS)
        return true
    }
}

/** Intents that open a chart (from the lists, notifications, the widget and app links). */
object Links {
    const val EXTRA_HASH = "hash"
    const val EXTRA_TITLE = "title"
    const val EXTRA_TAB = "tab"

    fun chart(context: Context, e: Entry): Intent = chart(context, "c-${e.cik}-${e.end}", Feed.line(e))

    fun chart(context: Context, hash: String, title: String?): Intent =
        Intent(context, ChartActivity::class.java).putExtra(EXTRA_HASH, hash).putExtra(EXTRA_TITLE, title)

    fun home(context: Context, tab: String? = null): Intent =
        Intent(context, MainActivity::class.java).putExtra(EXTRA_TAB, tab)
            .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP)
}
