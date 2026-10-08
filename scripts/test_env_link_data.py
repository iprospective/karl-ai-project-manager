#!/usr/bin/env python3
"""Tests RM3419 — `env-link-data.sh` : les données d'un env pointent vers un socle, pour TOUTE appli.

Ce qui doit tenir, et qui coûte cher si ça casse :
  · un fichier SUIVI par git n'est jamais touché (sinon git voit une suppression et le prochain
    `git checkout` entre en conflit) ;
  · un sous-arbre dont un ANCÊTRE est déjà lié n'est jamais parcouru — sans cette garde on écrit
    un lien par-dessus le fichier DU SOCLE, c'est-à-dire qu'on corrompt la source unique ;
  · on pose le PLUS GROS lien possible : un dossier entier quand il n'a aucun fichier du dépôt,
    sinon on descend (38 000 liens au lieu de 27 sur un `img/p` réel, mesuré) ;
  · la liste des dossiers vient du MANIFESTE du type, jamais du code : Dolibarr tient en une ligne ;
  · aucun catalogue de traduction n'est lié (Finder Symfony, RM3410) ;
  · rien ne s'écrit sans `--apply`, et une seconde passe ne fait rien.

Lancer : python3 scripts/test_env_link_data.py
"""
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
RUNTIME = HERE.parent / "tools" / "env-runtime"
SCRIPT = RUNTIME / "env-link-data.sh"
FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


def git(*a, cwd):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)


def depot(root: pathlib.Path, suivis=(), libres=()):
    root.mkdir(parents=True, exist_ok=True)
    for rel in list(suivis) + list(libres):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x" * 8)
    git("init", "-q", ".", cwd=root)
    git("config", "user.email", "t@t", cwd=root); git("config", "user.name", "t", cwd=root)
    if suivis:
        git("add", "--", *suivis, cwd=root); git("commit", "-qm", "init", cwd=root)
    return root


def lance(env, socle, *args):
    return subprocess.run(["bash", str(SCRIPT), "--env", str(env), "--socle", str(socle), *args],
                          capture_output=True, text=True)


tmp = pathlib.Path(tempfile.mkdtemp(prefix="pm-linkdata-"))

# ── PrestaShop ───────────────────────────────────────────────────────────────
print("[RM3419] PrestaShop : manifeste + longue traîne")
PS = "app/AppKernel.php"
suivis = [PS, "img/p/index.php", "modules/blog/img/logo.png", "themes/t/config/theme.yml"]
libres = ["img/p/1/1-home.jpg", "img/p/1/2-home.jpg", "upload/piece.pdf",
          "modules/blog/img/photo.jpg", "modules/libre/img/libre.png",
          "themes/t/assets/img/banniere.png",
          "app/Resources/translations/fr-FR/ShopThemeCatalog.fr-FR.xlf"]
socle = depot(tmp / "socle", suivis=suivis, libres=libres)
(socle / PS).write_text("<?php class AppKernel { const VERSION = '1.7.8.10'; }")
env = depot(tmp / "env", suivis=suivis, libres=["modules/blog/img/photo.jpg"])
(env / PS).write_text("<?php class AppKernel { const VERSION = '1.7.8.10'; }")

r = lance(env, socle)
check("type et version LUS dans l'env", r.returncode == 0 and "type presta 1.7.8.10" in r.stdout, r.stdout[:160] + r.stderr[-160:])
check("le manifeste utilisé est nommé", "presta-data.map" in r.stdout)
check("simulation : rien n'est écrit", not (env / "upload" / "piece.pdf").exists() and "simulation" in r.stdout)

r = lance(env, socle, "--apply")
check("exécution sans erreur", r.returncode == 0, r.stderr[-200:])
check("un dossier de données sans fichier du dépôt est lié ENTIER (upload)",
      (env / "upload").is_symlink() and os.readlink(env / "upload") == str(socle / "upload"))
check("un dossier mixte est parcouru, pas lié (img/p porte index.php suivi)",
      not (env / "img" / "p").is_symlink() and (env / "img" / "p" / "index.php").exists()
      and not (env / "img" / "p" / "index.php").is_symlink())
check("…et son sous-dossier sans fichier du dépôt est lié entier (img/p/1)",
      (env / "img" / "p" / "1").is_symlink(), str(sorted(os.listdir(env / "img" / "p"))))
check("la longue traîne des modules est liée (image non déclarée)",
      (env / "modules" / "libre" / "img" / "libre.png").is_symlink())
check("une copie déjà présente devient un lien (source unique)",
      (env / "modules" / "blog" / "img" / "photo.jpg").is_symlink())
check("un fichier suivi par git n'est jamais lié",
      (env / "modules" / "blog" / "img" / "logo.png").exists()
      and not (env / "modules" / "blog" / "img" / "logo.png").is_symlink())
check("git ne voit aucune suppression", " D " not in git("status", "--porcelain", cwd=env).stdout,
      git("status", "--porcelain", cwd=env).stdout[:160])
check("aucun catalogue de traduction lié (RM3410)",
      not (env / "app/Resources/translations/fr-FR/ShopThemeCatalog.fr-FR.xlf").is_symlink())
check("les liens sont exclus du suivi git", "upload" in (env / ".git" / "info" / "exclude").read_text())

print("\n[RM3419] la garde qui protège le SOCLE")
avant = (socle / "img" / "p" / "1" / "1-home.jpg").is_symlink()
r2 = lance(env, socle, "--apply")
check("le socle n'a pas été réécrit à travers les liens",
      not (socle / "img" / "p" / "1" / "1-home.jpg").is_symlink() and not avant)
check("un sous-arbre déjà emprunté est compté, pas parcouru", "déjà emprunté" in r2.stdout)
import re as _re
_nb = lambda pat, txt: int((_re.search(pat, txt) or _re.match("(0)", "0")).group(1))
check("seconde passe : plus rien à lier",
      _nb(r"(\d+) dossier\(s\) lié\(s\) entier", r2.stdout) == 0
      and _nb(r"(\d+) fichier\(s\) lié\(s\)", r2.stdout) == 0
      and _nb(r"(\d+) image\(s\) liée\(s\)", r2.stdout) == 0,
      r2.stdout[-260:])

print("\n[RM3419] Dolibarr : une ligne suffit")
dol_s = depot(tmp / "dol-socle", suivis=["htdocs/conf/conf.php"], libres=["documents/facture/f1.pdf", "documents/ecm/x.odt"])
dol_e = depot(tmp / "dol-env", suivis=["htdocs/conf/conf.php"])
r3 = lance(dol_e, dol_s, "--apply")
check("type détecté sans --type", r3.returncode == 0 and "type dolibarr" in r3.stdout, r3.stdout[:140] + r3.stderr[-140:])
check("le manifeste dolibarr est utilisé", "dolibarr-data.map" in r3.stdout)
check("documents/ est lié en UN lien", (dol_e / "documents").is_symlink())
check("aucun scan sur dolibarr (inutile : tout est sous documents/)", "scan" not in r3.stdout)
check("le manifeste dolibarr tient en une ligne de données",
      len([l for l in (RUNTIME / "dolibarr-data.map").read_text().splitlines()
           if l.strip() and not l.strip().startswith("#")]) == 1)

print("\n[RM3419] garde-fous")
r4 = lance(env, env)
check("env == socle : refusé", r4.returncode != 0 and "même dossier" in (r4.stderr + r4.stdout))
r5 = lance(env, dol_s)
check("socle d'un autre type : refusé", r5.returncode != 0 and "même type" in r5.stderr)
nu = tmp / "nu"; nu.mkdir()
r6 = lance(nu, socle)
check("appli indétectable : refusé en nommant --type", r6.returncode != 0 and "--type" in r6.stderr)
r7 = subprocess.run(["bash", str(SCRIPT), "--env", str(env)], capture_output=True, text=True)
check("--socle manquant : refusé", r7.returncode == 2 and "requis" in r7.stderr)

print("\n[RM3419] la déclaration est PARTAGÉE")
lib = (RUNTIME / "env-data-manifest.sh").read_text()
check("une bibliothèque résout le manifeste (générique + site)",
      "manifeste_type" in lib and ".$type-data.map" in lib and ".mmi-pm/$type-data.map" in lib)
check("elle gère une variante par version majeure", "$type-data-$maj.map" in lib)
check("elle détecte presta, dolibarr et wordpress", all(t in lib for t in ("presta", "dolibarr", "wordpress")))
sync = (RUNTIME.parent / "synchro" / "lib" / "presta.sh").read_text()
check("la synchro depuis la prod lit le même manifeste (--data)", "presta_sync_data" in sync and "presta-data.map" in sync)
check("--data n'écrase pas par défaut", "--ignore-existing" in sync and "DATA_OVERWRITE" in sync)
shell = (RUNTIME.parent / "synchro" / "sync.sh").read_text()
check("sync.sh expose --data et refuse un type sans implémentation",
      "--data)" in shell and "n'est pas implémenté pour le type" in shell)
check("wordpress a son manifeste", (RUNTIME / "wordpress-data.map").is_file())

print("\n" + ("ÉCHEC — " + ", ".join(FAIL) if FAIL else "OK — env-link-data, modèle réutilisable (RM3419)"))
sys.exit(1 if FAIL else 0)
