package fi.akux.app

import android.Manifest
import android.annotation.SuppressLint
import android.content.BroadcastReceiver
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.provider.MediaStore
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.webkit.JavascriptInterface
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

class MainActivity : ComponentActivity() {
    companion object {
        const val BASE = "http://127.0.0.1:8765"
    }

    private lateinit var web: WebView
    private lateinit var splash: TextView
    private var fileCallback: ValueCallback<Array<Uri>>? = null

    private val pickFile = registerForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        fileCallback?.onReceiveValue(if (uri != null) arrayOf(uri) else null)
        fileCallback = null
    }

    private val stoppedReceiver = object : BroadcastReceiver() {
        override fun onReceive(c: Context?, i: Intent?) {
            finishAndRemoveTask()
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Ilmoitukset (Android 13+) ja Bluetooth-yhteys OBDLink MX+ -sovittimeen (Android 12+)
        val needed = mutableListOf<String>()
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) needed += Manifest.permission.POST_NOTIFICATIONS
        if (Build.VERSION.SDK_INT >= 31 &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED
        ) needed += Manifest.permission.BLUETOOTH_CONNECT
        if (needed.isNotEmpty()) requestPermissions(needed.toTypedArray(), 1)
        ContextCompat.startForegroundService(this, Intent(this, AkuxService::class.java))
        ContextCompat.registerReceiver(
            this, stoppedReceiver, IntentFilter(AkuxService.ACTION_STOPPED), ContextCompat.RECEIVER_NOT_EXPORTED
        )

        val root = FrameLayout(this)
        web = WebView(this)
        splash = TextView(this).apply {
            text = "AKVERI käynnistyy…"
            textSize = 18f
            setTextColor(Color.parseColor("#1B2430"))
            setBackgroundColor(Color.parseColor("#F3F4F6"))
            gravity = Gravity.CENTER
        }
        root.addView(web, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        root.addView(splash, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        setContentView(root)

        web.settings.javaScriptEnabled = true
        web.settings.domStorageEnabled = true
        web.settings.allowFileAccess = false
        web.settings.setSupportMultipleWindows(false)
        web.addJavascriptInterface(Bridge(), "AkuxAndroid")
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val url = request.url.toString()
                if (!url.startsWith(BASE)) {
                    startActivity(Intent(Intent.ACTION_VIEW, request.url))
                    return true
                }
                if (isDownload(request.url)) {
                    download(url)
                    return true
                }
                return false
            }
        }
        web.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(
                view: WebView, callback: ValueCallback<Array<Uri>>, params: FileChooserParams
            ): Boolean {
                fileCallback?.onReceiveValue(null)
                fileCallback = callback
                val type = params.acceptTypes.firstOrNull { it.isNotBlank() } ?: "*/*"
                pickFile.launch(
                    when {
                        type.startsWith("image") -> "image/*"
                        type.contains("zip") -> "application/zip"
                        else -> "*/*"
                    }
                )
                return true
            }
        }
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (web.canGoBack()) web.goBack() else moveTaskToBack(true)
            }
        })
        waitForServer()
    }

    private fun waitForServer() {
        thread(name = "akux-odotus") {
            val end = System.currentTimeMillis() + 120_000
            while (System.currentTimeMillis() < end) {
                try {
                    val c = URL("$BASE/api/tietoja").openConnection() as HttpURLConnection
                    c.connectTimeout = 1000
                    c.readTimeout = 2000
                    if (c.responseCode == 200) {
                        runOnUiThread {
                            web.loadUrl(BASE)
                            splash.visibility = View.GONE
                        }
                        return@thread
                    }
                } catch (_: Exception) {
                }
                Thread.sleep(400)
            }
            runOnUiThread { splash.text = "AKVERI ei käynnistynyt. Sulje sovellus ja avaa se uudelleen." }
        }
    }

    private fun isDownload(u: Uri): Boolean {
        val p = u.path ?: return false
        return p.endsWith(".pdf") || p.endsWith(".csv") || p.endsWith(".gz") || p.endsWith(".zip") || p.endsWith(".akux") || p.endsWith(".akveri") ||
            p == "/api/yllapito/varmuuskopio"
    }

    /** Lataa tiedoston ohjelmalta, tallentaa sen Lataukset/AKVERI-kansioon ja avaa tai jakaa sen. */
    private fun download(url: String) {
        Toast.makeText(this, "Avataan…", Toast.LENGTH_SHORT).show()
        thread(name = "akux-lataus") {
            try {
                val c = URL(url).openConnection() as HttpURLConnection
                c.readTimeout = 180_000
                if (c.responseCode != 200) throw Exception("Tiedostoa ei voitu muodostaa (${c.responseCode}).")
                val disp = c.getHeaderField("Content-Disposition") ?: ""
                val name = Regex("filename=\"?([^\";]+)").find(disp)?.groupValues?.get(1)
                    ?: Uri.parse(url).lastPathSegment ?: "akveri"
                val mime = (c.contentType ?: "application/octet-stream").substringBefore(";")
                val bytes = c.inputStream.use { it.readBytes() }

                val dir = File(cacheDir, "vienti").apply { mkdirs() }
                val f = File(dir, name)
                f.writeBytes(bytes)
                saveToDownloads(name, mime, bytes)
                val uri = FileProvider.getUriForFile(this, "$packageName.tiedostot", f)
                runOnUiThread {
                    Toast.makeText(this, "Tallennettu: Lataukset/AKVERI/$name", Toast.LENGTH_LONG).show()
                    val view = Intent(Intent.ACTION_VIEW).setDataAndType(uri, mime)
                        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    val send = Intent(Intent.ACTION_SEND).setType(mime).putExtra(Intent.EXTRA_STREAM, uri)
                        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    val target = if (mime == "application/pdf") view else send
                    try {
                        startActivity(Intent.createChooser(target, name))
                    } catch (_: Exception) {
                        startActivity(Intent.createChooser(send, name))
                    }
                }
            } catch (e: Exception) {
                runOnUiThread { Toast.makeText(this, e.message ?: "Tiedoston avaaminen epäonnistui", Toast.LENGTH_LONG).show() }
            }
        }
    }

    private fun saveToDownloads(name: String, mime: String, bytes: ByteArray) {
        try {
            val values = ContentValues().apply {
                put(MediaStore.Downloads.DISPLAY_NAME, name)
                put(MediaStore.Downloads.MIME_TYPE, mime)
                put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/AKVERI")
            }
            val uri = contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values) ?: return
            contentResolver.openOutputStream(uri)?.use { it.write(bytes) }
        } catch (_: Exception) {
        }
    }

    inner class Bridge {
        @JavascriptInterface
        fun close() {
            runOnUiThread { finishAndRemoveTask() }
        }

        @JavascriptInterface
        fun platform(): String = "android"
    }

    override fun onDestroy() {
        try {
            unregisterReceiver(stoppedReceiver)
        } catch (_: Exception) {
        }
        web.destroy()
        super.onDestroy()
    }
}
