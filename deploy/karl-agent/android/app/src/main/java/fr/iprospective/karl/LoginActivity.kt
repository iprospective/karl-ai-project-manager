package fr.iprospective.karl

import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.view.View
import android.view.inputmethod.EditorInfo
import android.widget.Button
import android.widget.EditText
import android.widget.ProgressBar
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import java.util.concurrent.Executors

/**
 * Connexion par identifiants, UNE fois (RM2331 / RM2334) : `POST /auth/login` →
 * jeton d'appareil scellé par [TokenVault]. Le mot de passe ne quitte pas le
 * champ de saisie : il n'est ni stocké ni journalisé.
 */
class LoginActivity : AppCompatActivity() {
    private lateinit var store: ProfileStore
    private lateinit var profile: Profile
    private val io = Executors.newSingleThreadExecutor()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = ProfileStore(this)
        profile = store.get(intent.getStringExtra(ServersActivity.EXTRA_PROFILE)) ?: return backToServers()
        setContentView(R.layout.activity_login)
        title = profile.name
        findViewById<TextView>(R.id.server).text = profile.url
        intent.getStringExtra(EXTRA_MESSAGE)?.let { showError(it) }
        val user = findViewById<EditText>(R.id.user)
        val pass = findViewById<EditText>(R.id.pass)
        val go = findViewById<Button>(R.id.login)
        user.setText(profile.user)
        pass.setOnEditorActionListener { _, id, _ -> if (id == EditorInfo.IME_ACTION_DONE) { go.performClick(); true } else false }
        go.setOnClickListener { login(user.text.toString().trim(), pass) }
        findViewById<View>(R.id.servers).setOnClickListener { backToServers() }
    }

    override fun onDestroy() { io.shutdownNow(); super.onDestroy() }

    private fun login(user: String, pass: EditText) {
        val pw = pass.text.toString()
        if (user.isEmpty() || pw.isEmpty()) return showError("Identifiant et mot de passe requis")
        busy(true)
        val device = "App Android / ${Build.MANUFACTURER} ${Build.MODEL}".trim()
        io.execute {
            val res = runCatching { KarlApi.login(profile.url, user, pw, device) }
            runOnUiThread {
                pass.text.clear()
                res.onFailure { busy(false); showError(describe(it)) }
                res.onSuccess { r ->
                    val p = profile.copy(user = r.optString("user"), deviceId = r.optString("device_id"), admin = r.optBoolean("admin"))
                    Bio.seal(this, p, r.getString("token")) { sealed, err ->
                        busy(false)
                        if (sealed == null) return@seal showError("Jeton non enregistré : $err")
                        store.save(sealed); store.last = sealed.id
                        startActivity(Intent(this, CockpitActivity::class.java).putExtra(ServersActivity.EXTRA_PROFILE, sealed.id))
                        finish()
                    }
                }
            }
        }
    }

    private fun describe(e: Throwable) = when {
        e is ApiError && e.code == 401 -> "Identifiants invalides"
        e is ApiError -> "${e.message} (HTTP ${e.code})"
        else -> "Serveur injoignable : ${e.message ?: e.javaClass.simpleName}"
    }

    private fun busy(on: Boolean) {
        findViewById<ProgressBar>(R.id.progress).visibility = if (on) View.VISIBLE else View.GONE
        findViewById<Button>(R.id.login).isEnabled = !on
        if (on) findViewById<TextView>(R.id.error).visibility = View.GONE
    }

    private fun showError(msg: String) {
        findViewById<TextView>(R.id.error).apply { text = msg; visibility = View.VISIBLE }
    }

    private fun backToServers() {
        startActivity(Intent(this, ServersActivity::class.java).putExtra(ServersActivity.EXTRA_CHOOSE, true))
        finish()
    }

    companion object { const val EXTRA_MESSAGE = "message" }
}
