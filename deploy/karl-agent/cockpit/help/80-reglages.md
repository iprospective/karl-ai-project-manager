# Réglages

Le panneau **🔧 réglages** regroupe les préférences du cockpit et de la conf PM.

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
(`mmi-pm core update`, mot de passe sudo).
