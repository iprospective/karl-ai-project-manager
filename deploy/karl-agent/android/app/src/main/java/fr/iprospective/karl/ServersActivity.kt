package fr.iprospective.karl

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.EditText
import android.widget.ListView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity

/**
 * Écran d'accueil : les serveurs karl mémorisés (URL du cockpit — décision RM2331
 * D001). Au lancement, rouvre directement le dernier serveur connecté, sauf si on
 * vient explicitement choisir (EXTRA_CHOOSE, menu « Serveurs » du cockpit).
 */
class ServersActivity : AppCompatActivity() {
    private lateinit var store: ProfileStore
    private lateinit var list: ListView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = ProfileStore(this)
        if (!intent.getBooleanExtra(EXTRA_CHOOSE, false) && savedInstanceState == null) {
            store.get(store.last)?.takeIf { it.loggedIn }?.let { return open(it) }
        }
        setContentView(R.layout.activity_servers)
        list = findViewById(R.id.servers)
        list.emptyView = findViewById(R.id.empty)
        list.setOnItemClickListener { _, _, pos, _ -> open(store.all()[pos]) }
        list.setOnItemLongClickListener { _, _, pos, _ -> manage(store.all()[pos]); true }
        findViewById<View>(R.id.add).setOnClickListener { edit(null) }
    }

    override fun onResume() {
        super.onResume()
        if (::list.isInitialized) refresh()
    }

    private fun refresh() {
        val items = store.all()
        list.adapter = object : ArrayAdapter<Profile>(this, android.R.layout.simple_list_item_2, android.R.id.text1, items) {
            override fun getView(position: Int, convertView: View?, parent: ViewGroup): View {
                val v = super.getView(position, convertView, parent)
                val p = items[position]
                v.findViewById<TextView>(android.R.id.text1).text = p.name
                v.findViewById<TextView>(android.R.id.text2).text = p.url + "  ·  " +
                    (if (p.loggedIn) "connecté : ${p.user}" + (if (p.bio) " 🔒" else "") else "non connecté")
                return v
            }
        }
    }

    private fun open(p: Profile) {
        store.last = p.id
        val target = if (p.loggedIn) CockpitActivity::class.java else LoginActivity::class.java
        startActivity(Intent(this, target).putExtra(EXTRA_PROFILE, p.id))
        finish()
    }

    private fun manage(p: Profile) {
        AlertDialog.Builder(this).setTitle(p.name)
            .setItems(arrayOf("Modifier", "Oublier ce serveur")) { _, which ->
                if (which == 0) edit(p) else forget(p)
            }.show()
    }

    private fun forget(p: Profile) {
        AlertDialog.Builder(this).setTitle("Oublier ${p.name} ?")
            .setMessage(if (p.loggedIn) "Le jeton local est effacé. Pour le révoquer côté serveur, déconnecte-toi depuis le cockpit (menu ⋮ → Se déconnecter)." else null)
            .setPositiveButton("Oublier") { _, _ -> store.delete(p.id); refresh() }
            .setNegativeButton("Annuler", null).show()
    }

    private fun edit(p: Profile?) {
        val v = layoutInflater.inflate(R.layout.dialog_profile, null)
        val name = v.findViewById<EditText>(R.id.name)
        val url = v.findViewById<EditText>(R.id.url)
        p?.let { name.setText(it.name); url.setText(it.url) }
        val dlg = AlertDialog.Builder(this).setTitle(if (p == null) "Ajouter un serveur" else "Modifier le serveur")
            .setView(v).setPositiveButton("Enregistrer", null).setNegativeButton("Annuler", null).create()
        dlg.setOnShowListener {
            dlg.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val origin = try { ProfileStore.normalizeUrl(url.text.toString()) } catch (e: IllegalArgumentException) {
                    url.error = e.message; return@setOnClickListener
                }
                if (p == null) {
                    store.create(name.text.toString().trim(), origin)
                } else {
                    // changer d'URL = changer de serveur : l'ancien jeton n'y vaut rien
                    val base = if (origin != p.url) p.loggedOut() else p
                    store.save(base.copy(name = name.text.toString().trim().ifBlank { p.name }, url = origin))
                }
                Toast.makeText(this, "Serveur enregistré", Toast.LENGTH_SHORT).show()
                dlg.dismiss(); refresh()
            }
        }
        dlg.show()
    }

    companion object {
        const val EXTRA_PROFILE = "profile"
        const val EXTRA_CHOOSE = "choose"
    }
}
