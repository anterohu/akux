package fi.akveri.app

import android.content.Context

/**
 * Sovelluksen natiivitekstien kieli (ilmoitus, ilmoitusikkunat, sovittimen virheet). Käyttöliittymä kertoo valitun kielen
 * (fi, en tai sv) käynnistyessään, ja se tallennetaan, jotta myös seuraavan käynnistyksen ensimmäiset tekstit ovat oikealla kielellä.
 */
object Kieli {
    private const val PREFS = "akveri"
    private const val AVAIN = "kieli"
    @Volatile private var nykyinen: String? = null

    fun aseta(ctx: Context, kieli: String) {
        if (kieli !in setOf("fi", "en", "sv")) return
        nykyinen = kieli
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putString(AVAIN, kieli).apply()
    }

    fun nyt(ctx: Context): String =
        nykyinen ?: (ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(AVAIN, "fi") ?: "fi").also { nykyinen = it }

    fun t(ctx: Context, fi: String, en: String, sv: String): String = when (nyt(ctx)) {
        "en" -> en
        "sv" -> sv
        else -> fi
    }
}
