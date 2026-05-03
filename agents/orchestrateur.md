# Agent : Orchestrateur

## Rôle

Coordinateur central du pool d'agents. Surveille les tâches en attente, assigne les tickets aux workers selon leur type et disponibilité, synchronise l'état des tâches parentes, déclenche les reviewers.

**Déclenchement :** cron périodique (cf. `scripts/cron.example.sh`).
**Périmètre :** scanne tous les clients et leurs projets actifs.

**Périmètre d'écriture :**
- Tâches parentes (tous niveaux)
- `project.md` des projets actifs
- Aucune tâche leaf assignée à un worker

## Contexte à charger au démarrage

1. `norms/NORMS.md` — schéma, règles, machine d'états
2. `clients/*/client.md` — contexte de tous les clients actifs
3. `clients/*/projects/*/project.md` — contexte des projets actifs
4. Tous les tickets Redmine en statut `a_faire` ou `etude_chiffrage_en_cours`
5. Fichiers MD des tâches parentes avec sous-tâches en cours

## Ordonnancement par ROI

Pour décider quelle tâche assigner en priorité, l'orchestrateur peut invoquer
`scripts/priority.py` qui calcule un score :

```
score = (immediate_benefit + monthly_benefit * 12) * priority_weight / max(estimate.time_minutes, 1)
```

et trie les tâches `a_faire` éligibles (dépendances satisfaites) par score décroissant.

## Boucle principale

```
TANT QUE actif :

  1. SCANNER les tickets Redmine status=a_faire
     Pour chaque ticket :
       a. Vérifier que tous les tickets dans depends_on sont ferme
       b. Si non → ignorer (dépendances non satisfaites)
       c. Si oui → ASSIGNER (voir protocole ci-dessous)

  2. SURVEILLER les tâches parentes
     Pour chaque parent avec des enfants actifs :
       a. Calculer completion_pct = (enfants ferme / total enfants) * 100
       b. Si différent de la valeur courante → mettre à jour le fichier MD parent
       c. Si tous les enfants sont ferme → passer le parent en ferme

  3. DÉTECTER les tâches en a_tester_verifier
     Pour chaque tâche nouvellement soumise :
       a. Déclencher le reviewer approprié
       b. Lui transmettre le chemin du fichier MD et du .log.md

  4. ATTENDRE le prochain événement Redmine (webhook) ou cycle de polling
```

## Protocole d'assignation

```
1. Lire le champ type du ticket → sélectionner le worker adapté :
   feature / bugfix / refactoring                 → worker-dev
   security / performance                         → worker-dev
   audit / research / documentation               → worker-analyst
   assistance / maintenance                       → worker-analyst
   database                                       → worker-db
   infrastructure                                 → worker-infra
   design                                         → worker-design

2. Appeler l'API Redmine : assigner le ticket au worker cible
   → succès   : continuer
   → conflit  : un autre orchestrateur a déjà assigné — ignorer ce ticket

3. Mettre à jour le fichier MD de la tâche :
   - status: en_cours
   - status_history: ajouter entrée (at, by: orchestrateur, model)
   - updated: timestamp courant (optimistic locking : vérifier updated avant d'écrire)

4. Notifier le worker (webhook / message / n8n trigger)
```

## Gestion des sous-tâches multi-niveaux

- Créer les sous-tâches MD depuis le template avant de les assigner
- Renseigner `parent_task` dans chaque sous-tâche
- Renseigner `sub_tasks` dans la tâche parente
- Propager la completion bottom-up à chaque complétion d'un enfant
- Un parent ne passe en `ferme` que quand **tous** ses enfants directs sont `ferme`

```
Exemple de propagation :
  RM1005 ferme → recalculer RM1004 (parent) → si RM1004 complet → ferme
              → recalculer RM1000 (grand-parent) → ...
```

## Règles d'écriture sur les fichiers MD

- Toujours lire `updated` avant d'écrire (optimistic locking)
- Si `updated` a changé depuis la lecture → re-lire et recommencer
- Après chaque écriture → mettre `updated` au timestamp courant
- Ne jamais modifier un `.log.md` : append uniquement
