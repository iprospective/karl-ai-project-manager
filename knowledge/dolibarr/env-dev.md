---
type: doc
created: 2026-10-06
ticket: RM3400
---

# Dolibarr — rendre un env de dev recettable

> À faire **à la création** de l'environnement, pas le jour où un défaut d'interface résiste.
> Règle générale et motif : NORMS `environments` § « Un env de dev doit être recettable par un
> agent ».

## 1. Désactiver le CAPTCHA de la page de connexion

La page de connexion Dolibarr peut porter un CAPTCHA. Tant qu'il est actif, **aucune recette
navigateur automatisée n'est possible** : le parcours s'arrête sur « Mauvaise valeur saisie
pour le code ». On ne le résout pas par script — on le désactive là où il ne protège rien.

```php
// depuis l'env de DEV, master.inc.php chargé
require_once DOL_DOCUMENT_ROOT.'/core/lib/admin.lib.php';
dolibarr_set_const($db, 'MAIN_SECURITY_ENABLECAPTCHA', 0, 'chaine', 0, '', $conf->entity);
```

**Vérifier ensuite que la production n'a pas bougé** — une base de dev est souvent une copie
de la prod, et la confusion d'instance est l'erreur à ne pas commettre :

```sql
SELECT value FROM llx_const WHERE name = 'MAIN_SECURITY_ENABLECAPTCHA';  -- prod : 1
```

## 2. Un compte nominatif pour l'agent

Sans compte, le CAPTCHA désactivé ne sert à rien. Le mot de passe vient du `.env` de l'agent
(`AGENT_TEST_PASS`), jamais de la ligne de commande.

```php
$admin = new User($db); $admin->fetch(1); $admin->getrights();
$u = new User($db);
$u->login = 'karl'; $u->lastname = 'Karl'; $u->firstname = 'Agent';
$u->email = 'karl@iprospective.fr'; $u->admin = 1; $u->statut = 1;
$u->create($admin);
$u->setPassword($admin, getenv('AGENT_TEST_PASS'), 0, 0, 1);
```

Deux pièges constatés (RM3040) :

- **`setPassword()` RETOURNE le mot de passe en clair.** Ne pas afficher son retour : il
  finit dans le transcript de session. `if ($res > 0)` suffit.
- **`$u->admin = 1` ne suffit pas toujours** à ouvrir les écrans : Dolibarr a rendu
  « Access denied » sur `commande/card.php` avec un compte pourtant admin. Attribuer
  explicitement les droits des modules du périmètre testé :

```sql
INSERT IGNORE INTO llx_user_rights (entity, fk_user, fk_id)
SELECT 1, <id_user>, id FROM llx_rights_def
 WHERE module IN ('commande','societe','produit','expedition','stock') AND entity = 1;
```

## 3. Atteindre le vhost depuis le conteneur

Le vhost d'un env de ticket (`<repo>-rm<id>.lxc`) **résout** depuis le conteneur `dev` — le
navigateur headless peut donc l'ouvrir directement, sans en-tête `Host` forgé :

```bash
getent hosts calicote-erp-rm3039.lxc     # 10.0.3.11
```

## 4. Ce qu'on observe, et qui ne se devine pas

Une capture d'écran ne suffit pas : ce qui tranche, c'est l'état calculé du DOM. Relever au
minimum, pour l'élément en cause — `display`/`visibility` effectifs, largeur et hauteur
rendues, classes réellement portées par `<body>` et par le conteneur. Sur RM3040, c'est
l'absence d'une classe sur `<body>` qui a désigné la cause en une fois, après cinq
déploiements passés à la deviner.

Un point d'attention qui vaut au-delà de Dolibarr : **un env de dev ne reproduit pas forcément
l'écran de l'utilisateur**. La composition d'une page dépend des modules actifs et des données
— sur RM3040, le champ cherché était dans la zone d'édition en dev, ailleurs en prod. Une
recette qui passe en dev ne vaut donc pas constat sur la prod ; le dire plutôt que de laisser
croire le contraire.
