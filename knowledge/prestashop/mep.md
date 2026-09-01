---
type: knowledge
product: prestashop
created: 2026-08-14
---

# PrestaShop — procédure de mise en production (commune au parc)

Invariants valables sur les **quatre** boutiques PrestaShop du parc. Chaque
`environments.md` de projet renvoie ici et ne garde que **ses** spécificités.

Tout ce qui suit est **constaté**, pas supposé : les pièges des § 2, 4 et 5 ont chacun
coûté une MEP (RM2625, pisceen, 2026-08-13).

> ⚠ **Tripwire prod (NORMS)** : aucune commande mutante sans consentement humain explicite
> **pour cette action précise**. Inspecter en lecture seule, proposer la commande exacte,
> attendre le feu vert. Un accord ne vaut pas pour l'étape suivante.

## Séquence

```
0. snapshot / point de restauration      (si infra opensvc/LXC/ZFS — cf. NORMS)
1. vérifier son IP dans PS_MAINTENANCE_IP   ← garde-fou, AVANT tout
2. maintenance ON
3. inspecter l'arbre git (status ciblé)
4. fetch + revue du lot
5. ── feu vert humain ──
6. git pull --ff-only
7. upgrade des modules dont la version a changé
8. purge de cache (conditionnelle, § 5)
9. vérification (présentation de panier, front)
10. maintenance OFF
11. miroir (projets concernés)
```

## 1. Maintenance — et le garde-fou qui va avec

Le commutateur est la clé de configuration **`PS_SHOP_ENABLE`** (`1` = boutique ouverte,
`0`/`NULL` = maintenance). Le cœur ne teste rien d'autre :

```php
// classes/controller/FrontController.php:763
if ($this->maintenance == true || !(int) Configuration::get('PS_SHOP_ENABLE')) {
```

`NULL` caste en `0` ⇒ **maintenance**. C'est d'ailleurs l'état des copies de dev du parc,
avec `10.0.3.1` (passerelle LXC) en liste blanche.

**Il n'existe aucune commande `bin/console` pour ça** (vérifié : `src/PrestaShopBundle/Command/`
n'expose que module/theme/translations/schema). Deux voies : le back-office
(*Paramètres de la boutique › Maintenance*), ou le CLI.

### ⚠ Le garde-fou : `PS_MAINTENANCE_IP` d'abord

En maintenance, seules les IP de `PS_MAINTENANCE_IP` voient le site. **Vérifier que la
sienne y est AVANT de couper**, sinon on se verrouille dehors au moment précis où il faut
vérifier que la MEP est bonne.

```bash
# 1) mon IP publique vue du serveur
curl -s https://ifconfig.me

# 2) est-elle dans la liste ?
php7.4 -r 'require "config/config.inc.php";
  $ips = array_map("trim", explode(",", (string) Configuration::get("PS_MAINTENANCE_IP")));
  $me  = trim(shell_exec("curl -s https://ifconfig.me"));
  echo in_array($me, $ips, true) ? "OK $me\n" : "ABSENT $me — ne pas couper\n";'
```

### Bascule

```bash
php7.4 -r 'require "config/config.inc.php"; Configuration::updateValue("PS_SHOP_ENABLE", 0);'  # ON
php7.4 -r 'require "config/config.inc.php"; Configuration::updateValue("PS_SHOP_ENABLE", 1);'  # OFF
```

Passer par `Configuration::updateValue()` et **non** par un `UPDATE` SQL direct : la classe
invalide le cache de configuration, l'`UPDATE` non.

## 2. ⚠ `php7.4`, jamais `php`

Sur les serveurs hébergeant plusieurs versions, le `php` par défaut n'est **pas** celui du
site. Sur la prod pisceen il est en **8.5**, sur laquelle PrestaShop 1.7.8 **ne démarre
pas** (doctrine/dbal : `PDOConnection::query() must be compatible with PDO::query()`, fatal
dès l'autoload).

Le site ne le voit jamais — son pool FPM tourne en 7.4. **Seules les commandes lancées à la
main tombent dedans**, c'est-à-dire pendant une MEP, au pire moment.

```bash
php7.4 bin/console prestashop:module upgrade <module>   # ✅
php    bin/console …                                    # ❌ fatal
```

Même règle sur le conteneur de dev, où `php` est aussi en 8.5.

## 3. `git pull --ff-only`, après inspection ciblée

Les arbres de prod PrestaShop sont **durablement sales** : les modules écrivent dans des
fichiers trackés (91 fichiers modifiés côté pisceen). C'est normal, ce n'est pas un
incident — mais ça interdit de lire `git status` en bloc.

```bash
git status --porcelain -uno | wc -l                  # la saleté est attendue
git status --porcelain -uno -- <fichiers du ticket>  # DOIT être vide
git fetch <remote> <branche> && git log --oneline HEAD..FETCH_HEAD
# ── feu vert ──
git pull --ff-only <remote> <branche>
```

`--ff-only` pour qu'un cas non prévu **échoue** au lieu de fabriquer silencieusement un
merge dans un arbre déjà sale.

## 4. ⚠ Upgrade de module en CLI : le faux « rien à faire »

Un `Module` instancié **hors back-office** a `installed` et `database_version` à **NULL**
(cache statique non amorcé). Or le cœur fait :

```php
// classes/module/Module.php:537
$ret = $module->installed && Module::needUpgrade($module);
```

`installed` étant NULL, la détection **n'est jamais appelée** : `runUpgradeModule()` renvoie
`available_upgrade => 0`. Ça **se lit « rien à faire » alors que rien n'a été tenté** — les
`upgrade/upgrade-x.y.z.php` ne sont pas joués et la MEP paraît réussie.

Second piège, juste au-dessus :

```php
// Module.php:519
if (((int) $module->installed == 1) & (empty($module->database_version) === true)) {
    Module::upgradeModuleVersion($module->name, $module->version);   // marque à jour !
```

Amorcer `installed` **sans** amorcer `database_version` fait pire que rien : le module est
déclaré à jour et les upgrades sont définitivement sautés. **Amorcer les deux, avec la vraie
valeur en base.**

```php
<?php
// upgrade-module.php — à lancer depuis la racine : php7.4 upgrade-module.php <module>
require dirname(__FILE__) . '/config/config.inc.php';

$name = $argv[1] ?? null;
if (!$name) { fwrite(STDERR, "usage: php7.4 upgrade-module.php <module>\n"); exit(1); }

$row = Db::getInstance()->getRow(
    'SELECT version FROM ' . _DB_PREFIX_ . 'module WHERE name = "' . pSQL($name) . '"'
);
if (!$row) { fwrite(STDERR, "module $name absent de la table module\n"); exit(1); }

$module = Module::getInstanceByName($name);
$module->installed        = true;          // ← sinon needUpgrade() n'est jamais appelé
$module->database_version = $row['version']; // ← sinon le module est marqué "à jour"

Module::initUpgradeModule($module);
$res = $module->runUpgradeModule();

printf("%s : %s → %s | upgrades dispo=%d appliqués=%d succès=%s\n",
    $name, $row['version'], $module->version,
    $res['available_upgrade'], $res['number_upgraded'],
    $res['success'] ? 'oui' : 'NON');
exit($res['success'] ? 0 : 1);
```

Vérifié sur l'env de dev pisceen le 2026-08-14 :

```
cins_newproductfields : 1.0.1 → 1.0.2 | upgrades dispo=1 appliqués=1 succès=oui
```

**Corollaire** : `php7.4 bin/console prestashop:module upgrade <module>` fonctionne et
n'a pas ce défaut, mais il est **lent** (boot du kernel Symfony + appels à
`api-addons.prestashop.com` qui partent en timeout). Le script ci-dessus est l'option rapide
en MEP ; la console reste la référence si on n'est pas pressé.

## 5. Purge de cache : conditionnelle, pas réflexe

Inutile quand `PS_SMARTY_FORCE_COMPILE = 1` (recompilation sur mtime). Contrôler plutôt que
supposer :

```bash
php7.4 -r 'require "config/config.inc.php";
  echo "PS_SMARTY_FORCE_COMPILE=" . var_export(Configuration::get("PS_SMARTY_FORCE_COMPILE"), true) . "\n";'
```

Si à `0` :

```bash
php7.4 bin/console cache:clear --env=prod
# ou, si le kernel refuse de démarrer : rm -rf var/cache/prod/*
```

⚠ Les valeurs relevées dans le tableau § 8 viennent des **copies de dev**. Sur une copie de
dev, `PS_SMARTY_FORCE_COMPILE` est typiquement forcé à 1 : **lire la valeur sur la prod**
au moment de la MEP, pas ici.

## 6. Vérifier sans navigateur : présenter un vrai panier

Le contrôle le plus probant après une MEP touchant au tunnel : **présenter de vrais paniers
de production** via le `CartPresenter`, en lecture seule. Ça traverse les hooks des modules
et prouve le comportement sur les données réelles — là où un test unitaire ne dit rien.

```php
<?php
// check-cart.php — php7.4 check-cart.php <id_cart> [<id_cart> …]  (LECTURE SEULE)
require dirname(__FILE__) . '/config/config.inc.php';

// Le CartPresenter formate les prix via le conteneur Symfony : il faut booter le kernel.
// SymfonyContainer::getInstance() lit la globale $kernel — d'où le `global` ci-dessous.
require_once dirname(__FILE__) . '/app/AppKernel.php';
global $kernel;
$kernel = new AppKernel('prod', false);
$kernel->boot();

$ctx = Context::getContext();
$ctx->container = $kernel->getContainer();

foreach (array_slice($argv, 1) as $idCart) {
    Cache::clean('*');   // sinon les caches statiques fuient d'un panier à l'autre

    $cart = new Cart((int) $idCart);
    if (!Validate::isLoadedObject($cart)) { echo "$idCart : panier introuvable\n"; continue; }

    // le presenter dépend d'un contexte complet
    $ctx->cart     = $cart;
    $ctx->customer = new Customer((int) $cart->id_customer);
    $ctx->currency = new Currency((int) $cart->id_currency);
    $ctx->language = new Language((int) $cart->id_lang);

    $presented = (new PrestaShop\PrestaShop\Adapter\Presenter\Cart\CartPresenter())->present($cart);
    printf("panier %d : port=%s | %d produit(s)\n",
        $idCart, $presented['subtotals']['shipping']['value'], count($presented['products']));
}
```

Sortie réelle (env de dev pisceen, 2026-08-14) :

```
panier 54806 : port=9,76 € | 2 produit(s)
panier 54805 : port=gratuit | 2 produit(s)
panier 54792 : port=gratuit | 3 produit(s)
```

**Pièges rencontrés** (RM2625) :

- **Le conteneur Symfony est obligatoire.** Sans le boot du kernel, `PriceFormatter::format()`
  remonte `ContainerNotFoundException: Kernel Container is not available`. Amorcer
  `$ctx->container` seul ne suffit pas si le kernel n'est pas booté :
  `SymfonyContainer::getInstance()` renvoie `null` tant que la globale `$kernel` n'existe pas.
- **Le contexte doit être complet** (`currency`, `language`, `customer`, `shop`), sinon le
  presenter tombe en erreur ou renvoie des prix non formatés.
- **Les caches statiques persistent dans le processus** (`Cart::getCartRules()` notamment) :
  sans `Cache::clean('*')` entre deux paniers, on obtient un **faux négatif** — un bon de
  réduction du panier précédent continue de s'appliquer.
- Pour certains formatages, `Adapter\Product\PriceFormatter` fonctionne en CLI là où
  `getCurrentLocale()->formatPrice()` renvoie null.

## 7. Miroirs

Pour les projets qui en ont un, **le push miroir fait partie de la MEP**, pas d'une étape
optionnelle : un partenaire externe consomme le miroir et travaillerait sinon sur une
version périmée.

Aujourd'hui **pisceen** est le seul cas actif du parc (miroir `gogs`, confirmé Mathieu
2026-07-21). L'alias `gogs:` passe par une clé **avec passphrase** : si l'agent SSH est
vide, le push échoue en `Permission denied (publickey)` — ce n'est **pas** un faux positif
à ignorer, il faut faire charger la clé.

## 8. Spécificités par site

Relevé le 2026-08-14 depuis les copies de dev et les manifestes PM. Les cases « à
documenter » sont des **trous connus**, pas des oublis de rédaction.

| Projet | Version PS | PHP CLI | Branche prod | Remote de déploiement | Miroir | Préfixe BDD |
|---|---|---|---|---|---|---|
| `pisceen/presta` | 1.7.8.10 | `php7.4` | `master` | `gitlab` (**`ssh -A` requis**) | **gogs (actif)** | `ps_` |
| `calicote/prestashop` | 1.7.8.7 | `php7.4` | `master` | alias SSH `calicote-presta` | — | `ps_` |
| `calyclay/prestashop` | 1.7.8.11 | `php7.4` | `master` | *pas de prod documentée* | `gogs` (remote présent) | `psy7_` |
| `villa-cactus/prestashop` | 1.7.8.7 | à documenter | `master` | remote `dev` = `php_calicote@prod.iprospective.fr:public/villa-cactus` | `gogs` (remote présent) | `ps_` |

Points d'attention spécifiques :

- **pisceen** — le `-A` (agent forwarding) est **obligatoire** : la prod n'a pas de clé
  propre vers le GitLab sfy, elle utilise la clé forwardée. Miroir gogs à pousser.
- **calicote** — flux à **trois** branches : `branche de ticket → dev → recette préprod →
  master → prod`. Une MR de ticket vise **`dev`**, jamais `master` (incident 2026-08-02 :
  quatre tickets mergés directement dans `master`). Purge de cache déclarée nécessaire en
  `post_deploy` (overrides).
- **calyclay** — gros WIP non committé hérité du checkout historique (~608 fichiers) : à
  trier **avant** tout travail sérieux. Aucune prod documentée.
- **villa-cactus** — **pas d'`environments.md`** ; trois remotes hétérogènes (bitbucket
  `cins`, `dev` en SSH direct vers `prod.iprospective.fr`, `gogs`, `origin`). Le déploiement
  réel est à établir avant toute MEP.

## Voir aussi

- `norms/src/modules/git-mep.md` — règles de branche/MR, tripwire sécurité prod, snapshot
- `norms/src/modules/git-mep-pratique.md` — dépannage du transport git
- Skill `mmi-presta-dev-vhost` — provisionnement d'un environnement de dev PrestaShop
