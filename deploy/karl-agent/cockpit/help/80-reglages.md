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

## Conf PM (surcharge contrôlée)

Certains réglages PM sont éditables depuis le cockpit et écrits dans une
**surcharge gitignorée** (`pm.config.local.yml`) — le fichier canonique commenté
n'est jamais réécrit. Exemples : notifications mail au changement de statut,
auto-commit / auto-push des écritures PM, env de session auto à la prise d'un
ticket.

## Mise à jour du code PM

Quand une mise à jour du core est disponible, un bandeau **⬆ MAJ dispo** apparaît.
C'est **informatif** : l'application reste un geste humain au terminal
(`mmi-pm core update`, mot de passe sudo).
