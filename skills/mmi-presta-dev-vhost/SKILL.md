---
name: mmi-presta-dev-vhost
description: Explique et vérifie l'exposition d'un worktree PrestaShop de DEV/TEST sur un domaine dédié tout en PARTAGEANT la base d'un autre env, sans subir la redirection canonique 301 que PS force vers le domaine de ps_shop_url. Le provisionnement est AUTOMATIQUE (mmi-pm task-take) : ce skill sert à comprendre le mécanisme, à vérifier qu'il est en place, et à traiter le cas résiduel d'un worktree hors env de session. Usage : "/mmi-presta-dev-vhost", "pourquoi mon env de ticket presta redirige vers la prod", "vhost de test pour la branche RMxxxx", "hack domaine canonique presta dev".
allowed-tools: Bash, Read, Write
---

# Skill : mmi-presta-dev-vhost

Servir un **worktree PrestaShop** sur un **domaine dédié** (ex.
`calicote-presta-rm2781.lxc`) **en partageant la base** d'un autre environnement,
sans que PrestaShop **redirige en 301** vers le domaine canonique de `ps_shop_url`.

> **Ce skill ne monte plus rien à la main.** Depuis RM2812, `mmi-pm task-take <id>`
> provisionne l'environnement complet : worktree, vhost, overrides, exclusion git,
> purge du cache. Ce qui suit sert à **comprendre** le mécanisme, à **vérifier**
> qu'il est en place, et à traiter le **cas résiduel** d'un worktree hors env de
> session. Toute procédure `sudo` de dépôt de vhost trouvée ailleurs est périmée.

## Le problème résolu

PS résout le shop courant par `HTTP_HOST` via `ps_shop_url` (`Shop::initialize`
→ `findShopByHost`, **privée**). Si l'hôte n'y figure pas, ou n'est pas l'URL
`main`, PS **force une redirection** (`PS_CANONICAL_REDIRECT`) vers le domaine
principal. Le domaine — et donc les liens de `Link::getBaseLink` **et** le domaine
du cookie de session (`config.inc.php`) — vient de `shop->domain`, lu en base.

Servir un worktree sur un domaine de test **sans** correctif, c'est donc renvoyer
le visiteur vers l'environnement principal, voire vers la production.

## Le mécanisme — QUATRE volets

**1/ `override/classes/shop/Shop.php` — résolution.** `findShopByHost` étant
privée, on surcharge `Shop::initialize()` : si l'hôte courant est **inconnu** de
`ps_shop_url`, on spoofe `HTTP_HOST` = domaine canonique (lu par requête directe,
`getMainShopDomain()` renvoyant vide trop tôt dans le bootstrap) le temps de
`parent::initialize()`, on restaure l'hôte réel, puis on force
`shop->domain`/`domain_ssl` = hôte réel.

**2/ `override/classes/shop/ShopUrl.php` — redirection aval et liens.**
`Tools::getShopDomain()`/`getShopDomainSsl()`, utilisés par `canonicalRedirection`,
lisent `ShopUrl::getMainShopDomain()`, qui renvoie le domaine **de la base**. On
surcharge `getMainShopDomain`/`getMainShopDomainSSL` → hôte courant pour un hôte
inconnu. **Sans ce second volet, le 301 persiste.**

**3/ `override/classes/Link.php` — back-office.** Les deux premiers suffisent au
front, pas à l'admin (RM2687). Pendant le `$kernel->handle()` de
`admin/index.php`, l'objet shop du contexte est **rechargé depuis la base**, ce qui
écrase le domaine forcé par `Shop::initialize()`. `Link::getAdminBaseLink()` lit
`$shop->domain` et reconstruit une URL canonique → le BO part vers l'env principal.
On corrige au point d'usage plutôt qu'en amont.

**4/ `override/classes/controller/AdminController.php` — confort BO.** Réaligne
`shop->domain` sur l'hôte courant (fait disparaître le bandeau « vous êtes connecté
avec le nom de domaine suivant… ») et masque les alertes `ps_accounts`, sans objet
sur un env de test.

Zéro écriture en base. Rien ne s'active pour un hôte **connu** : l'environnement
principal n'est jamais touché.

> **Piège de diagnostic** : le `/ → /fr/` (préfixe de langue) est un 301 **normal**.
> Vérifier la **cible** du `Location:`, pas le code.

> **Piège de diagnostic** : le `RequestContext` Symfony porte, lui, le bon hôte de
> test — l'erreur naturelle est d'aller y chercher la cause. Elle est dans
> `shop->domain`.

> **Les tests en CLI induisent en erreur** : le conteneur Symfony n'y est pas
> chargé, et `Tools::isPHPCLI()` désactive les overrides. Diagnostiquer par requête
> HTTP.

## Dépôt des overrides — un seul outil

`tools/env-runtime/presta-dev-overrides.sh` (repo PM), appelé par le
`runtime.post_create` des manifestes. **Ne jamais copier ces assets à la main.**

Le script n'écrase **jamais** un override métier, et c'est tout l'enjeu :

| état de la cible | comportement |
|---|---|
| absente ou non suivie par git | copie de l'asset + `info/exclude` |
| **suivie**, sans collision de membres | injection d'un bloc marqué + `skip-worktree` |
| **suivie**, avec collision | **refus**, rien n'est modifié |

Le cas « suivie » n'est pas théorique : `calicote` a un `override/classes/Link.php`
métier (redirection « Box » dans `getCategoryLink`) et, depuis RM2857, un
`override/classes/controller/AdminController.php` métier qui définit `init()` — le
même membre que l'asset dev, d'où un refus attendu sur cette classe.

⚠ `info/exclude` **ne protège rien sur un fichier suivi** : il ne s'applique qu'aux
fichiers non suivis. Un écrasement d'override métier n'apparaîtrait que comme une
modification ordinaire dans `git status`, à un `git add` malheureux de la perte.
C'est pourquoi le script refuse plutôt que d'écraser, et pourquoi les injections
sont passées en `skip-worktree`.

## Vérifier qu'un env de ticket est bien monté

```bash
# 1. le vhost existe (posé par task-take)
ls /etc/apache2/sites-enabled/ | grep rm<id>

# 2. le front ne part pas vers le domaine canonique
curl -s -o /dev/null -w "%{http_code} -> %{redirect_url}\n" \
     -H "Host: <repo>-rm<id>.lxc" http://127.0.0.1/
#    attendu : 200, ou 301 vers <repo>-rm<id>.lxc/fr/ — jamais vers l'env principal

# 3. le back-office non plus — l'oublier, c'est livrer un env où l'on ne peut pas
#    recetter un écran de configuration
curl -s -o /dev/null -w "%{http_code} -> %{redirect_url}\n" \
     -H "Host: <repo>-rm<id>.lxc" http://127.0.0.1/<admin>/index.php
#    attendu : 302 vers <repo>-rm<id>.lxc (redirection de login normale)

# 4. les overrides sont là, et le métier est intact
ls override/classes/shop/Shop.php override/classes/shop/ShopUrl.php
git status --porcelain override/    # doit être VIDE
```

Si le front redirige vers l'env principal, l'étape `presta-dev-overrides.sh` du
`post_create` a échoué — relire sa sortie plutôt que de déposer les fichiers à la
main.

## Cas résiduel : un worktree hors env de session

Pour exposer un worktree qui n'a pas été créé par `task-take` :

```bash
# vhost — jamais de dépôt manuel de conf Apache, jamais de sudo à demander.
# <name> est le nom NU : le helper y ajoute « .lxc ». Le 3e argument est la
# SOCKET FPM, pas le nom du pool.
pm-env-helper vhost-add <name> <docroot> /run/php/<pool>.sock

# overrides
bash <repo-pm>/tools/env-runtime/presta-dev-overrides.sh <worktree>

# le cache doit être purgé pour que le class_index reprenne les overrides
rm -rf <worktree>/var/cache/*/*
```

`pm-env-helper` est en `sudo NOPASSWD` avec une liste blanche de verbes : il n'y a
**aucune commande root à faire exécuter par un humain**. La résolution `*.lxc`
(dnsmasq wildcard) existe déjà côté hôte.

## Pré-requis : un worktree exécutable

Un `git worktree` ne contient que les fichiers suivis — il manque `vendor/`,
`config/settings.inc.php`, `app/config/parameters.{php,yml}`, `.htaccess`. C'est le
`runtime.post_create` du manifeste qui les fournit.

⚠ **Le `vendor/` racine se COPIE, il ne se symlinke pas.** Le classmap composer est
en chemins absolus et `__FILE__` résout les liens : depuis le worktree, un `vendor`
symlinké mappe `AppKernel` vers celui de l'env dev, puis l'`index.php` de l'admin
fait `require_once __DIR__.'/../app/AppKernel.php'` sur le fichier du worktree →
« Cannot declare class AppKernel », HTTP 500 **sur le back-office seulement**.
L'env paraît sain tant qu'on n'ouvre pas le BO.

Les symlinks de **modules** restent valides : le module entier est emprunté, il
n'existe donc pas en double. Critère : *symlinker ce qui n'existe qu'à un seul
endroit, copier ce qui a un homologue dans le worktree.*

Sur un env déjà provisionné avec le symlink, remplacer le lien ne suffit pas : les
workers FPM servent encore l'`autoload.php` de l'env dev (opcache + realpath).
Purger `var/cache/` **et** forcer `opcache_reset()`, ou recharger `php7.4-fpm`.

## Garde-fous

- **DEV-ONLY.** Ces overrides ne doivent jamais être commités ni déployés : PS
  deviendrait agnostique au domaine (faille SEO et sécurité). Le script s'en charge
  (`info/exclude`, `skip-worktree`), mais la règle reste à connaître.
- **Ne jamais copier un asset par-dessus un override existant.** Passer par le
  script, qui sait distinguer les trois cas.
- Si les assets sont introuvables, le script **s'arrête** au lieu de continuer :
  un worktree servi sans eux redirigerait vers la production.

## Notes

- Idempotent : relancer le script sans dégât (un bloc déjà injecté est reconnu).
- Multi-worktrees : un vhost par worktree, les mêmes overrides — ils lisent le
  domaine canonique dynamiquement.
- Si le login ou le panier ne tient pas, vérifier que le cookie est bien posé sur
  le domaine de test (conséquence directe de `shop->domain` forcé).
