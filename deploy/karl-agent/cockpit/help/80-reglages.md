# Réglages

**🔧 réglages** (menu du haut) regroupe les préférences du cockpit et de la conf PM.
Les réglages s'ouvrent au **centre**, dans un [onglet](onglets) comme les autres vues.

## Apparence

- **Thème** : `dark`, `light` ou `auto` (suit le système).

## Dictée

- **Langue** de la reconnaissance vocale (français par défaut) et choix du mode
  (serveur Whisper si disponible, sinon navigateur). Voir [Composer & dictée](composer).

## Appareils & accès

- **Appareils** : la connexion peut mémoriser l'appareil (jeton révocable ici).
- L'accès au cockpit passe par une **authentification** (Basic ou jeton) : aucune
  route n'est publique dès qu'un identifiant est configuré.

## Sessions — plafond mémoire

Chaque session tmux vit dans sa propre **scope systemd**, qui naît sans limite :
une session qui fuit peut faire ramer toute la workstation, et c'est alors le
kernel qui choisit sa victime — pas forcément le processus fautif. Deux réglages
plafonnent la scope pour qu'une session qui dérape **se fasse tuer seule** :

- **Seuil de pression** (`MemoryHigh`, 6 GiB par défaut) : au-delà, la session
  est freinée et sa mémoire recyclée — elle n'est pas tuée.
- **Plafond dur** (`MemoryMax`, 8 GiB par défaut) : au-delà, seule cette session
  est tuée (OOM de la scope), les autres et le poste ne bougent pas.
- **Swap autorisé** (`MemorySwapMax`, **0 = aucun** par défaut) : sans swap, une
  session qui fuit meurt au plafond dur au lieu d'y grimper lentement en
  saturant le swap — c'est le swap saturé qui fait ramer tout le poste. Ici la
  convention est **inversée** : `0` veut dire « aucun swap », et c'est `-1` qui
  lève le plafond.

En **GiB** ; pour le seuil et le plafond dur, `0` = pas de limite. La
modification s'applique aux sessions créées
**ensuite** — les sessions déjà lancées gardent leur plafond. 8 GiB est
volontairement large : ~20× la consommation normale d'une session (160–440 Mo).

Un cadenas 🔒 sur le champ signale que la valeur est **figée par le `.env`**
(`KARL_AGENT_MEM_HIGH` / `KARL_AGENT_MEM_MAX` / `KARL_AGENT_MEM_SWAP`) : elle
s'édite alors dans le `.env`, suivi d'un redémarrage de karl-agent.

## Sonde mémoire (ce navigateur)

Un onglet de cockpit qui grossit avec les heures (RM2807) se diagnostique avec la **sonde
mémoire** : cochée, elle prend un échantillon à la cadence choisie (5 à 60 s) et ventile,
**par module** du cockpit (sessions, centre, worklog, tickets…), ce que la page retient :
montages, **nœuds** DOM, écouteurs/minuteries/abonnements **retenus**, entrées de **store**,
abonnés, **rendus par minute**. Le panneau **🧠 mémoire** (bouton « ouvrir le panneau »,
ou l'onglet qu'il laisse au centre) montre le tableau, une courbe des nœuds par module et
signale en orange un compteur qui **grimpe sans redescendre** sur les six derniers
échantillons — c'est la signature d'une fuite. **⤓ JSON** télécharge l'historique pour le
joindre à un ticket ; **↺ vider** l'oublie.

Décochée, la sonde ne coûte rien : aucune minuterie ne tourne. La préférence et la cadence
sont propres à ce navigateur. Depuis la console, `karl.stats()` donne le même instantané
(`modules`, `probe`).

## Conf PM (surcharge contrôlée)

Certains réglages PM sont éditables depuis le cockpit et écrits dans une
**surcharge gitignorée** (`pm.config.local.yml`) — le fichier canonique commenté
n'est jamais réécrit. Exemples : notifications mail au changement de statut,
auto-commit / auto-push des écritures PM, env de session auto à la prise d'un
ticket.

## Mise à jour du code PM

Quand une mise à jour du core est disponible, un bouton **⬆ MAJ dispo** apparaît
dans le header, en orange et **clignotant** — il est resté longtemps grisé au
milieu des autres, donc invisible. Si tu as coupé les animations dans ton
système (« mouvement réduit »), il ne clignote pas mais garde sa couleur.
C'est **informatif** : l'application reste un geste humain au terminal
(`mmi-pm core-update`, mot de passe sudo demandé par la commande elle-même).

## Affichage (ce navigateur)

Le filtre **« Clients »** de l'en-tête (contexte client, pré-filtre global) est **masqué par défaut** ; la case
« Afficher le filtre Clients dans l'en-tête » de la carte 🎨 le réaffiche. Le contexte mémorisé reste appliqué même masqué (RM3063).

## Fournisseurs

La carte 🔌 **Fournisseurs** déclare ce que karl utilise : les **tickets** (Redmine), les **dépôts** (GitLab,
Gogs, GitHub), la **documentation**, les **coffres à secrets** et les **modèles de travail** (Lemonade sur
Ryzen AI, Ollama, serveur compatible OpenAI, API Anthropic). Chaque axe peut porter **plusieurs instances**
— deux Redmine, par exemple — et l'une d'elles est le défaut.

**Les clés ne se lisent pas, elles se remplacent.** Le panneau dit seulement « posée » ou « non renseignée »,
et le champ de saisie est vide : il est vidé dès l'enregistrement, et aucune route ne renvoie une valeur.
La clé va dans le fichier d'environnement de **ton** compte ; un administrateur peut cocher « global » pour
viser celui de l'instance.

**Le rôle appartient au couple projet ↔ instance.** Le détail d'une instance liste les projets qui s'en
servent et avec quel rôle : le même Redmine est primaire chez son client et secondaire ailleurs.

La déclaration part dans `pm.config.local.yml`, fusionné par-dessus `pm.config.yml` : le fichier commenté
de référence n'est jamais réécrit par le cockpit.

## Moteurs

La carte 🧩 **Moteurs** installe et tient à jour ce qui fait tourner les agents, en deux familles :

- **Moteurs de session** — les clients qui tiennent une conversation : Claude Code, opencode, Mistral vibe.
- **Serveurs de modèles** — Ollama, Lemonade Server. Ils ne tiennent aucune session : ils servent les modèles,
  et se déclarent ensuite comme fournisseurs de l'axe « modèles de travail » dans 🔌 Fournisseurs.

Pour chacun : présent ou absent, **où il est installé et pour qui**, version installée, version disponible,
état du service, et le nombre de sessions qui l'utilisent. **La commande exacte est affichée sous l'outil**,
et la confirmation la répète : le cockpit n'exécute que des recettes qu'il connaît, il n'envoie au serveur
qu'un identifiant, une action et une portée, jamais une commande.

### Deux portées : pour moi, pour tous

- **pour moi** — l'outil est posé dans votre espace (`~/.local/bin`, `~/.opencode/bin`…). Aucun privilège
  n'est requis, et rien n'est touché sur la machine des autres.
- **pour tous** (⚠) — l'outil est posé sur la machine entière, en `sudo` : réservé aux administrateurs.

Un outil déjà présent chez vous peut, en plus, être posé pour tous : les deux boutons cohabitent. La
détection ne se fie pas au seul `PATH` du démon — un outil installé par un utilisateur y est absent et
serait déclaré manquant à tort. Le mode d'installation de karl lui-même, mono ou multi-utilisateur, est
une question ouverte (RM3070).

**Une mise à jour est refusée tant que des sessions tournent** sur ce moteur : les couper d'abord, ou forcer
en connaissance de cause. Le bouton « tester » vérifie simplement que l'outil répond.
