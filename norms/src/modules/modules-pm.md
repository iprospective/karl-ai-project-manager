> 📂 **Module `modules-pm` — quand lire ceci :** je crée un module PM · je modifie le code d'un module (`modules/<nom>/`) · j'allume, j'éteins ou je force l'extinction d'un module · je transforme une partie du noyau en module.
> **Outils :** `mmi-pm module list|show|check|new|enable|disable`, onglet 🧩 Modules des réglages · **Préchargé par :** *(personne — ouvert à la demande)*.

# Modules PM — contrat, activation, et la règle qui ne se négocie pas

PM est un **noyau + des modules** (RM3145). Un module vit dans `modules/<nom>/` et se
déclare par un manifeste `module.yml` : ce qu'il fournit, ce dont il dépend.

## La règle : un module ne contourne AUCUN garde-fou

Les tripwires du KERNEL valent **dans le code d'un module** exactement comme ailleurs.
Un module ne s'en exempte pas parce qu'il est isolé, optionnel ou tiers :

- **tout changement d'état** — ticket, statut, branche, dépôt, Redmine — passe par l'outil
  PM (tripwire #1), jamais par un appel direct à Redmine ou à git ;
- **jamais de push direct** sur une branche protégée (tripwire #3) ;
- **aucun secret** lu en clair, journalisé ou écrit (tripwire #11). Un module DÉCLARE les
  secrets dont il a besoin (`secrets:` au manifeste) et les résout par `pm_secrets` ;
- **aucune action de production** sans consentement explicite (tripwire #10) ;
- un **abonné** au bus d'événements qui échoue ne casse jamais l'émetteur.

**Pourquoi c'est une règle et non un conseil.** Ce qui rend un module utile — s'installer,
s'activer, s'éteindre d'un geste — est aussi ce qui permet de l'ajouter *sans relire les
normes*. Le noyau porte les garde-fous ; un module qui les contournerait rouvrirait
exactement ce que les tripwires ferment, et le ferait depuis un endroit qu'on ne relit pas.

## Natif ou tiers (arbitrage du 2026-09-14)

- **Natif** : livré avec le noyau. Il s'**éteint**, il ne se **retire** pas. Tout ce qui
  vit aujourd'hui sous `modules/` est natif (`native: true`, valeur par défaut).
- **Tiers** : installé en plus. Lui seul se désinstalle.

## Allumer, éteindre, forcer

L'état d'activation vit dans la **configuration de l'instance** (`pm.config.local.yml ::
modules`), jamais dans le manifeste : le manifeste est versionné avec le noyau, et y lire
l'état voudrait dire qu'éteindre un module modifie le code livré.

- **Éteindre ne supprime rien.** Les tickets, notifications et fichiers qu'un module a
  produits restent lisibles. Un module éteint cesse d'agir, il n'efface rien.
- **Éteindre un module dont d'autres dépendent est REFUSÉ**, en nommant les dépendants.
- **Forcer** est possible sous **double sécurité** : le réglage de l'instance « autoriser le
  forçage » doit être posé, PUIS chaque forçage demande de **recopier le nom du module**.
  Les dépendants cassés sont signalés tant que ça dure (`éteint (forcé)`, `bloqué`).

## Créer un module

`mmi-pm module new <nom> --description "…"` crée un module **valide du premier coup** :
manifeste, dossiers standard (`routes`, `controllers`, `services`, `classes`, `templates`,
`config`, `hooks`, `triggers`). Transformer une partie du noyau en module doit être un
choix simple — c'est faute de patron outillé que les registres d'extension historiques ont
chacun été réinventés à leur façon.
