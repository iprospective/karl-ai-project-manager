# Guide d'invocation manuelle des agents

Les agents sont déclenchés manuellement via Claude Code CLI depuis la racine de ce dépôt.

```bash
# 1. Se placer à la racine du repo PM (chemin défini dans pm.config.yml ::
#    roots.pm_dir — adapter au besoin)
cd /zfs/workspaces/ai/project-management

# 2. Charger les variables d'environnement (credentials, URLs)
source .env

# 3. Lancer Claude Code — CLAUDE.md est chargé automatiquement
claude
```

Le `CLAUDE.md` est chargé automatiquement par Claude Code. Il suffit ensuite de
taper la commande d'invocation dans le chat.

---

## Invocations courantes

### Lancer un worker sur une tâche

```
Tu es worker-dev. Traite la tâche RM1234 du projet mon-projet.
```

```
Tu es worker-analyst. Traite la tâche RM1235 du projet mon-projet.
```

```
Tu es worker-db. Traite la tâche RM1236 du projet mon-projet.
```

```
Tu es worker-design. Traite la tâche RM1237 du projet mon-projet.
```

```
Tu es worker-infra. Traite la tâche RM1238 du projet mon-projet.
```

### Lancer un reviewer sur une tâche soumise

```
Tu es reviewer. Valide la tâche RM1234 du projet mon-projet.
```

### Demander à l'orchestrateur de scanner les tâches en attente

```
Tu es orchestrateur. Scanne les tâches en attente du projet mon-projet
et dis-moi ce qui est prêt à être assigné.
```

### Créer une nouvelle tâche depuis le template

```
Crée une nouvelle tâche pour le projet mon-projet :
- Redmine ID : 1234
- Titre : Scraping catalogue produits
- Type : feature
- Priorité : high
- Description : [...]
```

---

## Workflow typique d'une tâche

```
1. Créer le ticket Redmine
2. Créer le fichier MD via :
   python3 scripts/redmine-fetch-task.py --issue 1234
   (le chemin de destination est résolu via pm.config.yml :: paths.task_file)
3. Compléter le frontmatter (priority, due, roi, ...) et rédiger Contexte +
   Critères d'acceptation + Instructions
4. Assigner le ticket Redmine au worker
5. Invoquer l'agent :
   "Tu es worker-{role}. Traite la tâche RM1234 du projet mon-projet."
6. L'agent travaille, met à jour le MD et Redmine
7. Quand status = a_tester_verifier :
   "Tu es reviewer. Valide la tâche RM1234 du projet mon-projet."
8. Si approuvé → status = ferme, ticket Redmine clôturé
```

---

## Conseils

- Lancer Claude Code depuis la racine du dépôt project-management pour que
  `CLAUDE.md` soit chargé automatiquement
- Pour les tâches de dev, l'agent aura besoin d'accéder au repo de code du projet :
  s'assurer que le chemin est accessible ou indiquer le chemin dans la tâche
- Le fichier `.log.md` doit exister avant l'invocation (même vide)
