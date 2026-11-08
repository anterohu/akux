package fi.akux.app

import android.annotation.SuppressLint
import android.app.PendingIntent
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothSocket
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.hardware.usb.UsbManager
import android.os.Environment
import android.provider.MediaStore
import com.hoho.android.usbserial.driver.UsbSerialPort
import com.hoho.android.usbserial.driver.UsbSerialProber
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.util.UUID

/**
 * Sarjayhteys OBDLink-sovittimeen Android-laitteessa: USB (OBDLink EX, SX) tai
 * Bluetooth (OBDLink MX+, LX). Pythonin mittauskoodi kutsuu näitä metodeja samaan
 * tapaan kuin pyserial-kirjastoa.
 */
class UsbBridge(private val context: Context) {
    private val usb = context.getSystemService(Context.USB_SERVICE) as UsbManager
    private var port: UsbSerialPort? = null
    private val lock = Any()

    @Volatile
    var stoppedListener: (() -> Unit)? = null

    // Bluetooth (sarjaportti-profiili, SPP)
    private var bt: BluetoothSocket? = null
    private var btReader: Thread? = null
    private val btBuf = ByteArrayOutputStream()
    private val btLock = Object()

    private fun drivers() = UsbSerialProber.getDefaultProber().findAllDrivers(usb)

    @SuppressLint("MissingPermission")
    private fun bondedObd(): List<Pair<String, String>> = try {
        val mgr = context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
        val adapter = mgr.adapter
        if (adapter == null || !adapter.isEnabled) emptyList()
        else adapter.bondedDevices.map { (it.name ?: "Bluetooth-laite") to it.address }
    } catch (_: SecurityException) {
        emptyList()
    }

    /** Kytketyt sovittimet: "OBDLink (FTDI) 0403:6015" tai "Bluetooth: OBDLink MX+ 00:04:3E:..". */
    fun listDevices(): Array<String> {
        val usbDevs = drivers().map { d ->
            val dev = d.device
            val name = dev.productName ?: "USB-sovitin"
            "%s %04X:%04X".format(name, dev.vendorId, dev.productId)
        }
        val btDevs = bondedObd().map { (n, a) -> "Bluetooth: $n $a" }
        return (usbDevs + btDevs).toTypedArray()
    }

    @SuppressLint("MissingPermission")
    private fun openBluetooth(name: String) {
        val mgr = context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
        val adapter = mgr.adapter ?: throw IOException("Puhelimessa ei ole Bluetoothia.")
        if (!adapter.isEnabled) throw IOException("Kytke Bluetooth päälle puhelimen asetuksista.")
        val address = name.substringAfterLast(' ')
        val dev = try {
            adapter.bondedDevices.firstOrNull { it.address == address }
        } catch (_: SecurityException) {
            throw IOException("Salli Akuxille lähellä olevien laitteiden käyttö puhelimen asetuksista (Sovellukset > Akux > Luvat).")
        } ?: throw IOException("Sovitinta ei löydy. Muodosta pari OBDLinkin kanssa puhelimen Bluetooth-asetuksista.")
        val spp = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
        val sock = try {
            adapter.cancelDiscovery()
            dev.createRfcommSocketToServiceRecord(spp).also { it.connect() }
        } catch (e: SecurityException) {
            throw IOException("Salli Akuxille lähellä olevien laitteiden käyttö puhelimen asetuksista (Sovellukset > Akux > Luvat).")
        } catch (e: IOException) {
            throw IOException("Bluetooth-yhteys sovittimeen ei onnistunut. Tarkista, että sovitin on kytketty autoon ja lähellä.")
        }
        bt = sock
        synchronized(btLock) { btBuf.reset() }
        val input = sock.inputStream
        btReader = Thread({
            val tmp = ByteArray(4096)
            try {
                while (true) {
                    val n = input.read(tmp)
                    if (n < 0) break
                    synchronized(btLock) {
                        btBuf.write(tmp, 0, n)
                        btLock.notifyAll()
                    }
                }
            } catch (_: IOException) {
            }
            synchronized(btLock) { btLock.notifyAll() }
        }, "akux-bluetooth").apply { isDaemon = true; start() }
    }

    fun open(name: String, baud: Int) {
        synchronized(lock) {
            closeLocked()
            if (name.startsWith("Bluetooth: ")) {
                openBluetooth(name)
                return
            }
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
        bt?.let {
            it.outputStream.write(data)
            it.outputStream.flush()
            return
        }
        val p = port ?: throw IOException("Sovitin ei ole yhteydessä.")
        p.write(data, 2000)
    }

    /** Lukee enintään maxLen tavua. Palauttaa tyhjän taulukon, jos dataa ei tullut aikarajan sisällä. */
    fun read(maxLen: Int, timeoutMs: Int): ByteArray {
        val sock = bt
        if (sock != null) {
            synchronized(btLock) {
                if (btBuf.size() == 0) {
                    if (btReader?.isAlive != true) throw IOException("Bluetooth-yhteys katkesi.")
                    btLock.wait(maxOf(1, timeoutMs).toLong())
                }
                val all = btBuf.toByteArray()
                if (all.isEmpty()) return ByteArray(0)
                val n = minOf(all.size, maxOf(64, maxLen))
                btBuf.reset()
                if (n < all.size) btBuf.write(all, n, all.size - n)
                return all.copyOf(n)
            }
        }
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
        try {
            bt?.close()
        } catch (_: Exception) {
        }
        bt = null
        btReader = null
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
