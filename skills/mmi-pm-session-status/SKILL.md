---
name: mmi-pm-session-status
description: Suivi d'avancement par session — enregistre au fil de l'eau les tickets/tâches ouverts dans la session et leur statut, et répond cheap (lecture d'un seul fichier, sans rescanner le contexte) à « il reste quoi à faire dans cette session » / « où en est-on » / « récap session ». Usage : "/mmi-pm-session-status", ou langage naturel "il reste quoi à faire ?", "récap de la session", "qu'est-ce qu'on a ouvert comme tickets ?".
allowed-tools: Bash
---

# Skill : mmi-pm-session-status

Wrapper contextuel autour de `scripts/pm-session-status.py`. Suit la convention
`mmi-pm-<entité>-<action>` (cf. `memory/feedback_mmi_pm_skill_naming`).

Maintient un **worklog par session Claude Code** (keyé par `$CLAUDE_CODE_SESSION_ID`) listant
les tickets/tâches touchés dans la session et leur avancement. Permet de répondre à
« il reste quoi à faire ? » en **lisant un seul petit fichier** — pas de re-scan du contexte,
donc peu de tokens, et ça survit à la compaction.

Implémente le volet « manifest déclaratif » de **RM1875** + le **harvest automatique / statut live** de **RM2068**.

## Auto-alimenté + statut live (RM2068)

Deux propriétés réduisent fortement la charge :
- **Auto-alimentation (effet de bord, zéro token agent)** : `pm-task-add` / `pm-task-status-update` /
  `pm-task-link` et le **hook post-commit** upsertent le worklog tout seuls (via `pm_session_hook`,
  no-op hors session Claude). Tout ticket créé / transitionné / lié / committé dans la session
  **apparaît sans appel manuel**. L'écriture manuelle reste utile pour les **chantiers non-ticket**.
- **Statut live à la lecture** : `show` (et `refresh`) résolvent le statut **courant** de chaque
  ticket depuis le frontmatter de sa tâche, et **signalent la dérive** vs le statut d'ouverture
  (« ouvert `en_cours` → `ferme` (ailleurs) ») → fidèle même quand une **autre session** a fait
  avancer/fermer le ticket. `show --no-live` = rendu snapshot rapide (sans résolution).

## Stockage (instance-local, jamais committé)

- Source de vérité : `~/.claude/session-worklogs/<session-id>.json`
- Rendu lisible (régénéré à chaque mutation, et par `refresh`) : `~/.claude/session-worklogs/<session-id>.md`
- `refresh` (re-résout le live + réécrit le `.md`) est câblé sur les hooks **SessionStart**/**PreCompact**
  (settings.json) → la reprise / post-compaction lit un `.md` à jour sans re-scan.

État de session éphémère et propre à l'instance → **hors repo PM** (ne pas committer).

## Quand déclencher

**Lecture** (la question cible) :
- "état de la session ?", "état de session", "état session ?" (= « où on en est »),
  "il reste quoi à faire (dans cette session) ?", "où en est-on ?", "où on en est ?",
  "récap session", "qu'est-ce qu'on a ouvert ?", "/mmi-pm-session-status" → `show`

**Écriture** — depuis RM2068, les **tickets PM** sont logués **automatiquement** par les scripts
(`pm-task-add`/`-status-update`/`-link` + hook post-commit) : pas besoin de les `add` à la main.
Reste à faire proactivement par l'agent :
- **chantier non-ticket** décidé (« reste le déploiement prod ») → `add <slug> "<libellé>" --status à_faire`
- précision/avancée hors transition de statut → `set <ref> <statut>` ou `add <ref> --next "<prochaine action>"`

## Invocation

```bash
# (depuis la racine du repo PM)
scripts/pm-session-status.py show            # état avec statut live + dérive (défaut)
scripts/pm-session-status.py show --no-live  # rendu snapshot rapide (sans résolution frontmatter)
scripts/pm-session-status.py refresh         # re-résout le live + réécrit le .md (hooks SessionStart/PreCompact)

# ajouter / upsert un item (ref = RM-id ou slug libre) — surtout pour les chantiers non-ticket
scripts/pm-session-status.py add pisceen-facettes "Fix #-serveur facettes" --status en_attente --note "uncommitted; reste test nav + commit + déploiement prod"
scripts/pm-session-status.py add RM1886 --next "rebrancher le hook puis tester"   # enrichir la prochaine action

# changer un statut / divers
scripts/pm-session-status.py set RM1886 en_cours
scripts/pm-session-status.py rm <ref>
scripts/pm-session-status.py title "Libellé de la session"
```

## Notifications importantes (RM2466)

Canal d'**événements**, distinct des items de travail : un incident rencontré en
séance finissait au mieux dans une phrase de réponse, et se perdait au premier
défilement. Règle NORMS : `modules/session-tooling.md` § « Notifications
importantes » (déclencheur au KERNEL).

**Consigner sur-le-champ**, pas « à la fin » — à la fin, on a oublié :

```bash
scripts/pm-session-status.py notify "<fait court et factuel>" --kind <type> [--ref RM<id>] [--level info|warn|critical]
scripts/pm-session-status.py notify --list          # relire le canal
scripts/pm-session-status.py notify --clear         # acquitter (les `critical` restent)
scripts/pm-session-status.py notify --clear --all   # acquitter AUSSI les critiques
```

| `--kind` | quand | niveau par défaut |
|---|---|---|
| `secret` | un secret a transité en clair (transcript, log, capture, sortie de commande) | `critical` |
| `refus` | action refusée / permission manquante | `warn` |
| `garde-fou` | branche protégée, périmètre projet, worktree | `warn` |
| `outillage` | un script PM ne fait pas ce qu'il annonce | `warn` |
| `decision` | un arbitrage du demandeur manque et bloque l'avancement | `warn` |

Restitué **en tête** de `show` (donc du récap de session) et repris par le
cockpit, onglet « état ».

**Deux pièges :**
- une notification est un fait **notable et actionnable**, pas un commentaire —
  un canal noyé sous le bruit ne sera pas lu, donc ne servira à rien ;
- pour un secret exposé, la notification **trace** le fait ; la **rotation** du
  secret reste à faire, sur le ticket référencé par `--ref`. Consigner sans faire
  tourner le secret, c'est documenter une faille, pas la fermer.

## MR à merger (RM2583)

`pm-mr.py` inscrit lui-même les MR dans le worklog à la création, et les en sort
au merge / à la fermeture — rien à faire à la main. `show` liste alors ce qui
**reste à merger**, et le cockpit l'affiche dans l'onglet « état ».

```bash
scripts/pm-session-status.py mr --list          # tout l'historique de la session
```

Le worklog reflète ce que **cette session** a ouvert, pas l'état global de la
forge : une MR mergée à la main dans l'UI GitLab y restera « à merger ».
Correction : `pm-session-status.py mr <iid> --state merged`.

## Registre des demandes (RM2621)

Une demande formulée en séance n'existe que dans le fil : non ticketée
sur-le-champ, elle disparaît au premier défilement. Le registre la retient
**avant** de savoir ce qu'elle deviendra. Règle NORMS :
`modules/session-tooling.md` § « Registre des demandes ».

```bash
scripts/pm-session-status.py request "<la demande, telle que formulée>"
scripts/pm-session-status.py request --list
scripts/pm-session-status.py request --set 12 --status ticketee --ticket RM2621
scripts/pm-session-status.py request --set 12 --status repondu --note "traité sans ticket"
scripts/pm-session-status.py request --set 12 --status annulee
scripts/pm-session-status.py request --set 12 --status fusionnee --merged-into 9
scripts/pm-session-status.py request --audit           # contrôle d'exhaustivité
scripts/pm-session-status.py request --import-missing   # RATTRAPAGE (voir plus bas)
```

`--set` prend le **numéro affiché** par `show` / `--list`, pas un identifiant à
retenir. Seules les demandes `nouveau` apparaissent dans « 📥 Demandes à
traiter » ; les quatre autres statuts les en sortent sans les effacer.

**Ne filtre pas à la réception.** « fais une sous-tâche » fait 19 caractères et
c'est une demande ; « core update fait » en fait 17 et n'en est pas une. En cas
de doute : enregistre. Une entrée en trop se classe d'un geste, une demande
perdue ne se retrouve pas.

**`--audit` est le filet.** Il compte les messages du transcript, en retire les
accusés de réception, et compare au registre. Il ne juge pas le contenu — c'est
un comptage, il ne coûte aucun token, et c'est lui qui transforme « je crois
n'avoir rien oublié » en fait vérifiable. À lancer en fin de session.

**`--import-missing` est un rattrapage, pas le mode normal.** Il reprend du
transcript tout ce qui manque et le pose en `nouveau`, à trier. Utile quand la
règle n'était pas en place ; l'usage courant reste l'enregistrement explicite,
message par message.

## Statuts

Texte libre, mais reconnus pour le tri d'affichage :
- **terminés** (sortis du « reste à faire ») : `fait`, `done`, `ferme`, `livré`, `résolu`, `closed`
- **en attente / bloqué** (section à part) : `en_attente`, `bloqué`, `waiting`, `a_valider`
- tout le reste (`à_faire`, `en_cours`, `nouveau`, …) → **Reste à faire**

Pour les tickets PM, garder une cohérence avec les statuts NORMS quand pertinent
(`nouveau`, `en_cours`, `a_tester_demandeur`, `a_mep`, `ferme`…).

## Comportement de l'agent

- Sur une question « reste quoi à faire / récap » → exécuter `show` et **relayer la sortie** (déjà lisible en Markdown).
  Le statut affiché est **live** (frontmatter) ; une mention « ouvert X → Y (ailleurs) » = le ticket a bougé
  hors de cette session → en tenir compte dans le récap.
- Les tickets se loguent **seuls** (RM2068) ; à toi de logger les **chantiers non-ticket** (voir « Écriture »).
- Le worklog est **par session** : ne reflète que ce que CETTE session a ouvert/touché, pas l'ensemble du backlog projet (pour ça → `mmi-pm-task-list`).
