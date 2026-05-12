# Worker — Règles communes

Ce fichier est chargé par tous les agents workers en première position, avant leur fichier spécifique.

## Périmètre d'écriture

| Fichier | Droit |
|---|---|
| Fichier MD de la tâche assignée | Lecture + écriture (propriété exclusive via Redmine) |
| Fichier `.log.md` de la tâche | Append uniquement |
| Fichiers référencés dans `outputs[]` | Lecture + écriture |
| Tous les autres fichiers MD | Lecture seule |

## Contexte à charger à chaque tâche (cascade)

Lecture en cascade : système → client → projet → tâche. Chaque niveau complète
ou surcharge le précédent (cf. NORMS.md § Cascade et héritage).

1. `agents/worker-common.md` — ce fichier
2. `agents/worker-{role}.md` — règles spécifiques au rôle
3. `norms/NORMS.md` — schéma, machine d'états, protocoles
4. `clients/{C}/client/*.md` (overview + tous les aspects) + `clients/{C}/memory/*.md`
5. `clients/{C}/projects/{P}/project/*.md` (overview + aspects) + `memory/*.md`
6. `clients/{C}/projects/{P}/tasks/RM{id}_*.md` — la tâche assignée
7. Fichiers dans `refs[]` — documents de référence liés à la tâche
8. Fichiers MD des tâches dans `depends_on` — contexte amont (lecture seule)
9. Dernières 50 lignes de `RM{id}_*.log.md` — état courant

**Aspects cascade :** si un aspect (ex: `hosting.md`) existe à la fois au niveau client
et au niveau projet, lire les deux. Le projet précise/surcharge le client en cas
de contradiction.

**Résolution de chemins (workspace projet) :** depuis un workspace `/zfs/workspaces/{P}`,
`mmi-pm/` est un symlink vers le dossier PM centralisé. Pour atteindre le client, utiliser
`$PROJECTS_PATH/clients/{client-slug}/` (slug lu dans le frontmatter de `project/overview.md`),
**pas** `mmi-pm/../../client/` (la résolution logique des symlinks n'est pas fiable).

Respecter le `context_budget` du frontmatter.

## Vérification initiale

```
- Vérifier que status = en_cours ET assigned_to = soi-même
- Si non → ne pas travailler, signaler à l'orchestrateur et s'arrêter
- Si oui → appender dans .log.md : "Prise en charge — {résumé du plan de travail}"
```

## Travail itératif

À chaque étape significative :
```
- Effectuer le travail
- Appender dans .log.md (voir format ci-dessous)
- Mettre à jour completion_pct dans le frontmatter
- Cocher les critères d'acceptation accomplis (- [ ] → - [x])
```

## Format d'entrée de journal

Une entrée par session de travail, format imposé :

```markdown
## {YYYY-MM-DDTHH:MM} — {agent-id} ({modèle})
Tokens : {n} | Durée : {n} min

{Description factuelle et synthétique : ce qui a été fait, décisions prises,
problèmes rencontrés, questions ouvertes. Ne jamais laisser vide.}
```

## Protocole de soumission

Quand tous les critères d'acceptation sont cochés et les vérifications spécifiques au worker sont passées (voir fichier worker) :

```
1. Remplir outputs[] avec les chemins/URLs de tous les artefacts produits
2. Mettre status → a_tester_verifier dans le frontmatter
3. Ajouter une entrée dans status_history :
   {status: a_tester_verifier, at, by, model, tokens, duration_minutes}
4. Recalculer et mettre à jour tokens_total et time_total_minutes
5. Optimistic locking : relire updated — si changé → re-lire le fichier et recommencer
6. Écrire le fichier MD avec updated mis au timestamp courant
7. Passer le ticket Redmine en a_tester_verifier via API
8. Poster une note Redmine (contenu défini dans le fichier worker spécifique)
```

## Règle optimistic locking

S'applique à **toute écriture** sur un fichier `.md` :
```
1. Lire le champ updated (T1)
2. Préparer les modifications
3. Relire updated — si ≠ T1 → collision → re-lire le fichier entier et recommencer
4. Écrire, mettre updated à T2 (timestamp courant)
```
Ne s'applique **pas** aux `.log.md` (append-only, pas de perte possible).

## En cas de blocage

```
1. Appender dans .log.md : description précise du blocage ou de l'ambiguïté
2. Poster une note Redmine avec la question ou le problème
3. Rester en en_cours — ne jamais soumettre si les critères ne sont pas satisfaits
4. Ne jamais rester bloqué silencieusement
```
