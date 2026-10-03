package io.github.eurikamonica.filingflows

import android.Manifest
import android.annotation.SuppressLint
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat

/** The site in a WebView: same pages, same sign-in; exports save to Downloads; new charts arrive as notifications. */
class MainActivity : AppCompatActivity() {
    private lateinit var web: WebView
    private val site: Uri = Uri.parse(BuildConfig.SITE_URL)
    private var askedThisSession = false

    private val askNotifications = registerForActivityResult(ActivityResultContracts.RequestPermission()) { }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        val root = FrameLayout(this)
        root.setBackgroundColor(ContextCompat.getColor(this, R.color.ground))
        web = WebView(this)
        root.addView(web, FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT))
        setContentView(root)
        ViewCompat.setOnApplyWindowInsetsListener(root) { v, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            v.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            insets
        }
        val night = (resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES
        WindowCompat.getInsetsController(window, root).apply {
            isAppearanceLightStatusBars = !night
            isAppearanceLightNavigationBars = !night
        }

        if (BuildConfig.DEBUG) WebView.setWebContentsDebuggingEnabled(true)
        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true                       // keeps the sign-in between launches
            setSupportZoom(true)
            builtInZoomControls = true
            displayZoomControls = false
            userAgentString = "$userAgentString FilingFlowsApp/${BuildConfig.VERSION_NAME}"
        }
        web.addJavascriptInterface(Bridge(this), "FilingFlowsApp")
        web.webChromeClient = WebChromeClient()
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                if (isOurs(request.url)) return false
                openOutside(request.url)
                return true
            }

            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (request.isForMainFrame) showOffline()
            }
        }
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (web.canGoBack()) {
                    web.goBack()
                } else {
                    isEnabled = false
                    onBackPressedDispatcher.onBackPressed()
                }
            }
        })

        if (savedInstanceState == null || web.restoreState(savedInstanceState) == null) web.loadUrl(startUrl(intent))
        Notifications.ensureChannel(this)
        ChartCheckWorker.schedule(this)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        if (intent.hasExtra(EXTRA_HASH) || intent.data != null) web.loadUrl(startUrl(intent))
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        web.saveState(outState)
    }

    override fun onDestroy() {
        web.destroy()
        super.onDestroy()
    }

    fun askNotificationPermission() {
        if (Build.VERSION.SDK_INT < 33 || askedThisSession) return
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED) return
        askedThisSession = true
        askNotifications.launch(Manifest.permission.POST_NOTIFICATIONS)
    }

    private fun startUrl(i: Intent?): String {
        i?.getStringExtra(EXTRA_HASH)?.let { return BuildConfig.SITE_URL + "#" + it }
        i?.data?.let { if (isOurs(it)) return it.toString() }
        return BuildConfig.SITE_URL
    }

    private fun isOurs(u: Uri): Boolean =
        u.scheme == "https" && u.host.equals(site.host, ignoreCase = true) && (u.path ?: "/").startsWith(site.path ?: "/")

    private fun openOutside(u: Uri) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, u))
        } catch (e: ActivityNotFoundException) {
            // nothing on the phone handles this link
        }
    }

    private fun showOffline() {
        val html = """<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1">
            <style>body{font:16px/1.5 sans-serif;margin:0;padding:48px 24px;color:#1d1d1b;background:#f3f2ee}
            @media (prefers-color-scheme:dark){body{color:#ecebe6;background:#151514}}
            button{font:inherit;padding:10px 18px;border:0;border-radius:8px;background:#17734a;color:#fff}</style>
            <h2>No connection</h2><p>Filing Flows needs the internet to load the charts.</p>
            <button onclick="location.replace('${BuildConfig.SITE_URL}')">Try again</button>"""
        web.loadDataWithBaseURL(null, html, "text/html", "utf-8", null)
    }

    companion object {
        const val EXTRA_HASH = "hash"
    }
}
