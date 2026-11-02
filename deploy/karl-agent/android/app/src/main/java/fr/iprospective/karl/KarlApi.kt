package fr.iprospective.karl

import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

class ApiError(val code: Int, message: String) : IOException(message)

/**
 * Les trois routes d'auth du karl-agent consommées par l'app (livrées par RM2334) :
 * `POST /auth/login` (identifiants → jeton d'appareil), `GET /auth/whoami`,
 * `DELETE /auth/devices/<id>` (révocation). Appels BLOQUANTS : hors thread UI.
 */
object KarlApi {
    fun login(origin: String, user: String, pass: String, deviceName: String): JSONObject =
        JSONObject(call("POST", "$origin/auth/login", null,
            JSONObject().put("user", user).put("pass", pass).put("device_name", deviceName)))

    /** L'identité portée par le jeton ; [ApiError] 401 si le serveur l'a révoqué. */
    fun whoami(origin: String, token: String): JSONObject = JSONObject(call("GET", "$origin/auth/whoami", token))

    fun revoke(origin: String, token: String, deviceId: String) {
        call("DELETE", "$origin/auth/devices/$deviceId", token)
    }

    private fun call(method: String, url: String, token: String?, body: JSONObject? = null): String {
        val c = URL(url).openConnection() as HttpURLConnection
        try {
            c.requestMethod = method
            c.connectTimeout = 10_000
            c.readTimeout = 15_000
            c.setRequestProperty("Accept", "application/json")
            token?.let { c.setRequestProperty("X-Karl-Token", it) }
            if (body != null) {
                c.doOutput = true
                c.setRequestProperty("Content-Type", "application/json")
                c.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            }
            val code = c.responseCode
            val text = (if (code < 400) c.inputStream else c.errorStream)
                ?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            if (code >= 400) {
                val msg = runCatching { JSONObject(text).optString("error") }.getOrNull()
                throw ApiError(code, msg?.takeIf { it.isNotBlank() } ?: "HTTP $code")
            }
            return text
        } finally {
            c.disconnect()
        }
    }
}
