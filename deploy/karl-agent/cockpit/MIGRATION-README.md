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

## Deux ponts, pas un

`karlCall(domaine, fn, …)` rejoue un appel arrivé avant `karl:ready` et rend `undefined`
à une lecture trop tôt. Un pont qui doit rendre une **promesse** (`ensureResolved(rm).then(…)`)
ne peut pas se contenter de ça : `.then` sur `undefined` casse. D'où **`karlWhen(domaine)`**,
qui rend une promesse du domaine lui-même, résolue à `karl:ready` — le `.then` attend au lieu
de mourir. Règle : geste ou lecture tolérante → `karlCall` ; valeur asynchrone → `karlWhen`.

## Réintégrer un développement parti de l'ancienne base

1. `git diff origin/dev...<branche> -- deploy/karl-agent/cockpit/index.html`
2. pour chaque *hunk*, lire le symbole englobant, et chercher sa `cible` ici
3. appliquer le diff dans le fichier cible

C'est ce que fait **`scripts/pm-cockpit-remap.py <branche>`** : il rattache chaque
hunk à son symbole dans la pré-image de la branche, dit s'il est encore dans
`index.html` sur `dev` (merge normal) ou, sinon, dans quel fichier de `src/` le
reporter et si ce domaine est déjà migré. Sur les deux branches ouvertes au
2026-09-04 (RM2229, RM2808) : quatre symboles, tous encore dans `index.html`.

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
| projets (panneau de gauche « 📁 Projets ») | L4 | 2026-09-04 | `models/projects/`, `services/projects.service.js`, `viewmodels/projects/`, `views/projects/`, `controllers/projects.controller.js` — la fiche projet au centre reste à migrer |
| env (santé du poste, badge, verrous coffre/SSH) | L5 | 2026-09-04 | `models/env/`, `services/env.service.js`, `viewmodels/env/`, `views/env/`, `controllers/env.controller.js` |
| pmcmd (commandes PM, catalogue RM2209) | L5 | 2026-09-04 | `models/pmcmd/`, `services/pmcmd.service.js`, `viewmodels/pmcmd/`, `views/pmcmd/`, `controllers/pmcmd.controller.js` |
| settings (réglages whitelist RM2213, thème RM2386) | L5 | 2026-09-04 | `models/settings/`, `services/settings.service.js`, `viewmodels/settings/`, `views/settings/`, `controllers/settings.controller.js` |
| voice (mode voix, annonces, dictée, TTS/STT serveur ou navigateur) | L5 | 2026-09-04 | `models/voice/`, `services/voice.service.js`, `viewmodels/voice/`, `views/voice/`, `controllers/voice.controller.js` — moteurs du navigateur injectés par boot.js |
| **centre** — onglets, historique, titre, vues génériques (fichier, dossier, commit, email, client, conf), panneaux centraux, tableau de bord | cluster | 2026-09-04 | `models/center/`, `models/files/scope.js`, `viewmodels/center/`, `views/center/`, `controllers/center.controller.js` — les surfaces session / revue / fiche projet / nouveau ticket sont des **ponts enregistrés** par `boot.js` |
| nouveau ticket (formulaire pleine page RM2672/2726/2752) | surface du centre | 2026-09-05 | `models/tickets/newTicket.js`, `models/tickets/TicketsRepository.js`, `services/newticket.service.js`, `viewmodels/tickets/`, `views/tickets/NewTicket.view.js`, `controllers/newticket.controller.js` — **première surface enregistrée** auprès du routeur, remplaçant son pont |
| fiche projet (fiche, worklog projet, worktrees/fichiers, conf meta.yml — RM2353/2590/2531/2696) | surface du centre | 2026-09-05 | `models/projects/projectConfig.js`, `models/projects/ProjectRepository.js`, `services/project.service.js`, `viewmodels/projects/ProjectViewModels.js`, `views/projects/ProjectPane.view.js`, `controllers/project.controller.js` |
| file « à tester » (RM2210/2315/2588) | L3 | 2026-09-05 | `models/testqueue/`, `services/testqueue.service.js`, `viewmodels/testqueue/`, `views/testqueue/`, `controllers/testqueue.controller.js` — la revue lui emprunte ses gestes d'env par ponts |
| **modèle ticket** — résolution (TTL, dédup en vol), mergecheck, conso, sessions du ticket ; formats ; bannière git (RM2630/2763/2384/2373/2611/2818) | L3 (1/3 revue) | 2026-09-05 | `models/tickets/TicketRepository.js`, `models/tickets/ticketFormat.js`, `views/tickets/MergeBanner.view.js` — caches **partagés par référence** avec le monolithe jusqu'à L6 ; ponts `karlWhen` pour les promesses |

Un domaine est « migré » quand plus une ligne de son JS ne reste dans
`index.html`, que son bloc HTML n'est plus qu'un hôte vide monté par `boot.js`,
et que ses tests historiques ont été portés sur les couches (mêmes garanties,
au bon étage).

## Ce que la migration a appris sur la carte

**Les vues centrales ne sont pas un domaine L4.** `centerViewPane` / `centerViewLoad`
/ `openCenter*` sont le **routeur du centre** : ils ferment la revue, détachent la
session, ferment la fiche projet et le formulaire de ticket, écrivent dans les onglets
et le titre — et le harnais `test_cockpit_runtime.js` pilote `openCenterFile` *dans*
le script inline. La carte les rangeait en L4 par **position** dans le fichier ; leur
**couplage** est celui des onglets, de la revue et de l'attache (L2/L3). Ils migrent
avec eux, sous la forme d'un `center.controller` unique — **fait le 2026-09-04** : le
routeur est migré, les surfaces historiques lui sont enregistrées comme des ponts. Même sort pour la fiche
projet au centre et l'onglet fichiers, qui s'appuient dessus.

Conséquence pratique : la chaleur mesurée ordonne bien les domaines *autonomes*
(un panneau, un onglet, une modale) ; un symbole peu touché mais appelé de partout
n'est pas « froid », il est **structurel**.
