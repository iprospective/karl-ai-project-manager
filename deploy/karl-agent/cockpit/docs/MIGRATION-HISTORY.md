# Carte de migration du cockpit — historique (archivé le 2026-09-06, RM3009)

> **Document d'archive.** Il raconte comment le cockpit est passé du monolithe `index.html` à
> l'architecture 3.x (RM2889, lots L0→L8, puis RM3012/RM3010/RM3011/RM3000/RM3005). L'état
> **vivant** de l'architecture est dans [`../README.md`](../README.md) ; les fichiers
> `MIGRATION-MAP.tsv` et `MIGRATION-ROUTES.tsv` restent à la racine du cockpit parce que des
> outils les lisent encore (`scripts/cockpit-gen-endpoints.py`, `scripts/pm-cockpit-remap.py`,
> `test_cockpit_core.js`). Rien ici n'est à tenir à jour.


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

## Arborescence par module (RM3012, 2026-09-06)

Depuis RM3012, `src/` est organisé **par domaine**, plus par couche :

```
src/
  boot.js                      câblage : configuration, caches partagés, montage des modules, init
  core/                        socle : html (gabarit sûr), dom (mount/unmount), store, api, endpoints (routes nommées),
                               errors, markdown, version, Repository, Factory, EntityViewModel
  styles/                      _tokens.scss (palette/thème), _base.scss (socle), main.scss (ordre d'assemblage)
  modules/<domaine>/           un dossier par domaine, six pièces au plus, classées par SUFFIXE :
    <domaine>.js               modèle pur (fonctions sans DOM ni réseau)
    <Domaine>Repository.js     accès aux entités : routes nommées + store — le seul endroit qui voit core/api
    <domaine>.service.js       état et gestes du domaine, sans DOM
    <Domaine>ViewModel.js      ce que la vue présente (inerte)
    <Domaine>.view.js          gabarits `html` → fragments sûrs, gestes en data-action, aucun on*
    <domaine>.controller.js    montage sur les hôtes, délégation des gestes, API rendue à boot.js
    <domaine>.scss             le style du module, compilé dans cockpit.css
```

Les gardes d'imports (test core § 12) lisent la couche sur le suffixe : une vue n'importe ni service, ni dépôt, ni `core/api`, ni
ViewModel ; un ViewModel ni DOM ni service ; un modèle ou un dépôt ni vue ni contrôleur ni service ; un service ni DOM ni vue ;
un contrôleur jamais `core/api`. Modules transverses : `shell` (toast, liens cliquables, attache, commandes de la page), `ticket`
(modèle ticket partagé : résolution, formats, statuts, consignes, bannière git), `pm` (runner PM).

**Style.** `index.html` ne porte plus de `<style>` : il charge `/static/cockpit.css`, **généré** depuis `src/styles/main.scss` par
`npm run build:css` (dans `deploy/karl-agent/cockpit/tooling` ; `sass` est une dépendance de DÉVELOPPEMENT seulement — la page ne charge
rien de npm et ne demande aucune construction, `cockpit.css` est versionné). `main.scss` assemble `_tokens`, `_base` puis les modules
dans l'ordre de la feuille historique (la cascade compte). `cockpit.css` porte en tête l'empreinte de ses sources :
`test_cockpit_runtime.js` la recalcule et refuse un build périmé — **on ne modifie jamais `cockpit.css` à la main**.
`npm run watch:css` recompile en continu pendant le développement.

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
| **revue** — fiche 🧪 du ticket (en-tête, protocole, env de test, cohérence git, verdicts RM2786, actions PM), sessions du ticket + consignes (RM2726/2833/2873), alerte de doublon (RM2818), étiquettes (RM2832), menu et invites de statut (RM2888), gardes NORMS (checklist, merge gate) | surface du centre (2/3 revue) | 2026-09-05 | `models/tickets/ticketStatus.js`, `models/tickets/prompts.js`, `services/review.service.js`, `viewmodels/tickets/ReviewViewModel.js`, `views/tickets/Review.view.js`, `controllers/review.controller.js` — l'encart ℹ de droite (`renderMeta`, 3/3) reste au monolithe et reçoit le ticket courant via `setMetaTicket` ; `filterByTag` (recherche) reste legacy |
| **encart ℹ** — colonne de droite « infos » (session : libellé RM2894, registre RM2166/2605, conso live RM2373/2609/2611, récap presse-papier) et « tickets » (sous-onglet par ticket de la session RM2673, facettes détail / description / historique / conso / workspace RM2579/2797/2806, client-projet RM2614, pastille de phase RM2888) | surface de droite (3/3 revue) | 2026-09-05 | `models/tickets/ticketMeta.js`, `models/tickets/TicketMetaRepository.js`, `services/meta.service.js`, `viewmodels/tickets/MetaViewModel.js`, `views/tickets/Meta.view.js`, `controllers/meta.controller.js` — le ticket affiché et sa facette (ex-`metaTicket`/`metaFacet`) vivent dans le contrôleur ; ponts `renderMeta`/`showTicket`/`setMetaTicket`/`metaTicketIs`/`refreshWorkspace` ; le bouton « 🗂 fiche » du brief projet, mort depuis RM2579 (`showProject` n'existait plus), rouvre la fiche projet migrée ; `tmuxName` reste aussi dans le monolithe (sessions, L2) |
| **panneau 🎫 tickets** — triage ROI (RM1952/2830/2831 : filtres client/projet/étiquette/validation, lot = liste affichée), carte « Tickets ouverts » (RM2606/2637/2757/2883 : persistée, repliée par défaut, filtres client et famille de statut), infobulles d'un RM-id (RM2619 : briefs groupés en une requête, mis à jour en place) | L3 | 2026-09-05 | `models/tickets/{openedTickets,triage,briefs}.js`, `models/tickets/TicketsPanelRepository.js`, `services/tickets.service.js`, `viewmodels/tickets/TicketsPanelViewModel.js`, `views/tickets/TicketsPanel.view.js`, `controllers/tickets.controller.js` — la liste ouverte, le classement et le cache des briefs vivent dans le contrôleur ; ponts `noteOpenedTicket`/`openedForget`/`openedFilter`/`renderOpened`/`tipAttr`/`loadTriage`/`renderTriage`/`triageVisibleRows` ; le `<details>` et ses selects restent l'hôte HTML (sans `on*`), le « ? » d'aide reste legacy |
| **markdown, glossaires, aide, modale doc** — rendu markdown sûr (RM2309), glossaire du jargon (RM2623/2634 : entrées, index, recherche, soulignage inline, catégories), glossaire de projet (RM2675), aide intégrée (RM2593 : sommaire, pages, liens internes), modale doc (RM2759 : document rendu, envoi au centre) | L5 + socle | 2026-09-05 | `core/markdown.js`, `models/glossary/glossary.js`, `models/glossary/HelpRepository.js`, `services/help.service.js`, `viewmodels/glossary/GlossaryViewModel.js`, `views/glossary/Doc.view.js`, `controllers/doc.controller.js` — `#docmodal` reste l'hôte (les plans de lot du worklog y écrivent encore et la referment par le pont `closeDoc`) ; ponts `glossify` (pour `linkify`), `glossaireRows`/`glossaireFiltre` (vocabulaire des fichiers), `openDoc`/`closeDoc`/`docToCenter`/`openHelp`/`openGlossary` ; `mdToHtml` n'a plus aucun appelant dans le monolithe (boot.js l'importe) |
| **outline de conversation** — onglet 🗺 de la colonne de droite (RM2330 sauts ▲▼ moi, RM2466 chargement sans réentrance, RM2549 décor sur trois canaux + question suivante sans réponse + /scroll gardé pour les transcripts, RM2596 recherche surlignée + lecture inline en accordéon + copie, RM2601 filtres tout/moi/questions) | L5 | 2026-09-05 | `models/outline/{outline,OutlineRepository}.js`, `services/outline.service.js`, `viewmodels/outline/OutlineViewModel.js`, `views/outline/Outline.view.js` (`hlq` y vit), `controllers/outline.controller.js` — position, recherche, filtre et entrée dépliée vivent dans le contrôleur ; la barre `.outnav` reste l'hôte HTML sans `on*` ; ponts `loadOutline`/`renderOutline`/`closeOutlineRead`/`outlineReset`/`jumpUser`/`scrollLive` (attache, colonne, raccourcis Alt+↑/↓/Fin) ; `linkify`, `markPillHtml`, `openFileRef` restent au monolithe (worklog, sessions, fichiers) |
| **reprendre une session** — carte du lanceur (RM1939 reprise native, RM2834 client → projets cohérents, RM2991 recherche amortie + opt-in transcript + libellés de tickets + archivées non reprenables, RM2144 ancrage, RM2418 déplacement gardé, RM2396 panneau rechargé après reprise, RM2539 moteurs depuis la conf) | L2 | 2026-09-05 | `models/sessions/{resume,ResumeRepository}.js`, `services/resume.service.js`, `viewmodels/sessions/ResumeViewModel.js`, `views/sessions/Resume.view.js`, `controllers/resume.controller.js` — la carte `#rescard` reste l'hôte HTML sans `on*` ; pont `loadResumable` (panneau) ; le lanceur lui passe les projets (`setProjects`), le contexte client (`applyClientContext`) et les moteurs (`setEngines`) par `karlCall` ; `markPillHtml`, `warnSpawn`, `refreshSessions`, `attach` restent prêtés |
| **recherche de tickets** — carte du panneau 🎫 (RM2770 multi-source local/Redmine/les deux, panne Redmine à côté des résultats, absents signalés et ouverts chez Redmine ; RM2639 filtre client > contexte ; RM2830 étiquettes en usage partagées avec le triage ; RM2832 clic étiquette ; RM2795 marque) | L3 | 2026-09-05 | `models/tickets/{search,SearchRepository}.js`, `services/search.service.js`, `viewmodels/tickets/SearchViewModel.js`, `views/tickets/Search.view.js`, `controllers/search.controller.js` — la carte `#searchcard` reste l'hôte sans `on*` ; pont `search()` ; le lanceur lui parle par `karlCall` (`init`, `fillProjects`, `loadTags`, `refreshIfQuery`, `setTag`) ; la route `/tickets/search` (RM2770) manquait à `MIGRATION-ROUTES.tsv` → ajoutée, `endpoints.js` régénéré (94 routes) |
| **explorateur de fichiers** — onglet 📂 de la colonne de droite (RM2586 fil d'ariane, RM2622 doc ≠ worktree, RM2659 racines groupées par projet + barre conditionnelle, RM2673 repli sur le projet courant avec provenance + rechargement au seul changement de contexte, RM2675 vocabulaire filtrable, RM2759 fichier/dossier/commit au centre avec portée, RM2861 rendu commun, RM2596 référence de fichier) | L4 | 2026-09-05 | `models/files/{explorer,FilesRepository}.js` (+ `scope.js` existant), `services/files.service.js`, `viewmodels/files/FilesViewModel.js`, `views/files/Files.view.js`, `controllers/files.controller.js` — données du contexte et navigation vivent dans le service ; ponts `filesEnsure`/`loadFiles`/`filesReset`/`openFileRef` ; le routeur lit la portée par `files.data()` (plus de `lexical(filesData)`) |
| **worklog de la session et lots** — onglet 🗒 de la colonne de droite (RM2466 notifications/sections, RM2581 fraîcheur, RM2584/2935 documents cliquables, RM2605/2799 numéro cliquable, RM2610 sous-onglets, RM2695 avancement, RM2716/2719/2720/2786 lots traiter/à tester/analyser/merger/fermer avec récapitulatif dry_run et portée par points, RM2723 ligne de MR partagée avec la fiche projet, RM2796 dérive, RM2798 groupes, RM2801 étape de MR, RM2823/2831 embarquer un lot dans une session neuve (chemin partagé avec le triage), RM2888 menu de statut) | L3 | 2026-09-05 | `models/worklog/{worklog,WorklogRepository}.js`, `services/worklog.service.js`, `viewmodels/worklog/WorklogViewModel.js`, `views/worklog/Worklog.view.js`, `controllers/worklog.controller.js` — worklog, sélection et plans vivent dans le service ; les écrans de lot passent par la modale doc (`openCustom`) ; ponts `loadWorklog`/`renderWorklog` ; la pile /refresh pousse le bloc par `setFromRefresh` ; `pendStaleSet`/`loadPending` restent au monolithe (sessions) |
| **disposition des colonnes** — colonne de droite à onglets (RM2466 volet 3 : un seul actif, re-cliquer replie ; RM2952 : repli voulu respecté par les ouvertures automatiques), démarrage paramétrable (RM2579), repli de la colonne gauche, largeur réglable à la poignée et réinitialisation (RM2599/2952) | socle | 2026-09-05 | `models/layout/panels.js` (TABS, réducteur, clampWidth), `services/layout.service.js` (préférences de ce navigateur), `controllers/layout.controller.js` — ce qu'un onglet visible déclenche est prêté par boot.js (`onApply` : outline, encart, worklog, fichiers, git) ; ponts `showRight`/`collapseRight`/`rightVisible` (attache, pile /refresh) ; `layout.restore()` au boot, avant `center.restore()` ; les contrôleurs migrés lisent `layout.rightVisible` directement |
| **lanceur** — carte « Lancer une session » (§1 résolution amortie du RM, RM1941 modèles par moteur avec prescription du ticket, RM2873 consigne partagée avec la fiche, RM2818 garde de 2e session, spawn + suites), saisie éclair d'un ticket (§8, types/priorités depuis la config), contexte client (RM2639 : pré-filtre de ce navigateur qui prévient tickets ouverts, reprise, recherche, projets, sessions), réouverture d'un ticket fermé (RM2285), aller au ticket (RM2173/2427) | L3 | 2026-09-05 | `models/launcher/{launcher,LauncherRepository}.js`, `services/launcher.service.js`, `viewmodels/launcher/LauncherViewModel.js`, `views/launcher/Launcher.view.js`, `controllers/launcher.controller.js` — hôtes `#launchcard`, `#ntcard`, `#clientctx` sans `on*` ; ponts `resolveRm`/`gotoTicket`/`reopenTicket`/`setClientContext` ; la liste des sessions (legacy) lit `clientContext` tenu à jour par `setClientCtxLocal` ; `sessionInClient` et `renderClientCtxBanner` restent au monolithe (sessions) ; les autres contrôleurs lisent `launcher.projects()` / `launcher.clientContext()` |
| **actions de session** — chips en un clic (RM1893 §2, catalogue `CFG.actions`), actions PM d'un ticket (RM2720 : cible = session du ticket, sinon repli dit et confirmé, `{id}` = le ticket), moniteurs et disposition des panes (§3), menu de disposition + fermer (RM2515), fermeture d'une session | L2 | 2026-09-05 | `models/sessions/{actions,SessionActionsRepository}.js`, `services/actions.service.js`, `viewmodels/sessions/ActionsViewModel.js`, `views/sessions/Actions.view.js`, `controllers/actions.controller.js` — hôtes `#chipsrow` et `#tabactions` sans `on*` ; ponts `renderChips`/`kill`/`openDispositionMenu` (attache, tuiles de la liste des sessions) ; la revue lit `actions.pmTarget`/`sendPmAction` ; `approve`/`approveAll`/`setAutoYes` restent au monolithe (sessions) |
| **terminal et composer** — terminal de la session attachée (RM2522 client maison opt-in `karl_xterm=1`, sinon iframe ttyd ; RM2561 WebSocket même-origine `/ttyd` ; RM2700 cookie de gate depuis le token ; RM2807 sonde mémoire opt-in), composer (RM2527 : Entrée envoie, garde d'état attention/choice avec forçage explicite, historique par session et navigateur, ↑/↓, Échap), copies (RM2168/2631 : 300 lignes, copie tmux, replis presse-papier → execCommand → modale texte) | L2 | 2026-09-05 | `models/terminal/{terminal,TerminalRepository}.js`, `services/terminal.service.js`, `viewmodels/terminal/ComposerViewModel.js`, `views/terminal/Composer.view.js`, `controllers/terminal.controller.js` — hôtes `#termhost`, `#term`, `#composer` sans `on*` ; ponts `mountTerm`/`unmountTerm`/`composerRefresh`/`showCaptureModal` (attache, détache, pile /refresh, captures) ; la modale doc gagne `openPlain` (texte brut) ; `layout.onResized` et la voix (`clip`) lisent le contrôleur |
| **liste des sessions** — panneau « en cours » (RM2140/2283 groupes client/projet + compteurs, RM2344 ordre stable / tri dynamique opt-in, RM2346 bandeau « à traiter » + gel pendant l'interaction, RM2427/2439/2442/2451/2949 tuiles grises, RM2445/2537 vivantes hors jeu rangées par chantier et repliées, RM2448 pli persisté + mode sélection, RM2515 disposition, RM2598 question sans réponse, RM2639 contexte client + bannière, RM2673 ⊖ ⟳ selon `setWritable`, RM2787/2793 silence nommé, RM2210 revues ouvertes, RM2795 marque), raccourcis « ✔ Oui » / « ✔ tout » / auto-oui (RM2302/2327/2332/2699), titre de la session attachée (RM2283) et en-tête droit (RM2894) | L2 | 2026-09-05 | `models/sessions/{sessions,SessionsRepository}.js`, `services/sessions.service.js`, `viewmodels/sessions/SessionsViewModel.js`, `views/sessions/Sessions.view.js`, `controllers/sessions.controller.js` — hôtes `#runlist`, `#hcnt`, `#ln-count`/`#ln-att`, `#yesall`/`#yesatt`/`#yesbtn`/`#autoyes`, `#curtitle`, `#rtitle`, `#dynsort` sans `on*` ; `sessCache` reste au monolithe et est PARTAGÉ par référence (l'encart, le worklog, la voix… le lisent) ; ponts `renderSessions` (la pile /refresh livre le bloc et lit les compteurs pour sa cadence RM2613), `orderedSessions` (les jeux lisent les sessions AFFICHÉES, RM2439), `restartTip` (liste des entrées) ; les jeux (barre, `setWritable`/`setLabel`, ⊖ ⟳ relance, sélection `selMode`/`selected`) restent au monolithe et sont prêtés ; `pollDelay`/`pendStaleSet`/`hotSessions` restent avec la pile /refresh ; `effDisposition` est importé du modèle par boot.js (revue, modèle ticket) ; correctif de passage : `sessionInClient` reçoit désormais l'entrée résolue de la session (l'original lui passait tout le cache, le repli par résolution était donc inopérant) |
| **jeux de sessions** — barre du panneau « en cours » (RM2442/2445/2446/2452/2954 sélecteur vues · clients · jeux avec courant SERVEUR, RM2741 ＋ jeu unifié, 🗑, RM2448 sélection, RM2449 déplacer/copier, RM2439 💾 additif = l'affichage, RM2451/2741 ▶ relancer compté et chiffré), carte « Sessions enregistrées » (RM2955 jeu RÉGLÉ ≠ jeu courant, RM2452 règle éditable + figer, RM2427 entrées ⟳/⏸/⊖ avec annulation RM2443/2451, rétention, préférence de relance RM2395, versions RM2443, effacement), gestes prêtés à la liste (RM2446 ⊖ d'une vivante, RM2427/2536/2949 relance d'une tuile grise par identité, retrait, politique), avertissements de lancement RM2450/2951 | L2 | 2026-09-05 | `models/sessions/{sets,SetsRepository}.js`, `services/sets.service.js`, `viewmodels/sessions/SetsViewModel.js`, `views/sessions/Sets.view.js`, `controllers/sets.controller.js` — hôtes `#setbar` (nouvel id sur la barre) et `#sessions-set-card` sans `on*` (gestes en `data-action`) ; ponts `refreshSessionSets`/`refreshSessionSet`/`loadSessionSet` (init, PANEL_LOADERS) via `karlWhen` ; boot.js lit `sets`/`current`/`view`/`selection`/`label`/`writable` et les gestes ⊖ ⟳ relance directement sur le contrôleur (liste, fichiers, centre, reprise, worklog, revue, lanceur) ; deux redressements de passage : la règle éditée depuis la carte s'applique au jeu RÉGLÉ (l'original postait `currentSet`), et le 🗑 de la barre efface le jeu COURANT quand celui de la carte efface le jeu RÉGLÉ (l'original effaçait le réglé depuis les deux, contre son infobulle) |
| **pile /refresh, santé, MAJ core, panneaux gauche** — le tick unique du cockpit (RM2763 : un composite `GET /refresh?blocks=…` au rythme des sessions, hash par bloc, chaque bloc à sa période, un seul en vol et les includes rejoués ; RM2613 : cadence 3 s / 7 s selon les compteurs rendus, pause quand l'onglet est caché, rattrapage au retour), la pastille de santé (RM2889 : le « tmux ok » est dans 🩺 poste), « ⬆ MAJ dispo » (RM2571 : bouton + commande à lancer), les questions sans réponse (RM2598 `stale()`), les briefs semés en `partial` dans le cache de résolution partagé ; les panneaux commutables de la colonne gauche (RM2283/2760/2816 : actif persisté, chargeurs à la première activation) rejoignent le contrôleur de disposition | L2 | 2026-09-05 | `models/refresh/{refresh,RefreshRepository}.js`, `services/refresh.service.js`, `controllers/refresh.controller.js` ; `layout.controller` + `layout.service` étendus (`switchPanel`, `restorePanel`, hôtes `lnav`/`lbody`, `ctx.panelLoaders`) — hôtes `#health`, `#healthtxt`, `#updbtn`, `.lnav button[data-panel]` sans `on*` ; les blocs reçus sont livrés aux domaines par boot.js (`onSessions` → compteurs → cadence, `onWorklog`, `onDashboard`, `onEnv`) ; ponts `refreshSessions`/`refreshHealth` (attache, login), `tickSessions` (premier tick depuis l'init, une fois CFG et le jeton connus — le module démarre AVANT la config, d'où ce déclencheur gardé côté monolithe), `switchPanel` (attache, filtre par étiquette, init) ; l'init n'appelle plus `refreshHealth`/`loadPending`/`refreshCoreUpdate` (le premier tick porte tous les blocs) |
| **authentification** — écran de login plein-cadre (RM2334 : identifiants → jeton d'appareil, jamais de mot de passe stocké ; jeton partagé historique), cadenas de l'en-tête, carte « Authentification » (session, appareils : révoquer / celui-ci = déconnexion), carte « Utilisateurs » (superadmin : créer, désactiver/réactiver, mot de passe, supprimer), whoami sur session inconnue, 401 → l'écran revient | L0 | 2026-09-05 | `models/auth/{auth,AuthRepository}.js`, `services/auth.service.js`, `views/auth/Auth.view.js`, `controllers/auth.controller.js` — hôtes `#authgate` (avec `#auth-user`/`#auth-pass`/`#gate-err`/`#token`), `#authcard`, `#userscard`, `#lock` sans `on*` ; le monolithe garde `token()` (lu par son transport historique et l'init) et le pont `authBoot` (appelé par l'init une fois CFG connu) ; le terminal lit le jeton sur le contrôleur ; la connexion relance santé + sessions (pile /refresh) et ramène au panneau « en cours » |
| **L6 — coquille et extinction des ponts** — le toast (simple, erreur, avec action RM2451), les références cliquables (RM2585 `titleLink`, RM2596 `linkify`, RM2718 pastille, RM2623 glossaire : un écouteur en CAPTURE sur le document, le clic ne remonte jamais à la tuile), le runner PM partagé, l'attache/détache (RM2759/2816/2353/2672/2466/2173/2330/2602/2673/1893/2283/2697 + raccourcis RM2330/2527), les boutons statiques de la page (`data-cmd` → carte de gestes) et l'init (config, thème, auth, moteurs, panneaux, premier tick) ; le `<script>` inline principal est SUPPRIMÉ (reste le boot de thème, avant le premier paint), plus aucun `on*` dans la page, plus aucun `karlCall`/`legacy`/`lexical` ; CFG et les caches partagés vivent dans boot.js | L6 | 2026-09-05 | `controllers/{notify,links,attach,commands}.controller.js`, `views/common/Links.view.js`, `models/pm/PmRepository.js`, `services/pm.service.js`, `boot.js` (config, caches, init) — tests `test_cockpit_shell.js`, `test_cockpit_runtime.js` réécrit (un seul inline, tous les modules importables, imports de boot.js résolus) ; `window.karl` reste exposé pour la console (`karl.stats()`) et l'évènement `karl:ready` est conservé. Correctif de passage : `byId` était déclaré APRÈS son premier usage dans boot.js (TDZ au chargement du module, depuis le lot disposition) — désormais déclaré en tête |
| **L7 — bascule des routes** — `route()` rend désormais la CIBLE `/api/<type>/<action>` pour les 94 routes ; le générateur `scripts/cockpit-gen-endpoints.py` produit aussi `scripts/karl_api_routes.py` (alias cible → chemin historique, suffixe d'identifiant reporté, query string conservée) et `karl-agent.py` pose `api_alias` à l'entrée de GET/POST/PUT/DELETE ; les chemins historiques restent servis tels quels pour les autres clients (scripts, app mobile RM2331) — leur retrait est une décision à part | L7 | 2026-09-05 | `src/core/endpoints.js` (régénéré), `scripts/karl_api_routes.py` (généré), `scripts/karl-agent.py` (4 lignes + import) — **restart de karl-agent requis** ; test core : chaque cible a son alias, aligné sur le TSV |
| **L8 — version 3.0.0** — refonte CSMV achevée : plus de script inline, routes `/api/…`, 33 suites | L8 | 2026-09-05 | `src/core/version.js` (`VERSION`), `karl.version`, `<meta name="karl-cockpit-version">` dans la page — `test_cockpit_runtime.js` vérifie que les deux coïncident |
| **hotfix 2026-09-06** — page figée à « chargement… » pour un utilisateur revenu : `TicketsPanelRepository` gardait `setTimeout` DÉTACHÉ (`timers = { set: setTimeout }`) et l'appelait comme méthode → « Illegal invocation » dans tout navigateur (pas sous node) au restaurer d'un onglet épinglé (revue) → `center.restore()` levait, l'init de boot.js n'était jamais atteinte. Correctifs : timer enveloppé ; chaque étape de restauration et d'init isolée (`safe`) ; garde statique dans le test core (aucune référence détachée à setTimeout/fetch…) ; **`test_cockpit_browser.js`** (Playwright optionnel, `KARL_PLAYWRIGHT_DIR`) charge la page dans Chromium/Firefox avec un stockage semé et exige zéro erreur de page + init jusqu'au premier tick — à lancer avant toute MEP du front | hotfix | 2026-09-06 | `src/models/tickets/TicketsPanelRepository.js`, `src/boot.js`, `test_cockpit_core.js`, `test_cockpit_browser.js` |
| **RM3012 — structure par module + SCSS** — `src/modules/<domaine>/` (31 modules, 185 fichiers déplacés, imports réécrits automatiquement), gardes d'imports par suffixe, `src/styles/` + un `.scss` par module (25 fichiers) compilés en `cockpit.css` versionné (empreinte vérifiée), `index.html` sans `<style>` (698 lignes) ; rendu identique (438 règles, même multiensemble ; cascade contrôlée à spécificité égale ; test navigateur Chromium + Firefox) | RM3012 | 2026-09-06 | `src/modules/**`, `src/styles/**`, `cockpit.css`, `package.json` (sass dev), `scripts/css-stamp.js`, `test_cockpit_core.js` § 12, `test_cockpit_runtime.js` § 2b |
| **RM3011 — journal du cockpit** — `core/log.js` (tampon, mêmes sévérités/catégories que le serveur, abonnés, warn/error remontés par lots `POST /api/log/write` sans boucle, capture des exceptions non rattrapées et promesses rejetées ; `safe()` de boot.js y écrit), module `journal` (fusion serveur `GET /api/log/tail` relu par `since` + front, filtres sévérité × catégorie × texte persistés, suivi 5 s quand le panneau est visible, pause, copie, purge du front), bouton d'en-tête « 📜 journal » (`data-cmd="panel"`) avec badge des erreurs front non vues, panneau central `#cp-journal` enregistré au centre comme pm/réglages | RM3011 | 2026-09-06 | `src/core/log.js`, `src/modules/journal/*`, `boot.js`, `index.html`, centre (onglet `journal`) ; tests `test_cockpit_journal.js`, navigateur (erreur injectée → journal + badge) |
| **RM3005 — tous les caches dans `core/store.js`** — `appStores()` définit les six stores nommés et bornés (`STORE_BOUNDS` : `ticket.resolve` 500/30 min, `session.registry` 300/10 min, `ticket.mergecheck`, `ticket.usage`, `ticket.sessions` 200/10 min, `ticket.transitions` 100/20 s) ; le TTL est la borne dure, la fraîcheur douce des dépôts passe par `store.age()`/`expire()` ; `TicketRepository` reçoit `{ stores }`, `boot.js` prête `stores.resolve`/`sess`/`usage` (plus de `caches` par référence) ; les contrôleurs lisent `get()` et **s'abonnent** (centre, encart, panneau tickets : un abonnement, plus de `.then(render)`), les fonctions pures reçoivent `store.view` (lecture indexée, lecture seule) ; `karl.stats()` compte tout ; garde core §14 : zéro `new Store`/`defineStore`/`caches` hors `core/store.js`. Front v3.1.0. | ✅ livré |
| **RM3000 — coquille ≤ 1 000 lignes, version** — CSS sorti (RM3012), `index.html` à 706 lignes ; `/health` porte `version` (lue dans `src/core/version.js`, source unique) ; pied de page « cockpit vX » avec l'écart serveur ≠ front signalé (cache périmé, déploiement partiel) | RM3000 | 2026-09-06 | `scripts/karl-agent.py` (`_cockpit_version`), `index.html` (footer), `refresh.js` (`versionMismatch`), `refresh.controller.js`, `boot.js`, `_base.scss` |

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
