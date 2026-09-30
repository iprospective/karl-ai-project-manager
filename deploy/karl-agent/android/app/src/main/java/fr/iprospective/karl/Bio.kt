package fr.iprospective.karl

import android.content.Context
import android.security.keystore.KeyPermanentlyInvalidatedException
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricManager.Authenticators.BIOMETRIC_STRONG
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import javax.crypto.Cipher

/** Issue d'un déchiffrement : le jeton, ou une erreur (invalidated = clé biométrique perdue → reconnexion). */
data class Unsealed(val token: String?, val error: String? = null, val invalidated: Boolean = false)

/**
 * Colle entre [TokenVault] et BiometricPrompt : sceller / desceller le jeton d'un
 * profil selon son option biométrique. Le prompt porte le Cipher (CryptoObject) :
 * sans empreinte validée, la clé [TokenVault] refuse de servir.
 */
object Bio {
    fun available(ctx: Context): Boolean =
        BiometricManager.from(ctx).canAuthenticate(BIOMETRIC_STRONG) == BiometricManager.BIOMETRIC_SUCCESS

    fun prompt(a: FragmentActivity, title: String, subtitle: String, cipher: Cipher,
               onOk: (Cipher) -> Unit, onFail: (String) -> Unit) {
        val cb = object : BiometricPrompt.AuthenticationCallback() {
            override fun onAuthenticationSucceeded(r: BiometricPrompt.AuthenticationResult) {
                r.cryptoObject?.cipher?.let(onOk) ?: onFail("déverrouillage sans clé")
            }
            override fun onAuthenticationError(code: Int, msg: CharSequence) = onFail(msg.toString())
        }
        val info = BiometricPrompt.PromptInfo.Builder()
            .setTitle(title).setSubtitle(subtitle)
            .setNegativeButtonText("Annuler")
            .setAllowedAuthenticators(BIOMETRIC_STRONG)
            .build()
        BiometricPrompt(a, ContextCompat.getMainExecutor(a), cb).authenticate(info, BiometricPrompt.CryptoObject(cipher))
    }

    /** Chiffre [token] pour [p] (avec prompt si p.bio) → profil mis à jour, ou null + message. */
    fun seal(a: FragmentActivity, p: Profile, token: String, done: (Profile?, String?) -> Unit) {
        try {
            if (!p.bio) {
                val (ct, iv) = TokenVault.seal(TokenVault.encryptCipher(false), token)
                return done(p.copy(ct = ct, iv = iv), null)
            }
            val cipher = try {
                TokenVault.encryptCipher(true)
            } catch (e: KeyPermanentlyInvalidatedException) {
                TokenVault.dropBioKey(); TokenVault.encryptCipher(true)
            }
            prompt(a, "Protéger l'accès par biométrie", p.name, cipher,
                { ok -> val (ct, iv) = TokenVault.seal(ok, token); done(p.copy(ct = ct, iv = iv), null) },
                { msg -> done(null, msg) })
        } catch (e: Exception) {
            done(null, e.message ?: e.javaClass.simpleName)
        }
    }

    /** Déchiffre le jeton de [p] (avec prompt si p.bio). */
    fun unseal(a: FragmentActivity, p: Profile, done: (Unsealed) -> Unit) {
        try {
            if (!p.bio) return done(Unsealed(TokenVault.open(TokenVault.decryptCipher(false, p.iv), p.ct)))
            val cipher = TokenVault.decryptCipher(true, p.iv)
            prompt(a, "Déverrouiller karl", p.name, cipher,
                { ok -> done(runCatching { Unsealed(TokenVault.open(ok, p.ct)) }.getOrElse { Unsealed(null, it.message) }) },
                { msg -> done(Unsealed(null, msg)) })
        } catch (e: KeyPermanentlyInvalidatedException) {
            TokenVault.dropBioKey()
            done(Unsealed(null, "empreintes modifiées : reconnexion requise", invalidated = true))
        } catch (e: Exception) {
            done(Unsealed(null, e.message ?: e.javaClass.simpleName, invalidated = true))
        }
    }
}
