package io.github.eurikamonica.filingflows

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.content.res.ColorStateList
import android.content.res.Configuration
import android.os.Bundle
import android.text.format.DateUtils
import android.view.Menu
import android.view.ViewGroup
import android.webkit.WebView
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.lifecycle.lifecycleScope
import com.google.android.material.bottomnavigation.BottomNavigationView
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

/**
 * Home: native tabs. "Following" and "Latest" are native lists of charts (from the site's data, cached for offline use);
 * "Sectors" and "Alerts" (sign-in and settings) are the site's own pages. A chart opens in ChartActivity.
 * "Money" is personal bookkeeping kept on the phone only (MoneyView): no sign-in, not part of the website.
 */
class MainActivity : AppCompatActivity(), AppHost, MoneyHost {
    private lateinit var content: FrameLayout
    private lateinit var nav: BottomNavigationView
    private lateinit var following: ChartListView
    private lateinit var latest: ChartListView
    private lateinit var repo: ChartsRepo
    private var web: WebView? = null
    private var money: MoneyView? = null
    private var entries: List<Entry> = emptyList()
    private var companies: List<Entry> = emptyList()      // SEC's list, loaded the first time the reader searches
    private var companiesState = 0                        // 0 not loaded, 1 loading, 2 loaded (or failed)
    private var query = ""
    private var current = 0
    private var loading = false
    private var asked = false
    private val askNotifications = registerForActivityResult(ActivityResultContracts.RequestPermission()) { }
    private val pickBackup = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> if (uri != null) readBackup(uri) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        repo = ChartsRepo(this)

        val root = LinearLayout(this)
        root.orientation = LinearLayout.VERTICAL
        root.setBackgroundColor(ContextCompat.getColor(this, R.color.ground))
        content = FrameLayout(this)
        root.addView(content, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        nav = BottomNavigationView(this)
        nav.menu.add(Menu.NONE, R.id.tab_following, 0, R.string.tab_following).setIcon(R.drawable.ic_tab_following)
        nav.menu.add(Menu.NONE, R.id.tab_latest, 1, R.string.tab_latest).setIcon(R.drawable.ic_tab_latest)
        nav.menu.add(Menu.NONE, R.id.tab_sectors, 2, R.string.tab_sectors).setIcon(R.drawable.ic_tab_sectors)
        nav.menu.add(Menu.NONE, R.id.tab_alerts, 3, R.string.tab_alerts).setIcon(R.drawable.ic_tab_alerts)
        nav.menu.add(Menu.NONE, R.id.tab_money, 4, R.string.tab_money).setIcon(R.drawable.ic_tab_money)
        styleNav()
        root.addView(nav, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        setContentView(root)
        ViewCompat.setOnApplyWindowInsetsListener(root) { v, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            v.setPadding(bars.left, bars.top, bars.right, 0)        // the bottom bar pads itself above the navigation bar
            insets
        }
        val night = (resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES
        WindowCompat.getInsetsController(window, root).isAppearanceLightStatusBars = !night

        following = ChartListView(this, false)
        following.onOpen = { open(it) }
        following.onRefresh = { refresh(true) }
        latest = ChartListView(this, true)
        latest.onOpen = { open(it) }
        latest.onRefresh = { refresh(true) }
        latest.onQuery = {
            query = it
            render()
            if (it.isNotBlank()) loadCompanies()
        }

        entries = repo.cached()
        nav.setOnItemSelectedListener { show(it.itemId); true }
        val start = tabFor(intent.getStringExtra(Links.EXTRA_TAB)) ?: homeTab()
        nav.selectedItemId = start
        show(start)
        render()
        refresh(entries.isEmpty() || repo.age() > STALE_MS)
        handleLink(intent)

        Notifications.ensureChannel(this)
        ChartCheckWorker.schedule(this)
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                val w = web
                when {
                    isWebTab() && w != null && w.canGoBack() -> w.goBack()
                    current != homeTab() -> nav.selectedItemId = homeTab()
                    else -> {
                        isEnabled = false
                        onBackPressedDispatcher.onBackPressed()
                        isEnabled = true
                    }
                }
            }
        })
    }

    override fun onResume() {
        super.onResume()
        render()                                   // follows may have changed on a chart page
        if (repo.age() > STALE_MS) refresh(true)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        tabFor(intent.getStringExtra(Links.EXTRA_TAB))?.let { nav.selectedItemId = it }
        handleLink(intent)
    }

    override fun onDestroy() {
        web?.destroy()
        super.onDestroy()
    }

    // ---------------------------------------------------------------- tabs
    private fun styleNav() {
        val ink = ContextCompat.getColor(this, R.color.ink)
        val muted = ContextCompat.getColor(this, R.color.muted)
        val tint = ColorStateList(arrayOf(intArrayOf(android.R.attr.state_checked), intArrayOf()), intArrayOf(ink, muted))
        nav.setBackgroundColor(ContextCompat.getColor(this, R.color.paper))
        nav.itemIconTintList = tint
        nav.itemTextColor = tint
        nav.itemActiveIndicatorColor = ColorStateList.valueOf(ContextCompat.getColor(this, R.color.accent_soft))
    }

    private fun tabFor(name: String?): Int? = when (name) {
        "following" -> R.id.tab_following
        "latest" -> R.id.tab_latest
        "sectors" -> R.id.tab_sectors
        "alerts" -> R.id.tab_alerts
        "money" -> R.id.tab_money
        else -> null
    }

    private fun homeTab(): Int = if (Store(this).follows()?.any == true) R.id.tab_following else R.id.tab_latest

    private fun isWebTab() = current == R.id.tab_sectors || current == R.id.tab_alerts

    private fun show(id: Int) {
        if (id == current && content.childCount > 0) return
        current = id
        content.removeAllViews()
        val full = FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
        when (id) {
            R.id.tab_following -> content.addView(following, full)
            R.id.tab_latest -> content.addView(latest, full)
            R.id.tab_sectors -> showWeb(full, Web.url("sectors"))
            R.id.tab_alerts -> showWeb(full, Web.url("account"))
            R.id.tab_money -> content.addView(moneyView(), full)
        }
    }

    private fun moneyView(): MoneyView = money ?: MoneyView(this, this).also { money = it }

    private fun webView(): WebView = web ?: WebView(this).also {
        Web.configure(this, it)
        web = it
    }

    private fun showWeb(params: FrameLayout.LayoutParams, url: String) {
        val w = webView()
        content.addView(w, params)
        w.loadUrl(url)
    }

    // ---------------------------------------------------------------- data
    private fun render() {
        val follows = Store(this).follows()
        val mine = Feed.following(entries, follows)
        when {
            mine.isNotEmpty() || entries.isEmpty() -> following.show(mine, getString(R.string.latest_empty))
            follows?.any == true -> following.show(mine, getString(R.string.following_none_yet))
            else -> following.show(mine, getString(R.string.following_empty), getString(R.string.following_action)) {
                nav.selectedItemId = R.id.tab_alerts
            }
        }
        latest.show(Feed.search(entries, query, companies), getString(if (entries.isEmpty()) R.string.latest_empty else R.string.search_none))
    }

    /** SEC's company list, so the search finds companies the site has not drawn yet (cached for a day). */
    private fun loadCompanies() {
        if (companiesState != 0) return
        companiesState = 1
        lifecycleScope.launch {
            companies = withContext(Dispatchers.IO) {
                val cached = repo.cachedCompanies()
                if (cached.isNotEmpty() && repo.companiesAge() < DAY_MS) cached
                else runCatching { repo.refreshCompanies() }.getOrDefault(cached)
            }
            companiesState = if (companies.isEmpty()) 0 else 2      // offline: the next search tries again
            render()
        }
    }

    private fun refresh(force: Boolean) {
        if (!force || loading) {
            following.setRefreshing(false)
            latest.setRefreshing(false)
            return
        }
        loading = true
        following.setRefreshing(true)
        latest.setRefreshing(true)
        lifecycleScope.launch {
            val result = withContext(Dispatchers.IO) { runCatching { repo.refresh() } }
            loading = false
            following.setRefreshing(false)
            latest.setRefreshing(false)
            val note = if (result.isSuccess) {
                entries = result.getOrDefault(entries)
                FollowingWidget.updateAll(this@MainActivity)
                null
            } else if (entries.isNotEmpty()) {
                val age = DateUtils.getRelativeTimeSpanString(System.currentTimeMillis() - repo.age()).toString()
                getString(R.string.offline_cached, age)
            } else {
                getString(R.string.offline_none)
            }
            following.setStatus(note)
            latest.setStatus(note)
            render()
        }
    }

    private fun open(e: Entry) = startActivity(Links.chart(this, e))

    // ---------------------------------------------------------------- links from e-mails, notifications, shortcuts
    private fun handleLink(i: Intent?) {
        if (i == null) return
        val hash = i.getStringExtra(Links.EXTRA_HASH)
        if (hash != null) {
            route(hash, null)
            return
        }
        val data = i.data ?: return
        if (Web.isOurs(data)) route(data.fragment ?: "", data.toString())
    }

    private fun route(hash: String, url: String?) {
        when {
            hash.startsWith("c-") -> startActivity(Links.chart(this, hash, null))
            hash == "sectors" || hash.startsWith("s-") || hash.startsWith("i-") -> {
                nav.selectedItemId = R.id.tab_sectors
                webView().loadUrl(url ?: Web.url(hash))
            }
            hash == "account" || hash.startsWith("unsubscribe-") -> {
                nav.selectedItemId = R.id.tab_alerts
                webView().loadUrl(url ?: Web.url(hash))
            }
            else -> nav.selectedItemId = homeTab()
        }
    }

    // ---------------------------------------------------------------- AppHost (called by the web pages)
    override fun askNotificationPermission() {
        asked = Web.askNotifications(this, askNotifications, asked)
    }

    override fun onFollowsChanged() {
        render()
    }

    // ---------------------------------------------------------------- MoneyHost (the Money tab)
    override fun shareMoneyFile(name: String, mime: String, text: String) {
        try {
            val dir = File(cacheDir, "shared").apply { mkdirs() }
            val f = File(dir, name.replace(Regex("[^A-Za-z0-9._-]+"), "-"))
            f.writeText(text)
            val uri = FileProvider.getUriForFile(this, "$packageName.files", f)
            val send = Intent(Intent.ACTION_SEND)
                .setType(mime)
                .putExtra(Intent.EXTRA_STREAM, uri)
                .putExtra(Intent.EXTRA_SUBJECT, f.name)
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            startActivity(Intent.createChooser(send, f.name))
        } catch (e: Exception) {
            Toast.makeText(this, getString(R.string.save_failed), Toast.LENGTH_SHORT).show()
        }
    }

    override fun pickMoneyBackup() {
        try {
            pickBackup.launch(arrayOf("application/json", "text/plain", "application/octet-stream", "*/*"))
        } catch (e: ActivityNotFoundException) {
            Toast.makeText(this, "No app to pick a file with", Toast.LENGTH_SHORT).show()
        }
    }

    private fun readBackup(uri: Uri) {
        val text = runCatching { contentResolver.openInputStream(uri)?.use { it.readBytes().toString(Charsets.UTF_8) } }.getOrNull()
        if (text == null) {
            Toast.makeText(this, getString(R.string.save_failed), Toast.LENGTH_SHORT).show()
            return
        }
        nav.selectedItemId = R.id.tab_money
        moneyView().restore(text)
    }

    companion object {
        private const val STALE_MS = 15 * 60_000L
        private const val DAY_MS = 24 * 60 * 60_000L
    }
}
