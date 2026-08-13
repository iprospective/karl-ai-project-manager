> 📂 **Module `traceability` — quand lire ceci :** je commit / franchis une étape significative · je journalise une décision · je référence un commit.
> **Outils :** `pm-task-report` · **Préchargé par :** —.

#### Journalisation des échanges avec l'humain (obligatoire, au fil de l'eau)

Quand un échange utilisateur ↔ agent porte sur une tâche — arbitrage, décision,
re-cadrage du besoin, retour de test, correction de cap — l'agent **résume** cet
échange et l'appende au `.log.md` de la tâche **au fur et à mesure**, sans attendre
la clôture. On journalise le *pourquoi* des décisions, pas seulement le code produit.

- **Résumer, pas recopier** : une synthèse pertinente, pas le transcript verbatim.
- **Au fil de l'eau** : une entrée par étape significative, datée. Objectif :
  pouvoir reconstituer le fil de la tâche (et les raisons des choix) sans relire
  la conversation d'origine.
- N'enregistrer que ce qui est lié à la tâche ; le bavardage hors-sujet n'a pas
  sa place dans le journal.

#### Traces mécaniques templatées — RM2365 (CDC RM2316 § S4)

Les notes Redmine des **événements mécaniques** sont générées par l'outillage
depuis `templates/notes/` (ex. `status_change.md` : ancien → nouveau statut,
assignation, branche/MR) — **l'agent ne rédige plus cette partie**. La règle :

- **Transition de statut** : ne passer `--note` à `pm-task-status-update` /
  `pm-task-take` / `pm-task-deliver` **que pour un ajout sémantique** (décision,
  contexte, résumé de livraison) — jamais pour paraphraser la transition,
  l'assignation, la branche ou la MR (le template les porte déjà).
- Les événements déjà journalisés ailleurs **n'appellent pas de note
  supplémentaire** : estimation (CF 21/22 visibles sur le ticket), liens
  (journal Redmine natif des relations), tick/report (déjà templatés).
- Le **sémantique reste obligatoire** là où il l'a toujours été : prise en
  charge avec plan, décisions/arbitrages, blocages, livraison (le
  `--summary` de `pm-task-deliver`).

#### Unité de traçabilité : l'étape significative (canonique) — v1.23.0

**Référence unique** pour « quand commiter, quand noter ». L'unité de travail
tracée n'est ni le fichier ni la frappe : c'est l'**étape significative** — un
incrément consistant et cohérent (livraison, fonctionnalité, correctif, décision
structurante). On ne commit ni chaque fichier sauvé, ni un seul gros bloc à la
toute fin : on commit **à la frontière d'une étape significative**.

À cette frontière, à partir d'**un seul effort de fond** décliné en deux
granularités, l'agent produit :

1. **Message de commit** — résumé **court** (1 ligne + corps optionnel), langue du repo.
2. **Note Redmine** — résumé **détaillé**, human-readable, destiné au ticket : ce
   qui a été fait/livré et *pourquoi*, + **réf du commit** (SHA + URL GitLab, cf.
   « Référencer un commit ») + **temps + tokens** du delta (cf. § « Journalisation
   par commit »). C'est la trace que les humains lisent — donc **aérée** : sauts
   de ligne aux ruptures d'idée plutôt qu'un unique bloc compact, sans pour
   autant sur-formatter une note de trois phrases (pas de titres/listes à
   outrance).
3. **Entrée `.log.md`** — variante technique de l'agent (détail, décisions) + réf
   commit + métriques, append-only (format ci-dessus). Les humains ne la lisent pas.
4. Si l'étape est une **livraison** : transition de statut + `done_ratio` au même
   moment (cf. §§ dédiés).

> Même synthèse de fond, supports différents (long → note, court → commit,
> technique → log) : pas trois rédactions distinctes.

**Quand poster une note Redmine** — matrice unique, ne pas redéfinir ailleurs :

| Événement | Note ? |
|---|---|
| Commit de **travail / livraison / structurant** (chose dont on veut garder trace) | **Oui** — note détaillée + réf commit + métriques |
| Événement **structurant sans commit** (cahier des charges, réflexion, arbitrage, décision, re-cadrage) | **Oui** — note complémentaire (synthèse, sans réf commit) |
| Commit **trivial / housekeeping** (sync frontmatter, append `.log.md`, fix typo doc PM) | **Non** (sauf `commit_note_level: all`) |
| Simple changement de **statut** ou `done_ratio` | **Non** — Redmine les journalise nativement |
| Mise à jour de **description** (texte/checklist) | **Oui** — cf. § « Mise à jour de la description » (Redmine ne diff pas les descriptions) |

**Niveau de note par commit — configurable** (`pm.config.yml :: traceability.commit_note_level`,
pour calibrer le bruit à l'usage) :
- `work` (défaut) — note pour les commits de travail/livraison/structurants uniquement.
- `all` — note pour **tout** commit rattaché à une tâche (mode test : mesurer le bruit réel).
- `none` — pas de note auto par commit (on conserve `.log.md` + time_entry).

#### Référencer un commit dans une entrée

Toute entrée de journal qui **produit ou modifie du code** doit citer le(s)
commit(s) correspondant(s), pour tracer précisément quelle livraison à quelle étape :

```markdown
Commit: <repo-alias>@<sha-court> — <message court>
        https://gitlab.iprospective.fr/<ns>/<repo>/-/commit/<sha-complet>
```

- La forme **canonique de tracking** est le SHA (≥ 7 caractères) ou, mieux quand le
  repo est sur GitLab, l'**URL de commit complète** (cliquable et résolvable).
- Le frontmatter `git.branch` / `git.mr_url` reste le pointeur *courant* (branche de
  travail, MR ouverte) ; le `.log.md` conserve l'*historique* des commits par étape.
  Pour une référence ponctuelle hors workflow dev, utiliser `refs: [{type: commit, …}]`.
- **Prérequis** : le workspace doit être un dépôt git. S'il ne l'est pas (ex. un
  workspace infra non initialisé), il n'y a pas de commit à référencer — le signaler
  explicitement dans l'entrée plutôt que de laisser un trou.

---

