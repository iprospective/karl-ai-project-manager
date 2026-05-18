# TODO 008 — Nommage explicite des users Redmine dans `.env` + sélection dynamique côté scripts

| | |
|---|---|
| **Statut** | `pending` |
| **Priorité** | `#priority:high` |
| **Tags** | `#user-request` `#redmine` `#agents` `#scripts` |
| **Origine** | Demande user — 2026-05-15 (suite à la refonte multi-user de `.env`) |
| **Créé** | 2026-05-15 |
| **Ticket Redmine** | À créer dans le projet `pm-ai-agents` quand cette TODO est attaquée |

## Contexte

`.env` a été refait avec une structure multi-user pour distinguer la clé API de
l'orchestrateur de celle de l'agent chef de projet (et préparer l'ajout d'autres
agents avec leurs propres comptes Redmine) :

```
# État actuel (2026-05-15) — placeholder names
REDMINE_USER_MAIN_NAME=karl
REDMINE_USER_MAIN_API_KEY=...
REDMINE_USER_MAIN_OTP=...
REDMINE_USER_PJ1_NAME=claude-chefproj-1
REDMINE_USER_PJ1_API_KEY=...
```

Deux problèmes :

1. **Nommage opaque** : `MAIN` et `PJ1` n'évoquent pas le rôle de chaque compte.
   `MAIN` est en fait le compte de l'orchestrateur (`karl`), `PJ1` celui d'un
   agent chef de projet (`claude-chefproj-1`). Le suffixe `_NAME` devient
   redondant si la variable porte déjà le nom.

2. **Scripts non adaptés** : tous les scripts utilisant Redmine lisent encore
   `REDMINE_API_KEY` (variable simple) — la clé n'existe plus dans `.env`, donc
   les scripts plantent. Cf. test `python3 -c "..."` dans la discussion qui a
   échoué sur `KeyError: 'REDMINE_API_KEY'`.

## Décision

Nommer les variables par le **nom Redmine du compte** (pas par le rôle, qui
peut évoluer) :

```
# Cible
REDMINE_USER_KARL_API_KEY=...          # orchestrateur (rôle principal)
REDMINE_USER_KARL_OTP=...
REDMINE_USER_CHEFPROJ1_API_KEY=...     # agent chef de projet 1
# Plus tard : REDMINE_USER_<role-ou-nom>_API_KEY pour chaque agent
```

Le `_NAME` disparaît : il EST dans le nom de la variable.

Le **rôle** (orchestrateur, chef-projet, worker-dev, …) est résolu côté
script via une variable d'orientation, par exemple :
```
REDMINE_USER_ORCHESTRATEUR=karl
REDMINE_USER_CHEFPROJ1=chefproj1
```
ou via une table de mapping dans `pm.config.yml` :
```yaml
agents:
  orchestrateur:    karl
  chef-projet-1:    chefproj1
```

À discuter / arbitrer au moment de l'implémentation.

## Scripts à adapter

Tous lisent actuellement `os.environ.get("REDMINE_API_KEY")` :

- `scripts/redmine-fetch-task.py` (l.264-266)
- `scripts/redmine-fetch-updates.py` (l.131-132)
- `scripts/redmine-post-note.py` (l.90-91)
- `scripts/pm-project-bootstrap.py` (l.298-299)
- `scripts/redmine-test.py` (l.~64)

Chaque script doit :
- Soit prendre un `--as <agent-name>` en argument (sélection explicite)
- Soit déduire le user à partir du rôle déclaré dans la tâche (`assigned_to`
  côté MD)
- Soit utiliser un défaut configuré dans `pm.config.yml`

## Critères d'acceptation

- [ ] `.env` utilise des noms parlants (`REDMINE_USER_KARL_*`, `REDMINE_USER_CHEFPROJ1_*`)
- [ ] `.env.example` mis à jour
- [ ] Tous les scripts Redmine adaptés (sélection de clé via convention claire)
- [ ] `scripts/pm_paths.py` peut exposer `cfg.redmine_key(agent_name=...)` si
      pertinent, ou un helper séparé
- [ ] Aucun script ne plante avec le nouveau `.env`
- [ ] La doc (NORMS § Configuration globale, README, agents) reflète le mapping
- [ ] Convention NORMS pour déterminer **quel user** est utilisé selon le rôle
      de l'agent qui exécute le script

## Dépendances

- **Bloque** : exécution de tout script Redmine (urgent — l'état actuel laisse
  les scripts cassés)
- **Bloqué par** : rien
- **Co-bénéfice** : nettoyer le `OTP` (à stocker plutôt dans Vaultwarden ?)

## Journal

- **2026-05-15** : TODO créée. Origine : suite à la mise en place de la structure
  multi-user de `.env` par l'autre agent, l'utilisateur a explicité que
  `MAIN`/`PJ1` étaient des placeholders pas clairs et qu'il faudrait des noms
  réels (`karl`, `chefproj1`). Tracking ici pour décider une convention propre
  avant d'attaquer.
