package fi.akux.app

import android.app.PendingIntent
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.hardware.usb.UsbManager
import android.os.Environment
import android.provider.MediaStore
import com.hoho.android.usbserial.driver.UsbSerialPort
import com.hoho.android.usbserial.driver.UsbSerialProber
import java.io.IOException

/**
 * USB-sarjayhteys OBDLink-sovittimeen Android-laitteessa.
 * Pythonin mittauskoodi kutsuu näitä metodeja samaan tapaan kuin pyserial-kirjastoa.
 */
class UsbBridge(private val context: Context) {
    private val usb = context.getSystemService(Context.USB_SERVICE) as UsbManager
    private var port: UsbSerialPort? = null
    private val lock = Any()

    @Volatile
    var stoppedListener: (() -> Unit)? = null

    private fun drivers() = UsbSerialProber.getDefaultProber().findAllDrivers(usb)

    /** Kytketyt sovittimet muodossa "OBDLink (FTDI) 0403:6015". */
    fun listDevices(): Array<String> = drivers().map { d ->
        val dev = d.device
        val name = dev.productName ?: "USB-sovitin"
        "%s %04X:%04X".format(name, dev.vendorId, dev.productId)
    }.toTypedArray()

    fun open(name: String, baud: Int) {
        synchronized(lock) {
            closeLocked()
            val all = drivers()
            if (all.isEmpty()) throw IOException("Sovitinta ei löydy. Kytke OBDLink puhelimeen USB-C-sovittimella.")
            val driver = all.firstOrNull { name.endsWith("%04X:%04X".format(it.device.vendorId, it.device.productId)) }
                ?: all.first()
            if (!usb.hasPermission(driver.device)) {
                val intent = Intent("fi.akux.app.USB_LUPA").setPackage(context.packageName)
                val pi = PendingIntent.getBroadcast(context, 0, intent, PendingIntent.FLAG_MUTABLE)
                usb.requestPermission(driver.device, pi)
                throw IOException("Salli Akuxille pääsy sovittimeen puhelimen kysymässä ikkunassa.")
            }
            val conn = usb.openDevice(driver.device)
                ?: throw IOException("Sovittimen avaaminen epäonnistui.")
            val p = driver.ports[0]
            p.open(conn)
            p.setParameters(baud, 8, UsbSerialPort.STOPBITS_1, UsbSerialPort.PARITY_NONE)
            try {
                p.dtr = true
                p.rts = true
            } catch (_: Exception) {
            }
            port = p
        }
    }

    fun write(data: ByteArray) {
        val p = port ?: throw IOException("Sovitin ei ole yhteydessä.")
        p.write(data, 2000)
    }

    /** Lukee enintään maxLen tavua. Palauttaa tyhjän taulukon, jos dataa ei tullut aikarajan sisällä. */
    fun read(maxLen: Int, timeoutMs: Int): ByteArray {
        val p = port ?: throw IOException("Sovitin ei ole yhteydessä.")
        val buf = ByteArray(maxOf(64, maxLen))
        val n = p.read(buf, maxOf(1, timeoutMs))
        return if (n <= 0) ByteArray(0) else buf.copyOf(n)
    }

    fun close() {
        synchronized(lock) { closeLocked() }
    }

    private fun closeLocked() {
        try {
            port?.close()
        } catch (_: Exception) {
        }
        port = null
    }

    /**
     * Tallentaa tiedoston puhelimen Lataukset/Akux-kansioon. Python tallentaa tällä
     * jokaisen valmiin mittauksen mittaustiedostona ja PDF-raporttina.
     */
    fun saveToDownloads(name: String, mime: String, data: ByteArray): String {
        val resolver = context.contentResolver
        val values = ContentValues().apply {
            put(MediaStore.Downloads.DISPLAY_NAME, name)
            put(MediaStore.Downloads.MIME_TYPE, mime)
            put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/Akux")
        }
        val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
            ?: throw IOException("Tiedoston tallennus Lataukset-kansioon epäonnistui.")
        resolver.openOutputStream(uri)?.use { it.write(data) }
            ?: throw IOException("Tiedoston tallennus Lataukset-kansioon epäonnistui.")
        return "Lataukset/Akux/$name"
    }

    /** Python kutsuu tätä, kun ohjelma suljetaan käyttöliittymästä. */
    fun onStopped() {
        stoppedListener?.invoke()
    }
}
