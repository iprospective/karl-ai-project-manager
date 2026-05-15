---
bootstrap_template: "007-monitoring"
default_checked: false
title: "Setup : documenter monitoring et logs"
type: infrastructure
priority: normal
tags: [bootstrap, monitoring, observability]
roi:
  immediate_benefit: 2
  monthly_benefit: 3
estimate:
  difficulty: low
  time_minutes: 30
applicable_when: |
  Le projet a au moins un environnement actif et le monitoring/alerting n'est pas
  documenté.
---

## Contexte

Sans documentation sur où chercher quand ça pète, les agents (et toi) perdent du
temps à naviguer entre logs, dashboards, alertes. Centraliser l'information dans
`monitoring.md` accélère le debug et l'audit.

## Critères d'acceptation

- [ ] `project/monitoring.md` existe (depuis `templates/aspects/common/monitoring.md`)
- [ ] Logs applicatifs : où, format, rotation, durée de rétention (par env)
- [ ] Logs serveur web / FPM : où, format (cf. `environments.<env>.logs.app/fpm`)
- [ ] Métriques : outil utilisé (Prometheus, Grafana, Datadog…), URL des dashboards
- [ ] Alertes : qui est alerté, sur quels événements, par quel canal (mail, Slack,
      Signal, etc.)
- [ ] Procédure de tri d'erreurs (ordre de consultation : prod.log → FPM → BDD → infra)
- [ ] Page de status publique si applicable
- [ ] Health check endpoints (URL + format de réponse attendu)

## Instructions

1. Copier `templates/aspects/common/monitoring.md` vers `project/monitoring.md`
2. Renseigner les sections
3. Si pas de monitoring en place, c'est un signal — créer une tâche
   "Mettre en place monitoring" séparément

## Références

- `templates/aspects/common/monitoring.md`
- `project/environments.md` (logs par env)
- `~/.claude/CLAUDE.md` (conventions log iProspective : `/var/log/php/<pool>.error.log`)
