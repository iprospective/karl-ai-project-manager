# App Android « karl » (RM2331)

Coquille Kotlin + WebView du cockpit (CDC `docs/cdc-rm2331-app-mobile-android-cockpit.md`
du projet PM `pm-ai-agents`, option A « wrapper du site mobile »). Aide utilisateur :
`../cockpit/help/87-app-android.md`.

| Fichier | Rôle |
|---|---|
| `ServersActivity` | serveurs mémorisés (URL du cockpit) ; rouvre le dernier connecté |
| `LoginActivity` | identifiants → `POST /auth/login` → jeton d'appareil (mot de passe jamais stocké) |
| `CockpitActivity` | WebView du cockpit, menu (biométrie, serveurs, déconnexion), micro, fichiers |
| `TokenVault` / `Bio` | jeton chiffré AES-GCM par clé Android Keystore ; clé à empreinte obligatoire si l'option est active |
| `assets/karl-boot.js` | injecté au début de chaque document (origine du serveur seulement) : sert `karlToken` & co **depuis la mémoire** — jamais écrits dans le localStorage de la WebView — et remonte login/logout faits dans le cockpit |

Aucun changement du cockpit n'est requis : il lit son jeton par `localStorage.getItem`,
que le script sert. Côté serveur, seule la route publique `/app/karl-cockpit.apk` a été
ajoutée (fichier publié dans l'état du karl-agent, hors git).

## Construire et publier

```bash
deploy/karl-agent/android/build-apk.sh        # APK release signé → <serveur>/app/karl-cockpit.apk
node deploy/karl-agent/android/test_karl_boot.js   # le script injecté contre le vrai AuthService
```

Prérequis : SDK Android (`ANDROID_HOME`, défaut `/opt/android-sdk`, platform 36), JDK 17+.
Gradle est téléchargé par le wrapper.

**Clé de signature** : `~/.config/karl-android/{release.jks,signing.properties}`, créée
au premier build, **hors du repo — à archiver dans Vaultwarden**. La perdre oblige à
désinstaller l'app pour installer une nouvelle version (signature différente).

Version : `versionCode` / `versionName` dans `app/build.gradle.kts` (incrémenter
`versionCode` à chaque APK publié).
