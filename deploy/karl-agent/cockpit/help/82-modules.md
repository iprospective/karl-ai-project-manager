# Modules

L'onglet 🧩 **Modules** des réglages montre ce que cette instance porte : les modules décrits,
ce qu'ils fournissent, ce dont ils dépendent — et ce que PM porte **encore sans module**.

## Ce que dit une ligne

Le nom, la version, et l'**état** :

- **actif** — décrit, ses dépendances sont là, il compte ;
- **désactivé** — décrit, mais volontairement mis de côté ;
- **bloqué** — il voudrait se charger mais quelque chose manque : la ligne dit quoi ;
- **erreur** — son manifeste est refusé, et la ligne dit pourquoi.

Un module cassé annonce son motif **sans qu'on l'ouvre** : une liste d'états sans motif ne
ferait que déplacer la question.

## Ce que dit le détail

Un clic ouvre le module, un second le referme — on compare deux modules en les ouvrant tour
à tour. On y lit ce qu'il **fournit** (fournisseurs, travaux, panneaux…), ce qu'il
**requiert**, et surtout ce qui le **requiert lui** : c'est la question qu'on se pose au
moment de désactiver quelque chose, et elle ne se répond pas en lisant son propre manifeste.

S'il réagit à des événements, ses abonnements sont listés : à quoi, sous quelle condition,
et ce qu'il lance.

## Le bus d'événements

Ce qui attend d'être traité, et ce qui a échoué. Un abonné qui casse ne rejoue pas
indéfiniment : son événement est marqué avec l'erreur. Sans cette liste, un module
semblerait branché et ne réagirait jamais.

## L'écart

PM porte **sept registres d'extension**, chacun réinventé dans son coin : fournisseurs,
moteurs, coffres, observateurs, services de modèles, travaux périodiques, veilles. Le
chantier des modules les unifie, et le tableau du bas mesure où il en est — combien de
points d'extension sont décrits, et surtout lesquels ne le sont pas.

C'est volontairement affiché : un panneau qui ne montrerait que les modules déclarés serait
flatteur et faux.

## En dehors du cockpit

`mmi-pm module list` · `show <nom>` · `check` · `inventory` — la même chose en ligne de
commande. Ni l'un ni l'autre ne charge le code d'un module : ils lisent.

## Allumer, éteindre, forcer (lot 1)

Ouvrez un module : **○ éteindre** ou **● allumer**.

- **Éteindre ne supprime rien.** Ce que le module a produit — tickets, notifications,
  fichiers — reste en place. Il cesse d'agir, il n'efface rien.
- **Un module dont d'autres dépendent ne s'éteint pas** : le panneau dit lesquels. C'est
  le comportement normal — éteignez d'abord ceux qui en dépendent.
- **Forcer** est possible, sous **deux** sécurités. D'abord cochez « autoriser le
  forçage » en haut du panneau (réglage de l'instance). Ensuite, à chaque fois, **recopiez
  le nom du module** : le bouton reste grisé tant que ce n'est pas exact. Les modules que
  vous cassez ainsi sont signalés `bloqué`, et le module forcé `éteint (forcé)`, tant que
  ça dure.
- **Natif / tiers** : un module natif est livré avec le noyau — il s'éteint, il ne se
  retire pas. Seul un module tiers se désinstalle.

En ligne de commande : `mmi-pm module enable|disable <nom>` — le forçage demande
`--force --confirm <nom>`. Pour créer un module : `mmi-pm module new <nom> --description "…"`.
