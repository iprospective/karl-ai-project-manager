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
    core/               socle sans DOM métier : html (gabarits sûrs), dom (mount/on), store (LRU+TTL+abonnés),
                        api (transport, 401), endpoints (GÉNÉRÉ depuis MIGRATION-ROUTES.tsv), errors,
                        markdown, log (journal du front), version, Repository / Factory / EntityViewModel
    modules/<domaine>/  un dossier par domaine, une couche par SUFFIXE (voir ci-dessous)
    styles/             _tokens.scss (couleurs, thèmes), _base.scss, main.scss (@use de chaque module)
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

Diagnostic en production : `karl.stats()` (stores, DOM, abonnés), `karl.log.entries()`,
le panneau 📜 journal, le pied de page (version).

## Livrer

MR ticket → `dev` → `main` (`mmi-pm mr create` / `mr merge`), puis `sudo mmi-pm core update`
sur l'instance. `systemctl --user restart karl-agent` **seulement** si `scripts/karl-agent.py`
change ; un front seul se recharge avec Ctrl+F5 (l'avertissement de version le dit).
