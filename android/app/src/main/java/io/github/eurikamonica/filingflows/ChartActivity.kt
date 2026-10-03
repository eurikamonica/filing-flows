package io.github.eurikamonica.filingflows

import android.content.Intent
import android.os.Bundle
import android.view.Menu
import android.view.MenuItem
import android.view.ViewGroup
import android.webkit.WebView
import android.widget.LinearLayout
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import com.google.android.material.appbar.MaterialToolbar

/** One company's chart: the site's interactive Sankey under a native toolbar with back and share. */
class ChartActivity : AppCompatActivity(), AppHost {
    private lateinit var web: WebView
    private var hash = ""
    private var heading = ""
    private var asked = false
    private val askNotifications = registerForActivityResult(ActivityResultContracts.RequestPermission()) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        hash = intent.getStringExtra(Links.EXTRA_HASH) ?: "home"
        heading = intent.getStringExtra(Links.EXTRA_TITLE) ?: getString(R.string.app_name)

        val root = LinearLayout(this)
        root.orientation = LinearLayout.VERTICAL
        root.setBackgroundColor(ContextCompat.getColor(this, R.color.ground))
        val bar = MaterialToolbar(this)
        bar.title = heading
        bar.setBackgroundColor(ContextCompat.getColor(this, R.color.paper))
        bar.setTitleTextColor(ContextCompat.getColor(this, R.color.ink))
        bar.setNavigationIcon(R.drawable.ic_arrow_back)
        bar.setNavigationContentDescription(R.string.back)
        bar.setNavigationOnClickListener { finish() }
        bar.menu.add(Menu.NONE, R.id.action_share, 0, R.string.share).setIcon(R.drawable.ic_share)
            .setShowAsAction(MenuItem.SHOW_AS_ACTION_ALWAYS)
        bar.setOnMenuItemClickListener { item ->
            if (item.itemId == R.id.action_share) {
                shareLink()
                true
            } else {
                false
            }
        }
        root.addView(bar, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        web = WebView(this)
        Web.configure(this, web)
        root.addView(web, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        setContentView(root)
        ViewCompat.setOnApplyWindowInsetsListener(root) { v, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            v.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            insets
        }

        if (savedInstanceState == null || web.restoreState(savedInstanceState) == null) web.loadUrl(Web.url(hash))
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (web.canGoBack()) web.goBack() else finish()
            }
        })
    }

    private fun shareLink() {
        val send = Intent(Intent.ACTION_SEND)
            .setType("text/plain")
            .putExtra(Intent.EXTRA_SUBJECT, heading)
            .putExtra(Intent.EXTRA_TEXT, heading + "\n" + Web.url(hash))
        startActivity(Intent.createChooser(send, getString(R.string.share_chart)))
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        web.saveState(outState)
    }

    override fun onDestroy() {
        web.destroy()
        super.onDestroy()
    }

    override fun askNotificationPermission() {
        asked = Web.askNotifications(this, askNotifications, asked)
    }

    override fun onFollowsChanged() {
        FollowingWidget.updateAll(this)
    }
}
