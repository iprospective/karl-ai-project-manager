# Cockpit karl-agent — architecture du front (3.x)

Le cockpit est l'interface web de `scripts/karl-agent.py` : il supervise les sessions
d'agents, pilote le PM et porte la console de test/revue. Depuis la **3.0.0** (RM2889) c'est
un front en **modules ES sans build à l'exécution** : le navigateur charge `index.html`, qui
charge `src/boot.js`, qui importe les modules. Rien de npm n'arrive dans la page ; seul le CSS
est compilé (voir « Styles »). L'histoire de la migration est archivée dans
[`docs/MIGRATION-HISTORY.md`](docs/MIGRATION-HISTORY.md) ; ce fichier décrit l'état vivant.

## Arborescence

```
cockpit/
  index.html            coquille : balisage des panneaux, <link cockpit.css>, <script type=module boot.js>
  cockpit.css           GÉNÉRÉ depuis les .scss (versionné ; empreinte des sources vérifiée par les tests)
  src/
    boot.js             câblage : CFG, stores, montage des domaines, window.karl, init
    core/               socle sans DOM métier : html (gabarits sûrs), dom (mount/on, stats par module), store (LRU+TTL+abonnés),
                        probe (sonde mémoire), entities (registre des types, quatre niveaux), api (transport, 401),
                        endpoints (GÉNÉRÉ depuis MIGRATION-ROUTES.tsv),
                        errors, markdown, log (journal du front), version, Repository / Factory / EntityViewModel
    modules/<domaine>/  un dossier par domaine, une couche par SUFFIXE (voir ci-dessous)
    styles/             _tokens.scss (couleurs, thèmes), _base.scss, _entities.scss (niveaux .e-row/.e-card/.e-panel/.e-full), main.scss
  help/                 aide intégrée (markdown, servie par /help, bouton ❓)
  tooling/              outillage de DÉVELOPPEMENT seulement : package.json (sass), npm run build:css
  scripts/css-stamp.js  écrit l'empreinte des sources SCSS dans cockpit.css
  test_cockpit*.js      suites node (une par domaine + core, runtime, shell) ; test_cockpit_browser.js = Playwright
  MIGRATION-MAP.tsv · MIGRATION-ROUTES.tsv   cartes encore lues par des outils (remap, gen-endpoints, test core)
```

## Les couches d'un domaine, par suffixe

| Fichier | Rôle | N'a PAS le droit de voir |
|---|---|---|
| `<domaine>.js` | modèle : fonctions **pures**, testées sous node nu | le DOM, le réseau |
| `<Domaine>Repository.js` | accès aux routes nommées (`route("type.action")`), hydratation | dom, vues, contrôleurs, services, ViewModels |
| `<domaine>.service.js` | cas d'usage, état du domaine, aucun balisage | dom, vues, contrôleurs |
| `<Domaine>ViewModel.js` | ce que la vue affiche, calculé, inerte (`EntityViewModel`) | — |
| `<Domaine>.view.js` | gabarits `html\`…\`` (échappement par défaut, `raw()` explicite) ; gestes en `data-action` | — |
| `<domaine>.controller.js` | `mount<Domaine>(hosts, ctx)` : monte, délègue les événements, rend, `unmount()` | `core/api.js` (jamais d'appel réseau direct) |
| `<domaine>.scss` | styles du domaine, `@use` dans `styles/main.scss` | — |

La garde d'imports (`test_cockpit_core.js` § 12) vérifie ces interdits sur chaque `import`.

## Règles qui ne se discutent pas

- **Toute écriture HTML passe par `core/dom.js`** : `mount()` / `handle.update()` pour un hôte,
  `paint(el, frag)` / `append(el, frag)` pour un sous-élément (options d'un select, badge). Ils
  n'acceptent qu'un fragment sûr (`html\`…\``, `raw()`) ou le vide — une chaîne nue lève. `esc()` est
  un détail du gabarit, jamais appelé par une vue ; les attributs conditionnels passent par
  `attrs({...})`. Garde § 15.
- **Zéro `on*`** dans le balisage : un geste est un `data-action` (dans un domaine),
  `data-cmd` (menu/en-tête) ou `data-link` (références cliquables), attrapé par délégation
  sur l'hôte du contrôleur (`mount(el, frag, { events })`).
- **Tout ce qu'un domaine emprunte passe par `ctx`** (fonctions prêtées par `boot.js`),
  jamais par `window` ni par import d'un autre contrôleur. Les emprunts se lisent **à
  l'appel**, jamais au montage (l'ordre de montage ne doit pas compter).
- **Un cache = un store** de `core/store.js` (`appStores()` / `STORE_BOUNDS` : nommé,
  borné par `max`, TTL dur, `age()`/`expire()` pour la fraîcheur douce, `subscribe()` pour
  re-rendre, `view` pour les fonctions pures). Garde § 14 : aucun `new Store`/`defineStore`
  hors `core/store.js`, aucun objet de cache partagé.
- **Jamais une fonction native détachée** (`{ set: setTimeout }`) : « Illegal invocation »
  dans tout navigateur, invisible sous node. Envelopper (`(fn, ms) => setTimeout(fn, ms)`).
  Garde § 13 + test navigateur.
- **`configureApi` et les objets à getters** : conserver les descripteurs (`Object.assign`
  fige un getter — incident du 2026-09-05).
- **Helpers et `let` de module déclarés AVANT leur premier usage** (TDZ : ReferenceError
  silencieuse au chargement, page bloquée à « chargement… »).
- **Un `.then(render)` par requête en vol au plus** (fan-out 2^N, RM2807) — préférer un
  abonnement au store.
- Routes : jamais un chemin en dur, toujours `route("type.action")` ; une route nouvelle
  s'ajoute dans `MIGRATION-ROUTES.tsv` puis `python3 scripts/cockpit-gen-endpoints.py`
  (régénère `src/core/endpoints.js` **et** `scripts/karl_api_routes.py` côté serveur).

## Le canal de push (RM3006)

`modules/refresh/push.service.js` ouvre un EventSource sur `/api/session/events` avec les mêmes
specs `bloc:hash` que le tick (`RefreshService.pushSpecs`) ; les blocs poussés passent par
`RefreshService.ingest` — la même livraison que le tick, dédoublonnée par hash. Le tick reste
(`pollDelay(hot, pushAlive)` : 6 s / 30 s quand le canal est vivant) et réconcilie ; une coupure
laisse EventSource se reconnecter et rend au tick sa cadence. Les sujets sans bloc (`mail`,
`sets`) remontent par `ctx.onTopics`. Côté serveur : `_EventBus`, `_events_stream`,
`op_events_publish` dans `karl-agent.py` ; côté scripts : `pm_events.publish()`.
`karl.stats().push` dit s'il est vivant et ce qu'il porte.

## Le gabarit mobile (RM3003)

Pas un second cockpit : la même page, **disposée autrement**. `modules/layout/mobile.js` décide
(`detectLayout` : `?layout=mobile|desktop` dans l'URL, sinon la préférence `karlLayout`, sinon la
media query ≤ 820 px prêtée par `boot.js`) ; le contrôleur `layout` pose `html[data-layout]` et
`main[data-mpage]` (`left` panneaux · `center` onglets/terminal/vues · `right` colonne de droite) et
peint la barre du bas (`#mnav`, `Layout.view.js`). Tout le reste est du CSS (`layout.scss`, bloc
`html[data-layout="mobile"]`) : aucun contrôleur, ViewModel ou vue n'est rendu deux fois. Les
surfaces préviennent la disposition par deux hooks : `center.note()` → page centre, `showRight()` →
page droite, `switchPanel()` → page panneaux. Le test navigateur joue un viewport de 390 px.

## Le registre des types d'entités (RM3002)

`core/entities.js` connaît chaque **type** que le centre et les listes manipulent (session, review,
project, client, conf, file, dir, commit, mail, newticket, dash et les panneaux pm / settings /
journal / memory) : icône, libellé d'onglet, infobulle, titre d'erreur, comment l'ouvrir (une
recette qui parle à l'`api` que le centre prête), s'il est restaurable au démarrage, s'il est une
surface à fermer. **Plus aucun `kind === "…"` hors de ce fichier** (garde dans
`test_cockpit_entities.js`) : ajouter un type, c'est un `defineEntity()`.

Chaque ViewModel de type se **lie** au registre (`bindEntity("review", ReviewViewModel)`) et
décrit sa fiche par une seule `sections()` : `[{ id, title, body, summary, level, empty }]`. Les
**quatre niveaux** en sont des compositions (`renderEntity(vm, level)` / `entityLevels(type, e, ctx)`) :
`row` (icône, titre, sous-titre, pastilles), `card` (+ sections `summary`), `panel` (+ toutes les
sections courantes), `full` (+ celles marquées `level: "full"`). La convention CSS est unique et
préfixée par niveau (`styles/_entities.scss` : `.e-row`, `.e-card`, `.e-sec`, `.e-kv`…) — un type de
plus ne coûte aucune ligne de CSS, et aucune classe `.e-<type>` n'est admise. Les vues
spécialisées du bureau (tuile de session, fiche de revue, fiche projet) restent en place ; le
gabarit mobile (RM3003) et les nouvelles surfaces composent les niveaux.

## Ajouter un domaine

1. `src/modules/<domaine>/` avec au minimum `<domaine>.js`, `<Domaine>.view.js`,
   `<domaine>.controller.js` ; `Repository`/`service`/`ViewModel` dès qu'il y a du réseau,
   de l'état ou du calcul d'affichage.
2. Le balisage hôte dans `index.html` (ids stables) ; les gestes en `data-action`.
3. `<domaine>.scss` + `@use "../modules/<domaine>/<domaine>"` dans `src/styles/main.scss`,
   puis `cd tooling && npm run build:css` (commiter `cockpit.css`).
4. Dans `src/boot.js` : `const x = mount<Domaine>(byId(...), { …ctx prêté… })`, exposé
   dans `window.karl`, et si c'est un panneau central, une entrée `panels.<domaine>`.
5. `test_cockpit_<domaine>.js` : modèle pur, vue (XSS : `<script>` doit ressortir échappé),
   ViewModel, contrôleur avec un faux DOM (`fakeElement` des suites voisines), `unmount()`
   libère tout (`listenerCount === 0`).
6. Aide utilisateur : `help/<NN>-<domaine>.md` si une surface utilisateur apparaît ; et le
   `Changelog.md` du repo (contrat « docs vivantes », `norms/src/modules/governance.md`).
7. Si le domaine introduit un **type** ouvert au centre : `defineEntity()` dans `core/entities.js`,
   `bindEntity(type, ViewModel)` dans son ViewModel, `sections()` pour ses quatre niveaux.

## Styles

Sources : `src/styles/_tokens.scss` (variables CSS, thèmes clair/sombre via
`[data-theme]`), `_base.scss`, `main.scss` qui `@use` chaque `<domaine>.scss` dans l'ordre
de la feuille historique. `cd tooling && npm ci && npm run build:css` produit `cockpit.css`
et y écrit l'empreinte sha256 des sources ; `test_cockpit_runtime.js` § 2b refuse un build
périmé (la CI et la MEP n'ont pas de sass : le CSS compilé est versionné).

## Journal et version

- `src/core/log.js` : journal du front (mêmes sévérités et catégories que `scripts/pm_log.py`),
  `installGlobalCapture` attrape exceptions et promesses rejetées, warn/error partent en lots
  par `POST /api/log/write`. Panneau 📜 journal (`modules/journal`), badge d'en-tête.
- `src/core/version.js` : **source unique** de la version du front — bump à chaque
  livraison du front. `/health` la relit côté serveur, le pied de page l'affiche et
  `modules/refresh` prévient quand serveur ≠ front (cache navigateur ou déploiement partiel).
  `index.html` porte la même valeur dans `<meta name="karl-cockpit-version">`
  (`test_cockpit_runtime.js` vérifie la cohérence).

## Tests

```bash
cd deploy/karl-agent/cockpit
for t in test_cockpit*.js; do node "$t" || break; done      # 35 suites node, ~15 s, sans réseau
KARL_PLAYWRIGHT_DIR=/chemin/vers/node_modules KARL_BROWSERS=chromium,firefox \
  node test_cockpit_browser.js                              # AVANT une MEP du front
```

Le test navigateur sert la page depuis ce dossier (aucun karl-agent), sème le stockage d'un
utilisateur revenu (jeton, onglets épinglés, préférences) et exige : aucune erreur de page,
`window.karl` posé, init jusqu'au premier `/api/session/refresh`, écran de login (401), les six
stores nommés dans `karl.stats()`, une exception injectée qui tombe dans le journal. Sans
Playwright résolu, il se déclare ignoré et passe : c'est le complément des suites node, pas
leur remplaçant. Un `node_modules` contenant Playwright suffit (celui d'un projet voisin).

Diagnostic en production : `karl.stats()` (stores, DOM par module, dernier échantillon de la
sonde), la **sonde mémoire** (🔧 réglages → panneau 🧠 mémoire : `core/probe.js`, alertes « grimpe
sans redescendre », export JSON), `karl.log.entries()`, le panneau 📜 journal, le pied de page
(version).

## Coût de lecture par domaine (RM3008)

Objectif de la refonte : modifier une vue ne doit demander de lire que son domaine, sous
**15 000 tokens** (≈ 4 caractères par token), contre ~120 k avec le monolithe. La mesure vit
dans `scripts/cockpit-view-cost.py` (`--md` pour ce tableau, `--domain <d>` fichier par fichier,
`--check 15000` comme garde ; `core` figure dans le tableau mais pas dans la garde : c'est le
socle, pas un domaine). Instantané du 2026-09-06, à régénérer plutôt qu'à corriger à la main :

| domaine | total | vue | model | repository | service | viewmodel | view | controller | style | test |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| sets ⚠ | 23746 | 18158 | 2843 | 692 | 2054 | 1084 | 1755 | 3939 | 0 | 11381 |
| sessions ⚠ | 21584 | 16885 | 2443 | 227 | 768 | 2252 | 2050 | 2881 | 1262 | 9704 |
| worklog ⚠ | 20569 | 15735 | 2799 | 258 | 1035 | 1460 | 2679 | 3162 | 743 | 8436 |
| center ⚠ | 17020 | 13918 | 1910 | 525 | 0 | 1351 | 1808 | 4006 | 668 | 6754 |
| core ⚠ | 16570 | 6112 | 9941 | 518 | 0 | 537 | 0 | 0 | 0 | 5575 |
| meta ⚠ | 16161 | 13634 | 860 | 465 | 256 | 2656 | 2906 | 2052 | 948 | 6022 |
| tickets | 12478 | 9007 | 1779 | 545 | 596 | 651 | 866 | 2250 | 553 | 5240 |
| review | 12391 | 11708 | 0 | 0 | 683 | 1154 | 2268 | 3367 | 0 | 4920 |
| doc | 11518 | 5498 | 4451 | 245 | 224 | 402 | 312 | 1528 | 1101 | 3257 |
| files | 11497 | 8646 | 1735 | 288 | 761 | 973 | 1333 | 1558 | 68 | 4784 |
| projects | 10863 | 8931 | 717 | 680 | 423 | 1641 | 2833 | 2275 | 115 | 2183 |
| terminal | 8708 | 6481 | 768 | 269 | 360 | 173 | 141 | 2662 | 832 | 3505 |
| launcher | 8524 | 6957 | 811 | 281 | 381 | 228 | 191 | 2631 | 95 | 3909 |
| auth | 8326 | 6531 | 468 | 345 | 708 | 0 | 383 | 1891 | 277 | 4257 |
| outline | 8297 | 5910 | 836 | 238 | 377 | 477 | 447 | 1411 | 938 | 3576 |
| env | 8213 | 6293 | 560 | 223 | 350 | 774 | 1283 | 1068 | 790 | 3168 |
| journal | 7904 | 5850 | 540 | 229 | 745 | 434 | 626 | 1015 | 541 | 3776 |
| refresh | 7623 | 4933 | 1241 | 226 | 872 | 0 | 0 | 1082 | 353 | 3852 |
| resume | 7456 | 6011 | 709 | 221 | 407 | 465 | 413 | 1679 | 109 | 3454 |
| layout | 6828 | 4842 | 494 | 0 | 403 | 0 | 0 | 1617 | 1091 | 3226 |
| dashboard | 6773 | 4556 | 956 | 237 | 305 | 735 | 794 | 586 | 721 | 2442 |
| voice | 6709 | 4640 | 615 | 315 | 1140 | 313 | 625 | 1219 | 0 | 2484 |
| shell | 6513 | 6242 | 0 | 0 | 0 | 0 | 643 | 2017 | 271 | 3582 |
| mail | 6316 | 5182 | 366 | 331 | 437 | 605 | 1237 | 955 | 0 | 2386 |
| search | 6176 | 5013 | 656 | 193 | 152 | 389 | 270 | 1449 | 164 | 2907 |
| actions | 6106 | 4708 | 574 | 288 | 241 | 211 | 202 | 1571 | 296 | 2725 |
| testqueue | 5949 | 4582 | 787 | 139 | 442 | 309 | 965 | 1079 | 0 | 2231 |
| ticket | 5877 | 2245 | 1932 | 1458 | 0 | 0 | 178 | 0 | 243 | 2067 |
| git | 5240 | 4196 | 270 | 328 | 110 | 657 | 851 | 795 | 338 | 1895 |
| newticket | 4962 | 3903 | 576 | 154 | 165 | 276 | 897 | 681 | 165 | 2051 |
| settings | 4303 | 3757 | 0 | 404 | 142 | 167 | 606 | 716 | 0 | 2269 |
| pmcmd | 2067 | 1432 | 0 | 335 | 300 | 377 | 554 | 502 | 0 | 0 |
| pm | 329 | 0 | 0 | 120 | 209 | 0 | 0 | 0 | 0 | 0 |

Les domaines marqués ⚠ ont chacun leur ticket de découpage (RM3017 sets, RM3018 sessions,
RM3019 worklog, RM3020 center, RM3021 meta) : le poste principal est le fichier de test, à
scinder par couche. `scripts/test_cockpit_view_cost.py` teste la mesure elle-même.

## Livrer

MR ticket → `dev` → `main` (`mmi-pm mr create` / `mr merge`), puis `sudo mmi-pm core update`
sur l'instance. `systemctl --user restart karl-agent` **seulement** si `scripts/karl-agent.py`
change ; un front seul se recharge avec Ctrl+F5 (l'avertissement de version le dit).
