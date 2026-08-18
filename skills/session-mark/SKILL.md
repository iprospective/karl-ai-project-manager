---
name: session-mark
description: Marque la session Claude Code courante avec un préfixe de statut dans son titre — [DONE] (terminée), [A TESTER] (livrée, le demandeur doit tester) ou [WIP] (à finir) — visible dans le picker `claude --resume` et dans le cockpit. Usage : "/session-mark done", "/session-mark a-tester", "/session-mark wip", "/session-mark clear", ou langage naturel "marque la session terminée", "tout est livré, il reste à tester", "note la session comme à finir", "ferme la session".
allowed-tools: Bash
---

# Skill : session-mark

Préfixe le **titre de la session Claude Code courante** avec un marqueur de statut, pour s'y retrouver dans `claude --resume` :

- `[DONE]` — session **terminée**
- `[A TESTER]` — travail **livré**, il ne reste qu'à **tester côté demandeur**
- `[WIP]` — session **à finir** / reprise prévue

## Quand déclencher

- "marque la session terminée", "ferme la session", "c'est fini pour cette session" → `done`
- "tout est livré", "il ne reste plus qu'à tester", "à tester", "je te rends la main pour test" → `a-tester`
- "note la session comme à finir", "session à reprendre / WIP / pas finie" → `wip`
- "enlève le marqueur de statut de la session" → `clear`
- `/session-mark done|a-tester|wip|clear`

## `[A TESTER]` : pourquoi un troisième statut (RM2718, 2026-08-18)

C'est l'état de fin le plus fréquent — et aucun des deux autres ne le disait sans mentir :

| | `[WIP]` | `[A TESTER]` | `[DONE]` |
|---|---|---|---|
| reste-t-il du travail côté agent ? | oui | **non** | non |
| relancée au démarrage de karl-agent | **oui** (`restart:auto`) | non | non |
| retirée du jeu de sessions une fois éteinte | non | **non** | oui |

Marquer `[DONE]` une session livrée mais non testée la fait **sortir du jeu** — or c'est précisément celle qu'on rouvre si le test échoue. La marquer `[WIP]` la fait **relancer au démarrage** : un TUI et une réhydratation de contexte payés pour une session qui n'a plus rien à faire. `[A TESTER]` tient les deux bouts : gardée sous la main, mais pas ranimée d'office.

Elle reste visible par défaut dans le panneau de reprise (filtre `sauf [DONE]`), filtrable explicitement (`[A TESTER] livrées, à tester`), et utilisable comme critère de **jeu dérivé** (`marque = test`) — un jeu « ce qui attend mon test » se crée sans rien y ranger à la main.

> **À ne pas confondre avec le statut de ticket `a_tester_demandeur`** : celui-ci porte sur **un ticket**, le marqueur porte sur **la session** — il dit que *tout* son lot est livré. Une session peut porter cinq tickets `a_tester_demandeur` et un sixième encore en cours : elle reste `[WIP]`.

## Comment ça marche (corrigé 2026-06-07)

⚠️ **On ne peut PAS changer le titre d'une session vivante en écrivant un fichier.** Le CLI tient le `custom-title` en mémoire (réglé par `/rename`) et le **ré-émet à chaque tour** dans le transcript — il écrase donc tout `append` externe au tour suivant, et c'est son dernier écrit que lit `claude --resume`. (Vérifié : chaque `[WIP]`/`[DONE]` appendé par l'ancienne version était suivi d'une réécriture du titre de base par le CLI → le marqueur n'apparaissait jamais.)

→ La **seule voie fiable** est la commande native **`/rename`**, qui mute l'état mémoire du CLI.

Le script se contente donc de **calculer** le nouveau titre — il lit le titre courant, retire un éventuel marqueur précédent, préfixe `[DONE]`/`[WIP]` — et **imprime la ligne `/rename` prête à coller**. L'agent la relaie à l'utilisateur, qui la tape.

L'ID de session courant vient de `$CLAUDE_CODE_SESSION_ID` (exposé par le CLI).

## D'où vient le titre de base (ajouté 2026-08-07)

⚠️ **Deux objets distincts s'appellent « titre de session »**, et ils ne communiquent pas :

| | Emplacement | Posé par |
|---|---|---|
| titre de session **CLI** | transcript `~/.claude/projects/<hash>/<sid>.jsonl` — `ai-title` (auto) / `custom-title` (`/rename`) | le CLI, ou l'utilisateur |
| titre du **worklog PM** | `~/.claude/session-worklogs/<sid>.json`, champ `title` | `pm-session-status.py title` |

Le script résout le titre de base dans cet ordre :

1. **`custom-title`** — renommage explicite de l'utilisateur, fait toujours foi. Y compris face à un `ai-title` plus récent : le CLI ré-émet les deux à chaque tour, la chronologie ne départage rien.
2. **titre du worklog PM** — posé par l'agent, il reflète ce que la session a réellement fait.
3. **`ai-title`** — auto-généré depuis le premier message, en dernier recours : il fige l'intention de départ, souvent dépassée.

*Pourquoi ce repli* : le 2026-08-07, le worklog PM était titré « RM2557 — bons plans du blog en 2 colonnes » alors que la session CLI s'appelait encore « Étudier et chiffrer la tâche RM2557 Calicote » (jamais renommée). Le skill proposait donc un `/rename` avec le nom périmé, incompréhensible pour l'utilisateur qui voyait l'autre titre affiché.

Le script imprime sa **provenance sur stderr** (`titre de base : worklog PM`) — utile quand le titre proposé surprend. La ligne `/rename` reste seule sur stdout.

## Marqueurs : le statut se remplace, le ticket survit (ajouté 2026-08-07)

Un marqueur de **statut** en chasse un autre — `[DONE]` remplace `[WIP]`, jamais ne s'y ajoute. Mais un `[RM1222]` n'est pas un statut : c'est une **identité**, elle doit survivre au marquage.

Le script parcourt donc **tous** les marqueurs en tête de titre, retire ceux de statut (`[DONE]`, `[WIP]`, `[TODO]`) **où qu'ils soient dans la série**, et conserve les autres **dans leur ordre** :

| titre courant | `done` donne |
|---|---|
| `Machin` | `[DONE] Machin` |
| `[WIP] Machin` | `[DONE] Machin` |
| `[A TESTER] Machin` | `[DONE] Machin` |
| `[RM1222] Machin` | `[DONE] [RM1222] Machin` |
| `[RM1222] [WIP] Machin` | `[DONE] [RM1222] Machin` |
| `[WIP] [RM1222] Machin` | `[DONE] [RM1222] Machin` |

Le marqueur écrit est toujours **`[A TESTER]` en ASCII** (la variante accentuée `[À TESTER]` est acceptée en lecture, si un titre a été tapé à la main) : c'est le jeton que karl-agent relit dans le transcript, il doit être stable des deux côtés. Le test `scripts/test_session_mark.py` vérifie cet aller-retour skill ⇄ karl-agent.

Seuls les marqueurs **en tête** sont traités : un `[WIP]` en fin de titre est du texte, pas un statut.

La même règle s'applique au titre passé via `--title`, pour qu'un statut collé par mégarde ne s'empile pas.

## Comportement de l'agent

L'agent exécute le script, récupère la ligne `/rename …`, puis **demande à l'utilisateur de la coller** (l'agent ne peut pas taper une slash-command natif lui-même). Format non documenté (CLI v2.1.x) → si `/rename` change de syntaxe, adapter.

Le skill **ne quitte pas** Claude Code (pas de commande d'arrêt programmatique). Après un `done` appliqué, indiquer de taper `exit` ou Ctrl+D.

## Invocation

```bash
python3 ~/.claude/skills/session-mark/mark-session.py done
python3 ~/.claude/skills/session-mark/mark-session.py a-tester
python3 ~/.claude/skills/session-mark/mark-session.py wip
python3 ~/.claude/skills/session-mark/mark-session.py clear
# Titre de base imposé (sinon réutilise le titre courant en retirant tout marqueur) :
python3 ~/.claude/skills/session-mark/mark-session.py done --title "Connecteur SMS Free Mobile"
```

Le script imprime une ligne **`/rename <nouveau titre>`** à coller. Aliases de statut : `todo` et `afinir` = `wip` ; `atester`, `tester` et `test` = `a-tester`.

## Après exécution

Relayer la ligne à l'utilisateur, p. ex. :
> Pour appliquer, colle : `/rename [DONE] Connecteur SMS Free Mobile`

Puis, pour un `done` :
> Une fois renommée, tape `exit` (ou Ctrl+D) pour fermer — la session reste reprenable via `claude --resume`.

Pour un `a-tester`, même chose, mais dire ce qui change : la session peut être fermée, elle **reste dans le jeu** et **ne se relancera pas** toute seule ; elle est là pour être rouverte si le test remonte quelque chose.
