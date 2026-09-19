#!/usr/bin/env python3
"""Tests RM3250 — synchro WordPress prod → recette (tools/synchro/lib/wordpress.sh).

Les vraies bibliothèques du framework sont sourcées dans un bash isolé ; `wp`, `rsync`,
`mysql`, `ssh` et `chown` y sont des doublures qui notent leurs appels (arguments ET
entrée standard) dans un journal. Aucun accès réseau, aucune base réelle.

Lancer : python3 scripts/test_synchro_wordpress.py
"""
import pathlib
import re
import shutil
import subprocess
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
SYNCHRO = HERE.parent / "tools" / "synchro"
fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


# Chaque doublure écrit « ARGV <nom> <args> » puis, si elle lit stdin, « STDIN <nom> <contenu> ».
STUBS = {
    "rsync": 'echo "ARGV rsync $*" >> "$STUB_LOG"',
    "chown": 'echo "ARGV chown $*" >> "$STUB_LOG"',
    "mysql": 'echo "ARGV mysql $*" >> "$STUB_LOG"; c=$(cat); [ -z "$c" ] || printf "STDIN mysql %s\\n" "$c" >> "$STUB_LOG"',
    "ssh": 'echo "ARGV ssh $*" >> "$STUB_LOG"; printf "CREATE TABLE t (i int);\\n" | gzip',
    "wp": r'''echo "ARGV wp $*" >> "$STUB_LOG"
path=""; for a in "$@"; do case "$a" in --path=*) path="${a#--path=}";; esac; done
case "$*" in
  *"config create"*)
    printf "STDIN wp " >> "$STUB_LOG"; cat >> "$STUB_LOG"
    echo "<?php // wp-config de test" > "$path/wp-config.php" ;;
  *"plugin is-active"*)
    for p in $WP_ACTIFS; do case "$*" in *"is-active $p"*) exit 0;; esac; done; exit 1 ;;
esac
exit 0''',
}


def make_bin(td):
    b = td / "bin"
    b.mkdir()
    for name, body in STUBS.items():
        f = b / name
        f.write_text("#!/bin/bash\n" + body + "\n")
        f.chmod(0o755)
    return b


def run(td, script, conf, extra_env=None):
    """Source common/helpers/db/wordpress puis la conf, exécute `script`."""
    log = td / "stub.log"
    log.write_text("")
    env = {"PATH": f"{td / 'bin'}:/usr/bin:/bin", "HOME": str(td), "STUB_LOG": str(log),
           "SYNCHRO_INSTANCE_ENV": "/nonexistent/pm.env", "TMPDIR": str(td),
           "ASSUME_YES": "1", "WP_ACTIFS": ""}
    env.update(extra_env or {})
    full = (f'set -uo pipefail\n. "{SYNCHRO}/lib/common.sh"\n. "{SYNCHRO}/lib/helpers.sh"\n'
            f'. "{SYNCHRO}/lib/db.sh"\n. "{SYNCHRO}/lib/wordpress.sh"\n{conf}\n{script}')
    r = subprocess.run(["bash", "-c", full], capture_output=True, text=True, env=env,
                       stdin=subprocess.DEVNULL)
    return r.returncode, r.stdout + r.stderr, log.read_text()


def conf_for(td, **over):
    v = {
        "WEBSITE_TYPE": "wordpress", "WORKSPACE_ROOT": str(td / "www"),
        "WEBSITE_PATH": "site-test", "SSH_AUTH": "root@prod.exemple.org",
        "REMOTE_FILES_PATH": "/srv/prod/site", "PROD_URL": "https://www.exemple.org",
        "DB_FROM": "site_www", "DB_TO": "site_test", "DB_PREFIX": "wp_",
        "DOMAIN": "site.test.exemple.org", "EMAIL": "dev@exemple.org",
        "MYSQL_HOST": "localhost", "TMP_PATH": str(td / "tmp"),
        "FILES_OWNER": "php_site:site", "WP_DEACTIVATE_PLUGINS": "crowdsec wp-fastest-cache",
    }
    v.update(over)
    return "\n".join(f'{k}="{val}"' for k, val in v.items())


def argv_lines(log, tool):
    return [l for l in log.splitlines() if l.startswith(f"ARGV {tool} ")]


with tempfile.TemporaryDirectory() as td:
    td = pathlib.Path(td)
    make_bin(td)
    dest = td / "www" / "site-test"
    dest.mkdir(parents=True)

    # ---- garde-fous ----------------------------------------------------------
    rc, out, _ = run(td, "wordpress_sync_files", conf_for(td, DOMAIN="www.exemple.org"))
    check("DOMAIN = hôte de la prod : refus", rc != 0 and "domaine de la prod" in out, out)
    rc, out, log = run(td, "wordpress_sync_files", conf_for(td, PROD_URL=""))
    check("PROD_URL absent : refus, et rien n'est copié", rc != 0 and not argv_lines(log, "rsync"), out)
    rc, out, _ = run(td, "wordpress_sync_files", conf_for(td, WEBSITE_PATH="absent"))
    check("dossier de recette absent : refus explicite", rc != 0 and "Cible inexistante" in out, out)

    # ---- fichiers : premier passage (pas de wp-config) -------------------------
    site_mu = td / "sans-traceur.php"
    site_mu.write_text("<?php // propre au site\n")
    rc, out, log = run(td, "wordpress_sync_files", conf_for(td, WP_RECETTE_MU=str(site_mu)))
    check("synchro fichiers : succès", rc == 0, out)
    rs = " ".join(argv_lines(log, "rsync"))
    check("rsync lit la prod et écrit dans la recette",
          "root@prod.exemple.org:/srv/prod/site/" in rs and f"{dest}/" in rs, rs)
    for motif in ("/wp-config.php", "/wp-content/cache/", "/.user.ini"):
        check(f"rsync exclut {motif}", f"--exclude={motif}" in rs, rs)
    check("rsync protège les mu-plugins de recette de --delete",
          "--exclude=/wp-content/mu-plugins/zz-pm-recette*.php" in rs, rs)
    check("rsync applique le propriétaire du site", "--chown=php_site:site" in rs, rs)
    check("robots.txt fermé", (dest / "robots.txt").read_text() == "User-agent: *\nDisallow: /\n")

    mu = dest / "wp-content" / "mu-plugins" / "zz-pm-recette.php"
    check("mu-plugin de recette posé", mu.exists())
    txt = mu.read_text() if mu.exists() else ""
    check("le mu-plugin coupe les mails (pre_wp_mail) et pose noindex",
          "pre_wp_mail" in txt and "X-Robots-Tag: noindex" in txt, txt[:200])
    if shutil.which("php") and mu.exists():
        lint = subprocess.run(["php", "-l", str(mu)], capture_output=True, text=True)
        check("le mu-plugin est du PHP valide", lint.returncode == 0, lint.stdout + lint.stderr)
    check("le mu-plugin propre au site est posé avec le préfixe de recette",
          (dest / "wp-content" / "mu-plugins" / "zz-pm-recette-sans-traceur.php").exists())

    # wp-config : compte MySQL dédié, mot de passe jamais en argument ni affiché
    cfg = dest / "wp-config.php"
    check("wp-config.php créé", cfg.exists())
    stdin_mysql = re.search(r"IDENTIFIED BY '([A-Za-z0-9]+)'", log)
    pw = stdin_mysql.group(1) if stdin_mysql else ""
    check("un mot de passe robuste est tiré (≥ 24 caractères)", len(pw) >= 24, pw and "trop court")
    check("compte MySQL limité à la base de recette",
          "GRANT ALL PRIVILEGES ON `site_test`.* TO 'site_test'@'localhost'" in log, log)
    check("le mot de passe n'apparaît dans AUCUN argument de commande",
          pw and not any(pw in l for l in log.splitlines() if l.startswith("ARGV")), "")
    check("…ni dans la sortie de la synchro", pw and pw not in out, "")
    check("wp-cli le reçoit par stdin (--prompt=dbpass)",
          "--prompt=dbpass" in " ".join(argv_lines(log, "wp")) and f"STDIN wp {pw}" in log, "")
    check("wp-config lisible du seul propriétaire et de son groupe",
          oct(cfg.stat().st_mode & 0o777) == "0o640", oct(cfg.stat().st_mode & 0o777))

    # ---- fichiers : passage suivant (wp-config présent) ------------------------
    rc, out, log = run(td, "wordpress_sync_files", conf_for(td))
    check("wp-config existant : ni nouveau compte MySQL, ni nouveau fichier",
          rc == 0 and not argv_lines(log, "mysql") and "config create" not in log, log)

    # ---- base : adaptations ----------------------------------------------------
    rc, out, log = run(td, "wordpress_adapt_db", conf_for(td), {"WP_ACTIFS": "crowdsec"})
    check("adaptation BDD : succès", rc == 0, out)
    wp = argv_lines(log, "wp")
    sr = [l for l in wp if "search-replace" in l]

    def replaced(a, b):
        return any(f"search-replace {a} {b} " in l for l in sr)

    check("URL de prod → URL de recette", replaced("https://www.exemple.org", "https://site.test.exemple.org"), sr)
    check("URL sans schéma remplacée", replaced("//www.exemple.org", "//site.test.exemple.org"), sr)
    check("URL échappée JSON remplacée", replaced(r"\/\/www.exemple.org", r"\/\/site.test.exemple.org"), sr)
    check("chemin disque de prod → chemin de recette", replaced("/srv/prod/site", str(dest)), sr)
    check("remplacements sûrs : toutes les tables du préfixe, guid préservé",
          sr and all("--all-tables-with-prefix" in l and "--skip-columns=guid" in l for l in sr), sr)
    check("wp-cli vise la recette, jamais un autre chemin",
          wp and all(f"--path={dest}" in l for l in wp), wp)
    check("recette non indexable (blog_public 0)", any("option update blog_public 0" in l for l in wp), wp)
    check("admin_email → adresse de dev", any("option update admin_email dev@exemple.org" in l for l in wp), wp)
    check("extension active listée : désactivée", any("plugin deactivate crowdsec" in l for l in wp), wp)
    check("extension inactive listée : laissée telle quelle",
          not any("plugin deactivate wp-fastest-cache" in l for l in wp), wp)

    rc, out, log = run(td, "wordpress_adapt_db", conf_for(td, WEBSITE_PATH="vide"))
    check("adaptation sans wp-config : refus avant tout remplacement",
          rc != 0 and "search-replace" not in log, out)

    # ---- dump par socket : aucun identifiant de prod ---------------------------
    rc, out, log = run(td, "db_dump_from_prod; zcat \"$DUMP_FILE\"",
                       conf_for(td, DB_DUMP_STRATEGY="remote-mysqldump-socket"))
    ssh = " ".join(argv_lines(log, "ssh"))
    check("dump par socket : succès et contenu récupéré", rc == 0 and "CREATE TABLE t" in out, out)
    check("dump par socket : mysqldump de la base de prod, sans -u ni mot de passe",
          "mysqldump --single-transaction --skip-comments site_www" in ssh
          and " -u" not in ssh and "MYSQL_PWD" not in ssh, ssh)

    # ---- de bout en bout : sync.sh avec une conf WordPress ----------------------
    shutil.rmtree(dest)
    dest.mkdir()
    conf = td / "recette.conf"
    conf.write_text(conf_for(td, DB_DUMP_STRATEGY="remote-mysqldump-socket") + "\n")
    log = td / "stub.log"
    log.write_text("")
    env = {"PATH": f"{td / 'bin'}:/usr/bin:/bin", "HOME": str(td), "STUB_LOG": str(log),
           "SYNCHRO_INSTANCE_ENV": "/nonexistent/pm.env", "TMPDIR": str(td), "WP_ACTIFS": ""}
    r = subprocess.run(["bash", str(SYNCHRO / "sync.sh"), str(conf), "--yes"],
                       capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL)
    full = log.read_text()
    check("sync.sh de bout en bout : succès", r.returncode == 0, r.stdout[-600:] + r.stderr[-600:])
    order = [m.group(1) for m in re.finditer(r"^ARGV (rsync|ssh|wp \S+ search-replace)", full, re.M)]
    check("ordre : fichiers, puis dump, puis remplacements",
          order[:2] == ["rsync", "ssh"] and any(o.startswith("wp") for o in order[2:]), order)
    check("la base est importée dans la base de RECETTE", "CREATE DATABASE `site_test`" in full, "")
    check("le dump temporaire est supprimé", not (td / "tmp" / "site_test.sql.gz").exists())

print()
if fails:
    print(f"{len(fails)} test(s) en échec : {', '.join(fails)}")
    raise SystemExit(1)
print("tous les tests passent")
