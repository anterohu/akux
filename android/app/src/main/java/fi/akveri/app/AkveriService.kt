package fi.akveri.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ApplicationInfo
import android.content.pm.ServiceInfo
import android.os.IBinder
import android.os.PowerManager
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

/**
 * AKVERI toimii etualapalveluna, jotta mittaus jatkuu myös näytön ollessa
 * sammuksissa tai sovelluksen ollessa taustalla. Pitkä kapasiteettimittaus
 * kestää kymmenkunta tuntia.
 */
class AkveriService : Service() {
    private var wakeLock: PowerManager.WakeLock? = null

    companion object {
        const val CHANNEL = "akveri_kaynnissa"
        const val ACTION_STOPPED = "fi.akveri.app.PYSAYTETTY"

        @Volatile
        var started = false
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL, Kieli.t(this, "AKVERI käynnissä", "AKVERI running", "AKVERI körs"), NotificationManager.IMPORTANCE_LOW).apply {
                description = Kieli.t(this@AkveriService, "Näkyy, kun AKVERI on käynnissä ja voi mitata", "Shown when AKVERI is running and can measure", "Visas när AKVERI körs och kan mäta")
            }
        )
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE
        )
        val n: Notification = Notification.Builder(this, CHANNEL)
            .setContentTitle(Kieli.t(this, "AKVERI on käynnissä", "AKVERI is running", "AKVERI körs"))
            .setContentText(Kieli.t(this, "Mittaus jatkuu, vaikka näyttö sammuu.", "The test continues even when the screen turns off.", "Testet fortsätter även när skärmen släcks."))
            .setSmallIcon(R.drawable.ic_stat_akveri)
            .setContentIntent(open)
            .setOngoing(true)
            .build()
        startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE)

        if (wakeLock == null) {
            val pm = getSystemService(PowerManager::class.java)
            wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "AKVERI::mittaus").apply {
                setReferenceCounted(false)
                acquire()
            }
        }

        if (!started) {
            started = true
            if (!Python.isStarted()) Python.start(AndroidPlatform(this))
            val bridge = UsbBridge(applicationContext)
            bridge.stoppedListener = {
                started = false
                sendBroadcast(Intent(ACTION_STOPPED).setPackage(packageName))
                stopSelf()
            }
            // Testiversiossa (debug) esittelytila on aina käytössä emulaattoritestejä varten. Play-versiossa se on vain
            // akveri.fi:n testitileillä.
            if ((applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE) != 0) {
                Python.getInstance().getModule("os")["environ"]?.callAttr("__setitem__", "AKVERI_ESITTELY", "1")
            }
            Python.getInstance().getModule("akveri.android").callAttr("start", filesDir.absolutePath, bridge)
        }
        return START_STICKY
    }

    override fun onDestroy() {
        wakeLock?.let { if (it.isHeld) it.release() }
        wakeLock = null
        super.onDestroy()
    }
}
