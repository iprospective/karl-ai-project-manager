package fr.iprospective.karl

import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Chiffrement du jeton d'appareil par une clé AES-GCM de l'Android Keystore
 * (non extractible). Deux clés :
 *  - [PLAIN] : sans authentification — le jeton est lisible par l'app seule ;
 *  - [BIO]   : authentification biométrique forte exigée à CHAQUE usage, invalidée
 *    si une nouvelle empreinte est enrôlée → le jeton n'est déchiffrable qu'après
 *    un BiometricPrompt réussi (option « déverrouillage biométrique », RM2331 C).
 */
object TokenVault {
    private const val KS = "AndroidKeyStore"
    private const val PLAIN = "karl.token"
    private const val BIO = "karl.token.bio"
    private const val TRANSFORM = "AES/GCM/NoPadding"

    private fun keyStore() = KeyStore.getInstance(KS).apply { load(null) }

    private fun key(bio: Boolean): SecretKey {
        val alias = if (bio) BIO else PLAIN
        (keyStore().getKey(alias, null) as SecretKey?)?.let { return it }
        val spec = KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256)
        if (bio) {
            spec.setUserAuthenticationRequired(true).setInvalidatedByBiometricEnrollment(true)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                spec.setUserAuthenticationParameters(0, KeyProperties.AUTH_BIOMETRIC_STRONG)
            } else {
                @Suppress("DEPRECATION")
                spec.setUserAuthenticationValidityDurationSeconds(-1)
            }
        }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KS).run {
            init(spec.build()); generateKey()
        }
    }

    /** Cipher prêt à chiffrer ; pour [bio], à faire valider par un BiometricPrompt (CryptoObject). */
    fun encryptCipher(bio: Boolean): Cipher = Cipher.getInstance(TRANSFORM).apply { init(Cipher.ENCRYPT_MODE, key(bio)) }

    fun decryptCipher(bio: Boolean, iv: String): Cipher = Cipher.getInstance(TRANSFORM).apply {
        init(Cipher.DECRYPT_MODE, key(bio), GCMParameterSpec(128, b64d(iv)))
    }

    /** (ct, iv) en base64. */
    fun seal(cipher: Cipher, token: String): Pair<String, String> =
        b64e(cipher.doFinal(token.toByteArray(Charsets.UTF_8))) to b64e(cipher.iv)

    fun open(cipher: Cipher, ct: String): String = String(cipher.doFinal(b64d(ct)), Charsets.UTF_8)

    /** Clé biométrique invalidée (nouvelle empreinte) : on la jette, une nouvelle sera créée. */
    fun dropBioKey() = runCatching { keyStore().deleteEntry(BIO) }

    private fun b64e(b: ByteArray) = Base64.encodeToString(b, Base64.NO_WRAP)
    private fun b64d(s: String) = Base64.decode(s, Base64.NO_WRAP)
}
