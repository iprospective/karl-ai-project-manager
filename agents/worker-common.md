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
ou surcharge le précédent (cf. `norms/src/NORMS-KERNEL.md` § Cascade et héritage).

1. `agents/worker-common.md` — ce fichier
2. `agents/worker-{role}.md` — règles spécifiques au rôle
3. `norms/src/NORMS-KERNEL.md` — **KERNEL** (déclencheurs + tripwires + schéma) ; ouvre `norms/src/modules/*.md` **à la demande** selon les déclencheurs (ne charge pas tout)
4. `{entity_client_dir}/*.md` (overview + tous les aspects) + `{entity_memory_dir}/*.md`
5. `{project_dir}/*.md` (overview + aspects) + `{project_memory_dir}/*.md` ;
   côté `{docs_dir}` : lire **`docs/INDEX.md`** (1 ligne par doc), puis ouvrir
   les docs **à la demande** — jamais le dossier entier (budget
   `context.budget_tokens.project_docs`, vérifié par `pm-context-budget --check`)
5bis. **`pm-glossaire.py <projet> inject`** — le VOCABULAIRE MÉTIER du projet
   (RM2675), **systématiquement**, pas à la demande. C'est la seule pièce du
   niveau projet qui échappe à la règle « ouvrir au besoin », et pour une raison
   précise : un agent qui croise un terme qu'il ne connaît pas **n'ira pas
   ouvrir le glossaire** — il supposera, et se trompera silencieusement. Lire
   « rampe » en croyant à une pente au lieu de la barre porte-guillotines ne
   déclenche aucun doute.
   Plafonné à **1 500 tokens** (≈ 70 termes, 7,5 % du budget `project_docs`), et
   la troncature est **annoncée** dans le bloc — jamais muette. Glossaire absent
   ⇒ rien à lire, aucun coût.
6. **`pm-task-brief.py <id>`** — le pack contexte de la tâche en ≤ 30 lignes
   (statut, estimé vs réel, critères, liens/sous-tâches, dernières entrées de
   journal, journaux Redmine non lus). C'est le point d'entrée par défaut ;
   n'ouvre le MD complet que si le brief ne suffit pas (description longue,
   CDC dans le corps).
7. Fichiers dans `refs[]` — documents de référence liés à la tâche
8. Tâches dans `depends_on` — contexte amont : `pm-task-brief.py <dep-id>`
   (lecture seule ; MD complet à la demande)
9. Journal : couvert par le brief ; pour approfondir, `pm-task-log.py <id>
   --tail N [--grep RX] [--full]` (jamais de `cat` du `.log.md` entier).
   Lecture ciblée d'un champ : `pm-task-show.py <id> --field a,b.c` (jamais de
   `grep` manuel du frontmatter).

(Les patterns `{entity_client_dir}`, `{project_dir}`, `paths.task_file` etc. sont
définis dans `pm.config.yml` ; la résolution par défaut donne
`{projects_root}/clients/{C}/...`. La lib `scripts/pm_paths.py` les résout :
`cfg.path("project_dir", entity={C}, project={P})`.)

**Aspects cascade :** si un aspect (ex: `hosting.md`) existe à la fois au niveau client
et au niveau projet, lire les deux. Le projet précise/surcharge le client en cas
de contradiction.

**Résolution de chemins (workspace projet) :** depuis un workspace de code, le
symlink caché `paths.reverse_link` (`.mmi-pm/` par défaut) pointe vers le dossier
PM centralisé du projet. Pour atteindre le client, utiliser
`cfg.path("entity", entity=<slug>)` (slug lu dans le frontmatter de
`project/overview.md`), **pas** `.mmi-pm/../../client/` (la résolution logique des
symlinks n'est pas fiable).

Respecter le `context_budget` du frontmatter.

## Deux champs à tenir au fil de l'eau

Ni l'un ni l'autre ne se rattrape après coup : ce qu'on ne note pas au moment où on le
comprend est perdu. Tous deux ont un CF Redmine canonique et un miroir frontmatter —
on n'écrit ni dans l'un ni dans l'autre à la main, on passe par l'outil.

**Proposition d'implémentation** (`pm-task-implementation <id> --set -`). Quel que soit
ton rôle, si tu produis un CDC en `etude_chiffrage_en_cours` et que l'étude **débouche
sur du code**, tu poses l'esquisse technique issue de ton audit : modèle de données,
composants, **points d'insertion `fichier:fonction`**, vues, flux, migration, pièges
relevés. 15 à 40 lignes, elle **oriente sans prescrire**. Pas d'exemption pour les
petits développements. Sans elle, l'agent qui reprend le ticket refait ton audit — et
souvent avec un modèle moins capable que le tien. Détail, dispenses et condition de
sortie : `norms/src/modules/status-workflow-pratique.md` § *La proposition
d'implémentation*.

**Actions au déploiement** (`pm-task-deploy <id> --add "…"`). C'est la **procédure de
MEP de ton ticket** — une suite **ordonnée** d'étapes, pas un pense-bête : migration à
jouer et dans quel ordre, constante à créer avant le premier passage, service à
recharger, dépôt A avant dépôt B, rollback s'il ne se réduit pas au commit précédent.
Tu l'écris **au moment où tu découvres l'étape**, pas à la livraison. Ce qui est
systématique pour l'environnement n'y va pas : c'est `environments[].post_deploy`. Rien
de particulier ⇒ liste **vide**, c'est une réponse. Cf. `norms/src/modules/git-mep.md`
§ *Actions au déploiement*.

## Vérification initiale

```
- Vérifier que status = en_cours ET assigned_to = soi-même
- Si non, deux cas :
    - Mode orchestré (lancé par l'orchestrateur) → ne pas travailler, signaler et s'arrêter
    - Mode interactif (lancé par un humain ou en auto) → appliquer activement les deux
      opérations (cf. NORMS § « Prise en charge d'une tâche : en_cours ⇒ auto-assignation »),
      puis continuer.
- Si oui → appender dans .log.md : "Prise en charge — {résumé du plan de travail}"
```

## Se placer dans le BON worktree (RM2240)

Avant **toute édition ou commit** pour RM<id> : résoudre `git.worktree` du
frontmatter et **s'y placer** — un sous-processus (`pm-branch-start`) ne change
pas le cwd du shell, c'est à toi de faire le `cd` :

```bash
cd "$(pm-task-cd.py <id>)"        # résout git.worktree du frontmatter
# ou, à la création :
cd "$(pm-branch-start.py <id> --take --worktree --print-cd)"
```

`pm-branch-start --worktree` termine sa sortie par la ligne `→ cd <chemin>` :
**exécute-la**. Le hook pre-commit (pm-pre-commit, RM2240) refuse un commit de
ticket fait ailleurs que dans son worktree enregistré — si ça t'arrive, c'est
que tu as édité au mauvais endroit : rapatrie tes modifs, ne contourne pas.
Attention aussi au piège inverse : lancer `pm-branch-start --worktree` **depuis
le worktree d'un autre ticket** base la nouvelle branche dessus — se placer
d'abord dans l'env d'intégration (`envs/<repo>-dev`).

## La plomberie des données PM est transparente — et hors sujet (RM2440)

> **Tripwire #15 du KERNEL** — énoncé court là-bas, détail ici. Elle est passée
> tripwire parce qu'elle s'applique au moment où tu **rédiges ta réponse**, quand
> tu n'ouvres plus aucun fichier : aucun déclencheur ne peut l'attraper (RM2676).

La mécanique git des dépôts de **données PM** (`*-core` : auto-commits `pm(...)`,
push) **ne figure jamais dans ta restitution** — ni hash, ni branche, ni MR, ni
« ✓ commité ». Tu parles du **fond du ticket** et du **code livré** (une MR de
code, elle, se raconte : c'est une livraison).

**Exception : l'échec.** Un auto-push qui échoue se signale en **une ligne** —
sinon l'arriéré redevient silencieux. Même règle côté outillage : `pm_git` est
muet sur le chemin nominal (`git.verbose: true`).

**Et la règle vaut en LECTURE, pas seulement en écriture.** Quand l'utilisateur
pose une question non qualifiée — « les tickets sont mergés en main ? », « c'est
poussé ? », « où en est la branche ? » — il parle des dépôts de **CODE** et du
dépôt du **projet PM**, jamais d'un `*-core`. Il ne parle **jamais** de cette
plomberie sauf à la **nommer explicitement**. Répondre sur un `*-core` qu'il n'a
pas nommé est la même violation vue de l'autre côté : au lieu de noyer la
restitution sous du bruit, on répond entièrement à côté, et il faut un tour de
conversation pour rattraper. En cas de doute sur la cible d'une question de
merge/push/branche : les dépôts de code d'abord ; le `*-core` seulement s'il est
nommé (redit le 2026-09-01, « je n'en parle jamais, sauf explicitement »).

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
