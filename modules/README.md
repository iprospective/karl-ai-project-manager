# `modules/` — les modules de PM

Un sous-dossier par module, et dans chacun un `module.yml` qui le décrit. La structure
visée (RM3145, décision du 2026-09-14) :

```
modules/<nom>/
  module.yml        le manifeste : nom, version, dépendances, ce qu'il fournit
  routes/           les URLs d'API du module — /api/modules/<nom>/…
  controllers/      ce qui répond à ces routes
  services/         la logique, sans HTTP ni DOM
  classes/          les objets du domaine
  templates/        l'interface : vues, ViewModels, styles
  config/           les réglages du module et leurs défauts
  hooks/            ce qu'il pose ailleurs
  triggers/         ce à quoi il réagit, et ce qu'il déclare à l'ordonnanceur
```

## État actuel : on DÉCRIT, on ne déplace pas

Les manifestes présents décrivent du code qui vit encore dans `scripts/` et
`deploy/karl-agent/cockpit/`. C'est délibéré (lot 0) : déménager d'abord et constater
ensuite, c'est se priver de la seule chose qui rend le chantier discutable — une mesure
de l'écart.

`mmi-pm module list` montre les deux mondes : ce qui est décrit, et les points
d'extension que les registres portent sans que personne les ait déclarés.

## Écrire un manifeste

```yaml
name: task-gitlab-issues          # minuscules, chiffres, tirets
version: 1.0.0                    # X.Y.Z
label: "Tickets · GitLab issues"
description: "…"                  # requise : sans elle, on active à l'aveugle
requires: ["core >= 3.0", "forge-gitlab >= 1.0"]
provides:
  - {kind: provider, axis: task, type: gitlab_issues}
enabled: true                     # absent = activé
```

Les natures acceptées pour `provides` : `provider`, `job`, `panel`, `route`, `hook`,
`trigger`, `skill`, `watch`, `engine`. Une nature inconnue fait **rejeter** le manifeste :
mieux vaut un module refusé qu'un module qui croit fournir ce que personne ne lira.


## Réagir à un événement (`triggers/`)

Un module déclare ses abonnements dans `triggers/*.yml`, un fichier par abonnement :

```yaml
event: task.status.changed          # le NOM de l'événement — c'est un contrat
when: {to: a_tester_demandeur}      # filtre facultatif ; une liste vaut « l'un de »
run: ["python3", "modules/<nom>/services/prevenir.py"]
```

⚠ La clé est **`event`**, pas `on` : en YAML, `on` est un **booléen** (comme `yes` et
`off`), donc `on: task.status.changed` produit une clé `True` et l'abonnement écoute le
vide, sans rien dire. `on:` est rattrapé quand même — l'habitude est trop forte — mais
`event` est la forme juste.

`run` est une **liste d'arguments**, jamais une ligne de shell : un abonné ne doit pas
pouvoir faire dépendre son exécution d'une interprétation de la ligne de commande.

L'événement arrive par l'environnement : `PM_EVENT_NAME`, `PM_EVENT_ID`, et
`PM_EVENT_PAYLOAD` (du JSON).

Les noms d'événements connus sont déclarés dans `scripts/pm_bus.py` — un nom inconnu est
refusé à l'émission plutôt que déposé en silence, et un abonné à un nom mal orthographié
se tairait pour toujours.

**Qui exécute** : `mmi-pm bus-drain`, appelé par l'ordonnanceur. Les émetteurs de PM sont
des processus courts — ils déposent un fait et meurent. La réaction attend donc un tour
d'ordonnanceur ; ce qui doit être instantané (rafraîchir un écran) passe par `pm_events`,
le canal de push vers le cockpit, qui est un autre mécanisme et porte un autre nom.
