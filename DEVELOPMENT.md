# DEVELOPMENT — point d'entrée développeur

Orientation pour développer **le système PM lui-même** (ce repo). Ce fichier
**relie** la doc existante et n'en recopie pas le détail — il pointe les sources
vivantes. Pour l'usage courant (créer entité/projet/tâche, structure du repo,
onboarding agent), voir d'abord [README.md](README.md).

## Où lire quoi

| Besoin | Source |
|---|---|
| Structure du repo, démarrage | [README.md](README.md) |
| Normes runtime (déclencheurs + tripwires) | `norms/src/NORMS-KERNEL.md` (KERNEL) |
| Normes complètes (généré) | `norms/NORMS.md` — **ne pas éditer** |
| Flux nominaux + inventaire d'outils (généré) | `norms/CHEATSHEET.md` |
| « NORMS de NORMS » (comment écrire une norme) | `norms/MAINTAINING.md` |
| Décisions d'architecture | `docs/adr/`, `docs/cdc/` |
| Savoir technique par produit (Redmine, GitLab…) | `knowledge/INDEX.md` |

## Architecture (le récit)

- **Deux dépôts, deux rôles.** Le **code** (outillage `pm-*`, cockpit, normes)
  vit dans `ai-project-management` (GitLab id **79**). Les **données** (tâches,
  clients/projets) vivent dans un dépôt séparé (`$PROJECTS_PATH`, id **138**),
  résolu par `pm.config.yml`. Ne pas les confondre : un même hôte peut avoir
  plusieurs checkouts (ex. une copie **PROD** root-owned qui fait tourner le
  système, une copie **DEV** éditable).
- **Privilege separation (3 couches).** Le provisioning privilégié passe par un
  point d'entrée unique `bin/mmi-pm` (`core update`, doctor…) et un helper
  confiné `pm-env-helper` (NOPASSWD ciblé). Détail : `docs/cdc/*privsep*`,
  `docs/cdc/*mmi-pm-cli*`.
- **Cockpit / karl-agent.** Le service HTTP (loopback) est `scripts/karl-agent.py` ;
  `deploy/karl-agent/` porte l'UI `cockpit/` (servie **en même origine**), le vhost
  Apache HTTPS et les units systemd. Aide utilisateur intégrée :
  `deploy/karl-agent/cockpit/help/` (servie via `/help`). Tests UI sans navigateur :
  `deploy/karl-agent/cockpit/test_cockpit.js`.
- **Sessions tmux et cgroups (RM2690).** tmux crée une scope systemd par pane
  (`tmux-spawn-<uuid>.scope`, UUID aléatoire ⇒ pas de drop-in déclaratif) : le
  plafond mémoire se pose au spawn (`_apply_memory_limits`), jamais bloquant.
  Valeurs dans `pm.config.yml` (`sessions.memory_{high,max,swap}_gib`, éditables
  depuis le cockpit) ; `KARL_AGENT_MEM_HIGH` / `_MAX` / `_SWAP` du `.env`
  priment et figent le réglage. Piège : sur `swap`, `0` est un plafond réel
  (aucun swap, le défaut) et c'est `-1` qui lève la limite.
- **De l'email au ticket (chantier RM2666).** Quatre scripts, quatre gestes, aucune
  boîte noire : `karl-mail-fetch` relève la boîte IMAP de karl vers une **file de
  triage** locale (`$XDG_STATE_HOME/karl-agent/mail/`, **hors git** — c'est du courrier
  client) ; `karl-mail-route` propose client/projet avec une confiance et une source
  (fil `[RM<id>]`, table apprise `mail-routing.yml`, compte Redmine, `contacts[]`,
  indice) ; `karl-mail-draft` rédige (via `claude -p` sans outils, JSON strict) **puis
  crée à la validation humaine**. CDC : `docs/cdc-rm2666-emails-vers-tickets.md` côté
  données. Les contacts qui alimentent le routage se saisissent avec
  `pm-client-contact` (`meta.yml` du client). Côté cockpit, le panneau **📧 emails**
  (RM2671) ne fait que lire `/mail/queue` et déléguer aux scripts : aucune logique de
  triage n'est dupliquée dans l'UI.
- **Layout des workspaces de code (RM1993).** Un workspace de code = un dépôt
  **bare** `repos/<nom>.git` + des **worktrees** `envs/<nom>-rm<id>` (un par
  ticket). `pm-branch-start` crée le worktree, `pm-env-session`/`pm-cockpit-test-env`
  montent les environnements de test.

## Flux — cycle de vie d'un ticket

Statuts NORMS : `nouveau → en_cours → a_tester_dev | a_tester_demandeur → a_mep →
ferme`. **Redmine est le mutex** : l'assignation confère la propriété exclusive du
fichier MD. Chaque transition synchronise Redmine et journalise dans le `.log.md`.
Vue outillée : `norms/CHEATSHEET.md`.

## Contribuer — la boucle de dev

Branches protégées : **jamais de push direct sur `main`** (les commits partent
sur `dev`, puis MR/promote). Boucle type :

```bash
# 1. prendre un ticket (crée la branche + worktree, passe en_cours)
pm-branch-start.py <RM> --take --worktree --from origin/dev

# 2. coder dans le worktree envs/<repo>-rm<RM> ; tester
mmi-pm test                                        # TOUTE la suite (~10 s)
mmi-pm test vault session                          # ou seulement ce qu'on touche
node deploy/karl-agent/cockpit/test_cockpit.js     # si cockpit touché

# 3. livrer : MR vers dev, puis livraison outillée (statut + note + report)
pm-mr.py create <RM>
pm-task-deliver.py <RM> --check-all --protocol - --summary -

# 4. MEP : promotion dev→main (branche protégée) puis déploiement
pm-promote.py                 # ouvre + merge une MR dev→main
mmi-pm core update            # geste HUMAIN au terminal (sudo) : pull + restart

# 0 bis. NAISSANCE d'un dépôt (RM2640) — avant tout le reste, si le dépôt n'existe pas
pm-repo-new.py --path <groupe>/<nom> [--push-from <dépôt local>] [--porcelain]
#   groupe résolu par chemin EXACT, privé par défaut, protections via pm-protect,
#   remote posé en alias `gitlab:` (jamais HTTPS). --dry-run montre tout sans écrire.
```

**La suite de tests n'exige RIEN de l'environnement** (RM2749). `mmi-pm test`
purge au contraire les variables qui pointent le runtime (`PM_CORE_DIR`,
`PROJECTS_PATH`…) : chaque test se fabrique le core jetable dont il a besoin, via
`scripts/test_support.py`. C'est ce qui rend le verdict reproductible — avant,
trois tests tombaient avec `PM_CORE_DIR` exporté, cinq autres sans, et « la suite
passe » ne voulait rien dire tant qu'on ne précisait pas le shell. Deux
conséquences pratiques :

- un test qui n'y arrive qu'avec le `.env` canonique lit la configuration de
  PRODUCTION : ce n'est pas un test, c'est une inspection du poste ;
- `mmi-pm test --inherit` rejoue la suite dans le shell tel quel. Les deux
  verdicts doivent être identiques ; un écart est un défaut de test, pas un
  détail d'installation.

Un test sans matière à examiner sort en **77** (ignoré, avec sa raison) plutôt
que vert : une absence de preuve n'est pas une preuve.

**Docs vivantes (obligatoire à la livraison).** Toute MR qui change la surface met
à jour la doc concernée **dans la même MR** — voir la norme dédiée « Développement
du PM » (`norms/src/modules/governance.md`) : `Changelog.md`, `README.md`, aide
cockpit (`cockpit/help/`), et ce fichier.

## Anti-périmé

Aucune valeur qui rouille ici (version des normes, nombre d'outils, ports…) :
se référer aux **sources vivantes** — `norms/VERSION`, `scripts/` (inventaire réel),
le command-catalog du cockpit, `pm.config.yml`.
