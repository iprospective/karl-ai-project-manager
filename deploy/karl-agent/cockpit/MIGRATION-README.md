# Carte de migration du cockpit — mode d'emploi

Deux fichiers, générés puis relus à la main, qui pilotent la refonte RM2889
(cf. l'aspect `docs/cockpit-architecture.md`, § 15 et § 17.1).

## `MIGRATION-MAP.tsv` — où part chaque morceau

Une ligne par symbole d'`index.html` : fonction JS de premier niveau, règle CSS,
bloc HTML. Colonnes :

| Colonne | Sens |
|---|---|
| `symbole` | le nom tel qu'il est **aujourd'hui** dans `index.html` |
| `type` | `js` · `css` · `html` |
| `lot` | L0…L5 — l'ordre est celui du § 17.1, du plus froid au plus chaud |
| `domaine` | sessions, tickets, projets, terminal… |
| `couche` | `controller` · `service` · `model` · `view` · `component` · `style` |
| `cible` | le fichier où il atterrit |
| `routes` | les routes d'API que ce symbole appelle |
| `lignes` · `refs` | taille, et nombre d'appelants ailleurs dans le fichier |
| `tickets_90j` | **combien de tickets distincts** l'ont touché sur 90 jours |
| `ligne_source` | sa ligne actuelle |

`tickets_90j` est la colonne qui décide : c'est le nombre de réintégrations
qu'un lot aura à affronter. Elle est produite par
`scripts/pm-file-heatmap.py`, rejouable à tout moment.

**Règle de conduite : un lot déplace, il ne renomme pas.** Le `symbole` reste
identique de part et d'autre du déplacement — c'est ce qui permet de reporter
mécaniquement un développement concurrent parti de l'ancienne base.

## `MIGRATION-ROUTES.tsv` — la grammaire d'API cible

Une ligne par route appelée par le front (86 aujourd'hui), avec la route
normalisée `/api/<type>/<action>` visée au § 10.4. Les routes actuelles restent
servies en **alias** pendant toute la migration ; leur retrait est le lot L7.

Deux routes qui tombent sur la même cible signalent un doublon hérité à trancher
(`/file` et `/fs/file`, par exemple).

## Réintégrer un développement parti de l'ancienne base

1. `git diff origin/dev...<branche> -- deploy/karl-agent/cockpit/index.html`
2. pour chaque *hunk*, lire le symbole englobant, et chercher sa `cible` ici
3. appliquer le diff dans le fichier cible

C'est ce que fera `pm-cockpit-remap` (à livrer avec L4, § 17.1). Tant qu'il
n'existe pas, la table se lit à la main — mais elle se lit.

## Comment les modules sont servis (constat L0)

`/static/<chemin>` sert **déjà** tout `.js` / `.css` / `.svg` situé sous le
dossier du cockpit, avec `ETag` + `Cache-Control: no-cache` et un garde-fou
anti-évasion (`_resolve_asset`). Les modules ES de `src/` sont donc servis
**sans aucune modification du serveur**, et un correctif est visible au simple
rechargement.

Corollaire qui a corrigé la carte : `.html` n'est **pas** dans la liste blanche
des types servis. Un gabarit n'est donc pas un fichier `.html` à charger, mais
un **module `.view.js`** qui exporte une fonction rendant un fragment — ce qui
est de toute façon la forme voulue au § 7 (une vue est une fonction pure du
ViewModel vers du HTML sûr).

## État d'avancement

| Domaine | Lot | Migré le | Où |
|---|---|---|---|
| mail (file de triage des emails) | L1 — pilote | 2026-09-04 | `models/mail/`, `services/mail.service.js`, `viewmodels/mail/`, `views/mail/`, `controllers/mail.controller.js` |
| git (journal, commit, diff de la session) | L4 | 2026-09-04 | `models/git/`, `services/git.service.js`, `viewmodels/git/`, `views/git/`, `controllers/git.controller.js` |
| dashboard (« ce qui requiert ton attention », dérives) | L4 | 2026-09-04 | `models/dashboard/`, `services/dashboard.service.js`, `viewmodels/dashboard/`, `views/dashboard/`, `controllers/dashboard.controller.js` |

Un domaine est « migré » quand plus une ligne de son JS ne reste dans
`index.html`, que son bloc HTML n'est plus qu'un hôte vide monté par `boot.js`,
et que ses tests historiques ont été portés sur les couches (mêmes garanties,
au bon étage).
