package fr.iprospective.karl

import android.content.Context
import android.net.Uri
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

/**
 * Un serveur karl mémorisé (RM2331, « mémorisation serveur ») : l'URL du cockpit
 * et, une fois connecté, le jeton d'appareil CHIFFRÉ (ct/iv, clé Android Keystore —
 * cf. [TokenVault]). Le mot de passe n'est jamais stocké.
 */
data class Profile(
    val id: String,
    val name: String,
    val url: String,
    val user: String = "",
    val deviceId: String = "",
    val admin: Boolean = false,
    val bio: Boolean = false,
    val ct: String = "",
    val iv: String = "",
) {
    val loggedIn: Boolean get() = ct.isNotEmpty()

    fun toJson(): JSONObject = JSONObject()
        .put("id", id).put("name", name).put("url", url).put("user", user)
        .put("deviceId", deviceId).put("admin", admin).put("bio", bio).put("ct", ct).put("iv", iv)

    /** Oublie la session (jeton, appareil) mais garde le serveur et le choix biométrique. */
    fun loggedOut(): Profile = copy(user = "", deviceId = "", admin = false, ct = "", iv = "")

    companion object {
        fun fromJson(o: JSONObject) = Profile(
            id = o.getString("id"), name = o.optString("name"), url = o.getString("url"),
            user = o.optString("user"), deviceId = o.optString("deviceId"), admin = o.optBoolean("admin"),
            bio = o.optBoolean("bio"), ct = o.optString("ct"), iv = o.optString("iv"),
        )
    }
}

class ProfileStore(context: Context) {
    private val prefs = context.getSharedPreferences("karl", Context.MODE_PRIVATE)

    fun all(): List<Profile> {
        val arr = JSONArray(prefs.getString("profiles", "[]"))
        return (0 until arr.length()).map { Profile.fromJson(arr.getJSONObject(it)) }
    }

    fun get(id: String?): Profile? = all().firstOrNull { it.id == id }

    fun save(p: Profile) {
        val list = all().toMutableList()
        val i = list.indexOfFirst { it.id == p.id }
        if (i >= 0) list[i] = p else list.add(p)
        write(list)
    }

    fun delete(id: String) {
        write(all().filterNot { it.id == id })
        if (last == id) last = null
    }

    fun create(name: String, url: String): Profile =
        Profile(UUID.randomUUID().toString(), name.ifBlank { Uri.parse(url).host ?: url }, url).also { save(it) }

    /** Dernier serveur ouvert : l'app y retourne directement au lancement. */
    var last: String?
        get() = prefs.getString("last", null)
        set(v) { prefs.edit().putString("last", v).apply() }

    private fun write(list: List<Profile>) {
        prefs.edit().putString("profiles", JSONArray(list.map { it.toJson() }).toString()).apply()
    }

    companion object {
        /**
         * URL saisie → origine du cockpit (`https://hôte[:port]`), ou exception au
         * message lisible. HTTP clair réservé au réseau local (cf. network_security_config).
         */
        fun normalizeUrl(input: String): String {
            var s = input.trim().trimEnd('/')
            require(s.isNotEmpty()) { "URL du cockpit requise" }
            if (!s.contains("://")) s = "https://$s"
            val u = Uri.parse(s)
            val scheme = u.scheme?.lowercase()
            val host = u.host?.lowercase()
            require(scheme == "https" || scheme == "http") { "URL en http(s) attendue" }
            require(!host.isNullOrEmpty()) { "URL invalide" }
            require(scheme == "https" || isLocalHost(host)) {
                "HTTPS obligatoire hors réseau local (*.lxc, localhost)"
            }
            return "$scheme://$host" + (if (u.port > 0) ":${u.port}" else "")
        }

        fun isLocalHost(host: String) =
            host.endsWith(".lxc") || host == "localhost" || host == "10.0.2.2"
    }
}
