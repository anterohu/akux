package fi.akveri.app

import androidx.test.ext.junit.rules.ActivityScenarioRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.rule.GrantPermissionRule
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.net.HttpURLConnection
import java.net.URL

/**
 * Sovelluksen kokonaistesti Android-laitteella: Python-ympäristö käynnistyy,
 * käyttöliittymän palvelin vastaa, esittelytilan auto yhdistyy, pikatarkastus
 * valmistuu, raportti muodostuu PDF:ksi ja laaduntarkistus menee läpi.
 */
@RunWith(AndroidJUnit4::class)
class AkveriSovellusTest {
    @get:Rule
    val permissions: GrantPermissionRule = GrantPermissionRule.grant(android.Manifest.permission.POST_NOTIFICATIONS)

    @get:Rule
    val activity = ActivityScenarioRule(MainActivity::class.java)

    private val base = "http://127.0.0.1:8765"

    private fun request(path: String, body: String? = null, timeout: Int = 30_000): Pair<Int, ByteArray> {
        val c = URL(base + path).openConnection() as HttpURLConnection
        c.connectTimeout = 3000
        c.readTimeout = timeout
        if (body != null) {
            c.requestMethod = "POST"
            c.doOutput = true
            c.setRequestProperty("Content-Type", "application/json")
            c.outputStream.use { it.write(body.toByteArray()) }
        }
        val code = c.responseCode
        val bytes = (if (code < 400) c.inputStream else c.errorStream).use { it.readBytes() }
        return code to bytes
    }

    private fun json(path: String, body: String? = null, timeout: Int = 30_000): JSONObject {
        val (code, b) = request(path, body, timeout)
        assertTrue("$path vastasi $code: ${String(b)}", code == 200)
        return JSONObject(String(b))
    }

    private fun waitFor(seconds: Int, cond: () -> Boolean): Boolean {
        val end = System.currentTimeMillis() + seconds * 1000L
        while (System.currentTimeMillis() < end) {
            try {
                if (cond()) return true
            } catch (_: Exception) {
            }
            Thread.sleep(500)
        }
        return false
    }

    @Test
    fun kokoMittausketju() {
        assertTrue("Palvelin ei käynnistynyt", waitFor(240) { request("/api/tietoja").first == 200 })
        val info = json("/api/tietoja")
        assertEquals("android", info.getString("alusta"))

        json("/api/yhdista", """{"tyyppi":"demo","soc":60,"nopeutus":60}""")
        assertTrue("Esittelytilan tiedot eivät tulleet", waitFor(60) {
            val t = json("/api/tila")
            !t.isNull("vaylatesti") && t.getJSONObject("vaylatesti").getBoolean("kunnossa") &&
                !t.getJSONObject("live").isNull("vin")
        })
        val vin = json("/api/tila").getJSONObject("live").getString("vin")
        val vid = json("/api/ajoneuvot", """{"vin":"$vin","rekisteri":"TEST-1"}""").getInt("id")
        val tid = json("/api/mittaukset", """{"ajoneuvo_id":$vid,"tyyppi":"pikatarkastus"}""").getInt("id")
        assertTrue("Pikatarkastus ei valmistunut", waitFor(180) { json("/api/tila").isNull("mittaus") })
        val test = json("/api/mittaukset/$tid")
        assertEquals("valmis", test.getString("tila"))
        val kunto = test.getJSONObject("tulos").getJSONObject("yhteenveto").getDouble("kunto_pct")
        assertTrue("Kunto $kunto", kunto > 90 && kunto < 96)

        val (code, pdf) = request("/api/mittaukset/$tid/raportti.pdf", timeout = 180_000)
        assertEquals(200, code)
        assertTrue("Raportti ei ole PDF", String(pdf, 0, 4) == "%PDF")
        assertTrue("Raportti liian pieni: ${pdf.size}", pdf.size > 50_000)

        val (gc, guide) = request("/api/ohjeet.pdf", timeout = 120_000)
        assertEquals(200, gc)
        assertTrue(String(guide, 0, 4) == "%PDF")

        val q = json("/api/yllapito/tarkistus", timeout = 240_000)
        val checks = q.getJSONArray("tarkistukset")
        for (i in 0 until checks.length()) {
            val c = checks.getJSONObject(i)
            assertTrue("${c.getString("nimi")}: ${c.getString("tieto")}", c.getString("tila") != "virhe")
        }
        json("/api/katkaise", "{}")
    }
}
