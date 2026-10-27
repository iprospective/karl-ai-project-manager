---
type: knowledge
product: dolibarr
created: 2026-10-27
ticket: RM3524
modele: ../_modeles/developpement-extension.md
---

# Dolibarr — développer un module

Comment écrire, déboguer, tester et livrer un **module externe** Dolibarr sur les versions du parc.
Mise en production : [mep.md](./mep.md). Env de dev recettable par un agent : [env-dev.md](./env-dev.md).

Exemple de bout en bout cité partout : le module **AtomBox** (`dolibarr/dolibarr-module-atombox`,
RM3523 et suivants), écrit, déployé et éprouvé sur l'instance de démonstration de `mmi` en
octobre 2026.

> Provenance : `(24.0.2)` = vérifié dans le code de l'instance de démonstration de `mmi` ;
> `(19–22)` = vérifié dans les sources de `/zfs/workspaces/dolibarr/{19,20,21,dev}` (22.0.0-bêta) ;
> `(AtomBox)` = constaté en réalisant le module. Sans mention : pratique courante, **non vérifiée
> ici** — à vérifier avant d'en dépendre.

## 1. Fiche d'identité

| Instance | Version | PHP | Où |
|---|---|---|---|
| compta (Mathieu) | 19.0.1 | 7.4 (pool `compta-74`) | `mmi:/home/compta` |
| démonstration (devcamp) | 24.0.2 | 8.4 (pool `dolidemo-84`) | `mmi:/home/dolidemo` — `dolibarr.iprospective.eu` |
| sources locales | 13, 16–21, 22.0.0-bêta | — | `/zfs/workspaces/dolibarr/<version>`, `…/dev` |
| clients | voir l'`environments.md` de chaque projet | | |

- **Numéros de module iProspective : 437800 à 437850** (réservés au wiki Dolibarr) ; pris : 437800
  à 437826 (`mmi*`, voir `dolibarr/mmi-dolibarr-modules/README.md`), 437827 AtomBox. Prendre le
  suivant libre et l'inscrire au README.
- Les droits d'un module se numérotent `numero` suivi de deux chiffres (`43782701`).

## 2. Démarrer

**ModuleBuilder** (module « Module Builder », `htdocs/modulebuilder/`) génère un module complet et
le fait évoluer : onglets `description, objects, languages, dictionaries, menus, permissions, tabs,
hooks, triggers, widgets, emailings, exportimport, css, js, cli, cron, specifications,
buildpackage` (24.0.2). L'onglet *objects* engendre, depuis un tableau de champs, la classe
(`CommonObject`), la fiche, la liste, le SQL et l'API REST d'un objet métier.

- L'utiliser pour **créer** un module et pour **tout objet métier** (table + fiche + liste) : il produit
  ce que Dolibarr attend, et se met à jour avec Dolibarr.
- Il écrit dans le répertoire `custom` déclaré (`$dolibarr_main_document_root_alt`) ; le paramètre
  `dirins=` force un autre dossier (24.0.2 — `modulebuilder/index.php`). Ne l'activer qu'en dev.
- Un module **sans objet métier** (AtomBox : des onglets, un crochet, des déclencheurs, une page)
  peut s'écrire à la main à partir du gabarit `htdocs/modulebuilder/template/` — c'est la référence de
  structure, même sans le générateur.
- **Le gabarit contient un `AGENTS.md`** (24.0.2) : les consignes de Dolibarr pour les agents IA qui
  écrivent un module. Le lire avant de commencer ; ses règles principales : passer par les fonctions du
  cœur (`getURLContent`, `CommonObject`, `htdocs/core/lib/`) plutôt que les réécrire, préférer les
  crochets, séparer `/* Actions */` et `/* Views */`, préfixe `llx_` pour les tables.

Où vit le code : un dépôt par module, groupe GitLab `dolibarr/` (`dolibarr-module-<nom>`), créé par
`mmi-pm repo-new --path dolibarr/dolibarr-module-<nom> --license GPL-3.0 …` ; développement local
dans `/zfs/workspaces/dolibarr/modules/<nom>`, monté dans `htdocs/custom/<nom>` de l'instance.

## 3. Structure d'un module

D'après le gabarit (24.0.2 — `modulebuilder/template/`) :

```
<module>/
  core/modules/mod<Module>.class.php   le DESCRIPTEUR (numéro, droits, menus, onglets, constantes, parts)
  core/triggers/interface_99_mod<Module>_<Nom>Triggers.class.php   les déclencheurs
  core/boxes/                           widgets du tableau de bord
  class/<objet>.class.php               objets métier (CommonObject)
  class/actions_<module>.class.php      les crochets (classe Actions<Module>)
  class/api_<module>.class.php          l'API REST
  admin/setup.php, admin/about.php      réglages
  lib/<module>.lib.php                  fonctions et onglets (prepare_head)
  langs/<lang>/<module>.lang            traductions (« Module<numero>Name » = nom du module)
  sql/llx_<module>_<objet>.sql, .key.sql, data.sql, update_x.x.x-y.y.y.sql
  scripts/                              scripts en ligne de commande
  test/phpunit/                         tests
  css/, js/, img/, doc/, build/
```

Le **descripteur** (`DolibarrModules`) déclare tout ce que l'activation rejoue : `numero`, `family`,
`version`, `need_dolibarr_version` (le gabarit 24 met `array(19, -3)`), `phpmin`, `module_parts`
(`triggers`, `hooks`, `login`, `substitutions`, `menus`, `tpl`, `barcode`, `models`, `printing`,
`theme`, `css`…), `config_page_url`, `const`, `tabs`, `rights`, `menu`, `langfiles`.

## 4. Points d'extension

| Besoin | Mécanisme | Exemple (AtomBox) |
|---|---|---|
| un onglet sur une fiche | `$this->tabs[] = array('data' => '<type>:+<code>:<Titre>:<lang>@<module>:<condition>:/<module>/page.php?id=__ID__')` ; types : `thirdparty, propal, order, invoice, project, supplier_order, supplier_invoice`… | onglet « Échanges » sur 7 fiches |
| un menu | `$this->menu[]` (`type` `top`/`left`, `mainmenu`, `url`, `perms`, `enabled`) | menu « Courrier » |
| un droit | `$this->rights[]` ; tester par `$user->hasRight('<module>', '<droit>')` | `atombox read` |
| réagir à un événement | déclencheur `runTrigger($action, $object, …)` ; ne jamais bloquer : journaliser, `return 0` | pousser un objet à chaque `*_CREATE/MODIFY/VALIDATE/DELETE` |
| modifier une page du cœur | crochet : `module_parts['hooks'] = array('<contexte>')`, classe `Actions<Module>`, méthode du nom du crochet | `formObjectOptions` en contexte `thirdpartycard` |
| réglages | `admin/setup.php` + `dolibarr_set_const()` / `getDolGlobalString()` | URL, jeton, correspondance des comptes |
| documents d'un objet | `getMultidirOutput($objet, '', 1)` = le répertoire de l'onglet Documents ; indexer avec `addFileIntoDatabaseIndex($dir, $nom, '', 'uploaded', 0, $objet)` (24.0.2) | « Ajouter aux documents » |
| appeler un service HTTP | `getURLContent()` — **voir § 8** pour les méthodes selon la version | client AtomBox |

Noms utiles (24.0.2) :
- **déclencheurs** : `PROPAL_*`, `ORDER_*`, `BILL_*` (dont `BILL_PAYED`, `BILL_UNPAYED`, `BILL_CANCEL`),
  `PROJECT_*`, `ORDER_SUPPLIER_*`, `BILL_SUPPLIER_*`, `COMPANY_*`, `CONTACT_*` ;
  `ORDER_` est un préfixe de `ORDER_SUPPLIER_` : trancher par `$object->element` ;
- **éléments** (`$object->element`) : `propal`, `commande`, `facture`, `project`, `order_supplier`,
  `invoice_supplier`, `societe`, `contact` ; un contact porte son tiers dans `$object->socid` ;
- **colonnes d'état** : `fk_statut` (propal, commande, facture), `paye`, `date_lim_reglement` (facture).

## 5. Cycle de vie

- **Activer** rejoue le descripteur : SQL, constantes, droits, menus, onglets, crochets. Une MEP qui
  change la version d'un module exige **désactiver puis réactiver** ([mep.md](./mep.md) § 4).
- **Désactiver** retire droits, menus, onglets, crochets — et les constantes dont le 7ᵉ champ
  (`deleteonunactive`) vaut 1. Mettre **0** pour la configuration (URL, jeton…), sinon la
  désactivation l'efface (AtomBox).
- **Les droits sont retirés à TOUS les utilisateurs** à la désactivation : après une réactivation, il
  faut les rendre (AtomBox).
- **En ligne de commande** (`master.inc.php`, `core/lib/admin.lib.php`) :
  - `activateModule('mod<Module>')` sur un module **déjà actif** ne réinsère ni menus ni crochets nouveaux ;
  - `unActivateModule()` puis `activateModule()` dans le même processus **ne réactive rien** tant
    que la configuration en mémoire n'est pas rechargée : `$conf->setValues($db)` entre les deux
    (AtomBox — le module était resté désactivé).
- Dolibarr **chiffre** certaines constantes en base (`dolcrypt:AES-256-CTR:…`) ; les lire par
  `getDolGlobalString`, jamais en SQL (24.0.2, AtomBox).

## 6. Déboguer

- **Journal** : module *Syslog* ; réglages `SYSLOG_HANDLERS`, `SYSLOG_LEVEL` (7 = débogage),
  `SYSLOG_FILE`, `SYSLOG_FILE_SAVES` (24.0.2 — `admin/syslog.php`) ; fichier par défaut
  `<documents>/dolibarr.log` ; écrire par `dol_syslog($message, LOG_DEBUG|LOG_WARNING|LOG_ERR)`.
  Les requêtes SQL y figurent en DEBUG.
- **Barre de débogage** : module *DebugBar* (PHP DebugBar : requêtes, journal, temps, mémoire) ;
  réglages `DEBUGBAR_LOGS_LINES_NUMBER`, `DEBUGBAR_USE_LOG_FILE` (24.0.2). En dev seulement.
- **Erreurs PHP à l'écran** : `$dolibarr_main_prod = '0'` dans `conf/conf.php` (24.0.2 —
  `conf.php.example`) ; jamais en production.
- **Débogueur pas à pas** : Xdebug n'est pas chargé sur le PHP du conteneur `dev` (constaté le 27/10).
- **Protection CSRF** : une action en GET sans `token=newToken()` est refusée et journalisée
  « refused by CSRF protection » ; les formulaires POST portent `token` (vérifié par `main.inc.php`).

## 7. Tester

- **PHPUnit** : le gabarit fournit `test/phpunit/MyObjectTest.php` et un test fonctionnel ; le cadre de
  Dolibarr est `test/phpunit/CommonClassTest.class.php` dans les SOURCES (présent dans
  `/zfs/workspaces/dolibarr/dev/test/phpunit/`, pas dans l'archive d'une instance).
- **Tests sur base réelle en transaction annulée** : le modèle du parc est
  `calicote/dolibarr` (`test/mmi/*_test.php`, RM3515) — invariants vérifiés à chaque étape.
- **Recette par un agent** : instance recettable ([env-dev.md](./env-dev.md)) ; connexion par `curl`
  (jeton CSRF de la page de connexion, puis POST `username`/`password`/`token`). Piège : un mot de
  passe passé par `<<<` porte un saut de ligne final et la connexion échoue — `printf '%s'` (AtomBox).
- **Lint par version** : `php7.4 -l` et `php8.4 -l` sur chaque fichier avant de livrer.

## 8. Compatibilité entre versions

| API ou comportement | 19.0 | 20–21 | 22.0.0-bêta | 24.0.2 | Source |
|---|---|---|---|---|---|
| `getURLContent` : `GET POST PUT DELETE HEAD`, `PUTALREADYFORMATED`, `POSTALREADYFORMATED` | oui | oui | oui | oui | `core/lib/geturl.lib.php` |
| `getURLContent` : **`PATCH`, `PATCHALREADYFORMATED`** | **non** | **non** | **non** | oui | idem |
| `getURLContent` : `$localurl` (0 externe seul, 1 local seul, 2 les deux) | oui | oui | oui | oui | idem |
| `GETPOSTINT()` | oui (19.0.1 et 19.0.4) | oui | oui | oui | `core/lib/functions.lib.php` |
| `$user->hasRight()` | oui | oui | oui | oui | `user/class/user.class.php` |
| `getMultidirOutput($objet, $module)` — répertoire du MODULE | oui | oui | oui | oui | `core/lib/functions.lib.php` |
| `getMultidirOutput($objet, '', 1)` — répertoire de l'OBJET (`$forobject`) | **non** | oui | oui | oui | idem ; en 19, ajouter soi-même `get_exdir(…)` / la référence |
| `$user->loadRights()` | **non** (`getrights()`) | oui | oui | oui | `user/class/user.class.php` |

`?` = non vérifié : à compléter quand on y passe. Un module qui annonce `need_dolibarr_version`
19 doit s'en tenir à la colonne 19, ou tester la version (`DOL_VERSION`) avant d'utiliser une API.

## 9. Pièges

| Symptôme | Cause | Parade | Provenance |
|---|---|---|---|
| un module réactivé reste désactivé | `unActivateModule` + `activateModule` dans le même processus | `$conf->setValues($db)` entre les deux | AtomBox, RM3550 |
| menu ou crochet nouveau absent | `activateModule` sur un module déjà actif | désactiver puis réactiver | AtomBox, RM3545 |
| configuration perdue à la désactivation | constante avec `deleteonunactive = 1` | 7ᵉ champ à 0 | AtomBox |
| droits disparus après une MEP | la désactivation les retire à tous | les rendre (réactivation = ré-attribution) | AtomBox |
| un module « compatible 19 » plante en 19 | API récente : `PATCH` par `getURLContent`, `getMultidirOutput(…, 1)`, `loadRights()` | § 8 avant d'appeler ; lint ne le voit pas (appel d'une fonction existante avec un paramètre en trop, méthode absente à l'exécution) | RM3524 |
| on « sait » qu'une API manque en 19… et elle existe | fait affirmé sans vérification (`GETPOSTINT` existe en 19.0.1) | vérifier dans le code de la version, noter la provenance | RM3524 |
| la fiche tiers n'a pas de crochet en colonne de droite | pas d'`executeHooks` à cet endroit (24.0.2) | `formObjectOptions` (contexte `thirdpartycard`) | AtomBox, RM3550 |
| retrouver l'objet d'un courriel envoyé par Dolibarr | Dolibarr écrit le `trackid` dans le Message-ID et le recopie dans `References` | `…-dolibarr-<trackid>@<dol_getprefix('email')>` ; trackid `pro<id>`, `ord<id>`, `inv<id>`, `proj<id>`, `sord<id>`, `sinv<id>`, `thi<id>` ; `dol_getprefix('email')` = `MAIL_PREFIX_FOR_EMAIL_ID` ou une empreinte de l'instance | AtomBox, RM3518 |
| copie des envois dans une boîte | — | `MAIN_MAIL_AUTOCOPY_TO` (copie cachée de tout envoi) | RM3520 |
| créer un tiers ou un contact pré-rempli depuis l'extérieur | — | `societe/card.php?action=create&name=…&email=…&url=…`, `contact/card.php?action=create&lastname=…&email=…` | AtomBox, RM3547 |
| installer une instance sans interface | — | `install/install.forced.php` + POST des étapes `step1/2/5.php` | RM3521 (`infrastructure/containers/mmi/dolibarr-demo/`) |

## 10. Livrer

- Dépôt GitLab par module, `main` protégée : toute évolution par branche + MR (`mmi-pm mr create`).
- Paquet : ModuleBuilder, onglet *buildpackage* (zip installable par l'interface).
- Déploiement sur une instance : [mep.md](./mep.md) ; script de mise en route d'AtomBox
  (`scripts/setup-cli.php` : activer, régler par l'environnement, synchroniser) comme exemple de
  configuration sans interface.
- Publication publique (GitHub `lemathou/dolibarr-module-*` pour les `mmi*`) : décision de Mathieu,
  module par module.

## 11. Sources

- Wiki développeur : https://wiki.dolibarr.org/index.php/Developer_documentation (non relu ici).
- Dans le code (à lire en premier, c'est la référence de la version) : `htdocs/modulebuilder/template/`
  (dont `AGENTS.md`), `htdocs/core/modules/DolibarrModules.class.php`, `htdocs/core/lib/admin.lib.php`
  (`activateModule`, `unActivateModule`, `dolibarr_set_const`), `htdocs/core/lib/geturl.lib.php`,
  `htdocs/core/lib/functions.lib.php`.
