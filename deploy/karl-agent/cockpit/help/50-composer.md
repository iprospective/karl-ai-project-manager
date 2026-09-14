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


## ↻ Relancer — le prompt de travail, en un bouton

Le bouton **↻ Relancer**, dans la barre du composer, écrit dans le champ un prompt enregistré, puis
l'envoie. C'est une **frappe**, pas un automate : le texte reste visible, il entre dans l'historique,
et la garde d'état s'applique comme à tout envoi — si la session affiche un menu ou attend un choix,
l'envoi est retenu et le composer le dit.

Ce texte est un **réglage** : *🔧 Réglages → Sessions → « Prompt du bouton "relancer la session" »*.
Il est fait pour être amendé au fil de l'usage, sans toucher au code.

Le prompt livré au départ enchaîne le cycle de travail : vérifier ce qui est déployé, fermer ce qui
est en prod et bouclé, mettre en prod ce qui est fait, puis reprendre les tickets de la session qui
sont faisables sans arbitrage.

Quelques précisions gagnent à y figurer, parce qu'elles ont manqué à l'usage :

- **l'ordre** — fermer d'abord, mettre en prod ensuite : l'inverse ferme ce qu'on vient d'y mettre ;
- **ce qu'il ne faut pas forcer** — un ticket qui porte des questions non tranchées reste ouvert,
  sauf mention explicite : ces questions sont le seul endroit où la réflexion non résolue survit ;
- **un compte rendu chiffré** — combien fermés, combien mis en prod, et ce qui a été écarté avec son
  motif : sans cela, un lot de deux cents transitions ne laisse aucune trace lisible ;
- **ne pas toucher aux tickets portés par une autre session vivante** — deux agents sur un même
  ticket se disputent sa fiche et sa branche ;
- **un seul ticket à la fois**, livré de bout en bout, plutôt que trois entamés.

Sans session attachée, le composer entier est masqué : le bouton n'apparaît pas.

## Dictée (micro / Whisper)

Le bouton **🎤 dicter** capture le micro et transcrit la parole en texte à
**confirmer avant envoi**.

- Langue réglable dans **🔧 réglages** (français par défaut).
- Transcription **serveur** (sidecar Whisper) si disponible et préférée, sinon
  repli sur la reconnaissance du **navigateur**.
- Nécessite **Chrome** et un **contexte sécurisé** (HTTPS ou localhost) : sur
  `http://` le navigateur refuse l'accès micro.
