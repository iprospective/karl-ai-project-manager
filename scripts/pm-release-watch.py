#!/usr/bin/env python3
"""pm-release-watch — la veille des publications qu'on attend (RM2792 lot 4, RM2429).

« Est-ce que la version qui corrige mon problème est sortie ? » On surveille un dépôt, on compare à
un plancher, et le jour où ça tombe on veut le savoir UNE fois. Pas tous les jours, pas jamais.

Le « une seule fois » ne se code pas ici : le fil de notifications le donne déjà. Une notification
est identifiée par l'empreinte de son contenu — tant que c'est la même version qui est annoncée,
c'est la même entrée qui remonte, jamais une de plus. Une version PLUS récente change le message,
donc l'entrée : on est re-prévenu quand il y a réellement du nouveau.

Les veilles se déclarent dans `releases.watch.yml` ; ce script ne connaît aucun produit.

  pm-release-watch                 vérifie toutes les veilles actives, notifie ce qui est sorti
  pm-release-watch --watch vaultwarden     une seule
  pm-release-watch --json          pour les scripts
  pm-release-watch --dry-run       dit ce qui serait notifié, n'écrit rien dans le fil

Réseau indisponible : ce n'est pas une alerte. Une veille quotidienne qui rate un jour ne coûte
rien, et un GitHub injoignable qui ferait clignoter le cockpit apprendrait surtout à l'ignorer.
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pm_notify as N                                   # noqa: E402
try:
    import yaml
except ImportError:
    yaml = None

REGISTRE = "releases.watch.yml"
API = "https://api.github.com/repos/{repo}/releases/latest"
_NUM = re.compile(r"\d+")


def version_tuple(v: str) -> tuple:
    """« v1.37.1 » et « 1.37.1 » sont la même version. Comparer des CHAÎNES dirait que 1.9 > 1.10."""
    return tuple(int(n) for n in _NUM.findall(str(v or ""))[:4]) or (0,)


def registre(racine: Path) -> dict:
    f = racine / REGISTRE
    if not f.is_file() or yaml is None:
        return {}
    try:
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        print(f"ERREUR : {REGISTRE} illisible — {e}", file=sys.stderr)
        return {}
    return data.get("watches") or {}


def derniere(repo: str, timeout=20) -> dict | None:
    """La dernière release publiée, ou None si GitHub n'a rien à dire (réseau, dépôt sans release)."""
    req = urllib.request.Request(API.format(repo=repo),
                                 headers={"Accept": "application/vnd.github+json",
                                          "User-Agent": "pm-release-watch"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return None


def examine(nom: str, veille: dict, dry=False) -> dict:
    repo = str(veille.get("repo") or "").strip()
    plancher = str(veille.get("min_version") or "").strip()
    if not repo or not plancher:
        return {"watch": nom, "ok": False, "error": "veille incomplète (repo et min_version requis)"}
    rel = derniere(repo)
    if not rel:
        return {"watch": nom, "ok": False, "error": f"{repo} injoignable ou sans release"}
    tag = str(rel.get("tag_name") or rel.get("name") or "").strip()
    neuve = version_tuple(tag) > version_tuple(plancher)
    d = {"watch": nom, "ok": True, "repo": repo, "latest": tag, "min_version": plancher,
         "newer": neuve, "url": rel.get("html_url") or "", "notified": False}
    if not neuve or dry:
        return d
    pourquoi = " ".join(str(veille.get("why") or "").split())
    rm = veille.get("rm")
    msg = (f"{repo} {tag} est publiée (on attendait mieux que {plancher})"
           + (f" — {pourquoi}" if pourquoi else ""))
    e = N.add("forge", "warn", msg, job=f"release-watch:{nom}", rm=(str(rm) if rm else None),
              ref=d["url"] or None)
    d["notified"] = bool(e)
    return d


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--watch", help="ne vérifier que cette veille")
    ap.add_argument("--root", help="racine PM (défaut : le parent de scripts/)")
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    racine = Path(a.root).expanduser() if a.root else HERE.parent
    veilles = registre(racine)
    if a.watch:
        veilles = {k: v for k, v in veilles.items() if k == a.watch}
        if not veilles:
            sys.exit(f"ERREUR : aucune veille « {a.watch} » dans {REGISTRE}")
    actives = {k: v for k, v in veilles.items() if (v or {}).get("enabled", True)}

    res = [examine(k, v or {}, dry=a.dry_run) for k, v in actives.items()]
    if a.json:
        print(json.dumps({"watches": res}, ensure_ascii=False, indent=1))
        return 0
    if not res:
        print(f"aucune veille active dans {REGISTRE}")
        return 0
    for d in res:
        if not d["ok"]:
            print(f"  ? {d['watch']:14} {d['error']}")
        elif d["newer"]:
            print(f"  ! {d['watch']:14} {d['repo']} {d['latest']} > {d['min_version']}"
                  + ("  → notifié" if d["notified"] else "  (non notifié)"))
        else:
            print(f"  · {d['watch']:14} {d['repo']} {d['latest']} — rien de neuf")
    return 0


if __name__ == "__main__":
    sys.exit(main())
