# tools/php-fpm — normalisation des pools PHP-FPM (dev.lxc)

Outillage d'ops pour le conteneur de dev `dev.lxc`. Réf. ticket **RM2081**
(prépare l'incrément runtime des worktrees de session **RM1834** / **RM1947**).

## Le pattern d'includes

Chaque version PHP a, dans `/etc/php/<v>/fpm/pool.d/` :

- **`default.conf.inc`** : le `www.conf` *stock*, section `[www]` commentée → includable.
  Fournit les défauts FPM (user/group, pm.*, security…).
- **`common.conf.inc`** : overrides maison, à base de `$pool` :
  `listen = /run/php/$pool.sock`, `pm = ondemand`, logs `/var/log/php/$pool.{error,slow}.log`.
- **`www.conf`** : pool par défaut réécrit en `[www-<v>]` + `include default` + `include common`
  (l'original archivé en `www.conf.orig`).

Chaque pool projet = `[<nom>-<v>]` + `include default` + `include common` + ses overrides
(`user`/`group`, `php_admin_value[...]`). Le socket vaut donc toujours
`/run/php/<nom>-<v>.sock` → les vhosts Apache restent valides sans modification.

## `php-fpm-pattern-migrate.sh`

Applique/normalise ce pattern sur une ou toutes les versions installées.

```bash
# dry-run (n'écrit rien)
sudo ./php-fpm-pattern-migrate.sh all
# une version, état propre (recrée le socket du pool www renommé)
sudo ./php-fpm-pattern-migrate.sh 8.3 --apply --restart
# une version sans coupure des pools projet (le www flippe au prochain restart)
sudo ./php-fpm-pattern-migrate.sh 7.4 --apply --reload
```

Sûretés : **dry-run par défaut**, backup `tar.gz` du `pool.d/` avant écriture
(`/root/fpm-pattern-backups/`), `php-fpm<v> -t` obligatoire (restauration auto du
backup si échec) ; ne touche **pas** les pools projet existants (seulement les `.inc`
+ neutralisation du `www` par défaut, inutilisé) ; fusionne un `common.conf.inc`
préexistant au lieu de l'écraser ; refuse de neutraliser un `www` stock si un vhost
**actif** référence encore `php<v>-fpm.sock`.

Les `.inc` canoniques sont sourcés depuis la version de référence `REF_VER` (8.4).

## À réconcilier (RM1834, incrément runtime)

`common.conf.inc` pose `php_admin_value[error_log]` (= `PHP_INI_SYSTEM`, **verrouillé**) :
ça empêche un `.user.ini` de rediriger `error_log` **par worktree**. Pour des logs par
worktree, basculer `error_log` en `php_value` côté pool, ou séparer les logs autrement.
