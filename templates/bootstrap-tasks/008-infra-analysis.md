---
bootstrap_template: "008-infra-analysis"
default_checked: true
title: "Analyse de l'infra : inventaire, état, risques"
type: infrastructure
priority: high
tags: [bootstrap, infra, audit, inventory]
roi:
  immediate_benefit: 3
  monthly_benefit: 3
estimate:
  difficulty: medium
  time_minutes: 90
applicable_when: |
  Le projet est de nature infrastructure (slug/nom « infra », ou aspect
  hosting/infrastructure), c.-à-d. qu'il gère un ou plusieurs serveurs / hyperviseurs
  / réseaux / stockage plutôt qu'une seule application. Pour ces projets, ce template
  est proposé COCHÉ par défaut. Pour les projets applicatifs, il n'est pas applicable.
---

## Contexte

Tout projet infra doit démarrer par un **état des lieux** de ce qu'on gère : sans
inventaire à jour (matériel, disques, pools, VMs/CT, réseau, monitoring), on découvre
l'infra dans l'urgence le jour où ça casse, et les anomalies (SMART, saturation, temp)
passent sous le radar. Ce ticket est créé **par défaut** à la création d'un projet
infra (convention NORMS § Tâches de bootstrap).

## Critères d'acceptation

- [ ] Un document d'inventaire/analyse existe (workspace `docs/infrastructure.md` ou
      aspect `project/hosting.md`) et est référencé dans `overview.md`
- [ ] Inventaire matériel : CPU, RAM, NIC, hyperviseur + version
- [ ] Stockage : disques physiques (modèle, S/N, état SMART), pools/RAID, topologie,
      taux de remplissage, mapping device↔pool
- [ ] Charges hébergées : VMs/CT (nom, statut, storage, rôle), réseau (bridges, IP)
- [ ] Monitoring en place : agents (Zabbix…), smartd, alerting, self-tests planifiés
- [ ] Section **Anomalies & points de vigilance** : ce qui dérive, ce qui sature, ce
      qui chauffe — avec, pour chaque anomalie significative, **un ticket dédié**
- [ ] Section historique des interventions (table datée)

## Instructions

1. Se connecter au(x) serveur(s) (`ssh <alias>`), collecter l'inventaire (lsblk,
   smartctl, zpool/RAID status, qm/pct list, pvesm/df, ip a, journaux smartd/dmesg).
2. Consigner dans `docs/infrastructure.md` (workspace) — document vivant, mis à jour à
   chaque intervention notable.
3. Pour chaque anomalie détectée (disque qui dérive, saturation, surchauffe…), ouvrir
   un **ticket d'anomalie séparé** avec décision attendue, et le lier à ce ticket.
4. Référencer le document dans `project/overview.md` (section Aspects).

## Références

- `templates/aspects/common/hosting.md`
- NORMS § « Tâches de bootstrap » (template `008-infra-analysis`, coché par défaut sur
  projets infra)
- `~/.claude/CLAUDE.md` (conventions accès serveurs : alias SSH = nom du conteneur/hôte)
