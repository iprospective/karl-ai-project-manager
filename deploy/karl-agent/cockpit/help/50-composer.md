# Composer & dictée

Le **composer** est la zone de saisie qui envoie une consigne à la session
attachée.

## Saisie

- Le **collage** de contenu est encadré et envoyé en un bloc ; la validation est
  émise à part.
- Une **garde d'état** protège les menus : pendant qu'une session affiche un menu
  numéroté ou attend un choix, un envoi texte pourrait sélectionner une entrée
  par erreur — le composer prévient.
- L'**historique** des consignes est accessible (sans doublon, le plus récent en
  tête, plafonné).

## Dictée (micro / Whisper)

Le bouton **🎤 dicter** capture le micro et transcrit la parole en texte à
**confirmer avant envoi**.

- Langue réglable dans **🔧 réglages** (français par défaut).
- Transcription **serveur** (sidecar Whisper) si disponible et préférée, sinon
  repli sur la reconnaissance du **navigateur**.
- Nécessite **Chrome** et un **contexte sécurisé** (HTTPS ou localhost) : sur
  `http://` le navigateur refuse l'accès micro.
