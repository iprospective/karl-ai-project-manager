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
