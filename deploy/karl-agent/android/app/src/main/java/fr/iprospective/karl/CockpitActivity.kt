package fr.iprospective.karl

import android.Manifest
import android.annotation.SuppressLint
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.os.SystemClock
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.webkit.CookieManager
import android.webkit.PermissionRequest
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.TextView
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature
import org.json.JSONObject
import java.util.concurrent.Executors

/**
 * Le cockpit karl dans une WebView (wrapper du site mobile, RM2331 option A).
 *
 * Le jeton d'appareil n'est JAMAIS posé sur le disque de la WebView : un script
 * de début de document (limité à l'origine du serveur) sert `karlToken` & co
 * depuis la mémoire à `localStorage.getItem` — le cockpit n'y voit que du feu —
 * et remonte à l'app, par un canal restreint à la même origine, les connexions /
 * déconnexions faites dans le cockpit. La copie de référence reste chiffrée par
 * [TokenVault] (et, option biométrique, n'est lisible qu'après empreinte).
 */
class CockpitActivity : AppCompatActivity() {
    private lateinit var store: ProfileStore
    private lateinit var profile: Profile
    private lateinit var web: WebView
    private lateinit var status: TextView
    private var token: String? = null
    private var stoppedAt = 0L
    private var locked = false
    private var pendingPermission: PermissionRequest? = null
    private var fileCallback: ValueCallback<Array<Uri>>? = null
    private val io = Executors.newSingleThreadExecutor()

    private val micPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { ok ->
        pendingPermission?.let { if (ok) it.grant(arrayOf(PermissionRequest.RESOURCE_AUDIO_CAPTURE)) else it.deny() }
        pendingPermission = null
    }
    private val filePicker = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { r ->
        fileCallback?.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(r.resultCode, r.data))
        fileCallback = null
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = ProfileStore(this)
        profile = store.get(intent.getStringExtra(ServersActivity.EXTRA_PROFILE)) ?: return toServers()
        if (!profile.loggedIn) return toLogin(null)
        setContentView(R.layout.activity_cockpit)
        title = profile.name
        web = findViewById(R.id.web)
        status = findViewById(R.id.status)
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (web.canGoBack()) web.goBack() else { isEnabled = false; onBackPressedDispatcher.onBackPressed() }
            }
        })
        if (!WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT) ||
            !WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER)) {
            return showStatus("WebView trop ancienne : mets à jour « Android System WebView » (ou Chrome) depuis le Play Store.")
        }
        unlock { t -> token = t; verifyThenLoad(t) }
    }

    override fun onStop() { super.onStop(); stoppedAt = SystemClock.elapsedRealtime() }

    override fun onStart() {
        super.onStart()
        // Option biométrique : revenir sur l'app après une absence re-verrouille l'accès.
        if (::web.isInitialized && profile.bio && token != null && stoppedAt > 0 &&
            SystemClock.elapsedRealtime() - stoppedAt > RELOCK_MS && !locked) {
            locked = true
            web.visibility = View.INVISIBLE
            unlock { t ->
                locked = false
                if (t != token) { token = t; verifyThenLoad(t) } else web.visibility = View.VISIBLE
            }
        }
    }

    override fun onDestroy() {
        io.shutdownNow()
        if (::web.isInitialized) web.destroy()
        super.onDestroy()
    }

    /** Descelle le jeton (empreinte si l'option est active) ; échec → sortie ou reconnexion. */
    private fun unlock(then: (String) -> Unit) {
        Bio.unseal(this, profile) { r ->
            when {
                r.token != null -> then(r.token)
                r.invalidated -> { store.save(profile.loggedOut()); toLogin(r.error) }
                else -> { Toast.makeText(this, r.error ?: "Déverrouillage annulé", Toast.LENGTH_SHORT).show(); finish() }
            }
        }
    }

    /** Le serveur connaît-il encore ce jeton ? 401 → révoqué (autre appareil, admin) → reconnexion. Hors réseau : on charge quand même. */
    private fun verifyThenLoad(t: String) {
        showStatus("Connexion à ${profile.url}…")
        io.execute {
            val r = runCatching { KarlApi.whoami(profile.url, t) }
            runOnUiThread {
                val e = r.exceptionOrNull()
                if (e is ApiError && e.code == 401) {
                    store.save(profile.loggedOut())
                    return@runOnUiThread toLogin("Cet appareil a été révoqué ou sa session a expiré : reconnecte-toi.")
                }
                r.getOrNull()?.let { w ->
                    profile = profile.copy(user = w.optString("user", profile.user),
                        admin = w.optBoolean("admin", profile.admin),
                        deviceId = w.optString("device_id").ifEmpty { profile.deviceId })
                    store.save(profile)
                }
                load(t)
            }
        }
    }

    // RequiresFeature : DOCUMENT_START_SCRIPT et WEB_MESSAGE_LISTENER sont vérifiés dans onCreate.
    @SuppressLint("SetJavaScriptEnabled", "RequiresFeature")
    private fun load(t: String) {
        status.visibility = View.GONE
        web.visibility = View.VISIBLE
        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            mediaPlaybackRequiresUserGesture = false
            setSupportMultipleWindows(false)   // target=_blank → même WebView → shouldOverrideUrlLoading
            userAgentString = "$userAgentString KarlCockpitApp/${BuildConfig.VERSION_NAME}"
        }
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
        CookieManager.getInstance().apply { setAcceptCookie(true); removeSessionCookies(null) }
        val origins = setOf(profile.url)
        WebViewCompat.addWebMessageListener(web, "KarlApp", origins) { _, msg, source, isMainFrame, _ ->
            if (isMainFrame && source.toString().trimEnd('/') == profile.url) onPageMessage(msg.data)
        }
        WebViewCompat.addDocumentStartJavaScript(web, bootScript(t), origins)
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, req: WebResourceRequest): Boolean {
                val u = req.url
                if ((u.scheme == "http" || u.scheme == "https") && originOf(u) == profile.url) return false
                // tout le reste (GitLab, Redmine, mailto:…) s'ouvre hors de l'app
                try { startActivity(Intent(Intent.ACTION_VIEW, u)) } catch (e: ActivityNotFoundException) { /* rien pour l'ouvrir */ }
                return true
            }
        }
        // téléchargements (ex. l'APK depuis l'aide) : au navigateur du téléphone
        web.setDownloadListener { url, _, _, _, _ ->
            try { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) } catch (e: ActivityNotFoundException) { /* rien pour l'ouvrir */ }
        }
        web.webChromeClient = object : WebChromeClient() {
            override fun onPermissionRequest(req: PermissionRequest) {
                // micro (saisie vocale du cockpit) : seulement pour le serveur lui-même
                val mic = PermissionRequest.RESOURCE_AUDIO_CAPTURE
                if (originOf(req.origin) != profile.url || mic !in req.resources) return req.deny()
                if (ContextCompat.checkSelfPermission(this@CockpitActivity, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                    req.grant(arrayOf(mic))
                } else {
                    pendingPermission = req
                    micPermission.launch(Manifest.permission.RECORD_AUDIO)
                }
            }

            override fun onShowFileChooser(view: WebView, cb: ValueCallback<Array<Uri>>, params: FileChooserParams): Boolean {
                fileCallback?.onReceiveValue(null)
                fileCallback = cb
                return try { filePicker.launch(params.createIntent()); true } catch (e: ActivityNotFoundException) { fileCallback = null; false }
            }
        }
        web.loadUrl(profile.url + "/")
    }

    /** Messages du script de début de document (même origine, cadre principal). */
    private fun onPageMessage(data: String?) {
        val m = runCatching { JSONObject(data ?: return) }.getOrNull() ?: return
        when (m.optString("type")) {
            // déconnexion faite dans le cockpit : l'appareil y est déjà révoqué
            "logout" -> { token = null; store.save(profile.loggedOut()); clearWebSession(); toLogin("Déconnecté.") }
            // (re)connexion faite dans la carte de login du cockpit : on adopte le nouveau jeton
            "login" -> {
                val t = m.optString("karlToken").ifEmpty { return }
                val p = profile.copy(user = m.optString("karlUser"), deviceId = m.optString("karlDeviceId"),
                    admin = m.optString("karlAdmin") == "1")
                Bio.seal(this, p, t) { sealed, err ->
                    if (sealed != null) { profile = sealed; token = t; store.save(sealed) }
                    else Toast.makeText(this, "Jeton non mémorisé : $err", Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.cockpit, menu)
        return true
    }

    override fun onPrepareOptionsMenu(menu: Menu): Boolean {
        menu.findItem(R.id.bio)?.apply {
            isChecked = profile.bio
            isEnabled = token != null && (profile.bio || Bio.available(this@CockpitActivity))
        }
        return super.onPrepareOptionsMenu(menu)
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        when (item.itemId) {
            R.id.reload -> if (::web.isInitialized) web.reload()
            R.id.servers -> toServers()
            R.id.bio -> toggleBio()
            R.id.logout -> confirmLogout()
            else -> return super.onOptionsItemSelected(item)
        }
        return true
    }

    /** Activer / couper la biométrie = re-sceller le jeton avec l'autre clé ; couper exige aussi l'empreinte. */
    private fun toggleBio() {
        val t = token ?: return
        val want = !profile.bio
        val reseal = {
            Bio.seal(this, profile.copy(bio = want), t) { sealed, err ->
                if (sealed == null) return@seal Toast.makeText(this, "Inchangé : $err", Toast.LENGTH_SHORT).show()
                profile = sealed; store.save(sealed); invalidateOptionsMenu()
                Toast.makeText(this, if (want) "Déverrouillage biométrique activé" else "Biométrie désactivée", Toast.LENGTH_SHORT).show()
            }
        }
        if (want) return reseal()
        Bio.unseal(this, profile) { r ->
            if (r.token != null) reseal() else Toast.makeText(this, "Inchangé : ${r.error}", Toast.LENGTH_SHORT).show()
        }
    }

    private fun confirmLogout() {
        AlertDialog.Builder(this).setTitle("Se déconnecter de ${profile.name} ?")
            .setMessage("Le jeton de cet appareil est révoqué sur le serveur. Il faudra se reconnecter avec ses identifiants.")
            .setPositiveButton("Se déconnecter") { _, _ -> logout() }
            .setNegativeButton("Annuler", null).show()
    }

    private fun logout() {
        val t = token
        val p = profile
        io.execute {
            // révocation serveur au mieux : hors réseau, on oublie quand même localement
            if (t != null && p.deviceId.isNotEmpty()) runCatching { KarlApi.revoke(p.url, t, p.deviceId) }
            runOnUiThread {
                token = null; store.save(p.loggedOut()); clearWebSession(); toLogin("Déconnecté : appareil révoqué.")
            }
        }
    }

    private fun clearWebSession() {
        CookieManager.getInstance().removeAllCookies(null)
    }

    private fun showStatus(msg: String) {
        status.text = msg
        status.visibility = View.VISIBLE
    }

    private fun toLogin(msg: String?) {
        startActivity(Intent(this, LoginActivity::class.java)
            .putExtra(ServersActivity.EXTRA_PROFILE, profile.id).putExtra(LoginActivity.EXTRA_MESSAGE, msg))
        finish()
    }

    private fun toServers() {
        startActivity(Intent(this, ServersActivity::class.java).putExtra(ServersActivity.EXTRA_CHOOSE, true))
        finish()
    }

    /** Script injecté avant tout JS de la page (origine du serveur seulement) : assets/karl-boot.js. */
    private fun bootScript(t: String): String {
        val mem = JSONObject().put("karlToken", t).put("karlDeviceId", profile.deviceId)
            .put("karlUser", profile.user).put("karlAdmin", if (profile.admin) "1" else "0")
        val js = assets.open("karl-boot.js").bufferedReader(Charsets.UTF_8).use { it.readText() }
        return js.replace("__MEM__", mem.toString())
    }

    companion object {
        private const val RELOCK_MS = 5 * 60_000L

        fun originOf(u: Uri): String = "${u.scheme}://${u.host}" + (if (u.port > 0) ":${u.port}" else "")
    }
}
